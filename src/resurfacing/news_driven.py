"""
Ten31 Thoughts - News-driven resurfacing trigger

When an external content item completes analysis, semantic-search the
notes collection for matches that didn't receive a Connection, and
generate one-sentence bridge texts via LLM.

Per-match LLM call (bounded at MAX_EVENTS_PER_ITEM per item). 7-day
per-note cooldown. Tighter distance threshold than semantic-on-write
(0.45 vs 0.5).

Fires from process_analysis_job after ConnectionAnalyzer succeeds.
OUR_THESIS items are excluded — they produce notes, not connections.
"""

import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from ..db.models import (
    ContentItem, Note, Connection, ResurfacingEvent,
    ResurfacingTrigger, AnalysisStatus, gen_id,
)
from ..db.vector import VectorStore
from ..llm.router import LLMRouter
from ..analysis.prompts.bridge import (
    NEWS_DRIVEN_BRIDGE_SYSTEM, NEWS_DRIVEN_BRIDGE_USER,
)

logger = logging.getLogger(__name__)

DISTANCE_THRESHOLD = 0.45
MAX_EVENTS_PER_ITEM = 3
COOLDOWN_DAYS = 7
CONTENT_EXCERPT_CHARS = 2000
CHROMA_FETCH_N = 10


async def fire_news_driven(session: Session, llm: LLMRouter, item_id: str) -> int:
    """
    Run the news-driven resurfacing trigger for a content item.
    Returns the number of ResurfacingEvent rows written.
    Failures are caught and logged; this function never raises.
    """
    try:
        return await _run(session, llm, item_id)
    except Exception as e:
        logger.warning(
            f"News-driven resurfacing failed for item {item_id}: {e}. "
            f"Item unaffected."
        )
        return 0


async def _run(session: Session, llm: LLMRouter, item_id: str) -> int:
    item = session.get(ContentItem, item_id)
    if not item:
        logger.debug(f"News-driven: item {item_id} not found")
        return 0

    if item.analysis_status != AnalysisStatus.COMPLETE:
        logger.debug(f"News-driven: item {item_id} not COMPLETE, skipping")
        return 0

    # Semantic search against notes collection
    vs = VectorStore()
    excerpt = (item.content_text or "")[:CONTENT_EXCERPT_CHARS]
    if not excerpt:
        return 0

    raw_results = vs.notes.query(
        query_texts=[excerpt],
        n_results=CHROMA_FETCH_N,
        where={"archived": False},
    )

    if not raw_results or not raw_results.get("ids") or not raw_results["ids"][0]:
        logger.debug(f"News-driven: no Chroma candidates for item {item_id}")
        return 0

    candidate_ids = raw_results["ids"][0]
    candidate_distances = (
        raw_results["distances"][0] if raw_results.get("distances") else [None] * len(candidate_ids)
    )

    # Filter by distance threshold
    candidates: list[tuple[str, float]] = []
    for cid, dist in zip(candidate_ids, candidate_distances):
        if dist is None:
            continue
        if dist > DISTANCE_THRESHOLD:
            continue
        candidates.append((cid, dist))

    if not candidates:
        logger.debug(f"News-driven: no candidates passed threshold for item {item_id}")
        return 0

    candidate_id_set = {cid for cid, _ in candidates}

    # Filter out notes that already have a Connection with this item
    connected_rows = session.execute(
        select(Connection.note_id).where(and_(
            Connection.item_id == item_id,
            Connection.note_id.in_(candidate_id_set),
        ))
    ).scalars().all()
    connected_set = set(connected_rows)

    # Filter out notes with NEWS_DRIVEN event in last 7 days (cooldown)
    cooldown_cutoff = datetime.now(timezone.utc) - timedelta(days=COOLDOWN_DAYS)
    recently_surfaced_rows = session.execute(
        select(ResurfacingEvent.note_id).where(and_(
            ResurfacingEvent.note_id.in_(candidate_id_set),
            ResurfacingEvent.trigger == ResurfacingTrigger.NEWS_DRIVEN,
            ResurfacingEvent.surfaced_at >= cooldown_cutoff,
        ))
    ).scalars().all()
    recently_surfaced = set(recently_surfaced_rows)

    # Filter out archived notes and verify they exist in SQL
    surviving_ids = candidate_id_set - connected_set - recently_surfaced
    if not surviving_ids:
        logger.debug(f"News-driven: all candidates filtered for item {item_id}")
        return 0

    existing_notes = session.execute(
        select(Note).where(and_(
            Note.note_id.in_(surviving_ids),
            Note.archived == False,  # noqa: E712
        ))
    ).scalars().all()
    existing_map = {n.note_id: n for n in existing_notes}

    # Sort by distance (best first), cap at MAX_EVENTS_PER_ITEM
    filtered = [(cid, dist) for cid, dist in candidates if cid in existing_map]
    filtered.sort(key=lambda pair: pair[1])
    selected = filtered[:MAX_EVENTS_PER_ITEM]

    if not selected:
        return 0

    # Prepare item metadata for bridge prompts
    authors = ", ".join(item.authors) if item.authors else "unknown"
    date_str = item.published_date.strftime("%Y-%m-%d") if item.published_date else "unknown"

    written = 0
    for cid, dist in selected:
        note = existing_map[cid]

        # Generate bridge text via LLM
        try:
            user_msg = NEWS_DRIVEN_BRIDGE_USER.format(
                item_title=item.title or "Untitled",
                authors=authors,
                date=date_str,
                content_excerpt=excerpt[:500],
                note_body=(note.body or "")[:500],
            )
            bridge_text = await llm.complete(
                task="chat",
                messages=[{"role": "user", "content": user_msg}],
                system=NEWS_DRIVEN_BRIDGE_SYSTEM,
                max_tokens=100,
                temperature=0.3,
            )
        except Exception as e:
            logger.warning(f"News-driven: LLM bridge failed for note {cid}: {e}")
            raise  # Fail the whole batch — no partial commits

        event = ResurfacingEvent(
            event_id=gen_id(),
            note_id=cid,
            trigger=ResurfacingTrigger.NEWS_DRIVEN,
            trigger_item_id=item_id,
            similarity_score=round(1.0 - dist, 4),
            bridge_text=bridge_text.strip() if bridge_text else None,
        )
        session.add(event)
        written += 1

    if written > 0:
        session.commit()

    logger.info(
        f"News-driven resurfacing: {written} events for item {item_id} "
        f"(from {len(candidates)} above-threshold, "
        f"{len(connected_set)} already connected, "
        f"{len(recently_surfaced)} within cooldown)"
    )
    return written
