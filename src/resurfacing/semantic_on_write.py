"""
Ten31 Thoughts - Semantic-on-write trigger
When a note is created or meaningfully updated, find existing notes whose
embeddings match above a threshold and write ResurfacingEvent rows for them.
The Echoes view (later step) reads these events.

Design:
- Runs inline in the notes API endpoints, not as a background job.
- Searches Chroma BEFORE the new note is indexed, so the new note can't
  match itself.
- Filters out archived notes via Chroma metadata.
- Filters out notes that already have a SEMANTIC_ON_WRITE event in the
  last 7 days (anti-spam cooldown).
- Caps surfaced events at 5 per write.
- Lenient: any failure logs a warning and returns; the SQL commit on the
  source note is never rolled back by this trigger.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from ..db.models import (
    Note, ResurfacingEvent, ResurfacingTrigger, gen_id,
)
from ..db.vector import VectorStore

logger = logging.getLogger(__name__)


# ─── Tuning constants ───
DISTANCE_THRESHOLD = 0.5
MAX_EVENTS_PER_WRITE = 5
COOLDOWN_DAYS = 7
SEARCH_FETCH_MULTIPLIER = 4


def fire_semantic_on_write(
    session: Session,
    source_note: Note,
) -> int:
    """
    Run the semantic-on-write trigger for a single source note.
    Returns the number of ResurfacingEvent rows written.
    Failures are caught and logged; this function never raises.

    Call AFTER session.commit() on the source note, but BEFORE the source
    note has been written to Chroma.
    """
    try:
        return _run(session, source_note)
    except Exception as e:
        logger.warning(
            f"Semantic-on-write trigger failed for note {source_note.note_id}: {e}. "
            f"Source note unaffected."
        )
        return 0


def _run(session: Session, source_note: Note) -> int:
    vs = VectorStore()
    fetch_n = MAX_EVENTS_PER_WRITE * SEARCH_FETCH_MULTIPLIER

    raw_results = vs.notes.query(
        query_texts=[source_note.body],
        n_results=fetch_n,
        where={"archived": False},
    )

    if not raw_results or not raw_results.get("ids") or not raw_results["ids"][0]:
        logger.debug(f"Semantic-on-write: no candidates for note {source_note.note_id}")
        return 0

    candidate_ids = raw_results["ids"][0]
    candidate_distances = (
        raw_results["distances"][0] if raw_results.get("distances") else [None] * len(candidate_ids)
    )

    candidates: list[tuple[str, float]] = []
    for cid, dist in zip(candidate_ids, candidate_distances):
        if cid == source_note.note_id:
            continue
        if dist is None:
            continue
        if dist > DISTANCE_THRESHOLD:
            continue
        candidates.append((cid, dist))

    if not candidates:
        logger.debug(f"Semantic-on-write: no candidates passed threshold for {source_note.note_id}")
        return 0

    candidate_id_set = {cid for cid, _ in candidates}
    cooldown_cutoff = datetime.now(timezone.utc) - timedelta(days=COOLDOWN_DAYS)

    recently_surfaced_rows = session.execute(
        select(ResurfacingEvent.note_id).where(and_(
            ResurfacingEvent.note_id.in_(candidate_id_set),
            ResurfacingEvent.trigger == ResurfacingTrigger.SEMANTIC_ON_WRITE,
            ResurfacingEvent.surfaced_at >= cooldown_cutoff,
        ))
    ).scalars().all()
    recently_surfaced = set(recently_surfaced_rows)

    fresh_candidates = [(cid, dist) for cid, dist in candidates if cid not in recently_surfaced]

    if not fresh_candidates:
        logger.debug(
            f"Semantic-on-write: all {len(candidates)} candidates for "
            f"{source_note.note_id} were within cooldown"
        )
        return 0

    fresh_candidates.sort(key=lambda pair: pair[1])
    selected = fresh_candidates[:MAX_EVENTS_PER_WRITE]

    surviving_ids = [cid for cid, _ in selected]
    existing_notes = session.execute(
        select(Note.note_id).where(Note.note_id.in_(surviving_ids))
    ).scalars().all()
    existing_set = set(existing_notes)

    written = 0
    for cid, dist in selected:
        if cid not in existing_set:
            logger.debug(f"Semantic-on-write: skipping orphan Chroma id {cid}")
            continue

        event = ResurfacingEvent(
            event_id=gen_id(),
            note_id=cid,
            trigger=ResurfacingTrigger.SEMANTIC_ON_WRITE,
            trigger_note_id=source_note.note_id,
            similarity_score=round(1.0 - dist, 4),
        )
        session.add(event)
        written += 1

    session.commit()

    logger.info(
        f"Semantic-on-write: wrote {written} events for source note "
        f"{source_note.note_id} (from {len(candidates)} above-threshold, "
        f"{len(fresh_candidates)} after cooldown)"
    )
    return written
