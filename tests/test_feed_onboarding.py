"""
Ten31 Thoughts - Feed Onboarding Tests
Verifies that initial feed polls mark items SKIPPED while subsequent polls
mark new items PENDING (forward-only processing).

Run with: pytest tests/test_feed_onboarding.py -v
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from src.db.models import (
    Base, Feed, ContentItem, FeedCategory, FeedStatus, AnalysisStatus,
    get_engine, create_tables, get_session, gen_id,
)
from src.feeds.manager import FeedManager
from src.feeds.parser import ParsedItem, FeedMetadata


# ─── Helpers ───

def _make_parsed_items(count: int, base_url: str = "https://example.com/post") -> list[ParsedItem]:
    """Create a list of fake parsed feed items."""
    items = []
    for i in range(count):
        items.append(ParsedItem(
            url=f"{base_url}/{i}",
            title=f"Post {i}",
            published_date=datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(days=i),
            authors=["Author A"],
            summary=f"Summary of post {i}",
            content_text=f"Full content of post {i}. " * 20,
            content_hash=f"hash_{i:04d}",
            content_type="article",
        ))
    return items


def _make_metadata(title: str = "Test Feed", count: int = 5) -> FeedMetadata:
    return FeedMetadata(
        title=title,
        description="A test feed",
        link="https://example.com",
        item_count=count,
    )


# ─── Fixtures ───

@pytest.fixture
def session(tmp_path):
    db_path = tmp_path / "test.db"
    engine = get_engine(f"sqlite:///{db_path}")
    create_tables(engine)
    sess = get_session(engine)
    yield sess
    sess.close()


@pytest.fixture
def mock_parser():
    """A FeedParser mock that validates and returns configurable items."""
    parser = MagicMock()
    parser.validate_feed.return_value = (True, _make_metadata(), None)
    parser.fetch_and_parse.return_value = _make_parsed_items(5)
    return parser


@pytest.fixture
def manager(session, mock_parser):
    return FeedManager(session, parser=mock_parser)


# ─── Tests ───

class TestInitialPollMarksSkipped:
    """When a feed is first added, all existing RSS items should be SKIPPED."""

    def test_initial_poll_marks_skipped(self, manager, session, mock_parser):
        """add_feed triggers an initial poll; all discovered items get SKIPPED."""
        feed, error = manager.add_feed(
            url="https://example.com/feed.xml",
            category=FeedCategory.EXTERNAL_INTERVIEW,
        )

        assert error is None
        assert feed is not None

        items = session.query(ContentItem).filter_by(feed_id=feed.feed_id).all()
        assert len(items) == 5

        for item in items:
            assert item.analysis_status == AnalysisStatus.SKIPPED, (
                f"Expected SKIPPED but got {item.analysis_status} for {item.title}"
            )

    def test_initial_poll_marks_skipped_our_thesis(self, manager, session):
        """SKIPPED applies regardless of feed category."""
        feed, error = manager.add_feed(
            url="https://example.com/thesis.xml",
            category=FeedCategory.OUR_THESIS,
        )

        assert error is None
        items = session.query(ContentItem).filter_by(feed_id=feed.feed_id).all()
        assert len(items) == 5
        assert all(i.analysis_status == AnalysisStatus.SKIPPED for i in items)


class TestSubsequentPollMarksPending:
    """After the initial poll, new items discovered later should be PENDING."""

    def test_subsequent_poll_marks_pending(self, manager, session, mock_parser):
        # Step 1: Add the feed (initial poll → SKIPPED)
        feed, _ = manager.add_feed(
            url="https://example.com/feed.xml",
            category=FeedCategory.EXTERNAL_INTERVIEW,
        )
        assert session.query(ContentItem).filter_by(feed_id=feed.feed_id).count() == 5

        # Step 2: Simulate a new item appearing in the RSS
        new_item = ParsedItem(
            url="https://example.com/post/new",
            title="Brand New Post",
            published_date=datetime(2025, 6, 1, tzinfo=timezone.utc),
            authors=["Author B"],
            summary="This just came out",
            content_text="Fresh content " * 30,
            content_hash="hash_new",
            content_type="article",
        )
        # Parser now returns original 5 + 1 new (duplicates are filtered by manager)
        mock_parser.fetch_and_parse.return_value = _make_parsed_items(5) + [new_item]

        # Step 3: Regular poll (default → PENDING)
        new_items = manager.poll_feed(feed)

        assert len(new_items) == 1
        assert new_items[0].title == "Brand New Post"
        assert new_items[0].analysis_status == AnalysisStatus.PENDING

    def test_mixed_statuses_after_two_polls(self, manager, session, mock_parser):
        """DB should contain both SKIPPED (initial) and PENDING (subsequent) items."""
        feed, _ = manager.add_feed(
            url="https://example.com/feed.xml",
            category=FeedCategory.EXTERNAL_INTERVIEW,
        )

        # Add a new item for the second poll
        new_item = ParsedItem(
            url="https://example.com/post/6",
            title="Post 6",
            published_date=datetime(2025, 6, 1, tzinfo=timezone.utc),
            authors=[],
            summary="New",
            content_text="New content",
            content_hash="hash_0006",
            content_type="article",
        )
        mock_parser.fetch_and_parse.return_value = _make_parsed_items(5) + [new_item]
        manager.poll_feed(feed)

        all_items = session.query(ContentItem).filter_by(feed_id=feed.feed_id).all()
        assert len(all_items) == 6

        skipped = [i for i in all_items if i.analysis_status == AnalysisStatus.SKIPPED]
        pending = [i for i in all_items if i.analysis_status == AnalysisStatus.PENDING]
        assert len(skipped) == 5
        assert len(pending) == 1


class TestSkippedItemsStillExist:
    """SKIPPED items remain in the DB and are queryable."""

    def test_skipped_items_in_database(self, manager, session):
        feed, _ = manager.add_feed(
            url="https://example.com/feed.xml",
            category=FeedCategory.EXTERNAL_INTERVIEW,
        )

        skipped = (
            session.query(ContentItem)
            .filter_by(feed_id=feed.feed_id, analysis_status=AnalysisStatus.SKIPPED)
            .all()
        )
        assert len(skipped) == 5

        # Each item has content preserved
        for item in skipped:
            assert item.content_text is not None
            assert len(item.content_text) > 0
            assert item.title is not None

    def test_skipped_not_in_pending_queue(self, manager, session):
        """get_pending_items should NOT return SKIPPED items."""
        feed, _ = manager.add_feed(
            url="https://example.com/feed.xml",
            category=FeedCategory.EXTERNAL_INTERVIEW,
        )

        pending = manager.get_pending_items()
        assert len(pending) == 0, "SKIPPED items must not appear in the pending queue"

    def test_skipped_items_queryable_by_feed(self, manager, session):
        """get_items_for_feed returns SKIPPED items (they're visible, just not analyzed)."""
        feed, _ = manager.add_feed(
            url="https://example.com/feed.xml",
            category=FeedCategory.EXTERNAL_INTERVIEW,
        )

        items = manager.get_items_for_feed(feed.feed_id)
        assert len(items) == 5


class TestSchedulerUnchanged:
    """Regular poll_feed (no mark_new_as override) uses default PENDING."""

    def test_default_poll_uses_pending(self, manager, session, mock_parser):
        """poll_feed with default args marks items PENDING (scheduler path)."""
        # Manually create a feed (bypassing add_feed to skip initial poll)
        feed = Feed(
            feed_id=gen_id(),
            url="https://example.com/existing.xml",
            category=FeedCategory.EXTERNAL_INTERVIEW,
            display_name="Pre-existing Feed",
            status=FeedStatus.ACTIVE,
        )
        session.add(feed)
        session.commit()

        mock_parser.fetch_and_parse.return_value = _make_parsed_items(3)

        new_items = manager.poll_feed(feed)
        assert len(new_items) == 3

        items = session.query(ContentItem).filter_by(feed_id=feed.feed_id).all()
        assert all(i.analysis_status == AnalysisStatus.PENDING for i in items)
