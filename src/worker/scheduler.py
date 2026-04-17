"""
Ten31 Thoughts - Background Scheduler Jobs
APScheduler job functions that replace Celery tasks.
All jobs run in-process — no Redis or separate worker needed.

v3: Rewired to use connection pass + note extractor instead of
    multi-pass analysis pipeline. Daily brief and market matching removed.
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Conditional imports — these modules live on other v3 branches and may not
# be present until branches are merged.  The scheduler gracefully degrades.
try:
    from ..analysis.connection_pass import ConnectionAnalyzer
except ImportError:
    ConnectionAnalyzer = None

try:
    from ..analysis.note_extractor import NoteExtractor
except ImportError:
    NoteExtractor = None


def _get_session():
    """Get a fresh database session for a background job."""
    from ..db.session import SessionLocal
    return SessionLocal()


# ── Feed polling (unchanged) ────────────────────────────────────────────

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


# ── Connection-first analysis (v3) ──────────────────────────────────────

def process_connection_job():
    """Process pending content items via the new connection-first pipeline.

    * OUR_THESIS items  → NoteExtractor  (extract notes from our own writing)
    * Everything else    → ConnectionAnalyzer (find connections to existing notes)
    """
    from ..db.models import ContentItem, AnalysisStatus, FeedCategory
    from ..llm.router import LLMRouter

    if ConnectionAnalyzer is None or NoteExtractor is None:
        logger.warning("Connection pass / note extractor not available yet — skipping")
        return

    session = _get_session()
    try:
        pending = (
            session.query(ContentItem)
            .filter(ContentItem.analysis_status == AnalysisStatus.PENDING)
            .limit(20)
            .all()
        )

        if not pending:
            return

        llm = LLMRouter()

        for item in pending:
            try:
                feed = item.feed
                if feed.category == FeedCategory.OUR_THESIS:
                    extractor = NoteExtractor(llm, session)
                    extractor.extract(item.item_id)
                else:
                    analyzer = ConnectionAnalyzer(llm, session)
                    analyzer.analyze(item.item_id)
            except Exception as e:
                logger.error(f"Connection job failed for {item.item_id}: {e}")
                item.analysis_status = AnalysisStatus.ERROR
                session.commit()
    except Exception as e:
        logger.error(f"Connection job processing failed: {e}")
    finally:
        session.close()


# ── Weekly synthesis (placeholder until Step 8 digest generator) ────────

def weekly_synthesis_job():
    """Placeholder for the weekly digest — will be replaced by Step 8."""
    logger.info("Weekly synthesis job triggered (placeholder — awaiting v3 digest generator)")
