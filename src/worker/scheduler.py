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


def scheduled_resurfacing_job():
    """Fire FSRS scheduled resurfacing for due notes."""
    from ..resurfacing.scheduled import fire_scheduled

    session = _get_session()
    try:
        count = fire_scheduled(session)
        if count > 0:
            logger.info(f"Scheduled resurfacing: surfaced {count} notes")
    except Exception as e:
        logger.error(f"Scheduled resurfacing failed: {e}")
    finally:
        session.close()


def monday_briefing_job():
    """Generate Monday briefing — runs every Monday at 10:00 UTC."""
    from ..synthesis.monday_briefing import MondayBriefing
    
    session = _get_session()
    try:
        briefing = MondayBriefing(session)
        data = briefing.generate()
        
        # Store as a digest
        from ..db.models import Digest, gen_id
        from datetime import datetime, timezone, timedelta
        
        now = datetime.now(timezone.utc)
        digest = Digest(
            digest_id=gen_id(),
            period_start=now - timedelta(days=7),
            period_end=now,
            html_content="",  # Will be rendered by frontend
            opening=f"Monday Briefing — {data['summary_stats']['total_open']} open predictions, {len(data['due_predictions'])} due soon",
            raw_data=data,
        )
        session.add(digest)
        session.commit()
        
        logger.info(f"Monday briefing generated: {data['summary_stats']}")
    except Exception as e:
        logger.error(f"Monday briefing failed: {e}")
    finally:
        session.close()


def transcribe_audio_job():
    """Transcribe audio items that need transcription."""
    from ..feeds.transcriber import PodcastTranscriber

    session = _get_session()
    try:
        transcriber = PodcastTranscriber(session)
        
        if not transcriber.can_transcribe():
            logger.debug("Whisper not configured, skipping transcription job")
            return

        items = transcriber.get_transcribable_items(limit=3)  # Limit to 3 per run - transcription is slow
        
        if not items:
            return

        logger.info(f"Transcribing {len(items)} audio items")
        
        for item in items:
            try:
                loop = asyncio.new_event_loop()
                try:
                    success = loop.run_until_complete(transcriber.transcribe(item))
                    if success:
                        logger.info(f"Successfully transcribed: {item.title}")
                    else:
                        logger.warning(f"Transcription failed for: {item.title}")
                finally:
                    loop.close()
            except Exception as e:
                logger.error(f"Transcription error for {item.item_id}: {e}")
                
    except Exception as e:
        logger.error(f"Transcription job failed: {e}")
    finally:
        session.close()


def extraction_job():
    """Extract predictions and frameworks from notes."""
    from ..analysis.extraction_engine import ExtractionEngine
    from ..llm.router import LLMRouter

    session = _get_session()
    try:
        llm = LLMRouter()
        engine = ExtractionEngine(llm, session)
        
        loop = asyncio.new_event_loop()
        try:
            stats = loop.run_until_complete(engine.extract_pending_notes())
            if stats["notes_processed"] > 0:
                logger.info(
                    f"Extraction: {stats['notes_processed']} notes processed, "
                    f"{stats['predictions_created']} predictions, "
                    f"{stats['new_frameworks_created']} new frameworks"
                )
        finally:
            loop.close()
                
    except Exception as e:
        logger.error(f"Extraction job failed: {e}")
    finally:
        session.close()


def _run_content_analysis(item_id: str):
    """Run v3 content analysis (connection pass + note extraction) on a content item."""
    from ..db.models import ContentItem, FeedCategory, AnalysisStatus
    from ..db.vector import VectorStore

    session = _get_session()
    try:
        item = session.get(ContentItem, item_id)
        if not item:
            return

        # Skip audio items with no or minimal content_text - they need transcription first
        if item.content_type == "audio" and (not item.content_text or len(item.content_text.strip()) < 200):
            logger.debug(f"Skipping analysis for audio item {item_id} - needs transcription first")
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

        # Fire news-driven resurfacing for external content
        feed_category = item.feed.category if item.feed else None
        if feed_category == FeedCategory.EXTERNAL_INTERVIEW:
            try:
                from ..resurfacing.news_driven import fire_news_driven
                from ..llm.router import LLMRouter
                llm = LLMRouter()
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(fire_news_driven(session, llm, item_id))
                finally:
                    loop.close()
            except Exception as nde:
                logger.warning(f"News-driven resurfacing failed for {item_id}: {nde}")

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
