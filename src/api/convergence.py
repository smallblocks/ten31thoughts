"""
Ten31 Thoughts - Convergence API
Endpoints for querying alignment, validation, blind spots, and narrative evolution.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..convergence.validation import ValidationTracker
from ..convergence.blindspots import BlindSpotDetector
from ..convergence.narrative import NarrativeTracker
from ..llm.router import LLMRouter

router = APIRouter(prefix="/api/convergence", tags=["convergence"])


@router.get("/scorecard")
def get_scorecard(
    days: Optional[int] = Query(None, description="Lookback period in days"),
    session: Session = Depends(get_db),
):
    """Get prediction accuracy scorecards for thesis and external guests."""
    tracker = ValidationTracker(LLMRouter(), session)
    return tracker.generate_scorecard(days=days)


@router.get("/blind-spots/summary")
def get_blind_spot_summary(
    days: int = Query(30, description="Lookback period"),
    session: Session = Depends(get_db),
):
    """Get blind spot summary for briefing."""
    detector = BlindSpotDetector(LLMRouter(), session)
    return detector.get_blind_spot_summary(days=days)


@router.get("/blind-spots/systematic")
def get_systematic_blind_spots(
    days: int = Query(90, description="Lookback period"),
    session: Session = Depends(get_db),
):
    """Get topics that are systematically under-discussed."""
    detector = BlindSpotDetector(LLMRouter(), session)
    return detector.get_systematic_blind_spots(lookback_days=days)


@router.get("/narratives")
def get_narratives(
    days: int = Query(180, description="Lookback period"),
    session: Session = Depends(get_db),
):
    """Get all narrative evolution arcs."""
    tracker = NarrativeTracker(LLMRouter(), session)
    return tracker.get_narrative_arcs(lookback_days=days)


@router.get("/narratives/summary")
def get_narrative_summary(
    days: int = Query(30, description="Lookback period"),
    session: Session = Depends(get_db),
):
    """Get narrative evolution summary for briefing."""
    tracker = NarrativeTracker(LLMRouter(), session)
    return tracker.get_narrative_summary(days=days)


# ─── Classical Reference Library ───

@router.get("/principles")
def list_principles(domain: Optional[str] = None, topic: Optional[str] = None):
    """
    Query the classical reference library.
    Filter by domain (sound_money, political_cycles, human_nature, property_rights)
    or by macro topic (fed_policy, labor_market, etc.).
    """
    from ..analysis.classical_reference import (
        CLASSICAL_DOMAINS, ALL_PRINCIPLES, get_principles_for_topic
    )

    if topic:
        return get_principles_for_topic(topic)
    if domain:
        for d in CLASSICAL_DOMAINS:
            if d["domain"] == domain:
                return d
        return {"error": f"Domain '{domain}' not found"}
    return {"domains": [d["domain"] for d in CLASSICAL_DOMAINS], "total_principles": len(ALL_PRINCIPLES)}


@router.get("/principles/domains")
def list_domains():
    """List all classical domains with their principle counts."""
    from ..analysis.classical_reference import CLASSICAL_DOMAINS
    return [
        {
            "domain": d["domain"],
            "title": d["title"],
            "principle_count": len(d["principles"]),
            "applies_to": d["applies_to"],
        }
        for d in CLASSICAL_DOMAINS
    ]
