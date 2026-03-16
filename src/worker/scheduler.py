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
        pending = manager.get_pending_items(limit=20)

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


def daily_brief_job():
    """Generate the daily intelligence brief (runs every morning)."""
    from ..synthesis.daily_brief import DailyBriefGenerator
    from ..llm.router import LLMRouter

    logger.info("Generating daily intelligence brief...")
    session = _get_session()

    try:
        llm = LLMRouter()
        generator = DailyBriefGenerator(llm, session)

        loop = asyncio.new_event_loop()
        try:
            brief = loop.run_until_complete(generator.generate_daily_brief(lookback_hours=24))
            logger.info(
                f"Daily brief complete: {brief['items_analyzed']} items, "
                f"{len(brief['verdicts'])} verdicts"
            )
        finally:
            loop.close()

    except Exception as e:
        logger.error(f"Daily brief generation failed: {e}")
    finally:
        session.close()


def market_matching_job():
    """Match new predictions to prediction markets and check resolutions."""
    from sqlalchemy import select, and_

    from ..markets.resolver import MarketResolver
    from ..markets.matcher import PredictionMarketMatcher
    from ..llm.router import LLMRouter
    from ..db.models import ThesisElement, PredictionMarketLink, gen_id

    logger.info("Running prediction market matching and resolution check...")
    session = _get_session()

    try:
        # Check resolutions on existing links
        resolver = MarketResolver(session)
        resolution_stats = resolver.check_all_linked_markets()
        resolver.close()

        # Match new unlinked predictions
        linked_ids = session.execute(
            select(PredictionMarketLink.element_id)
            .where(PredictionMarketLink.element_id.isnot(None))
        ).scalars().all()

        unlinked = session.execute(
            select(ThesisElement).where(and_(
                ThesisElement.is_prediction == True,
                ThesisElement.element_id.notin_(linked_ids) if linked_ids else True,
            )).limit(10)
        ).scalars().all()

        matched = 0
        if unlinked:
            llm = LLMRouter()
            matcher = PredictionMarketMatcher(llm)

            loop = asyncio.new_event_loop()
            try:
                for element in unlinked:
                    item = element.content_item
                    matches = loop.run_until_complete(matcher.find_matches(
                        prediction_text=element.claim_text,
                        topic=element.topic,
                        horizon=element.prediction_horizon or "",
                        source=item.title if item else "",
                    ))

                    if matches:
                        for match in matches[:2]:
                            link = PredictionMarketLink(
                                link_id=gen_id(),
                                element_id=element.element_id,
                                platform=match["platform"],
                                market_id=match["market_id"],
                                market_slug=match.get("market_slug"),
                                market_title=match["title"],
                                market_url=match.get("market_url"),
                                price_at_link=match.get("price"),
                                current_price=match.get("price"),
                                market_status="open",
                                our_side=match.get("our_side", "yes"),
                                match_confidence=match.get("match_confidence"),
                                match_rationale=match.get("match_rationale"),
                            )
                            session.add(link)
                        matched += 1

                session.commit()
            finally:
                loop.close()
                matcher.close()

            logger.info(f"Market matching: {matched} predictions linked to markets")

        logger.info(f"Market resolution: {resolution_stats}")

    except Exception as e:
        logger.error(f"Market matching/resolution failed: {e}")
    finally:
        session.close()
