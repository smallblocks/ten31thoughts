"""
Ten31 Thoughts - Connections & Signals API Tests
Tests for /api/connections and /api/signals endpoints.

Run with: pytest tests/test_connections_api.py -v
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from src.db.models import (
    Base, Connection, UnconnectedSignal, Note, ContentItem, Feed,
    FeedCategory, ConnectionRelation, gen_id, get_engine, create_tables,
)
from src.db.session import get_db
import src.db.session as session_module


@pytest.fixture
def db_setup(tmp_path, monkeypatch):
    """Create a temporary database, monkeypatch the session module, and yield a session."""
    monkeypatch.setenv("CHROMADB_PERSIST_DIR", str(tmp_path / "chromadb"))
    monkeypatch.setenv("CHROMADB_HOST", "127.0.0.1")
    monkeypatch.setenv("CHROMADB_PORT", "1")

    db_path = tmp_path / "test.db"
    engine = get_engine(f"sqlite:///{db_path}")
    create_tables(engine)

    # Monkeypatch the session module so lifespan's init_db() uses our test engine
    monkeypatch.setattr(session_module, "engine", engine)
    monkeypatch.setattr(session_module, "SessionLocal", sessionmaker(bind=engine))
    monkeypatch.setattr(session_module, "init_db", lambda: None)  # tables already created

    sess = sessionmaker(bind=engine)()
    yield sess
    sess.close()


@pytest.fixture
def client(db_setup):
    """Test client with overridden DB dependency."""
    from src.app import app

    def override_get_db():
        try:
            yield db_setup
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def sample_feed(db_setup):
    feed = Feed(
        feed_id=gen_id(),
        display_name="Test Feed",
        url="https://example.com/feed",
        category=FeedCategory.EXTERNAL_INTERVIEW,
    )
    db_setup.add(feed)
    db_setup.commit()
    return feed


@pytest.fixture
def sample_item(db_setup, sample_feed):
    item = ContentItem(
        item_id=gen_id(),
        feed_id=sample_feed.feed_id,
        title="Test Episode",
        url="https://example.com/ep1",
    )
    db_setup.add(item)
    db_setup.commit()
    return item


@pytest.fixture
def sample_note(db_setup):
    note = Note(
        note_id=gen_id(),
        title="Sound Money",
        body="Bitcoin is sound money because fixed supply.",
    )
    db_setup.add(note)
    db_setup.commit()
    return note


@pytest.fixture
def sample_connection(db_setup, sample_item, sample_note):
    conn = Connection(
        connection_id=gen_id(),
        item_id=sample_item.item_id,
        note_id=sample_note.note_id,
        relation=ConnectionRelation.REINFORCES.value,
        articulation="This episode reinforces the sound money thesis.",
        strength=0.85,
    )
    db_setup.add(conn)
    db_setup.commit()
    return conn


@pytest.fixture
def sample_signal(db_setup, sample_item):
    signal = UnconnectedSignal(
        signal_id=gen_id(),
        item_id=sample_item.item_id,
        topic_summary="CBDC timeline accelerating",
        why_it_matters="Could change the competitive landscape for bitcoin.",
    )
    db_setup.add(signal)
    db_setup.commit()
    return signal


# ─── Connection Tests ───

class TestListConnections:
    def test_empty_list(self, client):
        resp = client.get("/api/connections/")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_connection(self, client, sample_connection):
        resp = client.get("/api/connections/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["connection_id"] == sample_connection.connection_id
        assert data[0]["item_title"] == "Test Episode"
        assert data[0]["note_body"] == "Bitcoin is sound money because fixed supply."

    def test_filter_by_note_id(self, client, sample_connection, sample_note):
        resp = client.get(f"/api/connections/?note_id={sample_note.note_id}")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

        resp2 = client.get("/api/connections/?note_id=nonexistent")
        assert resp2.status_code == 200
        assert len(resp2.json()) == 0

    def test_filter_by_relation(self, client, sample_connection):
        resp = client.get("/api/connections/?relation=reinforces")
        assert len(resp.json()) == 1

        resp2 = client.get("/api/connections/?relation=contradicts")
        assert len(resp2.json()) == 0

    def test_filter_unrated(self, client, sample_connection, db_setup):
        resp = client.get("/api/connections/?unrated=true")
        assert len(resp.json()) == 1

        sample_connection.user_rating = 4
        db_setup.commit()

        resp2 = client.get("/api/connections/?unrated=true")
        assert len(resp2.json()) == 0

    def test_filter_min_strength(self, client, sample_connection):
        resp = client.get("/api/connections/?min_strength=0.8")
        assert len(resp.json()) == 1

        resp2 = client.get("/api/connections/?min_strength=0.9")
        assert len(resp2.json()) == 0

    def test_excludes_dismissed_by_default(self, client, sample_connection, db_setup):
        sample_connection.user_dismissed = True
        db_setup.commit()

        resp = client.get("/api/connections/")
        assert len(resp.json()) == 0

        resp2 = client.get("/api/connections/?dismissed=true")
        assert len(resp2.json()) == 1

    def test_pagination(self, client, db_setup, sample_item, sample_note):
        for i in range(5):
            conn = Connection(
                connection_id=gen_id(),
                item_id=sample_item.item_id,
                note_id=sample_note.note_id,
                relation="reinforces",
                articulation=f"Connection {i}",
                strength=0.5 + i * 0.1,
            )
            db_setup.add(conn)
        db_setup.commit()

        resp = client.get("/api/connections/?limit=2&offset=0")
        assert len(resp.json()) == 2

        resp2 = client.get("/api/connections/?limit=2&offset=3")
        assert len(resp2.json()) == 2

        resp3 = client.get("/api/connections/?limit=10&offset=0")
        assert len(resp3.json()) == 5


class TestGetConnection:
    def test_existing(self, client, sample_connection):
        resp = client.get(f"/api/connections/{sample_connection.connection_id}")
        assert resp.status_code == 200
        assert resp.json()["connection_id"] == sample_connection.connection_id

    def test_missing(self, client):
        resp = client.get("/api/connections/nonexistent")
        assert resp.status_code == 404


class TestRateConnection:
    def test_rate_valid(self, client, sample_connection):
        resp = client.patch(
            f"/api/connections/{sample_connection.connection_id}/rating",
            json={"rating": 4},
        )
        assert resp.status_code == 200
        assert resp.json()["user_rating"] == 4

    def test_rate_boundary_values(self, client, sample_connection):
        resp1 = client.patch(
            f"/api/connections/{sample_connection.connection_id}/rating",
            json={"rating": 1},
        )
        assert resp1.status_code == 200
        assert resp1.json()["user_rating"] == 1

        resp5 = client.patch(
            f"/api/connections/{sample_connection.connection_id}/rating",
            json={"rating": 5},
        )
        assert resp5.status_code == 200
        assert resp5.json()["user_rating"] == 5

    def test_rate_invalid_zero(self, client, sample_connection):
        resp = client.patch(
            f"/api/connections/{sample_connection.connection_id}/rating",
            json={"rating": 0},
        )
        assert resp.status_code == 422

    def test_rate_invalid_six(self, client, sample_connection):
        resp = client.patch(
            f"/api/connections/{sample_connection.connection_id}/rating",
            json={"rating": 6},
        )
        assert resp.status_code == 422

    def test_rate_missing_connection(self, client):
        resp = client.patch(
            "/api/connections/nonexistent/rating",
            json={"rating": 3},
        )
        assert resp.status_code == 404


class TestPromoteConnection:
    def test_promote_creates_note(self, client, sample_connection, db_setup):
        resp = client.post(
            f"/api/connections/{sample_connection.connection_id}/promote"
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["body"] == sample_connection.articulation
        assert data["source"] == "promoted_from_connection"
        assert data["source_item_id"] == sample_connection.item_id
        assert data["source_url"] == "https://example.com/ep1"

        db_setup.refresh(sample_connection)
        assert sample_connection.user_promoted_to_note is True

    def test_promote_missing_connection(self, client):
        resp = client.post("/api/connections/nonexistent/promote")
        assert resp.status_code == 404


class TestDismissConnection:
    def test_dismiss(self, client, sample_connection, db_setup):
        resp = client.delete(
            f"/api/connections/{sample_connection.connection_id}"
        )
        assert resp.status_code == 204

        db_setup.refresh(sample_connection)
        assert sample_connection.user_dismissed is True

    def test_dismiss_idempotent(self, client, sample_connection, db_setup):
        client.delete(f"/api/connections/{sample_connection.connection_id}")
        resp = client.delete(f"/api/connections/{sample_connection.connection_id}")
        assert resp.status_code == 204

    def test_dismiss_missing(self, client):
        resp = client.delete("/api/connections/nonexistent")
        assert resp.status_code == 404


# ─── Signal Tests ───

class TestListSignals:
    def test_empty_list(self, client):
        resp = client.get("/api/signals/")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_returns_signal(self, client, sample_signal):
        resp = client.get("/api/signals/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["signal_id"] == sample_signal.signal_id
        assert data[0]["item_title"] == "Test Episode"

    def test_excludes_dismissed_by_default(self, client, sample_signal, db_setup):
        sample_signal.user_dismissed = True
        db_setup.commit()

        resp = client.get("/api/signals/")
        assert len(resp.json()) == 0

        resp2 = client.get("/api/signals/?dismissed=true")
        assert len(resp2.json()) == 1


class TestDismissSignal:
    def test_dismiss(self, client, sample_signal, db_setup):
        resp = client.patch(
            f"/api/signals/{sample_signal.signal_id}/dismiss"
        )
        assert resp.status_code == 204

        db_setup.refresh(sample_signal)
        assert sample_signal.user_dismissed is True

    def test_dismiss_idempotent(self, client, sample_signal):
        client.patch(f"/api/signals/{sample_signal.signal_id}/dismiss")
        resp = client.patch(f"/api/signals/{sample_signal.signal_id}/dismiss")
        assert resp.status_code == 204

    def test_dismiss_missing(self, client):
        resp = client.patch("/api/signals/nonexistent/dismiss")
        assert resp.status_code == 404


class TestPromoteSignal:
    def test_promote_creates_note(self, client, sample_signal, db_setup):
        resp = client.post(
            f"/api/signals/{sample_signal.signal_id}/promote"
        )
        assert resp.status_code == 201
        data = resp.json()
        expected_body = "CBDC timeline accelerating\n\nCould change the competitive landscape for bitcoin."
        assert data["body"] == expected_body
        assert data["source"] == "promoted_from_signal"
        assert data["source_item_id"] == sample_signal.item_id

        db_setup.refresh(sample_signal)
        assert sample_signal.user_promoted_to_note is True

    def test_promote_missing_signal(self, client):
        resp = client.post("/api/signals/nonexistent/promote")
        assert resp.status_code == 404
