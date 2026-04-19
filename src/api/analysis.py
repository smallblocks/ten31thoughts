"""
Ten31 Thoughts - Analysis API
Endpoints for monitoring analysis progress and querying results.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_

from ..db.models import (
    ContentItem, Feed, FeedCategory, AnalysisStatus
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
