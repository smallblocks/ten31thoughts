"""
Tests for the news-driven resurfacing trigger.
"""

import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from src.db.models import (
    Base, Feed, ContentItem, Note, Connection, ResurfacingEvent,
    ResurfacingTrigger, FeedCategory, AnalysisStatus, gen_id,
)
from src.resurfacing.news_driven import fire_news_driven


@pytest.fixture
def db_session(tmp_path):
    """In-memory SQLite session with schema created."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def mock_llm():
    """Mock LLMRouter that returns bridge text."""
    llm = AsyncMock()
    llm.complete = AsyncMock(return_value="Fed tightening data now echoes across two quarters of labor softening.")
    return llm


def _make_feed(session, category=FeedCategory.EXTERNAL_INTERVIEW):
    feed = Feed(
        feed_id=gen_id(),
        url=f"test-feed-{gen_id()[:8]}",
        category=category,
        display_name="Test Feed",
    )
    session.add(feed)
    session.commit()
    return feed


def _make_item(session, feed, status=AnalysisStatus.COMPLETE):
    item = ContentItem(
        item_id=gen_id(),
        feed_id=feed.feed_id,
        url=f"https://example.com/{gen_id()[:8]}",
        title="MacroVoices #500: Luke Gromen on Dollar Endgame",
        content_text="The Fed is trapped between inflation and fiscal dominance. " * 50,
        analysis_status=status,
        authors=["Luke Gromen"],
        published_date=datetime.now(timezone.utc),
    )
    session.add(item)
    session.commit()
    return item


def _make_note(session, *, note_id=None, archived=False):
    note = Note(
        note_id=note_id or gen_id(),
        body="Fed fiscal dominance thesis: treasury issuance outpaces demand.",
        topic="fed_policy",
        archived=archived,
    )
    session.add(note)
    session.commit()
    return note


def _make_connection(session, item_id, note_id):
    conn = Connection(
        connection_id=gen_id(),
        item_id=item_id,
        note_id=note_id,
        relation="reinforces",
        articulation="Test articulation.",
        strength=0.8,
    )
    session.add(conn)
    session.commit()
    return conn


def _make_event(session, note_id, trigger, hours_ago):
    event = ResurfacingEvent(
        event_id=gen_id(),
        note_id=note_id,
        trigger=trigger,
        surfaced_at=datetime.now(timezone.utc) - timedelta(hours=hours_ago),
    )
    session.add(event)
    session.commit()
    return event


def _mock_chroma_results(note_ids, distances):
    """Build a Chroma-style query result dict."""
    return {
        "ids": [note_ids],
        "distances": [distances],
        "metadatas": [[{"archived": False}] * len(note_ids)],
    }


def _run_async(coro):
    """Run an async function synchronously."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestFireNewsDriven:
    """Tests for fire_news_driven()."""

    @patch("src.resurfacing.news_driven.VectorStore")
    def test_one_match_no_connection_creates_event(self, MockVS, db_session, mock_llm):
        """Item with one semantic match, no existing Connection → one event."""
        feed = _make_feed(db_session)
        item = _make_item(db_session, feed)
        note = _make_note(db_session)

        mock_vs = MagicMock()
        mock_vs.notes.query.return_value = _mock_chroma_results([note.note_id], [0.3])
        MockVS.return_value = mock_vs

        count = _run_async(fire_news_driven(db_session, mock_llm, item.item_id))

        assert count == 1
        events = db_session.execute(
            select(ResurfacingEvent).where(ResurfacingEvent.note_id == note.note_id)
        ).scalars().all()
        assert len(events) == 1
        assert events[0].trigger == ResurfacingTrigger.NEWS_DRIVEN
        assert events[0].trigger_item_id == item.item_id
        assert events[0].bridge_text is not None
        assert events[0].similarity_score == pytest.approx(0.7, abs=0.01)

    @patch("src.resurfacing.news_driven.VectorStore")
    def test_match_with_existing_connection_no_event(self, MockVS, db_session, mock_llm):
        """Item with a semantic match that already has a Connection → no event."""
        feed = _make_feed(db_session)
        item = _make_item(db_session, feed)
        note = _make_note(db_session)
        _make_connection(db_session, item.item_id, note.note_id)

        mock_vs = MagicMock()
        mock_vs.notes.query.return_value = _mock_chroma_results([note.note_id], [0.3])
        MockVS.return_value = mock_vs

        count = _run_async(fire_news_driven(db_session, mock_llm, item.item_id))

        assert count == 0

    @patch("src.resurfacing.news_driven.VectorStore")
    def test_match_above_threshold_no_event(self, MockVS, db_session, mock_llm):
        """Match with distance > 0.45 → no event."""
        feed = _make_feed(db_session)
        item = _make_item(db_session, feed)
        note = _make_note(db_session)

        mock_vs = MagicMock()
        mock_vs.notes.query.return_value = _mock_chroma_results([note.note_id], [0.6])
        MockVS.return_value = mock_vs

        count = _run_async(fire_news_driven(db_session, mock_llm, item.item_id))

        assert count == 0

    @patch("src.resurfacing.news_driven.VectorStore")
    def test_archived_note_no_event(self, MockVS, db_session, mock_llm):
        """Archived note → no event."""
        feed = _make_feed(db_session)
        item = _make_item(db_session, feed)
        note = _make_note(db_session, archived=True)

        mock_vs = MagicMock()
        mock_vs.notes.query.return_value = _mock_chroma_results([note.note_id], [0.3])
        MockVS.return_value = mock_vs

        count = _run_async(fire_news_driven(db_session, mock_llm, item.item_id))

        assert count == 0

    @patch("src.resurfacing.news_driven.VectorStore")
    def test_recent_news_driven_cooldown(self, MockVS, db_session, mock_llm):
        """NEWS_DRIVEN event within 7 days → no event (cooldown)."""
        feed = _make_feed(db_session)
        item = _make_item(db_session, feed)
        note = _make_note(db_session)
        _make_event(db_session, note.note_id, ResurfacingTrigger.NEWS_DRIVEN, hours_ago=48)

        mock_vs = MagicMock()
        mock_vs.notes.query.return_value = _mock_chroma_results([note.note_id], [0.3])
        MockVS.return_value = mock_vs

        count = _run_async(fire_news_driven(db_session, mock_llm, item.item_id))

        assert count == 0

    @patch("src.resurfacing.news_driven.VectorStore")
    def test_five_matches_caps_at_three(self, MockVS, db_session, mock_llm):
        """5 valid matches → exactly 3 events (MAX_EVENTS_PER_ITEM cap)."""
        feed = _make_feed(db_session)
        item = _make_item(db_session, feed)
        notes = [_make_note(db_session) for _ in range(5)]

        note_ids = [n.note_id for n in notes]
        distances = [0.1, 0.15, 0.2, 0.25, 0.3]

        mock_vs = MagicMock()
        mock_vs.notes.query.return_value = _mock_chroma_results(note_ids, distances)
        MockVS.return_value = mock_vs

        count = _run_async(fire_news_driven(db_session, mock_llm, item.item_id))

        assert count == 3
        events = db_session.execute(
            select(ResurfacingEvent).where(
                ResurfacingEvent.trigger == ResurfacingTrigger.NEWS_DRIVEN
            )
        ).scalars().all()
        assert len(events) == 3

    @patch("src.resurfacing.news_driven.VectorStore")
    def test_llm_failure_returns_zero_no_partial(self, MockVS, db_session):
        """LLM raises → returns 0, no partial commits."""
        feed = _make_feed(db_session)
        item = _make_item(db_session, feed)
        note = _make_note(db_session)

        mock_vs = MagicMock()
        mock_vs.notes.query.return_value = _mock_chroma_results([note.note_id], [0.3])
        MockVS.return_value = mock_vs

        failing_llm = AsyncMock()
        failing_llm.complete = AsyncMock(side_effect=RuntimeError("LLM exploded"))

        count = _run_async(fire_news_driven(db_session, failing_llm, item.item_id))

        assert count == 0
        events = db_session.execute(
            select(ResurfacingEvent).where(
                ResurfacingEvent.trigger == ResurfacingTrigger.NEWS_DRIVEN
            )
        ).scalars().all()
        assert len(events) == 0

    @patch("src.resurfacing.news_driven.VectorStore")
    def test_item_not_complete_returns_zero(self, MockVS, db_session, mock_llm):
        """Item not COMPLETE → returns 0 immediately, no Chroma query."""
        feed = _make_feed(db_session)
        item = _make_item(db_session, feed, status=AnalysisStatus.PENDING)

        mock_vs = MagicMock()
        MockVS.return_value = mock_vs

        count = _run_async(fire_news_driven(db_session, mock_llm, item.item_id))

        assert count == 0
        mock_vs.notes.query.assert_not_called()
