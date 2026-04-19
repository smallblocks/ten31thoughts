"""
Ten31 Thoughts - Scheduled FSRS resurfacing trigger

Runs once daily. Finds notes where fsrs_due <= now, archived=False,
and fsrs_reps > 0 (i.e. the user has engaged at least once). Creates
SCHEDULED ResurfacingEvent rows. Per-note 24h cooldown prevents duplicates.

New notes (fsrs_reps == 0) are excluded — they surface via semantic-on-write
and news-driven triggers instead.

No LLM calls, no ChromaDB writes — pure SQL.
"""

import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from ..db.models import (
    Note, ResurfacingEvent, ResurfacingTrigger, gen_id,
)

logger = logging.getLogger(__name__)

COOLDOWN_HOURS = 24


def fire_scheduled(session: Session) -> int:
    """
    Find notes due for FSRS resurfacing and create SCHEDULED events.
    Returns the number of events written.
    Failures are caught and logged; this function never raises.
    """
    try:
        return _run(session)
    except Exception as e:
        logger.warning(f"Scheduled resurfacing trigger failed: {e}")
        return 0


def _run(session: Session) -> int:
    now = datetime.now(timezone.utc)

    # Find notes that are due, not archived, and have been reviewed at least once
    due_notes = session.execute(
        select(Note).where(and_(
            Note.fsrs_due <= now,
            Note.archived == False,  # noqa: E712
            Note.fsrs_reps > 0,
        ))
    ).scalars().all()

    if not due_notes:
        logger.debug("Scheduled resurfacing: no due notes")
        return 0

    # Check 24h cooldown per note for SCHEDULED trigger
    cooldown_cutoff = now - timedelta(hours=COOLDOWN_HOURS)
    note_ids = [n.note_id for n in due_notes]

    recently_surfaced_rows = session.execute(
        select(ResurfacingEvent.note_id).where(and_(
            ResurfacingEvent.note_id.in_(note_ids),
            ResurfacingEvent.trigger == ResurfacingTrigger.SCHEDULED,
            ResurfacingEvent.surfaced_at >= cooldown_cutoff,
        ))
    ).scalars().all()
    recently_surfaced = set(recently_surfaced_rows)

    written = 0
    for note in due_notes:
        if note.note_id in recently_surfaced:
            continue

        event = ResurfacingEvent(
            event_id=gen_id(),
            note_id=note.note_id,
            trigger=ResurfacingTrigger.SCHEDULED,
        )
        session.add(event)
        written += 1

    if written > 0:
        session.commit()

    logger.info(
        f"Scheduled resurfacing: {written} events from {len(due_notes)} due notes "
        f"({len(recently_surfaced)} within cooldown)"
    )
    return written
