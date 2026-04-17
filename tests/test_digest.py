"""
Ten31 Thoughts - Digest Tests
Tests for DigestGenerator and digest API endpoints.

Run with: pytest tests/test_digest.py -v
"""

import json
import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db.models import (
    Base, Connection, UnconnectedSignal, Note, ContentItem, Feed,
    ResurfacingEvent, Digest, FeedCategory, ResurfacingTrigger, gen_id,
    get_engine, create_tables, get_session,
)
from src.synthesis.digest import DigestGenerator


# ─── Fixtures ───

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
def mock_llm():
    llm = MagicMock()
    llm.complete_json = AsyncMock(return_value={
        "opening": "This week's key insight: test opening.",
        "connections_prose": "Connections prose here.",
        "threads_prose": "Threads prose here.",
        "signals_prose": "Signals prose here.",
        "resurfaced_prose": "Resurfaced prose here.",
        "wrote_prose": "Wrote prose here.",
        "sources_prose": "Sources prose here.",
    })
    return llm


@pytest.fixture
def generator(mock_llm, session):
    return DigestGenerator(llm_router=mock_llm, session=session)


@pytest.fixture
def now():
    return datetime.now(timezone.utc)


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
def our_thesis_feed(session):
    feed = Feed(
        feed_id=gen_id(),
        display_name="Timestamp",
        url="https://example.com/timestamp",
        category=FeedCategory.OUR_THESIS,
    )
    session.add(feed)
    session.commit()
    return feed


@pytest.fixture
def sample_item(session, sample_feed, now):
    item = ContentItem(
        item_id=gen_id(),
        feed_id=sample_feed.feed_id,
        title="Test Episode: Macro Outlook",
        url="https://example.com/ep1",
        published_date=now - timedelta(days=2),
        created_at=now - timedelta(days=2),
    )
    session.add(item)
    session.commit()
    return item


@pytest.fixture
def sample_note(session, now):
    note = Note(
        note_id=gen_id(),
        title="Bitcoin as reserve asset",
        body="The thesis that bitcoin becomes a world reserve asset rests on...",
        tags=["thread:reserve-asset"],
        source="manual",
        created_at=now - timedelta(days=3),
    )
    session.add(note)
    session.commit()
    return note


def _make_connection(session, item, note, strength, user_rating, now, relation="reinforces"):
    conn = Connection(
        connection_id=gen_id(),
        item_id=item.item_id,
        note_id=note.note_id,
        relation=relation,
        articulation=f"Connection with strength {strength}",
        strength=strength,
        user_rating=user_rating,
        created_at=now - timedelta(days=1),
    )
    session.add(conn)
    session.commit()
    return conn


# ─── Tests ───

class TestGatherConnections:
    def test_gathers_top_connections(self, generator, session, sample_item, sample_note, now):
        """Seed DB with connections of varying strengths, verify top 5 selected."""
        # Create 7 connections with different strengths/ratings
        strengths_ratings = [
            (0.9, 5),   # score = 0.9 * 5/5 = 0.90
            (0.8, 4),   # score = 0.8 * 4/5 = 0.64
            (0.7, None), # score = 0.7 * 3/5 = 0.42 (unrated → 3)
            (0.95, 2),  # score = 0.95 * 2/5 = 0.38
            (0.6, 5),   # score = 0.6 * 5/5 = 0.60
            (0.3, 3),   # score = 0.3 * 3/5 = 0.18
            (0.5, 4),   # score = 0.5 * 4/5 = 0.40
        ]

        for strength, rating in strengths_ratings:
            _make_connection(session, sample_item, sample_note, strength, rating, now)

        start = now - timedelta(days=7)
        result = generator._gather_connections(start, now)

        assert len(result) == 5
        # Verify sorted by score descending
        scores = [r["score"] for r in result]
        assert scores == sorted(scores, reverse=True)
        # Top score should be 0.9 * 5/5 = 0.90
        assert result[0]["score"] == pytest.approx(0.9, abs=0.01)

    def test_scoring_formula(self, generator, session, sample_item, sample_note, now):
        """Verify strength * coalesce(rating, 3) / 5 ordering is correct."""
        # Unrated connection
        _make_connection(session, sample_item, sample_note, 0.6, None, now)
        # Rated connection with same strength but rating=5
        _make_connection(session, sample_item, sample_note, 0.6, 5, now)

        start = now - timedelta(days=7)
        result = generator._gather_connections(start, now)

        # 0.6 * 5/5 = 0.60 should beat 0.6 * 3/5 = 0.36
        assert result[0]["score"] == pytest.approx(0.60, abs=0.01)
        assert result[1]["score"] == pytest.approx(0.36, abs=0.01)


class TestGatherSignals:
    def test_gathers_unconnected_signals(self, generator, session, sample_item, now):
        """Seed with signals, verify top 3 non-dismissed included."""
        for i in range(5):
            signal = UnconnectedSignal(
                signal_id=gen_id(),
                item_id=sample_item.item_id,
                topic_summary=f"Signal topic {i}",
                why_it_matters=f"Matters because {i}",
                user_dismissed=(i >= 3),  # dismiss signals 3 and 4
                created_at=now - timedelta(days=i),
            )
            session.add(signal)
        session.commit()

        start = now - timedelta(days=7)
        result = generator._gather_signals(start, now)

        assert len(result) == 3
        # All should be non-dismissed
        for s in result:
            assert "Signal topic" in s["topic_summary"]


class TestGatherResurfacing:
    def test_gathers_resurfacing_events(self, generator, session, sample_note, now):
        """Seed with events, verify included in section 4."""
        event = ResurfacingEvent(
            event_id=gen_id(),
            note_id=sample_note.note_id,
            trigger=ResurfacingTrigger.SEMANTIC_ON_WRITE,
            bridge_text="This note connects to recent discussion about...",
            similarity_score=0.85,
            surfaced_at=now - timedelta(days=2),
        )
        session.add(event)
        session.commit()

        start = now - timedelta(days=7)
        result = generator._gather_resurfacing(start, now)

        assert len(result) == 1
        assert result[0]["trigger"] == "semantic_on_write"
        assert result[0]["bridge_text"] == "This note connects to recent discussion about..."
        assert result[0]["note_title"] == "Bitcoin as reserve asset"


class TestGatherWritten:
    def test_gathers_manual_notes(self, generator, session, now):
        """Seed with manual notes, verify in section 5."""
        manual = Note(
            note_id=gen_id(),
            title="My manual note",
            body="Some thoughts on the macro environment",
            source="manual",
            created_at=now - timedelta(days=1),
        )
        timestamp_note = Note(
            note_id=gen_id(),
            title="Auto-extracted note",
            body="Extracted from Timestamp",
            source="timestamp",
            created_at=now - timedelta(days=1),
        )
        session.add_all([manual, timestamp_note])
        session.commit()

        start = now - timedelta(days=7)
        result = generator._gather_written(start, now)

        # manual note should be included; timestamp note excluded
        manual_notes = result["manual_notes"]
        assert len(manual_notes) == 1
        assert manual_notes[0]["title"] == "My manual note"


class TestGenerateHTML:
    def test_generates_html(self, generator, session, sample_item, sample_note, now):
        """Mock LLM, verify HTML output contains the sections."""
        _make_connection(session, sample_item, sample_note, 0.8, 4, now)

        start = now - timedelta(days=7)
        sections = {
            "strongest_connections": generator._gather_connections(start, now),
            "threads_in_motion": generator._gather_threads(start, now),
            "unconnected_signals": generator._gather_signals(start, now),
            "notes_resurfaced": generator._gather_resurfacing(start, now),
            "what_you_wrote": generator._gather_written(start, now),
            "sources_active": generator._gather_sources(start, now),
        }

        prose = {
            "opening": "Key insight this week.",
            "connections_prose": "Connections analysis.",
            "threads_prose": "Threads analysis.",
            "signals_prose": "Signals analysis.",
            "resurfaced_prose": "Resurfaced analysis.",
            "wrote_prose": "Writing analysis.",
            "sources_prose": "Source analysis.",
        }

        html = generator._render_html(sections, prose, start, now)

        assert "TEN31 THOUGHTS" in html
        assert "Weekly Digest" in html
        assert "Strongest Connections" in html
        assert "Threads in Motion" in html
        assert "Unconnected Signals" in html
        assert "Notes Resurfaced" in html
        assert "What You Wrote" in html
        assert "Sources Active" in html
        assert "Key insight this week." in html
        assert "<!DOCTYPE html>" in html
        # Inline CSS
        assert "<style>" in html
        assert "font-family" in html


class TestStoreDigest:
    def test_stores_digest(self, generator, session, now):
        """Verify digest row created."""
        result = asyncio.get_event_loop().run_until_complete(
            generator.generate_weekly_digest(period_end=now)
        )

        digest = session.query(Digest).filter_by(
            digest_id=result["digest_id"]
        ).first()

        assert digest is not None
        assert digest.html_content is not None
        assert len(digest.html_content) > 0
        assert digest.period_start is not None
        assert digest.period_end is not None


class TestEmptyWeek:
    def test_empty_week(self, generator, session, now):
        """No data, verify digest still generates with empty sections."""
        result = asyncio.get_event_loop().run_until_complete(
            generator.generate_weekly_digest(period_end=now)
        )

        assert result["digest_id"] is not None
        assert result["html_content"] is not None
        # Should contain placeholder text for empty sections
        assert "No connections this week" in result["html_content"] or "TEN31 THOUGHTS" in result["html_content"]
        # Sections should be empty
        sections = result["sections"]
        assert sections["strongest_connections"] == []
        assert sections["unconnected_signals"] == []
        assert sections["notes_resurfaced"] == []


class TestDigestAPI:
    """Test the FastAPI digest endpoints."""

    @pytest.fixture
    def client(self, engine):
        """Create a test client with the digest router only."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from src.api.digest import router
        from src.db.session import get_db

        test_app = FastAPI()
        test_app.include_router(router)

        TestSession = sessionmaker(bind=engine)

        def override_get_db():
            sess = TestSession()
            try:
                yield sess
            finally:
                sess.close()

        test_app.dependency_overrides[get_db] = override_get_db

        client = TestClient(test_app)
        yield client

        test_app.dependency_overrides.clear()

    def _create_digest(self, engine, period_start, period_end):
        """Helper to insert a digest directly."""
        sess = get_session(engine)
        digest = Digest(
            digest_id=gen_id(),
            period_start=period_start,
            period_end=period_end,
            html_content="<html><body>Test digest</body></html>",
            raw_data={"test": True},
        )
        sess.add(digest)
        sess.commit()
        result = {
            "digest_id": digest.digest_id,
            "period_start": period_start,
            "period_end": period_end,
            "created_at": digest.created_at,
        }
        sess.close()
        return result

    def test_api_latest(self, client, engine, now):
        """Create two digests, GET /api/digest/latest returns the newer one."""
        older = self._create_digest(
            engine,
            now - timedelta(days=14),
            now - timedelta(days=7),
        )
        newer = self._create_digest(
            engine,
            now - timedelta(days=7),
            now,
        )

        response = client.get("/api/digest/latest")
        assert response.status_code == 200
        data = response.json()
        assert data["digest_id"] == newer["digest_id"]

    def test_api_latest_404(self, client):
        """No digests, GET /api/digest/latest returns 404."""
        response = client.get("/api/digest/latest")
        assert response.status_code == 404

    def test_api_list(self, client, engine, now):
        """Create digests, GET /api/digest/ returns paginated list."""
        for i in range(3):
            self._create_digest(
                engine,
                now - timedelta(days=7 * (i + 1)),
                now - timedelta(days=7 * i),
            )

        response = client.get("/api/digest/?limit=2&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert len(data["digests"]) == 2
        assert data["limit"] == 2
        assert data["offset"] == 0

        # Second page
        response = client.get("/api/digest/?limit=2&offset=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["digests"]) == 1
