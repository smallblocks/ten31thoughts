"""
Ten31 Thoughts - Resurfacing Events API
Endpoints for listing, engaging, and dismissing resurfacing events.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session

from ..db.models import ResurfacingEvent, ResurfacingTrigger, Note, ContentItem
from ..db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/resurfacing", tags=["resurfacing"])


# ─── Request Models ───

class EngageRequest(BaseModel):
    rating: Optional[int] = Field(None, ge=1, le=4)


# ─── Helpers ───

def _event_to_dict(event: ResurfacingEvent, note: Note, trigger_item: Optional[ContentItem] = None) -> dict:
    return {
        "event_id": event.event_id,
        "note_id": event.note_id,
        "note_title": note.title if note else None,
        "note_body_preview": (note.body[:200] if note and note.body else None),
        "note_topic": note.topic if note else None,
        "trigger": event.trigger.value if hasattr(event.trigger, "value") else str(event.trigger),
        "trigger_item_id": event.trigger_item_id,
        "trigger_item_title": trigger_item.title if trigger_item else None,
        "trigger_note_id": event.trigger_note_id,
        "similarity_score": event.similarity_score,
        "bridge_text": event.bridge_text,
        "surfaced_at": event.surfaced_at.isoformat() if event.surfaced_at else None,
        "engaged_at": event.engaged_at.isoformat() if event.engaged_at else None,
        "dismissed_at": event.dismissed_at.isoformat() if event.dismissed_at else None,
        "rating": event.rating,
    }


def _apply_fsrs_rating(session: Session, note: Note, rating_value: int) -> None:
    """Update note FSRS fields based on a 1-4 rating using the fsrs library."""
    from fsrs import Scheduler, Card, Rating

    rating_map = {1: Rating.Again, 2: Rating.Hard, 3: Rating.Good, 4: Rating.Easy}
    fsrs_rating = rating_map.get(rating_value, Rating.Good)

    # Reconstruct Card from note's stored FSRS state
    card = Card()
    if note.fsrs_stability is not None:
        card.stability = note.fsrs_stability
    if note.fsrs_difficulty is not None:
        card.difficulty = note.fsrs_difficulty
    if note.fsrs_state is not None:
        card.state = note.fsrs_state
    if note.fsrs_last_review is not None:
        card.last_review = note.fsrs_last_review
    if note.fsrs_due is not None:
        card.due = note.fsrs_due

    scheduler = Scheduler()
    updated_card, _review_log = scheduler.review_card(card, fsrs_rating)

    # Write back to note
    note.fsrs_due = updated_card.due
    note.fsrs_stability = updated_card.stability
    note.fsrs_difficulty = updated_card.difficulty
    note.fsrs_state = updated_card.state
    note.fsrs_reps = (note.fsrs_reps or 0) + 1
    note.fsrs_last_review = updated_card.last_review


# ─── Endpoints ───

@router.get("/")
def list_resurfacing_events(
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    trigger: Optional[str] = None,
    engaged: Optional[bool] = None,
    dismissed: Optional[bool] = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db),
):
    """
    List resurfacing events with optional filters.
    Default: last 7 days, not dismissed, ordered by surfaced_at desc.
    """
    query = (
        select(ResurfacingEvent, Note, ContentItem)
        .join(Note, ResurfacingEvent.note_id == Note.note_id)
        .outerjoin(ContentItem, ResurfacingEvent.trigger_item_id == ContentItem.item_id)
    )

    filters = []

    if since is not None:
        filters.append(ResurfacingEvent.surfaced_at >= since)
    elif until is None and trigger is None and engaged is None and dismissed is None:
        # Default: last 7 days
        filters.append(ResurfacingEvent.surfaced_at >= datetime.now(timezone.utc) - timedelta(days=7))

    if until is not None:
        filters.append(ResurfacingEvent.surfaced_at <= until)

    if trigger is not None:
        trigger_enum = ResurfacingTrigger(trigger)
        filters.append(ResurfacingEvent.trigger == trigger_enum)

    if engaged is True:
        filters.append(ResurfacingEvent.engaged_at.isnot(None))
    elif engaged is False:
        filters.append(ResurfacingEvent.engaged_at.is_(None))

    if dismissed is True:
        filters.append(ResurfacingEvent.dismissed_at.isnot(None))
    elif dismissed is False:
        filters.append(ResurfacingEvent.dismissed_at.is_(None))
    elif dismissed is None and since is None and until is None and trigger is None and engaged is None:
        # Default: not dismissed
        filters.append(ResurfacingEvent.dismissed_at.is_(None))

    if filters:
        query = query.where(and_(*filters))

    query = query.order_by(ResurfacingEvent.surfaced_at.desc()).limit(limit).offset(offset)

    rows = session.execute(query).all()
    return [_event_to_dict(event, note, trigger_item) for event, note, trigger_item in rows]


@router.get("/count")
def resurfacing_count(session: Session = Depends(get_db)):
    """Count of resurfacing events from the last 7 days, not dismissed."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    count = session.execute(
        select(func.count(ResurfacingEvent.event_id)).where(
            and_(
                ResurfacingEvent.surfaced_at >= cutoff,
                ResurfacingEvent.dismissed_at.is_(None),
            )
        )
    ).scalar()
    return {"count": count}


@router.patch("/{event_id}/engage")
def engage_event(
    event_id: str,
    body: Optional[EngageRequest] = None,
    session: Session = Depends(get_db),
):
    """Mark a resurfacing event as engaged. Optionally provide a rating (1-4)."""
    event = session.get(ResurfacingEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Resurfacing event not found")

    if event.engaged_at is None:
        event.engaged_at = datetime.now(timezone.utc)

    if body and body.rating is not None:
        event.rating = body.rating
        note = session.get(Note, event.note_id)
        if note:
            _apply_fsrs_rating(session, note, body.rating)

    session.commit()
    session.refresh(event)

    # Fetch related objects for response
    note = session.get(Note, event.note_id)
    trigger_item = session.get(ContentItem, event.trigger_item_id) if event.trigger_item_id else None

    return _event_to_dict(event, note, trigger_item)


@router.patch("/{event_id}/dismiss", status_code=204)
def dismiss_event(
    event_id: str,
    session: Session = Depends(get_db),
):
    """Dismiss a resurfacing event."""
    event = session.get(ResurfacingEvent, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Resurfacing event not found")

    event.dismissed_at = datetime.now(timezone.utc)
    session.commit()
