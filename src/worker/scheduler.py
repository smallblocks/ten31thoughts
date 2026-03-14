"""
Ten31 Thoughts - Background Scheduler Jobs
APScheduler job functions that replace Celery tasks.
All jobs run in-process — no Redis or separate worker needed.
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
    """Process pending content items through the analysis pipeline."""
    from ..feeds.manager import FeedManager
    from ..db.models import FeedCategory, ContentItem, AnalysisStatus

    session = _get_session()
    try:
        manager = FeedManager(session)
        pending = manager.get_pending_items(limit=5)

        if not pending:
            return

        for item in pending:
            try:
                category = item.feed.category
                if category == FeedCategory.OUR_THESIS:
                    _run_thesis_analysis(item.item_id)
                else:
                    _run_external_analysis(item.item_id)
            except Exception as e:
                logger.error(f"Analysis failed for {item.item_id}: {e}")
                # Mark as error so we don't retry infinitely
                item.analysis_status = AnalysisStatus.ERROR
                item.analysis_error = str(e)[:500]
                session.commit()
    except Exception as e:
        logger.error(f"Analysis queue processing failed: {e}")
    finally:
        session.close()


def _run_thesis_analysis(item_id: str):
    """Run 3-pass thesis analysis on a single content item."""
    from ..db.models import ContentItem, AnalysisStatus
    from ..analysis.thesis_passes import ThesisAnalyzer
    from ..llm.router import LLMRouter
    from ..db.vector import VectorStore

    session = _get_session()
    try:
        item = session.get(ContentItem, item_id)
        if not item:
            return

        llm = LLMRouter()
        analyzer = ThesisAnalyzer(llm, session)

        loop = asyncio.new_event_loop()
        try:
            stats = loop.run_until_complete(analyzer.analyze(item))
        finally:
            loop.close()

        # Index in vector store
        try:
            vs = VectorStore()
            vs.index_content(
                item_id=item_id,
                content=item.content_text,
                metadata={
                    "item_id": item_id,
                    "category": "our_thesis",
                    "feed_id": item.feed_id,
                    "title": item.title,
                    "date": item.published_date.isoformat() if item.published_date else "",
                }
            )
            for elem in item.thesis_elements:
                vs.index_thesis_element(
                    element_id=elem.element_id,
                    claim_text=elem.claim_text,
                    metadata={
                        "item_id": item_id,
                        "topic": elem.topic,
                        "conviction": elem.conviction.value if elem.conviction else "moderate",
                        "is_prediction": elem.is_prediction,
                        "is_data_skepticism": elem.is_data_skepticism,
                    }
                )
        except Exception as ve:
            logger.warning(f"Vector indexing failed for {item_id}: {ve}")

        logger.info(f"Thesis analysis complete: {item.title[:50]} -> {stats}")
    except Exception as e:
        logger.error(f"Thesis analysis failed for {item_id}: {e}")
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


def _run_external_analysis(item_id: str):
    """Run 4-pass external analysis on a single content item."""
    from ..db.models import ContentItem, AnalysisStatus
    from ..analysis.external_passes import ExternalAnalyzer
    from ..llm.router import LLMRouter
    from ..db.vector import VectorStore

    session = _get_session()
    try:
        item = session.get(ContentItem, item_id)
        if not item:
            return

        llm = LLMRouter()
        analyzer = ExternalAnalyzer(llm, session)

        loop = asyncio.new_event_loop()
        try:
            stats = loop.run_until_complete(analyzer.analyze(item))
        finally:
            loop.close()

        # Index in vector store
        try:
            vs = VectorStore()
            vs.index_content(
                item_id=item_id,
                content=item.content_text,
                metadata={
                    "item_id": item_id,
                    "category": "external_interview",
                    "feed_id": item.feed_id,
                    "title": item.title,
                    "date": item.published_date.isoformat() if item.published_date else "",
                    "authors": ", ".join(item.authors) if item.authors else "",
                }
            )
            for fw in item.external_frameworks:
                vs.index_framework(
                    framework_id=fw.framework_id,
                    text=f"{fw.framework_name}: {fw.description}",
                    metadata={
                        "item_id": item_id,
                        "guest_name": fw.guest_name or "",
                        "time_horizon": fw.time_horizon or "",
                        "reasoning_score": fw.reasoning_score or 0,
                    }
                )
            for spot in item.blind_spots:
                vs.index_blind_spot(
                    spot_id=spot.spot_id,
                    text=f"{spot.topic}: {spot.description}",
                    metadata={
                        "item_id": item_id,
                        "severity": spot.severity,
                        "source_type": spot.source_type,
                    }
                )
        except Exception as ve:
            logger.warning(f"Vector indexing failed for {item_id}: {ve}")

        logger.info(f"External analysis complete: {item.title[:50]} -> {stats}")
    except Exception as e:
        logger.error(f"External analysis failed for {item_id}: {e}")
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


def weekly_synthesis_job():
    """Run the full weekly synthesis pipeline."""
    from ..llm.router import LLMRouter
    from ..convergence.alignment import AlignmentMapper
    from ..convergence.validation import ValidationTracker
    from ..convergence.blindspots import BlindSpotDetector
    from ..convergence.narrative import NarrativeTracker
    from ..synthesis.briefing import BriefingGenerator

    logger.info("Starting weekly synthesis...")
    session = _get_session()

    try:
        llm = LLMRouter()
        loop = asyncio.new_event_loop()

        try:
            # Step 1: Alignment mapping
            logger.info("Synthesis step 1/5: Alignment mapping...")
            mapper = AlignmentMapper(llm, session)
            loop.run_until_complete(mapper.run_alignment_batch(lookback_days=14))

            # Step 2: Prediction validation
            logger.info("Synthesis step 2/5: Prediction validation...")
            validator = ValidationTracker(llm, session)
            loop.run_until_complete(validator.validate_due_predictions(min_age_days=30))

            # Step 3: Blind spot detection
            logger.info("Synthesis step 3/5: Blind spot detection...")
            detector = BlindSpotDetector(llm, session)
            loop.run_until_complete(detector.detect_mutual_blind_spots(lookback_days=14))

            # Step 4: Narrative threading
            logger.info("Synthesis step 4/5: Narrative threading...")
            narrator = NarrativeTracker(llm, session)
            loop.run_until_complete(narrator.update_thesis_threads(lookback_days=90))

            # Step 5: Generate briefing document
            logger.info("Synthesis step 5/5: Generating briefing...")
            generator = BriefingGenerator(llm, session)
            briefing = loop.run_until_complete(generator.generate_weekly_briefing())

            logger.info(f"Weekly synthesis complete. Briefing: {briefing.briefing_id}")
        finally:
            loop.close()

    except Exception as e:
        logger.error(f"Weekly synthesis failed: {e}")
    finally:
        session.close()
