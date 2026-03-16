"""
Ten31 Thoughts - Daily Brief API
Endpoints for the daily intelligence brief that external dashboards can consume.
"""

import logging
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..db.models import ContentItem, ExternalFramework, AnalysisStatus
from ..llm.router import LLMRouter
from ..synthesis.daily_brief import DailyBriefGenerator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/daily-brief", tags=["daily-brief"])


@router.get("/")
async def get_daily_brief(
    hours: int = Query(24, description="Lookback period in hours"),
    session: Session = Depends(get_db),
):
    """
    Get the daily intelligence brief.

    Returns structured JSON with:
    - verdicts: first-principles verdicts on each new piece of content
    - reasoning_map: which classical axioms were triggered
    - guest_scorecards: cumulative scores for guests in new content
    - prediction_tracker: new predictions + resolved predictions
    - blind_spot_radar: what nobody is talking about
    - convergence_signals: where new content agrees/diverges with thesis

    This endpoint is designed to be consumed by an external dashboard via cron.
    """
    llm = LLMRouter()
    generator = DailyBriefGenerator(llm, session)
    return await generator.generate_daily_brief(lookback_hours=hours)


@router.get("/verdicts")
async def get_verdicts_only(
    hours: int = Query(24, description="Lookback period in hours"),
    session: Session = Depends(get_db),
):
    """Get just the first-principles verdicts for new content."""
    llm = LLMRouter()
    generator = DailyBriefGenerator(llm, session)
    brief = await generator.generate_daily_brief(lookback_hours=hours)
    return {
        "generated_at": brief["generated_at"],
        "items_analyzed": brief["items_analyzed"],
        "verdicts": brief["verdicts"],
    }


@router.get("/guest/{guest_name}")
async def get_guest_scorecard(
    guest_name: str,
    session: Session = Depends(get_db),
):
    """
    Get the full scorecard for a specific guest across all appearances.

    Returns reasoning scores over time, framework evolution, thesis alignment history.
    """
    frameworks = session.execute(
        select(ExternalFramework, ContentItem.title, ContentItem.published_date)
        .join(ContentItem)
        .where(ExternalFramework.guest_name.ilike(f"%{guest_name}%"))
        .order_by(ContentItem.published_date.asc())
    ).all()

    if not frameworks:
        return {"error": f"No frameworks found for guest: {guest_name}"}

    scores_over_time = []
    all_scores = []

    for fw, title, pub_date in frameworks:
        entry = {
            "date": pub_date.isoformat() if pub_date else None,
            "episode": title,
            "framework": fw.framework_name,
            "reasoning_score": fw.reasoning_score,
            "thesis_alignment": fw.thesis_alignment.value if fw.thesis_alignment else "unrelated",
            "description": fw.description[:300] if fw.description else None,
        }
        scores_over_time.append(entry)
        if fw.reasoning_score is not None:
            all_scores.append(fw.reasoning_score)

    # Determine trend
    score_trend = "stable"
    if len(all_scores) >= 3:
        if all_scores[-1] > all_scores[0]:
            score_trend = "improving"
        elif all_scores[-1] < all_scores[0]:
            score_trend = "declining"

    return {
        "guest_name": guest_name,
        "total_appearances": len(set(fw.item_id for fw, _, _ in frameworks)),
        "total_frameworks": len(frameworks),
        "avg_score": round(sum(all_scores) / len(all_scores), 3) if all_scores else None,
        "score_trend": score_trend,
        "frameworks_over_time": scores_over_time,
    }


@router.get("/predictions")
async def get_prediction_tracker(
    session: Session = Depends(get_db),
):
    """Get the full prediction tracker with accuracy stats."""
    llm = LLMRouter()
    generator = DailyBriefGenerator(llm, session)
    since = datetime.now(timezone.utc) - timedelta(days=365)
    return generator._build_prediction_tracker(since)


@router.get("/reasoning-map")
async def get_reasoning_map(
    hours: int = Query(168, description="Lookback period in hours (default 7 days)"),
    session: Session = Depends(get_db),
):
    """Get the reasoning map showing which classical axioms are being triggered."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    items = session.execute(
        select(ContentItem)
        .where(and_(
            ContentItem.analyzed_at >= since,
            ContentItem.analysis_status == AnalysisStatus.COMPLETE,
        ))
    ).scalars().all()

    generator = DailyBriefGenerator(LLMRouter(), session)
    return generator._build_reasoning_map(items)
