"""
Ten31 Thoughts - Briefing Generator
DEPRECATED — the old weekly briefing system. Kept for reading existing briefings
from the database. New digest system in synthesis/digest.py replaces this.
"""

import logging
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import select

from ..db.models import WeeklyBriefing

logger = logging.getLogger(__name__)


class BriefingGenerator:
    """
    DEPRECATED — kept only for querying existing briefing records.
    Use the v3 digest system for new briefing generation.
    """

    def __init__(self, session: Session):
        self.session = session

    def get_latest_briefing(self) -> Optional[WeeklyBriefing]:
        """Get the most recent weekly briefing."""
        return self.session.execute(
            select(WeeklyBriefing)
            .order_by(WeeklyBriefing.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    def list_briefings(self, limit: int = 20) -> list[WeeklyBriefing]:
        """List recent briefings."""
        return list(self.session.execute(
            select(WeeklyBriefing)
            .order_by(WeeklyBriefing.created_at.desc())
            .limit(limit)
        ).scalars().all())
