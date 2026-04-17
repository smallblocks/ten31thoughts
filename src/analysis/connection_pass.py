"""
Ten31 Thoughts - Connection Pass
Single LLM call per ingested content item. Finds connections between
external content and the user's existing Notes.

Replaces the old 4-pass analysis pipeline (external_passes, thesis_passes,
first_principles, frameworks).
"""

import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import (
    ContentItem, Note, Connection, UnconnectedSignal,
    ConnectionRelation, AnalysisStatus, gen_id,
)
from ..db.vector import VectorStore
from ..llm.router import LLMRouter
from .classical_reference import (
    ALL_PRINCIPLES, TOPIC_TO_DOMAINS, get_principles_for_topic,
    format_principles_for_llm,
)
from .prompts.connection import CONNECTION_PASS_SYSTEM, CONNECTION_PASS_USER

logger = logging.getLogger(__name__)

MAX_CONNECTIONS = 8
MAX_SIGNALS = 3
CONTENT_TRUNCATE_CHARS = 60_000
CANDIDATE_NOTES_LIMIT = 30
ACTIVE_NOTES_DAYS = 60

# Valid relation values for validation
_VALID_RELATIONS = {r.value for r in ConnectionRelation}


class ConnectionAnalyzer:
    """
    Runs the single-pass connection analysis on an ingested content item.
    Finds connections to the user's existing Notes and optionally flags
    unconnected signals.
    """

    def __init__(self, llm: LLMRouter, session: Session):
        self.llm = llm
        self.session = session

    async def analyze(self, item_id: str) -> dict:
        """
        Run connection analysis on a content item.

        Returns stats dict: {"connections": N, "signals": M, "item_id": ...}
        """
        # 1. Load the content item
        item = self.session.get(ContentItem, item_id)
        if not item:
            logger.warning(f"ContentItem {item_id} not found")
            return {"connections": 0, "signals": 0, "item_id": item_id, "skipped": True}

        if item.analysis_status == AnalysisStatus.COMPLETE:
            logger.info(f"ContentItem {item_id} already COMPLETE, skipping")
            return {"connections": 0, "signals": 0, "item_id": item_id, "skipped": True}

        if not item.content_text or len(item.content_text.strip()) < 100:
            logger.warning(f"ContentItem {item_id}: content too short, skipping")
            item.analysis_status = AnalysisStatus.SKIPPED
            item.analysis_error = "Content too short for analysis"
            self.session.commit()
            return {"connections": 0, "signals": 0, "item_id": item_id, "skipped": True}

        item.analysis_status = AnalysisStatus.ANALYZING
        self.session.commit()

        try:
            # 2. Get candidate notes
            candidate_notes = self._get_candidate_notes(item)

            if not candidate_notes:
                logger.info(f"No candidate notes for {item_id}, marking COMPLETE with 0 connections")
                item.analysis_status = AnalysisStatus.COMPLETE
                item.analyzed_at = datetime.now(timezone.utc)
                self.session.commit()
                return {"connections": 0, "signals": 0, "item_id": item_id}

            # 3. Load relevant principles
            principles = self._get_relevant_principles(candidate_notes)

            # 4. Format prompts
            user_prompt = self._format_user_prompt(item, candidate_notes, principles)

            # 5. LLM call
            result = await self.llm.complete_json(
                task="analysis",
                messages=[{"role": "user", "content": user_prompt}],
                system=CONNECTION_PASS_SYSTEM,
            )

            # 6. Parse & validate
            valid_note_ids = {n.note_id for n in candidate_notes}
            connections_data = self._validate_connections(
                result.get("connections", []), valid_note_ids
            )
            signals_data = self._validate_signals(
                result.get("unconnected_signals", [])
            )

            # 7. Persist
            persisted_connections = self._persist_connections(item, connections_data)
            persisted_signals = self._persist_signals(item, signals_data)

            # Index connections in ChromaDB (lenient)
            self._index_connections(persisted_connections)

            item.analysis_status = AnalysisStatus.COMPLETE
            item.analyzed_at = datetime.now(timezone.utc)
            self.session.commit()

            stats = {
                "connections": len(persisted_connections),
                "signals": len(persisted_signals),
                "item_id": item_id,
            }
            logger.info(
                f"Connection pass complete for '{item.title[:50]}': "
                f"{stats['connections']} connections, {stats['signals']} signals"
            )
            return stats

        except Exception as e:
            logger.error(f"Connection pass failed for {item_id}: {e}")
            item.analysis_status = AnalysisStatus.ERROR
            item.analysis_error = str(e)[:500]
            self.session.commit()
            return {"connections": 0, "signals": 0, "item_id": item_id, "error": str(e)}

    def _get_candidate_notes(self, item: ContentItem) -> list[Note]:
        """
        Get candidate notes via semantic search + recently active notes.
        Deduplicates by note_id.
        """
        seen_ids = set()
        candidates = []

        # Semantic search via VectorStore
        try:
            vs = VectorStore()
            query_text = item.content_text[:2000]
            search_results = vs.search_notes(
                query=query_text, n_results=CANDIDATE_NOTES_LIMIT
            )
            for r in search_results:
                note_id = r.get("id") or r.get("metadata", {}).get("note_id")
                if note_id and note_id not in seen_ids:
                    seen_ids.add(note_id)
        except Exception as e:
            logger.warning(f"Vector search for candidate notes failed: {e}")

        # Also get recently updated notes
        cutoff = datetime.now(timezone.utc) - timedelta(days=ACTIVE_NOTES_DAYS)
        recent_stmt = (
            select(Note.note_id)
            .where(Note.updated_at >= cutoff)
            .where(Note.archived == False)  # noqa: E712
        )
        recent_ids = self.session.execute(recent_stmt).scalars().all()
        for nid in recent_ids:
            if nid not in seen_ids:
                seen_ids.add(nid)

        if not seen_ids:
            return []

        # Load full Note objects
        notes = (
            self.session.execute(
                select(Note).where(Note.note_id.in_(seen_ids))
            )
            .scalars()
            .all()
        )
        return list(notes)

    def _get_relevant_principles(self, candidate_notes: list[Note]) -> list[dict]:
        """
        Infer relevant principles from candidate note topics.
        """
        topics = set()
        for note in candidate_notes:
            if note.topic:
                topics.add(note.topic)
            if note.tags:
                for tag in note.tags:
                    if tag in TOPIC_TO_DOMAINS:
                        topics.add(tag)

        if not topics:
            # Return all principles if we can't narrow down
            return ALL_PRINCIPLES

        principles = []
        seen_ids = set()
        for topic in topics:
            for p in get_principles_for_topic(topic):
                if p["id"] not in seen_ids:
                    seen_ids.add(p["id"])
                    principles.append(p)

        return principles if principles else ALL_PRINCIPLES

    def _format_user_prompt(
        self,
        item: ContentItem,
        candidate_notes: list[Note],
        principles: list[dict],
    ) -> str:
        """Format the user prompt with all context."""
        # Format candidate notes
        note_lines = []
        for note in candidate_notes:
            tags_str = ", ".join(note.tags) if note.tags else ""
            note_lines.append(
                f"- **note_id:** `{note.note_id}`\n"
                f"  **Topic:** {note.topic or 'untagged'}\n"
                f"  **Tags:** {tags_str}\n"
                f"  **Body:** {note.body[:500]}"
            )
        candidate_notes_str = "\n\n".join(note_lines) if note_lines else "(no notes)"

        # Format principles
        principles_str = format_principles_for_llm(principles) if principles else "(none)"

        # Truncate content
        content_text = item.content_text
        if len(content_text) > CONTENT_TRUNCATE_CHARS:
            half = CONTENT_TRUNCATE_CHARS // 2
            content_text = (
                content_text[:half]
                + "\n\n[... content truncated ...]\n\n"
                + content_text[-half:]
            )

        return CONNECTION_PASS_USER.format(
            title=item.title,
            date=(
                item.published_date.strftime("%Y-%m-%d")
                if item.published_date
                else "Unknown"
            ),
            authors=(
                ", ".join(item.authors) if item.authors else "Unknown"
            ),
            content=content_text,
            candidate_notes=candidate_notes_str,
            principles=principles_str,
        )

    def _validate_connections(
        self, raw_connections: list, valid_note_ids: set[str]
    ) -> list[dict]:
        """Validate and cap connection data from the LLM response."""
        validated = []
        for raw in raw_connections:
            if len(validated) >= MAX_CONNECTIONS:
                break

            if not isinstance(raw, dict):
                logger.warning("Skipping non-dict connection entry")
                continue

            note_id = raw.get("note_id")
            if note_id not in valid_note_ids:
                logger.warning(
                    f"Skipping connection with invalid note_id: {note_id}"
                )
                continue

            relation = raw.get("relation", "")
            if relation not in _VALID_RELATIONS:
                logger.warning(
                    f"Skipping connection with invalid relation: {relation}"
                )
                continue

            articulation = raw.get("articulation", "")
            if not articulation or len(articulation.strip()) < 20:
                logger.warning("Skipping connection with missing/short articulation")
                continue

            strength = raw.get("strength", 0.5)
            try:
                strength = float(strength)
            except (TypeError, ValueError):
                strength = 0.5
            strength = max(0.0, min(1.0, strength))

            principles = raw.get("principles_invoked", [])
            if not isinstance(principles, list):
                principles = []

            validated.append({
                "note_id": note_id,
                "relation": relation,
                "articulation": articulation.strip(),
                "excerpt": raw.get("excerpt") or None,
                "excerpt_location": raw.get("excerpt_location") or None,
                "principles_invoked": principles,
                "strength": strength,
            })

        return validated

    def _validate_signals(self, raw_signals: list) -> list[dict]:
        """Validate and cap unconnected signal data from the LLM response."""
        validated = []
        for raw in raw_signals:
            if len(validated) >= MAX_SIGNALS:
                break

            if not isinstance(raw, dict):
                continue

            topic = raw.get("topic_summary", "")
            why = raw.get("why_it_matters", "")
            if not topic or not why:
                logger.warning("Skipping signal with missing topic/why_it_matters")
                continue

            validated.append({
                "topic_summary": topic.strip(),
                "why_it_matters": why.strip(),
                "excerpt": raw.get("excerpt") or None,
            })

        return validated

    def _persist_connections(
        self, item: ContentItem, connections_data: list[dict]
    ) -> list[Connection]:
        """Create Connection rows in the database."""
        connections = []
        for data in connections_data:
            conn = Connection(
                connection_id=gen_id(),
                item_id=item.item_id,
                note_id=data["note_id"],
                relation=data["relation"],
                articulation=data["articulation"],
                excerpt=data["excerpt"],
                excerpt_location=data["excerpt_location"],
                principles_invoked=data["principles_invoked"],
                strength=data["strength"],
            )
            self.session.add(conn)
            connections.append(conn)
        self.session.flush()
        return connections

    def _persist_signals(
        self, item: ContentItem, signals_data: list[dict]
    ) -> list[UnconnectedSignal]:
        """Create UnconnectedSignal rows in the database."""
        signals = []
        for data in signals_data:
            signal = UnconnectedSignal(
                signal_id=gen_id(),
                item_id=item.item_id,
                topic_summary=data["topic_summary"],
                why_it_matters=data["why_it_matters"],
                excerpt=data["excerpt"],
            )
            self.session.add(signal)
            signals.append(signal)
        self.session.flush()
        return signals

    def _index_connections(self, connections: list[Connection]) -> None:
        """Index connections in ChromaDB. Lenient — logs warnings on failure."""
        try:
            vs = VectorStore()
        except Exception as e:
            logger.warning(f"Failed to connect to VectorStore for indexing: {e}")
            return

        for conn in connections:
            try:
                vs.index_connection(
                    connection_id=conn.connection_id,
                    articulation=conn.articulation,
                    metadata={
                        "item_id": conn.item_id,
                        "note_id": conn.note_id,
                        "relation": conn.relation,
                        "strength": conn.strength,
                    },
                )
            except Exception as e:
                logger.warning(
                    f"Failed to index connection {conn.connection_id} in ChromaDB: {e}"
                )
