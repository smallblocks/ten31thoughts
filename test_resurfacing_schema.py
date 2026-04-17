"""
Ten31 Thoughts - Resurfacing Schema Tests
Verifies Note, ResurfacingEvent, ResurfacingTrigger, and the notes ChromaDB
collection round-trip correctly.

Run with: pytest tests/test_resurfacing_schema.py
Or: python -m pytest tests/test_resurfacing_schema.py -v
"""

import os
import tempfile
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from src.db.models import (
    Base, Note, ResurfacingEvent, ResurfacingTrigger,
    Feed, ContentItem, FeedCategory, FeedStatus, AnalysisStatus,
    get_engine, create_tables, get_session, gen_id,
)


# ─── Fixtures ───

@pytest.fixture
def session(tmp_path):
    """Fresh SQLite DB per test."""
    db_path = tmp_path / "test.db"
    engine = get_engine(f"sqlite:///{db_path}")
    create_tables(engine)
    sess = get_session(engine)
    yield sess
    sess.close()


@pytest.fixture
def vector_store(tmp_path, monkeypatch):
    """ChromaDB persistent client in a temp dir."""
    persist_dir = tmp_path / "chromadb"
    monkeypatch.setenv("CHROMADB_PERSIST_DIR", str(persist_dir))
    # Force embedded mode by pointing HttpClient at an unreachable host
    monkeypatch.setenv("CHROMADB_HOST", "127.0.0.1")
    monkeypatch.setenv("CHROMADB_PORT", "1")
    from src.db.vector import VectorStore
    return VectorStore()


@pytest.fixture
def sample_feed_and_item(session):
    """A feed + content item, useful as a target for trigger_item_id."""
    feed = Feed(
        feed_id=gen_id(),
        url="https://example.com/feed",
        category=FeedCategory.EXTERNAL_INTERVIEW,
        display_name="Test Feed",
        status=FeedStatus.ACTIVE,
    )
    session.add(feed)
    session.flush()

    item = ContentItem(
        item_id=gen_id(),
        feed_id=feed.feed_id,
        url="https://example.com/article",
        title="Test article",
        analysis_status=AnalysisStatus.COMPLETE,
    )
    session.add(item)
    session.commit()
    return feed, item


# ─── Note model tests ───

class TestNoteModel:
    def test_create_note_with_defaults(self, session):
        note = Note(body="Bitcoin is sound money because of fixed supply.")
        session.add(note)
        session.commit()

        fetched = session.execute(select(Note)).scalar_one()
        assert fetched.note_id is not None
        assert fetched.body == "Bitcoin is sound money because of fixed supply."
        assert fetched.title is None
        assert fetched.topic is None
        assert fetched.tags == []
        assert fetched.source_url is None
        assert fetched.archived is False
        assert fetched.fsrs_state == 0
        assert fetched.fsrs_reps == 0
        assert fetched.fsrs_lapses == 0
        assert fetched.fsrs_due is None
        assert fetched.fsrs_stability is None
        assert fetched.fsrs_difficulty is None
        assert fetched.fsrs_last_review is None
        assert fetched.created_at is not None
        assert fetched.updated_at is not None

    def test_create_note_with_all_fields(self, session):
        note = Note(
            title="On Polybius",
            body="Anacyclosis explains the decay of republics.",
            topic="political_cycles",
            tags=["polybius", "republic", "decay"],
            source_url="https://ten31timestamp.com/p/anacyclosis",
            fsrs_due=datetime(2026, 5, 1, tzinfo=timezone.utc),
            fsrs_stability=3.2,
            fsrs_difficulty=5.8,
            fsrs_state=2,
            fsrs_reps=4,
            fsrs_lapses=1,
            fsrs_last_review=datetime(2026, 4, 15, tzinfo=timezone.utc),
        )
        session.add(note)
        session.commit()

        fetched = session.execute(select(Note)).scalar_one()
        assert fetched.title == "On Polybius"
        assert fetched.topic == "political_cycles"
        assert fetched.tags == ["polybius", "republic", "decay"]
        assert fetched.fsrs_state == 2
        assert fetched.fsrs_stability == 3.2
        assert fetched.fsrs_reps == 4
        assert fetched.fsrs_lapses == 1

    def test_note_body_is_required(self, session):
        from sqlalchemy.exc import IntegrityError
        note = Note(title="No body here")
        session.add(note)
        with pytest.raises(IntegrityError):
            session.commit()

    def test_archived_flag_persists(self, session):
        note = Note(body="archive me")
        session.add(note)
        session.commit()

        note.archived = True
        session.commit()

        fetched = session.execute(select(Note)).scalar_one()
        assert fetched.archived is True


# ─── ResurfacingEvent model tests ───

class TestResurfacingEvent:
    def test_scheduled_event_minimal(self, session):
        """SCHEDULED trigger needs no context columns."""
        note = Note(body="Sound money.")
        session.add(note)
        session.flush()

        event = ResurfacingEvent(
            note_id=note.note_id,
            trigger=ResurfacingTrigger.SCHEDULED,
        )
        session.add(event)
        session.commit()

        fetched = session.execute(select(ResurfacingEvent)).scalar_one()
        assert fetched.event_id is not None
        assert fetched.trigger == ResurfacingTrigger.SCHEDULED
        assert fetched.trigger_item_id is None
        assert fetched.trigger_note_id is None
        assert fetched.similarity_score is None
        assert fetched.bridge_text is None
        assert fetched.surfaced_at is not None
        assert fetched.digest_date is None
        assert fetched.engaged_at is None
        assert fetched.dismissed_at is None
        assert fetched.rating is None

    def test_semantic_on_write_event(self, session):
        """SEMANTIC_ON_WRITE has trigger_note_id and similarity_score."""
        old_note = Note(body="Old idea about sound money.")
        new_note = Note(body="New idea about sound money.")
        session.add_all([old_note, new_note])
        session.flush()

        event = ResurfacingEvent(
            note_id=old_note.note_id,
            trigger=ResurfacingTrigger.SEMANTIC_ON_WRITE,
            trigger_note_id=new_note.note_id,
            similarity_score=0.87,
        )
        session.add(event)
        session.commit()

        fetched = session.execute(select(ResurfacingEvent)).scalar_one()
        assert fetched.trigger == ResurfacingTrigger.SEMANTIC_ON_WRITE
        assert fetched.trigger_note_id == new_note.note_id
        assert fetched.trigger_item_id is None
        assert fetched.similarity_score == 0.87
        assert fetched.bridge_text is None

    def test_news_driven_event(self, session, sample_feed_and_item):
        """NEWS_DRIVEN has trigger_item_id, similarity_score, and bridge_text."""
        _, item = sample_feed_and_item
        note = Note(body="Treasury debt dynamics will force the Fed's hand.")
        session.add(note)
        session.flush()

        event = ResurfacingEvent(
            note_id=note.note_id,
            trigger=ResurfacingTrigger.NEWS_DRIVEN,
            trigger_item_id=item.item_id,
            similarity_score=0.79,
            bridge_text=(
                "This MacroVoices episode echoes your earlier note on "
                "fiscal dominance — the mechanism Bastiat warned about."
            ),
        )
        session.add(event)
        session.commit()

        fetched = session.execute(select(ResurfacingEvent)).scalar_one()
        assert fetched.trigger == ResurfacingTrigger.NEWS_DRIVEN
        assert fetched.trigger_item_id == item.item_id
        assert fetched.trigger_note_id is None
        assert fetched.similarity_score == 0.79
        assert "Bastiat" in fetched.bridge_text

    def test_note_relationship_resolves(self, session):
        note = Note(body="Resolve me.")
        session.add(note)
        session.flush()

        event = ResurfacingEvent(
            note_id=note.note_id,
            trigger=ResurfacingTrigger.SCHEDULED,
        )
        session.add(event)
        session.commit()

        fetched = session.execute(select(ResurfacingEvent)).scalar_one()
        assert fetched.note is not None
        assert fetched.note.body == "Resolve me."

    def test_query_by_digest_date(self, session):
        note = Note(body="Pull me into today's digest.")
        session.add(note)
        session.flush()

        digest_day = datetime(2026, 4, 17, tzinfo=timezone.utc)
        event = ResurfacingEvent(
            note_id=note.note_id,
            trigger=ResurfacingTrigger.SCHEDULED,
            digest_date=digest_day,
        )
        session.add(event)
        session.commit()

        events = session.execute(
            select(ResurfacingEvent).where(ResurfacingEvent.digest_date == digest_day)
        ).scalars().all()
        assert len(events) == 1
        assert events[0].note_id == note.note_id

    def test_engagement_signals(self, session):
        note = Note(body="Engaged with.")
        session.add(note)
        session.flush()

        event = ResurfacingEvent(
            note_id=note.note_id,
            trigger=ResurfacingTrigger.SCHEDULED,
            engaged_at=datetime(2026, 4, 17, 9, 0, tzinfo=timezone.utc),
            rating=3,
        )
        session.add(event)
        session.commit()

        fetched = session.execute(select(ResurfacingEvent)).scalar_one()
        assert fetched.rating == 3
        assert fetched.engaged_at is not None
        assert fetched.dismissed_at is None


# ─── Vector store tests ───

class TestNotesVectorCollection:
    def test_notes_collection_exists(self, vector_store):
        assert hasattr(vector_store, "notes")
        assert vector_store.notes.count() == 0

    def test_index_and_search_note_roundtrip(self, vector_store):
        note_id = gen_id()
        body = (
            "Polybius's Anacyclosis describes the cycle of governments — "
            "monarchy decays into tyranny, aristocracy into oligarchy, "
            "democracy into mob rule."
        )
        vector_store.index_note(
            note_id=note_id,
            body=body,
            metadata={"topic": "political_cycles", "archived": False},
        )

        results = vector_store.search_notes(query="cycles of political decay")
        assert len(results) >= 1
        assert results[0]["id"] == note_id
        assert "Anacyclosis" in results[0]["document"]
        assert results[0]["metadata"]["topic"] == "political_cycles"

    def test_search_notes_filters_by_topic(self, vector_store):
        vector_store.index_note(
            note_id=gen_id(),
            body="Bitcoin fixed supply.",
            metadata={"topic": "bitcoin"},
        )
        vector_store.index_note(
            note_id=gen_id(),
            body="Polybius and republican decay.",
            metadata={"topic": "political_cycles"},
        )

        bitcoin_only = vector_store.search_notes(
            query="sound money", topic="bitcoin"
        )
        assert all(r["metadata"]["topic"] == "bitcoin" for r in bitcoin_only)

    def test_get_stats_includes_notes(self, vector_store):
        stats = vector_store.get_stats()
        assert "notes" in stats
        assert isinstance(stats["notes"], int)

    def test_search_all_excludes_notes(self, vector_store):
        """Notes belong to the resurfacing engine, not convergence queries."""
        vector_store.index_note(
            note_id=gen_id(),
            body="Some note about the Fed.",
            metadata={"topic": "fed_policy"},
        )
        results = vector_store.search_all(query="Fed policy")
        assert "notes" not in results
        assert set(results.keys()) == {
            "content", "thesis_elements", "frameworks", "blind_spots"
        }


# ─── FSRS library smoke test ───

class TestFsrsImportable:
    def test_fsrs_importable(self):
        from fsrs import Scheduler, Card, Rating
        scheduler = Scheduler()
        card = Card()
        assert card is not None
        # Confirm Rating enum has the four values FSRS uses
        assert Rating.Again == 1
        assert Rating.Hard == 2
        assert Rating.Good == 3
        assert Rating.Easy == 4
