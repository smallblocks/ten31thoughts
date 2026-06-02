"""
Ten31 Thoughts - Monday Briefing API
Endpoint for generating and retrieving weekly prediction review and calibration reports.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..synthesis.monday_briefing import MondayBriefing
from ..llm.router import LLMRouter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/briefing", tags=["briefing"])


class MondayBriefingResponse(BaseModel):
    """Monday briefing data response model."""
    generated_at: str
    due_predictions: list[dict]
    expiring_soon: list[dict]
    recently_resolved: list[dict]
    calibration: list[dict]
    framework_activity: list[dict]
    summary_stats: dict


@router.get("/monday", response_model=MondayBriefingResponse)
def get_monday_briefing(session: Session = Depends(get_db)):
    """Generate and return the Monday briefing data."""
    try:
        llm = LLMRouter()
    except Exception as e:
        logger.warning(f"Could not initialize LLM router: {e}")
        llm = None
    
    briefing = MondayBriefing(session, llm)
    data = briefing.generate()
    
    return MondayBriefingResponse(**data)