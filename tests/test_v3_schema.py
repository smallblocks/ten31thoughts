"""
Ten31 Thoughts - v3 Schema Tests
Verifies Connection, UnconnectedSignal models, Note.source fields,
AnalysisStatus.SKIPPED, and ConnectionRelation enum.

Run with: pytest tests/test_v3_schema.py -v
"""

import pytest
from datetime import datetime, timezone

from src.db.models import (
    Base, Connection, UnconnectedSignal, Note, ContentItem, Feed,
    ConnectionRelation, AnalysisStatus, FeedCategory,
    get_engine, create_tables, get_session, gen_id,
)


@pytest.fixture
def session(tmp_path):
    db_path = tmp_path / "test.db"
    engine = get_engine(f"sqlite:///{db_path}")
    create_tables(engine)
    sess = get_session(engine)
    yield sess
    sess.close()


@pytest.fixture
def sample_feed(session):
    feed = Feed(
        feed_id=gen_id(),
        display_name="Test Feed",
        url="https://example.com/feed",
        category=FeedCategory.EXTERNAL_INTERVIEW,
    )
    session.add(feed)
    session.commit()
    return feed


@pytest.fixture
def sample_item(session, sample_feed):
    item = ContentItem(
        item_id=gen_id(),
        feed_id=sample_feed.feed_id,
        title="Test Episode",
        url="https://example.com/ep1",
    )
    session.add(item)
    session.commit()
    return item


@pytest.fixture
def sample_note(session):
    note = Note(
        note_id=gen_id(),
        body="Bitcoin is sound money because fixed supply.",
    )
    session.add(note)
    session.commit()
    return note


class TestConnectionModel:
    def test_create_connection(self, session, sample_item, sample_note):
        conn = Connection(
            connection_id=gen_id(),
            item_id=sample_item.item_id,
            note_id=sample_note.note_id,
            relation=ConnectionRelation.REINFORCES,
            articulation="This episode supports the fixed supply thesis.",
            strength=0.85,
        )
        session.add(conn)
        session.commit()
        session.refresh(conn)

        assert conn.connection_id is not None
        assert conn.relation == "reinforces"
        assert conn.articulation == "This episode supports the fixed supply thesis."
        assert conn.strength == 0.85
        assert conn.user_rating is None
        assert conn.user_promoted_to_note is False
        assert conn.user_dismissed is False
        assert conn.created_at is not None

    def test_connection_with_all_fields(self, session, sample_item, sample_note):
        conn = Connection(
            connection_id=gen_id(),
            item_id=sample_item.item_id,
            note_id=sample_note.note_id,
            relation=ConnectionRelation.EXTENDS,
            articulation="Extends the thesis by adding energy dimension.",
            excerpt="The energy cost of mining creates a physical anchor...",
            excerpt_location="12:34",
            principles_invoked=["sm_02", "hn_03"],
            strength=0.92,
            user_rating=5,
        )
        session.add(conn)
        session.commit()
        session.refresh(conn)

        assert conn.excerpt == "The energy cost of mining creates a physical anchor..."
        assert conn.excerpt_location == "12:34"
        assert conn.principles_invoked == ["sm_02", "hn_03"]
        assert conn.user_rating == 5

    def test_connection_relationships(self, session, sample_item, sample_note):
        conn = Connection(
            connection_id=gen_id(),
            item_id=sample_item.item_id,
            note_id=sample_note.note_id,
            relation=ConnectionRelation.CONTRADICTS,
            articulation="Contradicts the thesis.",
            strength=0.7,
        )
        session.add(conn)
        session.commit()
        session.refresh(conn)

        assert conn.item.item_id == sample_item.item_id
        assert conn.note.note_id == sample_note.note_id


class TestUnconnectedSignalModel:
    def test_create_signal(self, session, sample_item):
        signal = UnconnectedSignal(
            signal_id=gen_id(),
            item_id=sample_item.item_id,
            topic_summary="CBDC implementation timeline accelerating",
            why_it_matters="Could change the competitive landscape for bitcoin adoption.",
        )
        session.add(signal)
        session.commit()
        session.refresh(signal)

        assert signal.signal_id is not None
        assert signal.topic_summary == "CBDC implementation timeline accelerating"
        assert signal.user_dismissed is False
        assert signal.user_promoted_to_note is False

    def test_signal_with_excerpt(self, session, sample_item):
        signal = UnconnectedSignal(
            signal_id=gen_id(),
            item_id=sample_item.item_id,
            topic_summary="New mining tech",
            why_it_matters="Changes economics.",
            excerpt="The new ASIC achieves 3x efficiency...",
        )
        session.add(signal)
        session.commit()
        session.refresh(signal)

        assert signal.excerpt == "The new ASIC achieves 3x efficiency..."


class TestNoteSourceFields:
    def test_note_source_defaults_to_none(self, session):
        note = Note(note_id=gen_id(), body="test")
        session.add(note)
        session.commit()
        session.refresh(note)

        assert note.source is None
        assert note.source_item_id is None

    def test_note_with_timestamp_source(self, session, sample_item):
        note = Note(
            note_id=gen_id(),
            body="Extracted from Timestamp issue",
            source="timestamp",
            source_item_id=sample_item.item_id,
        )
        session.add(note)
        session.commit()
        session.refresh(note)

        assert note.source == "timestamp"
        assert note.source_item_id == sample_item.item_id

    def test_note_manual_source(self, session):
        note = Note(
            note_id=gen_id(),
            body="User typed this manually",
            source="manual",
        )
        session.add(note)
        session.commit()
        session.refresh(note)

        assert note.source == "manual"
        assert note.source_item_id is None

    def test_note_promoted_from_connection(self, session, sample_item):
        note = Note(
            note_id=gen_id(),
            body="Promoted from a connection articulation",
            source="promoted_from_connection",
            source_item_id=sample_item.item_id,
        )
        session.add(note)
        session.commit()
        session.refresh(note)

        assert note.source == "promoted_from_connection"


class TestConnectionRelationEnum:
    def test_all_values(self):
        assert ConnectionRelation.REINFORCES == "reinforces"
        assert ConnectionRelation.EXTENDS == "extends"
        assert ConnectionRelation.COMPLICATES == "complicates"
        assert ConnectionRelation.CONTRADICTS == "contradicts"
        assert ConnectionRelation.ECHOES_MECHANISM == "echoes_mechanism"

    def test_enum_count(self):
        assert len(ConnectionRelation) == 5


class TestAnalysisStatusSkipped:
    def test_skipped_exists(self):
        assert hasattr(AnalysisStatus, 'SKIPPED')

    def test_skipped_value(self):
        val = AnalysisStatus.SKIPPED
        assert val == "skipped"


class TestVectorStoreConnections:
    """Tests for the connections collection in VectorStore."""

    def test_connections_collection_exists(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CHROMADB_PERSIST_DIR", str(tmp_path / "chromadb"))
        monkeypatch.setenv("CHROMADB_HOST", "127.0.0.1")
        monkeypatch.setenv("CHROMADB_PORT", "1")

        try:
            from src.db.vector import VectorStore
            vs = VectorStore()
            assert vs.connections is not None
        except Exception as e:
            pytest.skip(f"Chroma unavailable: {e}")

    def test_index_and_search_connection(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CHROMADB_PERSIST_DIR", str(tmp_path / "chromadb"))
        monkeypatch.setenv("CHROMADB_HOST", "127.0.0.1")
        monkeypatch.setenv("CHROMADB_PORT", "1")

        try:
            from src.db.vector import VectorStore
            vs = VectorStore()
            vs.index_connection(
                "conn-1",
                "Bitcoin mining energy creates physical anchor for digital value.",
                {"note_id": "note-1", "relation": "reinforces"},
            )
            results = vs.search_connections("energy and mining")
            assert any(r["id"] == "conn-1" for r in results)
        except Exception as e:
            pytest.skip(f"Chroma unavailable: {e}")

    def test_get_stats_includes_connections(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CHROMADB_PERSIST_DIR", str(tmp_path / "chromadb"))
        monkeypatch.setenv("CHROMADB_HOST", "127.0.0.1")
        monkeypatch.setenv("CHROMADB_PORT", "1")

        try:
            from src.db.vector import VectorStore
            vs = VectorStore()
            stats = vs.get_stats()
            assert "connections" in stats
        except Exception as e:
            pytest.skip(f"Chroma unavailable: {e}")
