"""
Ten31 Thoughts - Analysis API
Endpoints for monitoring analysis progress and querying results.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_

from ..db.models import (
    ContentItem, ThesisElement, ExternalFramework, BlindSpot,
    Feed, FeedCategory, AnalysisStatus
)
from ..db.session import get_db

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


# ─── Response Models ───

class AnalysisQueueResponse(BaseModel):
    total_pending: int
    total_analyzing: int
    total_complete: int
    total_error: int
    our_thesis_pending: int
    external_pending: int


class ThesisElementResponse(BaseModel):
    element_id: str
    item_id: str
    claim_text: str
    topic: str
    conviction: str
    is_prediction: bool
    prediction_status: Optional[str]
    prediction_horizon: Optional[str]
    is_data_skepticism: bool
    data_series: Optional[str]
    alternative_interpretation: Optional[str]
    source_title: Optional[str] = None
    source_date: Optional[str] = None


class FrameworkResponse(BaseModel):
    framework_id: str
    item_id: str
    framework_name: str
    description: str
    guest_name: Optional[str]
    causal_chain: Optional[dict]
    key_indicators: list
    time_horizon: Optional[str]
    thesis_alignment: str
    reasoning_score: Optional[float]
    reasoning_notes: Optional[str]
    predictions: list
    source_title: Optional[str] = None
    source_date: Optional[str] = None


class BlindSpotResponse(BaseModel):
    spot_id: str
    item_id: str
    topic: str
    description: str
    severity: str
    source_type: str
    macro_event: Optional[str]
    source_title: Optional[str] = None
    source_date: Optional[str] = None


# ─── Endpoints ───

@router.get("/queue", response_model=AnalysisQueueResponse)
def get_analysis_queue(session: Session = Depends(get_db)):
    """Get current analysis queue status."""
    counts = {}
    for status in AnalysisStatus:
        count = session.execute(
            select(func.count(ContentItem.item_id))
            .where(ContentItem.analysis_status == status)
        ).scalar()
        counts[status.value] = count

    # By category
    for cat_name, cat_val in [("our_thesis", FeedCategory.OUR_THESIS), ("external", FeedCategory.EXTERNAL_INTERVIEW)]:
        count = session.execute(
            select(func.count(ContentItem.item_id))
            .join(Feed)
            .where(and_(
                ContentItem.analysis_status == AnalysisStatus.PENDING,
                Feed.category == cat_val,
            ))
        ).scalar()
        counts[f"{cat_name}_pending"] = count

    return AnalysisQueueResponse(
        total_pending=counts.get("pending", 0),
        total_analyzing=counts.get("analyzing", 0),
        total_complete=counts.get("complete", 0),
        total_error=counts.get("error", 0),
        our_thesis_pending=counts.get("our_thesis_pending", 0),
        external_pending=counts.get("external_pending", 0),
    )


@router.get("/thesis-elements", response_model=list[ThesisElementResponse])
def list_thesis_elements(
    topic: Optional[str] = None,
    predictions_only: bool = False,
    skepticism_only: bool = False,
    limit: int = Query(50, le=200),
    offset: int = 0,
    session: Session = Depends(get_db),
):
    """List extracted thesis elements with optional filters."""
    query = (
        select(ThesisElement, ContentItem.title, ContentItem.published_date)
        .join(ContentItem)
    )

    if topic:
        query = query.where(ThesisElement.topic == topic)
    if predictions_only:
        query = query.where(ThesisElement.is_prediction == True)
    if skepticism_only:
        query = query.where(ThesisElement.is_data_skepticism == True)

    query = query.order_by(ContentItem.published_date.desc()).limit(limit).offset(offset)
    rows = session.execute(query).all()

    results = []
    for elem, title, pub_date in rows:
        results.append(ThesisElementResponse(
            element_id=elem.element_id,
            item_id=elem.item_id,
            claim_text=elem.claim_text,
            topic=elem.topic,
            conviction=elem.conviction.value if elem.conviction else "moderate",
            is_prediction=elem.is_prediction,
            prediction_status=elem.prediction_status.value if elem.prediction_status else None,
            prediction_horizon=elem.prediction_horizon,
            is_data_skepticism=elem.is_data_skepticism,
            data_series=elem.data_series,
            alternative_interpretation=elem.alternative_interpretation,
            source_title=title,
            source_date=pub_date.isoformat() if pub_date else None,
        ))

    return results


@router.get("/frameworks", response_model=list[FrameworkResponse])
def list_frameworks(
    guest_name: Optional[str] = None,
    min_reasoning_score: Optional[float] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    session: Session = Depends(get_db),
):
    """List extracted external frameworks with optional filters."""
    query = (
        select(ExternalFramework, ContentItem.title, ContentItem.published_date)
        .join(ContentItem)
    )

    if guest_name:
        query = query.where(ExternalFramework.guest_name.ilike(f"%{guest_name}%"))
    if min_reasoning_score is not None:
        query = query.where(ExternalFramework.reasoning_score >= min_reasoning_score)

    query = query.order_by(ContentItem.published_date.desc()).limit(limit).offset(offset)
    rows = session.execute(query).all()

    results = []
    for fw, title, pub_date in rows:
        results.append(FrameworkResponse(
            framework_id=fw.framework_id,
            item_id=fw.item_id,
            framework_name=fw.framework_name,
            description=fw.description,
            guest_name=fw.guest_name,
            causal_chain=fw.causal_chain,
            key_indicators=fw.key_indicators or [],
            time_horizon=fw.time_horizon,
            thesis_alignment=fw.thesis_alignment.value if fw.thesis_alignment else "unrelated",
            reasoning_score=fw.reasoning_score,
            reasoning_notes=fw.reasoning_notes,
            predictions=fw.predictions or [],
            source_title=title,
            source_date=pub_date.isoformat() if pub_date else None,
        ))

    return results


@router.get("/blind-spots", response_model=list[BlindSpotResponse])
def list_blind_spots(
    severity: Optional[str] = None,
    source_type: Optional[str] = None,
    limit: int = Query(50, le=200),
    offset: int = 0,
    session: Session = Depends(get_db),
):
    """List detected blind spots with optional filters."""
    query = (
        select(BlindSpot, ContentItem.title, ContentItem.published_date)
        .join(ContentItem)
    )

    if severity:
        query = query.where(BlindSpot.severity == severity)
    if source_type:
        query = query.where(BlindSpot.source_type == source_type)

    query = query.order_by(ContentItem.published_date.desc()).limit(limit).offset(offset)
    rows = session.execute(query).all()

    results = []
    for spot, title, pub_date in rows:
        results.append(BlindSpotResponse(
            spot_id=spot.spot_id,
            item_id=spot.item_id,
            topic=spot.topic,
            description=spot.description,
            severity=spot.severity,
            source_type=spot.source_type,
            macro_event=spot.macro_event,
            source_title=title,
            source_date=pub_date.isoformat() if pub_date else None,
        ))

    return results


@router.get("/topics")
def list_topics(session: Session = Depends(get_db)):
    """List all topics with counts across thesis elements and frameworks."""
    # Thesis element topics
    thesis_topics = session.execute(
        select(ThesisElement.topic, func.count(ThesisElement.element_id))
        .group_by(ThesisElement.topic)
    ).all()

    return {
        "thesis_topics": {topic: count for topic, count in thesis_topics},
    }


@router.get("/guests")
def list_guests(session: Session = Depends(get_db)):
    """List all external guests with framework counts."""
    guests = session.execute(
        select(
            ExternalFramework.guest_name,
            func.count(ExternalFramework.framework_id),
            func.avg(ExternalFramework.reasoning_score),
        )
        .where(ExternalFramework.guest_name.isnot(None))
        .group_by(ExternalFramework.guest_name)
        .order_by(func.count(ExternalFramework.framework_id).desc())
    ).all()

    return [
        {
            "guest_name": name,
            "framework_count": count,
            "avg_reasoning_score": round(float(avg_score), 3) if avg_score else None,
        }
        for name, count, avg_score in guests
    ]
