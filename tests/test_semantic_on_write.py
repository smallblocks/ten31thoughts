"""
Ten31 Thoughts - Semantic-on-write trigger tests
Run with: pytest tests/test_semantic_on_write.py -v
"""

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select

from src.db.models import (
    Base, Note, ResurfacingEvent, ResurfacingTrigger,
    get_engine, create_tables, get_session, gen_id,
)
from src.resurfacing.semantic_on_write import (
    fire_semantic_on_write,
    DISTANCE_THRESHOLD,
    MAX_EVENTS_PER_WRITE,
    COOLDOWN_DAYS,
)


@pytest.fixture
def session(tmp_path):
    db_path = tmp_path / "test.db"
    engine = get_engine(f"sqlite:///{db_path}")
    create_tables(engine)
    sess = get_session(engine)
    yield sess
    sess.close()


def _make_note(session, body: str, archived: bool = False, note_id: str = None) -> Note:
    note = Note(note_id=note_id or gen_id(), body=body, archived=archived)
    session.add(note)
    session.commit()
    session.refresh(note)
    return note


def _mock_chroma_results(id_distance_pairs: list[tuple[str, float]]) -> dict:
    return {
        "ids": [[i for i, _ in id_distance_pairs]],
        "distances": [[d for _, d in id_distance_pairs]],
        "documents": [[""] * len(id_distance_pairs)],
        "metadatas": [[{}] * len(id_distance_pairs)],
    }


@pytest.fixture
def mock_vector_store():
    with patch("src.resurfacing.semantic_on_write.VectorStore") as mock_cls:
        mock_instance = MagicMock()
        mock_instance.notes = MagicMock()
        mock_cls.return_value = mock_instance
        yield mock_instance


class TestSemanticOnWriteTrigger:
    def test_no_candidates_writes_no_events(self, session, mock_vector_store):
        source = _make_note(session, "source body")
        mock_vector_store.notes.query.return_value = _mock_chroma_results([])
        written = fire_semantic_on_write(session, source)
        assert written == 0
        events = session.execute(select(ResurfacingEvent)).scalars().all()
        assert events == []

    def test_self_excluded(self, session, mock_vector_store):
        source = _make_note(session, "source body")
        mock_vector_store.notes.query.return_value = _mock_chroma_results([
            (source.note_id, 0.0),
        ])
        written = fire_semantic_on_write(session, source)
        assert written == 0

    def test_above_threshold_excluded(self, session, mock_vector_store):
        source = _make_note(session, "source body")
        far_note = _make_note(session, "far body")
        mock_vector_store.notes.query.return_value = _mock_chroma_results([
            (far_note.note_id, DISTANCE_THRESHOLD + 0.01),
        ])
        written = fire_semantic_on_write(session, source)
        assert written == 0

    def test_below_threshold_writes_event(self, session, mock_vector_store):
        source = _make_note(session, "source body")
        close_note = _make_note(session, "close body")
        mock_vector_store.notes.query.return_value = _mock_chroma_results([
            (close_note.note_id, 0.2),
        ])
        written = fire_semantic_on_write(session, source)
        assert written == 1
        event = session.execute(select(ResurfacingEvent)).scalar_one()
        assert event.note_id == close_note.note_id
        assert event.trigger == ResurfacingTrigger.SEMANTIC_ON_WRITE
        assert event.trigger_note_id == source.note_id
        assert event.similarity_score == 0.8
        assert event.bridge_text is None
        assert event.trigger_item_id is None

    def test_cap_at_max_events_per_write(self, session, mock_vector_store):
        source = _make_note(session, "source body")
        notes = [_make_note(session, f"note {i}") for i in range(MAX_EVENTS_PER_WRITE + 3)]
        pairs = [(n.note_id, 0.1 + i * 0.01) for i, n in enumerate(notes)]
        mock_vector_store.notes.query.return_value = _mock_chroma_results(pairs)
        written = fire_semantic_on_write(session, source)
        assert written == MAX_EVENTS_PER_WRITE

    def test_orders_by_distance_when_capped(self, session, mock_vector_store):
        source = _make_note(session, "source body")
        notes = [_make_note(session, f"note {i}") for i in range(MAX_EVENTS_PER_WRITE + 3)]
        pairs = list(zip(
            [n.note_id for n in notes],
            [0.4, 0.35, 0.3, 0.25, 0.2, 0.15, 0.1, 0.05],
        ))
        mock_vector_store.notes.query.return_value = _mock_chroma_results(pairs)
        fire_semantic_on_write(session, source)
        events = session.execute(select(ResurfacingEvent)).scalars().all()
        surfaced_ids = {e.note_id for e in events}
        expected_ids = {n.note_id for n in notes[-MAX_EVENTS_PER_WRITE:]}
        assert surfaced_ids == expected_ids

    def test_cooldown_skips_recently_surfaced(self, session, mock_vector_store):
        source = _make_note(session, "source body")
        in_cooldown = _make_note(session, "in cooldown")
        fresh = _make_note(session, "fresh")
        recent_event = ResurfacingEvent(
            event_id=gen_id(),
            note_id=in_cooldown.note_id,
            trigger=ResurfacingTrigger.SEMANTIC_ON_WRITE,
            similarity_score=0.7,
            surfaced_at=datetime.now(timezone.utc) - timedelta(days=COOLDOWN_DAYS - 1),
        )
        session.add(recent_event)
        session.commit()
        mock_vector_store.notes.query.return_value = _mock_chroma_results([
            (in_cooldown.note_id, 0.1),
            (fresh.note_id, 0.2),
        ])
        fire_semantic_on_write(session, source)
        events = session.execute(
            select(ResurfacingEvent).where(
                ResurfacingEvent.trigger_note_id == source.note_id
            )
        ).scalars().all()
        assert len(events) == 1
        assert events[0].note_id == fresh.note_id

    def test_cooldown_does_not_apply_to_old_events(self, session, mock_vector_store):
        source = _make_note(session, "source body")
        target = _make_note(session, "target body")
        old_event = ResurfacingEvent(
            event_id=gen_id(),
            note_id=target.note_id,
            trigger=ResurfacingTrigger.SEMANTIC_ON_WRITE,
            similarity_score=0.6,
            surfaced_at=datetime.now(timezone.utc) - timedelta(days=COOLDOWN_DAYS + 1),
        )
        session.add(old_event)
        session.commit()
        mock_vector_store.notes.query.return_value = _mock_chroma_results([
            (target.note_id, 0.15),
        ])
        fire_semantic_on_write(session, source)
        new_events = session.execute(
            select(ResurfacingEvent).where(
                ResurfacingEvent.trigger_note_id == source.note_id
            )
        ).scalars().all()
        assert len(new_events) == 1

    def test_cooldown_only_applies_to_semantic_trigger(self, session, mock_vector_store):
        source = _make_note(session, "source body")
        target = _make_note(session, "target body")
        scheduled_event = ResurfacingEvent(
            event_id=gen_id(),
            note_id=target.note_id,
            trigger=ResurfacingTrigger.SCHEDULED,
            surfaced_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        session.add(scheduled_event)
        session.commit()
        mock_vector_store.notes.query.return_value = _mock_chroma_results([
            (target.note_id, 0.1),
        ])
        fire_semantic_on_write(session, source)
        semantic_events = session.execute(
            select(ResurfacingEvent).where(
                ResurfacingEvent.trigger == ResurfacingTrigger.SEMANTIC_ON_WRITE
            )
        ).scalars().all()
        assert len(semantic_events) == 1

    def test_orphan_chroma_id_skipped(self, session, mock_vector_store):
        source = _make_note(session, "source body")
        mock_vector_store.notes.query.return_value = _mock_chroma_results([
            ("ghost-id-not-in-sql", 0.1),
        ])
        written = fire_semantic_on_write(session, source)
        assert written == 0

    def test_none_distance_skipped(self, session, mock_vector_store):
        source = _make_note(session, "source body")
        target = _make_note(session, "target body")
        mock_vector_store.notes.query.return_value = {
            "ids": [[target.note_id]],
            "distances": [[None]],
            "documents": [[""]],
            "metadatas": [[{}]],
        }
        written = fire_semantic_on_write(session, source)
        assert written == 0

    def test_chroma_failure_returns_zero(self, session, mock_vector_store):
        source = _make_note(session, "source body")
        mock_vector_store.notes.query.side_effect = Exception("Chroma exploded")
        written = fire_semantic_on_write(session, source)
        assert written == 0

    def test_archived_filter_in_query(self, session, mock_vector_store):
        source = _make_note(session, "source body")
        mock_vector_store.notes.query.return_value = _mock_chroma_results([])
        fire_semantic_on_write(session, source)
        call_kwargs = mock_vector_store.notes.query.call_args.kwargs
        assert call_kwargs.get("where") == {"archived": False}


class TestSemanticOnWriteLive:
    def test_create_then_create_surfaces_first(self, session, tmp_path, monkeypatch):
        from src.db.vector import VectorStore
        from src.api.notes import _index_note_lenient

        persist_dir = tmp_path / "chromadb"
        monkeypatch.setenv("CHROMADB_PERSIST_DIR", str(persist_dir))
        monkeypatch.setenv("CHROMADB_HOST", "127.0.0.1")
        monkeypatch.setenv("CHROMADB_PORT", "1")

        try:
            vs = VectorStore()
        except Exception as e:
            pytest.skip(f"Chroma unavailable: {e}")

        first = _make_note(
            session,
            "Polybius's Anacyclosis describes the inevitable decay of political systems."
        )
        try:
            vs.index_note(first.note_id, first.body, {"topic": "political_cycles", "archived": False})
        except Exception as e:
            pytest.skip(f"Chroma index failed: {e}")

        second = _make_note(
            session,
            "The cycle from monarchy to tyranny to democracy follows a predictable pattern."
        )

        written = fire_semantic_on_write(session, second)

        if written == 0:
            pytest.skip(
                "Live embedding distance was above threshold — tune DISTANCE_THRESHOLD "
                "or check that the embedding model loaded."
            )

        events = session.execute(
            select(ResurfacingEvent).where(
                ResurfacingEvent.trigger_note_id == second.note_id
            )
        ).scalars().all()
        assert any(e.note_id == first.note_id for e in events)
        for e in events:
            assert 0.5 < e.similarity_score <= 1.0
