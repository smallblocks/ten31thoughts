"""
Ten31 Thoughts - Connection Pass Tests
Tests for the single-LLM-call connection analysis pass.

Mocks the LLM router to return controlled JSON responses.
Run with: pytest tests/test_connection_pass.py -v
"""

import json
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from src.db.models import (
    Base, Connection, UnconnectedSignal, Note, ContentItem, Feed,
    ConnectionRelation, AnalysisStatus, FeedCategory,
    get_engine, create_tables, get_session, gen_id,
)
from src.analysis.connection_pass import ConnectionAnalyzer


@pytest.fixture
def engine(tmp_path):
    db_path = tmp_path / "test.db"
    eng = get_engine(f"sqlite:///{db_path}")
    create_tables(eng)
    return eng


@pytest.fixture
def session(engine):
    sess = get_session(engine)
    yield sess
    sess.close()


@pytest.fixture
def sample_feed(session):
    feed = Feed(
        feed_id=gen_id(),
        display_name="Test Podcast",
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
        title="Episode 42: The Future of Sound Money",
        url="https://example.com/ep42",
        published_date=datetime(2024, 6, 15, tzinfo=timezone.utc),
        authors=["Guest Author"],
        content_text="A" * 200,  # min length to pass short-content check
        analysis_status=AnalysisStatus.PENDING,
    )
    session.add(item)
    session.commit()
    return item


@pytest.fixture
def sample_notes(session):
    notes = []
    for i, (body, topic) in enumerate([
        ("Bitcoin is sound money because of its fixed supply of 21 million.", "bitcoin"),
        ("Federal Reserve policy creates moral hazard in credit markets.", "fed_policy"),
        ("Energy production is the foundation of economic growth.", "energy"),
    ]):
        note = Note(
            note_id=f"note-{i+1}",
            body=body,
            topic=topic,
            tags=[topic],
            updated_at=datetime.now(timezone.utc),
        )
        session.add(note)
        notes.append(note)
    session.commit()
    return notes


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.complete_json = AsyncMock()
    return llm


@pytest.fixture
def mock_vector_store():
    """Mock VectorStore that returns note IDs from search."""
    vs = MagicMock()
    vs.search_notes.return_value = [
        {"id": "note-1", "document": "...", "metadata": {}, "distance": 0.1},
        {"id": "note-2", "document": "...", "metadata": {}, "distance": 0.2},
        {"id": "note-3", "document": "...", "metadata": {}, "distance": 0.3},
    ]
    vs.index_connection = MagicMock()
    return vs


def _make_llm_response(connections=None, signals=None):
    """Helper to build a standard LLM response dict."""
    return {
        "connections": connections or [],
        "unconnected_signals": signals or [],
    }


def _make_connection(note_id, relation="reinforces", strength=0.85):
    """Helper to build a valid connection dict."""
    return {
        "note_id": note_id,
        "relation": relation,
        "articulation": (
            "This content provides substantial new evidence supporting the thesis. "
            "The analysis maps directly to the core argument in the referenced note. "
            "The mechanism described here strengthens the analytical foundation."
        ),
        "excerpt": "The guest said something relevant here.",
        "excerpt_location": "12:34",
        "principles_invoked": ["sm_02"],
        "strength": strength,
    }


def _make_signal(topic="New topic"):
    """Helper to build a valid unconnected signal dict."""
    return {
        "topic_summary": topic,
        "why_it_matters": "This represents a genuinely new area of analysis.",
        "excerpt": "A relevant quote.",
    }


class TestBasicConnectionPass:
    @pytest.mark.asyncio
    async def test_basic_connection_pass(
        self, session, sample_item, sample_notes, mock_llm, mock_vector_store
    ):
        """Mock LLM returns 2 connections and 1 signal, verify rows created."""
        mock_llm.complete_json.return_value = _make_llm_response(
            connections=[
                _make_connection("note-1", "reinforces", 0.85),
                _make_connection("note-2", "extends", 0.75),
            ],
            signals=[_make_signal("CBDC timelines")],
        )

        with patch(
            "src.analysis.connection_pass.VectorStore",
            return_value=mock_vector_store,
        ):
            analyzer = ConnectionAnalyzer(mock_llm, session)
            result = await analyzer.analyze(sample_item.item_id)

        assert result["connections"] == 2
        assert result["signals"] == 1

        # Verify DB rows
        conns = session.query(Connection).filter_by(item_id=sample_item.item_id).all()
        assert len(conns) == 2
        assert {c.note_id for c in conns} == {"note-1", "note-2"}
        assert conns[0].relation in ("reinforces", "extends")
        assert len(conns[0].articulation) > 20

        signals = session.query(UnconnectedSignal).filter_by(item_id=sample_item.item_id).all()
        assert len(signals) == 1
        assert signals[0].topic_summary == "CBDC timelines"


class TestNoteIdValidation:
    @pytest.mark.asyncio
    async def test_validates_note_id_in_candidate_set(
        self, session, sample_item, sample_notes, mock_llm, mock_vector_store
    ):
        """Connection with note_id NOT in candidate set should be skipped."""
        mock_llm.complete_json.return_value = _make_llm_response(
            connections=[
                _make_connection("note-1", "reinforces", 0.9),
                _make_connection("FAKE-NOTE-ID", "extends", 0.8),
                _make_connection("note-2", "complicates", 0.7),
            ],
        )

        with patch(
            "src.analysis.connection_pass.VectorStore",
            return_value=mock_vector_store,
        ):
            analyzer = ConnectionAnalyzer(mock_llm, session)
            result = await analyzer.analyze(sample_item.item_id)

        assert result["connections"] == 2
        conns = session.query(Connection).filter_by(item_id=sample_item.item_id).all()
        note_ids = {c.note_id for c in conns}
        assert "FAKE-NOTE-ID" not in note_ids
        assert "note-1" in note_ids
        assert "note-2" in note_ids


class TestCaps:
    @pytest.mark.asyncio
    async def test_caps_at_max_connections(
        self, session, sample_item, sample_notes, mock_llm, mock_vector_store
    ):
        """12 connections returned, only 8 should be persisted."""
        connections = [
            _make_connection("note-1", "reinforces", 0.9 - i * 0.01)
            for i in range(12)
        ]
        mock_llm.complete_json.return_value = _make_llm_response(
            connections=connections
        )

        with patch(
            "src.analysis.connection_pass.VectorStore",
            return_value=mock_vector_store,
        ):
            analyzer = ConnectionAnalyzer(mock_llm, session)
            result = await analyzer.analyze(sample_item.item_id)

        assert result["connections"] == 8
        conns = session.query(Connection).filter_by(item_id=sample_item.item_id).all()
        assert len(conns) == 8

    @pytest.mark.asyncio
    async def test_caps_at_max_signals(
        self, session, sample_item, sample_notes, mock_llm, mock_vector_store
    ):
        """5 signals returned, only 3 should be persisted."""
        signals = [_make_signal(f"Topic {i}") for i in range(5)]
        mock_llm.complete_json.return_value = _make_llm_response(signals=signals)

        with patch(
            "src.analysis.connection_pass.VectorStore",
            return_value=mock_vector_store,
        ):
            analyzer = ConnectionAnalyzer(mock_llm, session)
            result = await analyzer.analyze(sample_item.item_id)

        assert result["signals"] == 3
        sigs = session.query(UnconnectedSignal).filter_by(item_id=sample_item.item_id).all()
        assert len(sigs) == 3


class TestStrengthClamping:
    @pytest.mark.asyncio
    async def test_clamps_strength(
        self, session, sample_item, sample_notes, mock_llm, mock_vector_store
    ):
        """Strength of 1.5 should be clamped to 1.0."""
        mock_llm.complete_json.return_value = _make_llm_response(
            connections=[_make_connection("note-1", "reinforces", 1.5)]
        )

        with patch(
            "src.analysis.connection_pass.VectorStore",
            return_value=mock_vector_store,
        ):
            analyzer = ConnectionAnalyzer(mock_llm, session)
            result = await analyzer.analyze(sample_item.item_id)

        assert result["connections"] == 1
        conn = session.query(Connection).filter_by(item_id=sample_item.item_id).first()
        assert conn.strength == 1.0


class TestStatusHandling:
    @pytest.mark.asyncio
    async def test_sets_complete_status(
        self, session, sample_item, sample_notes, mock_llm, mock_vector_store
    ):
        """Item should be marked COMPLETE after successful analysis."""
        mock_llm.complete_json.return_value = _make_llm_response(
            connections=[_make_connection("note-1")]
        )

        with patch(
            "src.analysis.connection_pass.VectorStore",
            return_value=mock_vector_store,
        ):
            analyzer = ConnectionAnalyzer(mock_llm, session)
            await analyzer.analyze(sample_item.item_id)

        session.refresh(sample_item)
        assert sample_item.analysis_status == AnalysisStatus.COMPLETE
        assert sample_item.analyzed_at is not None

    @pytest.mark.asyncio
    async def test_skips_already_complete(
        self, session, sample_item, sample_notes, mock_llm, mock_vector_store
    ):
        """Already-COMPLETE item should skip LLM call."""
        sample_item.analysis_status = AnalysisStatus.COMPLETE
        session.commit()

        with patch(
            "src.analysis.connection_pass.VectorStore",
            return_value=mock_vector_store,
        ):
            analyzer = ConnectionAnalyzer(mock_llm, session)
            result = await analyzer.analyze(sample_item.item_id)

        assert result["skipped"] is True
        mock_llm.complete_json.assert_not_called()


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_handles_llm_failure(
        self, session, sample_item, sample_notes, mock_llm, mock_vector_store
    ):
        """LLM exception should set ERROR status, not crash."""
        mock_llm.complete_json.side_effect = RuntimeError("LLM unavailable")

        with patch(
            "src.analysis.connection_pass.VectorStore",
            return_value=mock_vector_store,
        ):
            analyzer = ConnectionAnalyzer(mock_llm, session)
            result = await analyzer.analyze(sample_item.item_id)

        assert "error" in result
        session.refresh(sample_item)
        assert sample_item.analysis_status == AnalysisStatus.ERROR
        assert "LLM unavailable" in sample_item.analysis_error

    @pytest.mark.asyncio
    async def test_handles_malformed_json(
        self, session, sample_item, sample_notes, mock_llm, mock_vector_store
    ):
        """Malformed JSON from LLM should be handled gracefully."""
        mock_llm.complete_json.side_effect = json.JSONDecodeError(
            "Expecting value", "", 0
        )

        with patch(
            "src.analysis.connection_pass.VectorStore",
            return_value=mock_vector_store,
        ):
            analyzer = ConnectionAnalyzer(mock_llm, session)
            result = await analyzer.analyze(sample_item.item_id)

        assert "error" in result
        session.refresh(sample_item)
        assert sample_item.analysis_status == AnalysisStatus.ERROR


class TestChromaIndexing:
    @pytest.mark.asyncio
    async def test_indexes_connections_in_chroma(
        self, session, sample_item, sample_notes, mock_llm, mock_vector_store
    ):
        """Verify index_connection is called for each persisted connection."""
        mock_llm.complete_json.return_value = _make_llm_response(
            connections=[
                _make_connection("note-1", "reinforces", 0.9),
                _make_connection("note-2", "extends", 0.8),
            ]
        )

        with patch(
            "src.analysis.connection_pass.VectorStore",
            return_value=mock_vector_store,
        ):
            analyzer = ConnectionAnalyzer(mock_llm, session)
            await analyzer.analyze(sample_item.item_id)

        assert mock_vector_store.index_connection.call_count == 2
        # Verify metadata includes expected fields
        call_kwargs = mock_vector_store.index_connection.call_args_list[0]
        metadata = call_kwargs.kwargs.get("metadata") or call_kwargs[1].get("metadata")
        assert metadata["note_id"] in ("note-1", "note-2")
        assert "relation" in metadata
        assert "strength" in metadata
