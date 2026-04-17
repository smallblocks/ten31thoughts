"""
Tests for the Timestamp Note Extractor.
All LLM calls are mocked.
"""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db.models import (
    Base, Feed, FeedCategory, FeedStatus, ContentItem,
    Note, AnalysisStatus, gen_id,
)
from src.analysis.note_extractor import NoteExtractor


@pytest.fixture
def engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def session(engine):
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def our_thesis_feed(session):
    feed = Feed(
        feed_id="feed-ts",
        url="https://example.com/timestamp.xml",
        category=FeedCategory.OUR_THESIS,
        display_name="Timestamp",
        status=FeedStatus.ACTIVE,
    )
    session.add(feed)
    session.commit()
    return feed


@pytest.fixture
def external_feed(session):
    feed = Feed(
        feed_id="feed-ext",
        url="https://example.com/external.xml",
        category=FeedCategory.EXTERNAL_INTERVIEW,
        display_name="External",
        status=FeedStatus.ACTIVE,
    )
    session.add(feed)
    session.commit()
    return feed


@pytest.fixture
def sample_item(session, our_thesis_feed):
    item = ContentItem(
        item_id="item-001",
        feed_id=our_thesis_feed.feed_id,
        url="https://example.com/timestamp-42",
        title="Timestamp #42: The Sats Flow",
        published_date=datetime(2025, 4, 10, tzinfo=timezone.utc),
        content_text="Bitcoin adoption is accelerating across nation-states. " * 50,
        analysis_status=AnalysisStatus.PENDING,
    )
    session.add(item)
    session.commit()
    return item


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.complete_json = AsyncMock()
    return llm


def _make_llm_response(notes):
    """Helper to build a mock LLM JSON response."""
    return {"notes": notes}


THREE_NOTES = [
    {
        "body": "Bitcoin adoption is accelerating across nation-states as they seek monetary sovereignty.",
        "title": "Nation-state adoption",
        "topic": "bitcoin",
        "tags": ["adoption", "nation-states"],
        "thread_id": None,
    },
    {
        "body": "The Fed is cornered — they can't raise rates without blowing up the Treasury market.",
        "title": "Fed policy trap",
        "topic": "fed_policy",
        "tags": ["fed", "rates", "treasury"],
        "thread_id": None,
    },
    {
        "body": "Energy companies are starting to integrate bitcoin mining into their operations.",
        "title": "Energy-bitcoin convergence",
        "topic": "energy",
        "tags": ["energy", "mining"],
        "thread_id": None,
    },
]


class TestBasicExtraction:
    def test_basic_extraction(self, session, sample_item, mock_llm):
        """Mock LLM returns 3 notes, verify Note rows created with source='timestamp'."""
        mock_llm.complete_json.return_value = _make_llm_response(THREE_NOTES)
        extractor = NoteExtractor(mock_llm, session)

        notes = asyncio.get_event_loop().run_until_complete(
            extractor.extract(sample_item.item_id)
        )

        assert len(notes) == 3
        for note in notes:
            assert note.source == "timestamp"
            assert note.body
            assert note.topic in ("bitcoin", "fed_policy", "energy")

    def test_source_item_id_set(self, session, sample_item, mock_llm):
        """Verify each Note's source_item_id points to the ContentItem."""
        mock_llm.complete_json.return_value = _make_llm_response(THREE_NOTES)
        extractor = NoteExtractor(mock_llm, session)

        notes = asyncio.get_event_loop().run_until_complete(
            extractor.extract(sample_item.item_id)
        )

        for note in notes:
            assert note.source_item_id == sample_item.item_id


class TestThreadAssignment:
    def test_thread_assignment_existing(self, session, sample_item, our_thesis_feed, mock_llm):
        """Mock LLM assigns an existing thread_id, verify it's preserved."""
        # Create an existing note with a thread tag
        existing_note = Note(
            note_id=gen_id(),
            body="Previous note about energy thesis.",
            topic="energy",
            tags=["thread:energy-thesis-abc"],
            source="timestamp",
            source_item_id=sample_item.item_id,
            updated_at=datetime.now(timezone.utc),
        )
        session.add(existing_note)
        session.commit()

        notes_data = [
            {
                "body": "Energy mining thesis continues to play out.",
                "title": "Energy update",
                "topic": "energy",
                "tags": ["energy"],
                "thread_id": "energy-thesis-abc",
            }
        ]
        mock_llm.complete_json.return_value = _make_llm_response(notes_data)

        # Need a fresh item (the original is now COMPLETE from this test's perspective)
        item2 = ContentItem(
            item_id="item-thread-test",
            feed_id=our_thesis_feed.feed_id,
            url="https://example.com/timestamp-43",
            title="Timestamp #43",
            published_date=datetime(2025, 4, 17, tzinfo=timezone.utc),
            content_text="Energy and bitcoin mining " * 50,
            analysis_status=AnalysisStatus.PENDING,
        )
        session.add(item2)
        session.commit()

        extractor = NoteExtractor(mock_llm, session)
        notes = asyncio.get_event_loop().run_until_complete(
            extractor.extract(item2.item_id)
        )

        assert len(notes) == 1
        assert any("thread:energy-thesis-abc" in (t or "") for t in notes[0].tags)

    def test_thread_assignment_new(self, session, sample_item, mock_llm):
        """Mock LLM returns thread_id: 'new:energy-thesis', verify a new thread_id is generated."""
        notes_data = [
            {
                "body": "A new energy thesis thread starting here.",
                "title": "New energy thread",
                "topic": "energy",
                "tags": ["energy"],
                "thread_id": "new:energy-thesis",
            }
        ]
        mock_llm.complete_json.return_value = _make_llm_response(notes_data)
        extractor = NoteExtractor(mock_llm, session)

        notes = asyncio.get_event_loop().run_until_complete(
            extractor.extract(sample_item.item_id)
        )

        assert len(notes) == 1
        thread_tags = [t for t in notes[0].tags if t.startswith("thread:")]
        assert len(thread_tags) == 1
        # Should be a generated ID, not the raw "new:energy-thesis"
        assert "new:" not in thread_tags[0]
        assert "energy-thesis" in thread_tags[0]


class TestTopicValidation:
    def test_invalid_topic_handled(self, session, sample_item, mock_llm):
        """Mock LLM returns a topic not in vocabulary, verify it's set to None."""
        notes_data = [
            {
                "body": "Some note about an unknown topic.",
                "title": "Unknown topic",
                "topic": "martian_economics",
                "tags": ["weird"],
                "thread_id": None,
            }
        ]
        mock_llm.complete_json.return_value = _make_llm_response(notes_data)
        extractor = NoteExtractor(mock_llm, session)

        notes = asyncio.get_event_loop().run_until_complete(
            extractor.extract(sample_item.item_id)
        )

        assert len(notes) == 1
        assert notes[0].topic is None


class TestStatusHandling:
    def test_sets_complete_status(self, session, sample_item, mock_llm):
        """Verify item status set to COMPLETE after extraction."""
        mock_llm.complete_json.return_value = _make_llm_response(THREE_NOTES)
        extractor = NoteExtractor(mock_llm, session)

        asyncio.get_event_loop().run_until_complete(
            extractor.extract(sample_item.item_id)
        )

        session.refresh(sample_item)
        assert sample_item.analysis_status == AnalysisStatus.COMPLETE
        assert sample_item.analyzed_at is not None

    def test_handles_llm_failure(self, session, sample_item, mock_llm):
        """Mock LLM raises, verify error status, no crash."""
        mock_llm.complete_json.side_effect = RuntimeError("LLM provider down")
        extractor = NoteExtractor(mock_llm, session)

        notes = asyncio.get_event_loop().run_until_complete(
            extractor.extract(sample_item.item_id)
        )

        assert notes == []
        session.refresh(sample_item)
        assert sample_item.analysis_status == AnalysisStatus.ERROR
        assert "LLM" in (sample_item.analysis_error or "")


class TestSkipConditions:
    def test_skips_non_our_thesis(self, session, external_feed, mock_llm):
        """Pass an EXTERNAL_INTERVIEW item, verify no LLM call."""
        item = ContentItem(
            item_id="item-ext",
            feed_id=external_feed.feed_id,
            url="https://example.com/interview",
            title="External Interview",
            content_text="Some interview content " * 50,
            analysis_status=AnalysisStatus.PENDING,
        )
        session.add(item)
        session.commit()

        extractor = NoteExtractor(mock_llm, session)
        notes = asyncio.get_event_loop().run_until_complete(
            extractor.extract(item.item_id)
        )

        assert notes == []
        mock_llm.complete_json.assert_not_called()

    def test_skips_already_complete(self, session, our_thesis_feed, mock_llm):
        """Pass COMPLETE item, verify no LLM call."""
        item = ContentItem(
            item_id="item-done",
            feed_id=our_thesis_feed.feed_id,
            url="https://example.com/done",
            title="Already Done",
            content_text="Already analyzed content " * 50,
            analysis_status=AnalysisStatus.COMPLETE,
        )
        session.add(item)
        session.commit()

        extractor = NoteExtractor(mock_llm, session)
        notes = asyncio.get_event_loop().run_until_complete(
            extractor.extract(item.item_id)
        )

        assert notes == []
        mock_llm.complete_json.assert_not_called()


class TestVectorIndexing:
    @patch("src.analysis.note_extractor.NoteExtractor._index_notes")
    def test_indexes_notes_in_chroma(self, mock_index, session, sample_item, mock_llm):
        """Verify _index_notes called with created notes (mock VectorStore)."""
        mock_llm.complete_json.return_value = _make_llm_response(THREE_NOTES)
        extractor = NoteExtractor(mock_llm, session)

        notes = asyncio.get_event_loop().run_until_complete(
            extractor.extract(sample_item.item_id)
        )

        mock_index.assert_called_once()
        indexed_notes = mock_index.call_args[0][0]
        assert len(indexed_notes) == 3
        for note in indexed_notes:
            assert note.note_id
            assert note.body
