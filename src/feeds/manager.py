"""
Ten31 Thoughts - Feed Manager
Manages feed CRUD, polling orchestration, and content ingestion pipeline.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from ..db.models import (
    Feed, ContentItem, FeedCategory, FeedStatus, AnalysisStatus, gen_id
)
from .parser import FeedParser, ParsedItem, FeedMetadata

logger = logging.getLogger(__name__)


class FeedManager:
    """
    Orchestrates feed management: adding/removing feeds, polling for new content,
    and queueing items for analysis.
    """

    def __init__(self, session: Session, parser: Optional[FeedParser] = None):
        self.session = session
        self.parser = parser or FeedParser()

    # ─── Feed CRUD ───

    def add_feed(
        self,
        url: str,
        category: FeedCategory,
        display_name: Optional[str] = None,
        tags: Optional[list[str]] = None,
        poll_interval_minutes: int = 30,
    ) -> tuple[Optional[Feed], Optional[str]]:
        """
        Add a new RSS feed to the system.
        Returns (feed, error_message). Feed is None if validation fails.
        """
        # Check for duplicate URL
        existing = self.session.execute(
            select(Feed).where(Feed.url == url)
        ).scalar_one_or_none()

        if existing:
            return None, f"Feed already exists: {existing.display_name} ({existing.feed_id})"

        # Validate the feed
        is_valid, metadata, error = self.parser.validate_feed(url)
        if not is_valid:
            return None, f"Invalid feed URL: {error}"

        # Create feed record
        feed = Feed(
            feed_id=gen_id(),
            url=url,
            category=category,
            display_name=display_name or metadata.title,
            tags=tags or [],
            poll_interval_minutes=poll_interval_minutes,
            status=FeedStatus.ACTIVE,
        )

        self.session.add(feed)
        self.session.commit()

        logger.info(
            f"Added feed: {feed.display_name} ({feed.category.value}) "
            f"with {metadata.item_count} discoverable items"
        )

        return feed, None

    def list_feeds(
        self,
        category: Optional[FeedCategory] = None,
        status: Optional[FeedStatus] = None,
    ) -> list[Feed]:
        """List all feeds, optionally filtered by category or status."""
        query = select(Feed)

        if category:
            query = query.where(Feed.category == category)
        if status:
            query = query.where(Feed.status == status)

        query = query.order_by(Feed.created_at.desc())
        return list(self.session.execute(query).scalars().all())

    def get_feed(self, feed_id: str) -> Optional[Feed]:
        """Get a specific feed by ID."""
        return self.session.get(Feed, feed_id)

    def update_feed(
        self,
        feed_id: str,
        display_name: Optional[str] = None,
        tags: Optional[list[str]] = None,
        category: Optional[FeedCategory] = None,
        poll_interval_minutes: Optional[int] = None,
        status: Optional[FeedStatus] = None,
    ) -> Optional[Feed]:
        """Update feed configuration."""
        feed = self.get_feed(feed_id)
        if not feed:
            return None

        if display_name is not None:
            feed.display_name = display_name
        if tags is not None:
            feed.tags = tags
        if category is not None:
            feed.category = category
        if poll_interval_minutes is not None:
            feed.poll_interval_minutes = poll_interval_minutes
        if status is not None:
            feed.status = status

        self.session.commit()
        return feed

    def delete_feed(self, feed_id: str) -> bool:
        """Delete a feed and all its content items."""
        feed = self.get_feed(feed_id)
        if not feed:
            return False

        self.session.delete(feed)
        self.session.commit()
        logger.info(f"Deleted feed: {feed.display_name}")
        return True

    # ─── Polling & Ingestion ───

    def get_feeds_due_for_poll(self) -> list[Feed]:
        """Get all active feeds that are due for polling based on their interval."""
        now = datetime.now(timezone.utc)
        feeds = self.session.execute(
            select(Feed).where(Feed.status == FeedStatus.ACTIVE)
        ).scalars().all()

        due_feeds = []
        for feed in feeds:
            if feed.last_fetched is None:
                due_feeds.append(feed)
            else:
                next_poll = feed.last_fetched + timedelta(minutes=feed.poll_interval_minutes)
                if now >= next_poll:
                    due_feeds.append(feed)

        return due_feeds

    def poll_feed(self, feed: Feed) -> list[ContentItem]:
        """
        Poll a single feed for new content.
        Returns list of newly created ContentItem objects.
        """
        logger.info(f"Polling feed: {feed.display_name} ({feed.url})")

        try:
            # Fetch and parse feed items
            parsed_items = self.parser.fetch_and_parse(
                feed.url,
                since=feed.last_fetched
            )

            new_items = []
            for parsed in parsed_items:
                # Check for duplicates by URL or content hash
                existing = self.session.execute(
                    select(ContentItem).where(
                        and_(
                            ContentItem.feed_id == feed.feed_id,
                            (ContentItem.url == parsed.url) |
                            (ContentItem.content_hash == parsed.content_hash)
                        )
                    )
                ).scalar_one_or_none()

                if existing:
                    continue

                # Create new content item
                item = ContentItem(
                    item_id=gen_id(),
                    feed_id=feed.feed_id,
                    url=parsed.url,
                    title=parsed.title,
                    published_date=parsed.published_date,
                    authors=parsed.authors,
                    summary=parsed.summary,
                    content_text=parsed.content_text,
                    content_hash=parsed.content_hash,
                    content_type=parsed.content_type,
                    audio_url=parsed.audio_url,
                    analysis_status=AnalysisStatus.PENDING,
                )

                self.session.add(item)
                new_items.append(item)

            # Update feed status
            feed.last_fetched = datetime.now(timezone.utc)
            feed.error_count = 0
            feed.last_error = None
            self.session.commit()

            if new_items:
                logger.info(
                    f"Ingested {len(new_items)} new items from {feed.display_name}"
                )
            else:
                logger.debug(f"No new items from {feed.display_name}")

            return new_items

        except Exception as e:
            # Handle polling errors with exponential backoff tracking
            feed.error_count += 1
            feed.last_error = str(e)

            if feed.error_count >= 10:
                feed.status = FeedStatus.ERROR
                logger.error(
                    f"Feed {feed.display_name} disabled after {feed.error_count} "
                    f"consecutive errors: {e}"
                )
            else:
                logger.warning(
                    f"Error polling {feed.display_name} "
                    f"(attempt {feed.error_count}): {e}"
                )

            self.session.commit()
            return []

    def poll_all_due(self) -> dict:
        """
        Poll all feeds that are due. Returns summary stats.
        Priority: our_thesis feeds first, then external.
        """
        due_feeds = self.get_feeds_due_for_poll()

        # Sort: our_thesis first
        due_feeds.sort(
            key=lambda f: (0 if f.category == FeedCategory.OUR_THESIS else 1)
        )

        stats = {
            "feeds_polled": 0,
            "new_items": 0,
            "errors": 0,
            "our_thesis_items": 0,
            "external_items": 0,
        }

        for feed in due_feeds:
            new_items = self.poll_feed(feed)
            stats["feeds_polled"] += 1
            stats["new_items"] += len(new_items)

            if feed.category == FeedCategory.OUR_THESIS:
                stats["our_thesis_items"] += len(new_items)
            else:
                stats["external_items"] += len(new_items)

            if feed.last_error:
                stats["errors"] += 1

        logger.info(
            f"Poll complete: {stats['feeds_polled']} feeds, "
            f"{stats['new_items']} new items "
            f"({stats['our_thesis_items']} thesis, {stats['external_items']} external)"
        )

        return stats

    # ─── Content Queries ───

    def get_pending_items(
        self,
        category: Optional[FeedCategory] = None,
        limit: int = 50,
    ) -> list[ContentItem]:
        """Get content items pending analysis, optionally filtered by feed category."""
        query = (
            select(ContentItem)
            .join(Feed)
            .where(ContentItem.analysis_status == AnalysisStatus.PENDING)
        )

        if category:
            query = query.where(Feed.category == category)

        # Prioritize our_thesis, then by date (newest first)
        query = (
            query
            .order_by(
                Feed.category.asc(),  # our_thesis sorts before external
                ContentItem.published_date.desc()
            )
            .limit(limit)
        )

        return list(self.session.execute(query).scalars().all())

    def get_items_for_feed(
        self,
        feed_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ContentItem]:
        """Get content items for a specific feed."""
        query = (
            select(ContentItem)
            .where(ContentItem.feed_id == feed_id)
            .order_by(ContentItem.published_date.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.session.execute(query).scalars().all())

    def get_content_stats(self) -> dict:
        """Get overall content statistics."""
        from sqlalchemy import func

        total = self.session.execute(
            select(func.count(ContentItem.item_id))
        ).scalar()

        by_status = {}
        for status in AnalysisStatus:
            count = self.session.execute(
                select(func.count(ContentItem.item_id))
                .where(ContentItem.analysis_status == status)
            ).scalar()
            by_status[status.value] = count

        by_category = {}
        for category in FeedCategory:
            count = self.session.execute(
                select(func.count(ContentItem.item_id))
                .join(Feed)
                .where(Feed.category == category)
            ).scalar()
            by_category[category.value] = count

        feeds_active = self.session.execute(
            select(func.count(Feed.feed_id))
            .where(Feed.status == FeedStatus.ACTIVE)
        ).scalar()

        feeds_total = self.session.execute(
            select(func.count(Feed.feed_id))
        ).scalar()

        return {
            "total_items": total,
            "by_status": by_status,
            "by_category": by_category,
            "feeds_active": feeds_active,
            "feeds_total": feeds_total,
        }
