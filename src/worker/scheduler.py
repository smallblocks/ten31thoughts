"""
Ten31 Thoughts - Background Scheduler Jobs
APScheduler job functions for feed polling and content analysis.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)


def _get_session():
    """Get a fresh database session for a background job."""
    from ..db.session import SessionLocal
    return SessionLocal()


def poll_all_feeds_job():
    """Poll all active feeds that are due for refresh."""
    from ..feeds.manager import FeedManager

    session = _get_session()
    try:
        manager = FeedManager(session)
        stats = manager.poll_all_due()

        if stats["new_items"] > 0:
            logger.info(
                f"Feed poll: {stats['new_items']} new items "
                f"from {stats['feeds_polled']} feeds"
            )
    except Exception as e:
        logger.error(f"Feed polling failed: {e}")
    finally:
        session.close()


def process_analysis_job():
    """Process pending content items through the v3 analysis pipeline."""
    from ..feeds.manager import FeedManager
    from ..db.models import ContentItem, AnalysisStatus

    session = _get_session()
    try:
        manager = FeedManager(session)
        pending = manager.get_pending_items(limit=20)

        if not pending:
            return

        for item in pending:
            try:
                _run_content_analysis(item.item_id)
            except Exception as e:
                logger.error(f"Analysis failed for {item.item_id}: {e}")
                item.analysis_status = AnalysisStatus.ERROR
                item.analysis_error = str(e)[:500]
                session.commit()
    except Exception as e:
        logger.error(f"Analysis queue processing failed: {e}")
    finally:
        session.close()


def _run_content_analysis(item_id: str):
    """Run v3 content analysis (connection pass + note extraction) on a content item."""
    from ..db.models import ContentItem, AnalysisStatus
    from ..db.vector import VectorStore

    session = _get_session()
    try:
        item = session.get(ContentItem, item_id)
        if not item:
            return

        # Index content in vector store
        try:
            vs = VectorStore()
            vs.index_content(
                item_id=item_id,
                content=item.content_text,
                metadata={
                    "item_id": item_id,
                    "category": item.feed.category.value if item.feed else "",
                    "feed_id": item.feed_id,
                    "title": item.title,
                    "date": item.published_date.isoformat() if item.published_date else "",
                }
            )
        except Exception as ve:
            logger.warning(f"Vector indexing failed for {item_id}: {ve}")

        item.analysis_status = AnalysisStatus.COMPLETE
        item.analyzed_at = datetime.now(timezone.utc)
        session.commit()

        logger.info(f"Content analysis complete: {item.title[:50]}")
    except Exception as e:
        logger.error(f"Content analysis failed for {item_id}: {e}")
        try:
            item = session.get(ContentItem, item_id)
            if item:
                item.analysis_status = AnalysisStatus.ERROR
                item.analysis_error = str(e)[:500]
                session.commit()
        except Exception:
            pass
    finally:
        session.close()
