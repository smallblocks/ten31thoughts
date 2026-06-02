"""
Ten31 Thoughts - Extraction API
Endpoints for predictions, frameworks, and calibration scorecard.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session

from ..db.models import Prediction, Framework, FrameworkLink, Note, gen_id
from ..db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["extraction"])


# ─── Request/Response Models ───

class UpdatePredictionStatusRequest(BaseModel):
    status: str = Field(..., description="confirmed | invalidated | expired")
    evidence: Optional[str] = Field(None, description="Evidence for status change")


class CreateFrameworkRequest(BaseModel):
    name: str = Field(..., max_length=500)
    description: str = Field(...)
    domain: Optional[str] = None


class UpdateFrameworkRequest(BaseModel):
    description: str = Field(...)
    reason: Optional[str] = Field(None, description="Reason for the change")


class PredictionResponse(BaseModel):
    prediction_id: str
    note_id: str
    claim: str
    measurable_outcome: Optional[str]
    timeline: Optional[str]
    timeline_start: Optional[str]
    timeline_end: Optional[str]
    conviction: Optional[float]
    conviction_reasoning: Optional[str]
    status: str
    status_evidence: Optional[str]
    status_changed_at: Optional[str]
    domain: Optional[str]
    tags: List[str]
    created_at: str
    updated_at: str
    note_title: Optional[str] = None


class FrameworkResponse(BaseModel):
    framework_id: str
    name: str
    description: str
    domain: Optional[str]
    status: str
    superseded_by: Optional[str]
    created_at: str
    updated_at: str
    linked_notes_count: Optional[int] = None
    linked_predictions_count: Optional[int] = None


class FrameworkDetailResponse(FrameworkResponse):
    evolution_log: List[dict]
    linked_notes: List[dict] = []
    linked_predictions: List[dict] = []


class ScorecardResponse(BaseModel):
    total_predictions: int
    confirmed: int
    invalidated: int
    expired: int
    open: int
    calibration_by_conviction: List[dict]
    accuracy_rate: Optional[float]
    overconfidence_score: Optional[float]


# ─── Prediction Endpoints ───

@router.get("/predictions/scorecard", response_model=ScorecardResponse)
async def get_predictions_scorecard(db: Session = Depends(get_db)):
    """Get calibration stats and accuracy scorecard."""
    # Basic counts
    total_predictions = db.scalar(select(func.count(Prediction.prediction_id)))
    confirmed = db.scalar(select(func.count(Prediction.prediction_id)).where(Prediction.status == "confirmed"))
    invalidated = db.scalar(select(func.count(Prediction.prediction_id)).where(Prediction.status == "invalidated"))
    expired = db.scalar(select(func.count(Prediction.prediction_id)).where(Prediction.status == "expired"))
    open_count = db.scalar(select(func.count(Prediction.prediction_id)).where(Prediction.status == "open"))
    
    # Calibration analysis by conviction bins
    calibration_data = []
    bins = [(0.0, 0.3), (0.3, 0.5), (0.5, 0.7), (0.7, 0.9), (0.9, 1.0)]
    
    for low, high in bins:
        resolved_predictions = db.execute(
            select(Prediction)
            .where(
                and_(
                    Prediction.conviction.between(low, high),
                    Prediction.status.in_(["confirmed", "invalidated"])
                )
            )
        ).scalars().all()
        
        if resolved_predictions:
            correct = sum(1 for p in resolved_predictions if p.status == "confirmed")
            total = len(resolved_predictions)
            actual_rate = correct / total
            avg_conviction = sum(p.conviction for p in resolved_predictions) / total
            
            calibration_data.append({
                "conviction_range": f"{low:.1f}-{high:.1f}",
                "predicted_rate": round(avg_conviction, 3),
                "actual_rate": round(actual_rate, 3),
                "count": total,
                "correct": correct
            })
    
    # Overall accuracy
    resolved_total = confirmed + invalidated
    accuracy_rate = confirmed / resolved_total if resolved_total > 0 else None
    
    # Overconfidence score (simplified)
    overconfidence_score = None
    if calibration_data:
        total_overconfidence = sum(
            abs(item["predicted_rate"] - item["actual_rate"]) * item["count"]
            for item in calibration_data
        )
        total_resolved = sum(item["count"] for item in calibration_data)
        overconfidence_score = total_overconfidence / total_resolved if total_resolved > 0 else None
    
    return ScorecardResponse(
        total_predictions=total_predictions or 0,
        confirmed=confirmed or 0,
        invalidated=invalidated or 0,
        expired=expired or 0,
        open=open_count or 0,
        calibration_by_conviction=calibration_data,
        accuracy_rate=accuracy_rate,
        overconfidence_score=overconfidence_score
    )


@router.get("/predictions/due", response_model=List[PredictionResponse])
async def get_predictions_due(
    days: int = 30,
    db: Session = Depends(get_db)
):
    """Get predictions with timeline_end approaching."""
    cutoff_date = datetime.now(timezone.utc) + timedelta(days=days)
    
    results = db.execute(
        select(Prediction, Note.title)
        .join(Note, Prediction.note_id == Note.note_id)
        .where(
            and_(
                Prediction.timeline_end.isnot(None),
                Prediction.timeline_end <= cutoff_date,
                Prediction.status == "open"
            )
        )
        .order_by(Prediction.timeline_end)
    ).all()
    
    return [
        PredictionResponse(
            prediction_id=pred.prediction_id,
            note_id=pred.note_id,
            claim=pred.claim,
            measurable_outcome=pred.measurable_outcome,
            timeline=pred.timeline,
            timeline_start=pred.timeline_start.isoformat() if pred.timeline_start else None,
            timeline_end=pred.timeline_end.isoformat() if pred.timeline_end else None,
            conviction=pred.conviction,
            conviction_reasoning=pred.conviction_reasoning,
            status=pred.status,
            status_evidence=pred.status_evidence,
            status_changed_at=pred.status_changed_at.isoformat() if pred.status_changed_at else None,
            domain=pred.domain,
            tags=pred.tags or [],
            created_at=pred.created_at.isoformat(),
            updated_at=pred.updated_at.isoformat(),
            note_title=note_title
        )
        for pred, note_title in results
    ]


@router.get("/predictions/", response_model=List[PredictionResponse])
async def list_predictions(
    status: Optional[str] = None,
    domain: Optional[str] = None,
    note_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """List predictions with optional filters."""
    query = select(Prediction, Note.title).join(Note, Prediction.note_id == Note.note_id)
    
    if status:
        query = query.where(Prediction.status == status)
    if domain:
        query = query.where(Prediction.domain == domain)
    if note_id:
        query = query.where(Prediction.note_id == note_id)
    
    query = query.order_by(Prediction.created_at.desc()).limit(limit).offset(offset)
    results = db.execute(query).all()
    
    return [
        PredictionResponse(
            prediction_id=pred.prediction_id,
            note_id=pred.note_id,
            claim=pred.claim,
            measurable_outcome=pred.measurable_outcome,
            timeline=pred.timeline,
            timeline_start=pred.timeline_start.isoformat() if pred.timeline_start else None,
            timeline_end=pred.timeline_end.isoformat() if pred.timeline_end else None,
            conviction=pred.conviction,
            conviction_reasoning=pred.conviction_reasoning,
            status=pred.status,
            status_evidence=pred.status_evidence,
            status_changed_at=pred.status_changed_at.isoformat() if pred.status_changed_at else None,
            domain=pred.domain,
            tags=pred.tags or [],
            created_at=pred.created_at.isoformat(),
            updated_at=pred.updated_at.isoformat(),
            note_title=note_title
        )
        for pred, note_title in results
    ]


@router.get("/predictions/{prediction_id}", response_model=PredictionResponse)
async def get_prediction(prediction_id: str, db: Session = Depends(get_db)):
    """Get a single prediction."""
    result = db.execute(
        select(Prediction, Note.title)
        .join(Note, Prediction.note_id == Note.note_id)
        .where(Prediction.prediction_id == prediction_id)
    ).first()
    
    if not result:
        raise HTTPException(status_code=404, detail="Prediction not found")
    
    pred, note_title = result
    
    return PredictionResponse(
        prediction_id=pred.prediction_id,
        note_id=pred.note_id,
        claim=pred.claim,
        measurable_outcome=pred.measurable_outcome,
        timeline=pred.timeline,
        timeline_start=pred.timeline_start.isoformat() if pred.timeline_start else None,
        timeline_end=pred.timeline_end.isoformat() if pred.timeline_end else None,
        conviction=pred.conviction,
        conviction_reasoning=pred.conviction_reasoning,
        status=pred.status,
        status_evidence=pred.status_evidence,
        status_changed_at=pred.status_changed_at.isoformat() if pred.status_changed_at else None,
        domain=pred.domain,
        tags=pred.tags or [],
        created_at=pred.created_at.isoformat(),
        updated_at=pred.updated_at.isoformat(),
        note_title=note_title
    )


@router.put("/predictions/{prediction_id}/status")
async def update_prediction_status(
    prediction_id: str,
    request: UpdatePredictionStatusRequest,
    db: Session = Depends(get_db)
):
    """Update prediction status (confirmed/invalidated/expired)."""
    prediction = db.get(Prediction, prediction_id)
    if not prediction:
        raise HTTPException(status_code=404, detail="Prediction not found")
    
    if request.status not in ["confirmed", "invalidated", "expired", "open"]:
        raise HTTPException(status_code=400, detail="Invalid status")
    
    prediction.status = request.status
    prediction.status_evidence = request.evidence
    prediction.status_changed_at = datetime.now(timezone.utc)
    prediction.updated_at = datetime.now(timezone.utc)
    
    db.commit()
    
    return {"prediction_id": prediction_id, "status": prediction.status, "updated_at": prediction.updated_at.isoformat()}


@router.get("/predictions/due", response_model=List[PredictionResponse])
async def get_predictions_due(
    days: int = 30,
    db: Session = Depends(get_db)
):
    """Get predictions with timeline_end approaching."""
    cutoff_date = datetime.now(timezone.utc) + timedelta(days=days)
    
    results = db.execute(
        select(Prediction, Note.title)
        .join(Note, Prediction.note_id == Note.note_id)
        .where(
            and_(
                Prediction.timeline_end.isnot(None),
                Prediction.timeline_end <= cutoff_date,
                Prediction.status == "open"
            )
        )
        .order_by(Prediction.timeline_end)
    ).all()
    
    return [
        PredictionResponse(
            prediction_id=pred.prediction_id,
            note_id=pred.note_id,
            claim=pred.claim,
            measurable_outcome=pred.measurable_outcome,
            timeline=pred.timeline,
            timeline_start=pred.timeline_start.isoformat() if pred.timeline_start else None,
            timeline_end=pred.timeline_end.isoformat() if pred.timeline_end else None,
            conviction=pred.conviction,
            conviction_reasoning=pred.conviction_reasoning,
            status=pred.status,
            status_evidence=pred.status_evidence,
            status_changed_at=pred.status_changed_at.isoformat() if pred.status_changed_at else None,
            domain=pred.domain,
            tags=pred.tags or [],
            created_at=pred.created_at.isoformat(),
            updated_at=pred.updated_at.isoformat(),
            note_title=note_title
        )
        for pred, note_title in results
    ]


# ─── Framework Endpoints ───

@router.get("/frameworks/", response_model=List[FrameworkResponse])
async def list_frameworks(
    status: str = "active",
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """List frameworks with link counts."""
    # Get frameworks
    frameworks = db.execute(
        select(Framework)
        .where(Framework.status == status)
        .order_by(Framework.updated_at.desc())
        .limit(limit).offset(offset)
    ).scalars().all()
    
    result = []
    for fw in frameworks:
        # Count linked notes and predictions
        notes_count = db.scalar(
            select(func.count(FrameworkLink.link_id))
            .where(FrameworkLink.framework_id == fw.framework_id, FrameworkLink.note_id.isnot(None))
        ) or 0
        
        predictions_count = db.scalar(
            select(func.count(FrameworkLink.link_id))
            .where(FrameworkLink.framework_id == fw.framework_id, FrameworkLink.prediction_id.isnot(None))
        ) or 0
        
        result.append(FrameworkResponse(
            framework_id=fw.framework_id,
            name=fw.name,
            description=fw.description,
            domain=fw.domain,
            status=fw.status,
            superseded_by=fw.superseded_by,
            created_at=fw.created_at.isoformat(),
            updated_at=fw.updated_at.isoformat(),
            linked_notes_count=notes_count,
            linked_predictions_count=predictions_count
        ))
    
    return result


@router.post("/frameworks/", response_model=FrameworkResponse)
async def create_framework(request: CreateFrameworkRequest, db: Session = Depends(get_db)):
    """Create a new framework."""
    # Check if name already exists
    existing = db.execute(
        select(Framework).where(Framework.name == request.name, Framework.status == "active")
    ).scalar_one_or_none()
    
    if existing:
        raise HTTPException(status_code=400, detail="Framework name already exists")
    
    framework = Framework(
        framework_id=gen_id(),
        name=request.name,
        description=request.description,
        domain=request.domain,
        status="active",
        evolution_log=[]
    )
    
    db.add(framework)
    db.commit()
    db.refresh(framework)
    
    return FrameworkResponse(
        framework_id=framework.framework_id,
        name=framework.name,
        description=framework.description,
        domain=framework.domain,
        status=framework.status,
        superseded_by=framework.superseded_by,
        created_at=framework.created_at.isoformat(),
        updated_at=framework.updated_at.isoformat(),
        linked_notes_count=0,
        linked_predictions_count=0
    )


@router.get("/frameworks/{framework_id}", response_model=FrameworkDetailResponse)
async def get_framework(framework_id: str, db: Session = Depends(get_db)):
    """Get framework with linked notes and predictions."""
    framework = db.get(Framework, framework_id)
    if not framework:
        raise HTTPException(status_code=404, detail="Framework not found")
    
    # Get linked notes
    note_links = db.execute(
        select(FrameworkLink, Note.title, Note.body)
        .join(Note, FrameworkLink.note_id == Note.note_id)
        .where(FrameworkLink.framework_id == framework_id, FrameworkLink.note_id.isnot(None))
    ).all()
    
    linked_notes = [
        {
            "link_id": link.link_id,
            "note_id": link.note_id,
            "relation": link.relation,
            "context": link.context,
            "note_title": title,
            "note_preview": body[:200] + "..." if len(body) > 200 else body
        }
        for link, title, body in note_links
    ]
    
    # Get linked predictions
    pred_links = db.execute(
        select(FrameworkLink, Prediction.claim, Prediction.status)
        .join(Prediction, FrameworkLink.prediction_id == Prediction.prediction_id)
        .where(FrameworkLink.framework_id == framework_id, FrameworkLink.prediction_id.isnot(None))
    ).all()
    
    linked_predictions = [
        {
            "link_id": link.link_id,
            "prediction_id": link.prediction_id,
            "relation": link.relation,
            "context": link.context,
            "claim_preview": claim[:200] + "..." if len(claim) > 200 else claim,
            "status": status
        }
        for link, claim, status in pred_links
    ]
    
    return FrameworkDetailResponse(
        framework_id=framework.framework_id,
        name=framework.name,
        description=framework.description,
        domain=framework.domain,
        status=framework.status,
        superseded_by=framework.superseded_by,
        evolution_log=framework.evolution_log or [],
        created_at=framework.created_at.isoformat(),
        updated_at=framework.updated_at.isoformat(),
        linked_notes_count=len(linked_notes),
        linked_predictions_count=len(linked_predictions),
        linked_notes=linked_notes,
        linked_predictions=linked_predictions
    )


@router.put("/frameworks/{framework_id}", response_model=FrameworkResponse)
async def update_framework(
    framework_id: str,
    request: UpdateFrameworkRequest,
    db: Session = Depends(get_db)
):
    """Update framework description (adds to evolution log)."""
    framework = db.get(Framework, framework_id)
    if not framework:
        raise HTTPException(status_code=404, detail="Framework not found")
    
    old_description = framework.description
    framework.description = request.description
    framework.updated_at = datetime.now(timezone.utc)
    
    # Add to evolution log
    evolution_log = framework.evolution_log or []
    evolution_log.append({
        "date": framework.updated_at.isoformat(),
        "change": "description_updated",
        "old_description": old_description,
        "new_description": request.description,
        "reason": request.reason
    })
    framework.evolution_log = evolution_log
    
    db.commit()
    
    return FrameworkResponse(
        framework_id=framework.framework_id,
        name=framework.name,
        description=framework.description,
        domain=framework.domain,
        status=framework.status,
        superseded_by=framework.superseded_by,
        created_at=framework.created_at.isoformat(),
        updated_at=framework.updated_at.isoformat()
    )


@router.get("/frameworks/{framework_id}/evolution")
async def get_framework_evolution(framework_id: str, db: Session = Depends(get_db)):
    """Get framework evolution history."""
    framework = db.get(Framework, framework_id)
    if not framework:
        raise HTTPException(status_code=404, detail="Framework not found")
    
    return {
        "framework_id": framework_id,
        "name": framework.name,
        "evolution_log": framework.evolution_log or []
    }