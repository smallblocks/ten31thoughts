"""
Ten31 Thoughts - Timestamp Note Extractor
Converts Timestamp newsletter issues into discrete Notes.
Single LLM call per issue. Replaces the old ThesisAnalyzer.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db.models import (
    ContentItem, Feed, FeedCategory, Note, AnalysisStatus, gen_id,
)
from ..llm.router import LLMRouter
from .prompts.note_extraction import NOTE_EXTRACTION_SYSTEM, NOTE_EXTRACTION_USER

logger = logging.getLogger(__name__)

# Default topic vocabulary — matches thesis_passes.py VALID_TOPICS plus
# additional bitcoin-ecosystem topics relevant to Ten31.
DEFAULT_TOPIC_VOCABULARY = [
    "fed_policy", "labor_market", "fiscal_policy", "geopolitics",
    "bitcoin", "credit_markets", "energy", "currencies", "inflation",
    "financial_plumbing", "regulatory", "demographics", "technology",
    "bitcoin_monetary", "political_cycles", "technology_sovereignty",
]


class NoteExtractor:
    """
    Extracts discrete Notes from Timestamp newsletter issues.

    Single LLM call per issue. Each note is an atomic idea, argument,
    or claim that can stand alone as a searchable reference point.
    """

    def __init__(self, llm_router: LLMRouter, session: Session):
        self.llm = llm_router
        self.session = session

    async def extract(self, item_id: str) -> list[Note]:
        """
        Extract notes from a ContentItem.

        Returns list of created Note objects, or empty list if skipped/failed.
        """
        # 1. Load and validate the content item
        item = self.session.get(ContentItem, item_id)
        if not item:
            logger.warning(f"ContentItem {item_id} not found")
            return []

        if item.analysis_status == AnalysisStatus.COMPLETE:
            logger.info(f"Skipping already-complete item {item_id}")
            return []

        # Check category via feed
        feed = self.session.get(Feed, item.feed_id)
        if not feed or feed.category != FeedCategory.OUR_THESIS:
            logger.info(f"Skipping non-OUR_THESIS item {item_id}")
            return []

        if not item.content_text or len(item.content_text.strip()) < 100:
            logger.warning(f"Content too short for {item_id}")
            item.analysis_status = AnalysisStatus.ERROR
            item.analysis_error = "Content too short for note extraction"
            self.session.commit()
            return []

        # 2. Load active threads (notes with thread_id tag, updated in last 60 days)
        existing_threads = self._load_active_threads()

        # 3. Load topic vocabulary
        topic_vocabulary = self._load_topic_vocabulary()

        # 4. Format the prompt
        threads_text = self._format_threads(existing_threads)
        topics_text = ", ".join(sorted(topic_vocabulary))

        content_text = self._truncate_content(item.content_text)
        pub_date = (
            item.published_date.strftime("%Y-%m-%d")
            if item.published_date else "Unknown"
        )

        prompt = NOTE_EXTRACTION_USER.format(
            title=item.title,
            date=pub_date,
            topic_vocabulary=topics_text,
            existing_threads=threads_text,
            content=content_text,
        )

        # 5. Make LLM call
        item.analysis_status = AnalysisStatus.ANALYZING
        self.session.commit()

        try:
            result = await self.llm.complete_json(
                task="analysis",
                messages=[{"role": "user", "content": prompt}],
                system=NOTE_EXTRACTION_SYSTEM,
            )
        except Exception as e:
            logger.error(f"LLM call failed for note extraction on {item_id}: {e}")
            item.analysis_status = AnalysisStatus.ERROR
            item.analysis_error = f"LLM call failed: {str(e)[:400]}"
            self.session.commit()
            return []

        # 6. Parse response and create Notes
        raw_notes = result.get("notes", []) if isinstance(result, dict) else []
        created_notes: list[Note] = []

        # Collect existing thread IDs for validation
        existing_thread_ids = set(existing_threads.keys())

        for raw in raw_notes:
            try:
                body = raw.get("body", "").strip()
                if not body:
                    continue

                title = raw.get("title")
                if title:
                    title = title.strip()[:500] or None

                # Validate topic
                topic = raw.get("topic", "").strip().lower().replace(" ", "_")
                if topic not in topic_vocabulary:
                    topic = None

                # Handle tags
                tags = raw.get("tags", [])
                if not isinstance(tags, list):
                    tags = []
                tags = [str(t).strip().lower() for t in tags[:5] if t]

                # Handle thread_id
                thread_id = raw.get("thread_id")
                if thread_id:
                    thread_id = str(thread_id).strip()
                    if thread_id.startswith("new:"):
                        # Generate a new thread ID
                        desc = thread_id[4:].strip().lower().replace(" ", "-")[:50]
                        thread_id = f"thread-{desc}-{gen_id()[:8]}"
                    elif thread_id not in existing_thread_ids:
                        # Invalid thread reference — drop it
                        thread_id = None

                # Store thread_id as a tag convention: "thread:<id>"
                note_tags = list(tags)
                if thread_id:
                    note_tags.append(f"thread:{thread_id}")

                note = Note(
                    note_id=gen_id(),
                    title=title,
                    body=body,
                    topic=topic,
                    tags=note_tags,
                    source="timestamp_synopsis",
                    source_item_id=item_id,
                    source_url=item.url,
                )
                self.session.add(note)
                created_notes.append(note)

            except Exception as e:
                logger.warning(f"Failed to parse note from LLM response: {e}")
                continue

        # Commit all notes
        self.session.flush()

        # 7. Index notes in ChromaDB (lenient)
        self._index_notes(created_notes)

        # 8. Mark item complete
        item.analysis_status = AnalysisStatus.COMPLETE
        item.analyzed_at = datetime.now(timezone.utc)
        self.session.commit()

        logger.info(
            f"Note extraction complete for '{item.title[:50]}': "
            f"{len(created_notes)} notes created"
        )
        return created_notes

    # ─── Helpers ───

    def _load_active_threads(self) -> dict[str, str]:
        """
        Load active threads — notes with thread:<id> tags updated in last 60 days.
        Returns {thread_id: most_recent_note_body}.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=60)

        recent_notes = (
            self.session.query(Note)
            .filter(
                Note.source.in_(["timestamp", "timestamp_synopsis"]),
                Note.updated_at >= cutoff,
            )
            .order_by(Note.updated_at.desc())
            .all()
        )

        threads: dict[str, str] = {}
        for note in recent_notes:
            if not note.tags:
                continue
            for tag in note.tags:
                if isinstance(tag, str) and tag.startswith("thread:"):
                    tid = tag[7:]
                    if tid and tid not in threads:
                        threads[tid] = note.body[:200]
        return threads

    def _load_topic_vocabulary(self) -> set[str]:
        """Load topic vocabulary from existing notes + defaults."""
        vocab = set(DEFAULT_TOPIC_VOCABULARY)

        # Also include any distinct topics already in the DB
        try:
            existing_topics = (
                self.session.query(Note.topic)
                .filter(Note.topic.isnot(None))
                .distinct()
                .all()
            )
            for (topic,) in existing_topics:
                if topic:
                    vocab.add(topic)
        except Exception:
            pass

        return vocab

    def _format_threads(self, threads: dict[str, str]) -> str:
        """Format thread context for the prompt."""
        if not threads:
            return "(No active threads yet)"

        lines = []
        for tid, body in list(threads.items())[:20]:
            lines.append(f"- thread_id: {tid}\n  Recent note: {body}")
        return "\n".join(lines)

    def _truncate_content(self, text: str, max_chars: int = 80000) -> str:
        """Truncate content to fit within LLM context limits."""
        if len(text) <= max_chars:
            return text
        half = max_chars // 2
        return text[:half] + "\n\n[... content truncated ...]\n\n" + text[-half:]

    def _index_notes(self, notes: list[Note]) -> None:
        """Index notes in vector store. Lenient — warns on failure."""
        try:
            from ..db.vector import VectorStore
            vs = VectorStore()
            for note in notes:
                try:
                    vs.index_note(
                        note_id=note.note_id,
                        body=note.body,
                        metadata={
                            "topic": note.topic or "",
                            "source": note.source or "",
                            "source_item_id": note.source_item_id or "",
                            "title": note.title or "",
                        },
                    )
                except Exception as e:
                    logger.warning(f"Failed to index note {note.note_id}: {e}")
        except Exception as e:
            logger.warning(f"Vector store unavailable for note indexing: {e}")
