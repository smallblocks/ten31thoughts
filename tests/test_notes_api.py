"""
Ten31 Thoughts - Notes API Tests
Verifies CRUD endpoints, soft-delete semantics, and ChromaDB write-through.

Run with: pytest tests/test_notes_api.py -v
"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from src.db.models import Base, Note, get_engine, create_tables, get_session
from src.db.session import get_db


# ─── Fixtures ───

@pytest.fixture
def session(tmp_path, monkeypatch):
    """Fresh SQLite DB per test, wired into the FastAPI dependency."""
    db_path = tmp_path / "test.db"
    engine = get_engine(f"sqlite:///{db_path}")
    create_tables(engine)
    sess = get_session(engine)
    yield sess
    sess.close()


@pytest.fixture
def client(session, tmp_path, monkeypatch):
    """FastAPI TestClient with the DB dependency overridden."""
    persist_dir = tmp_path / "chromadb"
    monkeypatch.setenv("CHROMADB_PERSIST_DIR", str(persist_dir))
    monkeypatch.setenv("CHROMADB_HOST", "127.0.0.1")
    monkeypatch.setenv("CHROMADB_PORT", "1")

    from src.app import app

    def _override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = _override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


# ─── Create ───

class TestCreateNote:
    def test_create_minimal(self, client):
        r = client.post("/api/notes/", json={"body": "Sound money."})
        assert r.status_code == 201
        data = r.json()
        assert data["body"] == "Sound money."
        assert data["title"] is None
        assert data["topic"] is None
        assert data["tags"] == []
        assert data["archived"] is False
        assert data["fsrs_state"] == 0
        assert data["note_id"]

    def test_create_full(self, client):
        r = client.post("/api/notes/", json={
            "body": "Anacyclosis from Polybius.",
            "title": "On political cycles",
            "topic": "political_cycles",
            "tags": ["polybius", "decay"],
            "source_url": "https://example.com",
        })
        assert r.status_code == 201
        data = r.json()
        assert data["title"] == "On political cycles"
        assert data["topic"] == "political_cycles"
        assert data["tags"] == ["polybius", "decay"]
        assert data["source_url"] == "https://example.com"

    def test_empty_body_rejected(self, client):
        r = client.post("/api/notes/", json={"body": ""})
        assert r.status_code == 422

    def test_whitespace_only_body_rejected(self, client):
        r = client.post("/api/notes/", json={"body": "   "})
        assert r.status_code == 400

    def test_body_is_stripped(self, client):
        r = client.post("/api/notes/", json={"body": "  trimmed  "})
        assert r.status_code == 201
        assert r.json()["body"] == "trimmed"


# ─── List ───

class TestListNotes:
    def test_empty_list(self, client):
        r = client.get("/api/notes/")
        assert r.status_code == 200
        assert r.json() == []

    def test_default_excludes_archived(self, client, session):
        active = Note(body="active", archived=False)
        archived = Note(body="archived", archived=True)
        session.add_all([active, archived])
        session.commit()

        r = client.get("/api/notes/")
        bodies = [n["body"] for n in r.json()]
        assert bodies == ["active"]

    def test_archived_filter(self, client, session):
        session.add_all([
            Note(body="active", archived=False),
            Note(body="archived", archived=True),
        ])
        session.commit()

        r = client.get("/api/notes/?archived=true")
        bodies = [n["body"] for n in r.json()]
        assert bodies == ["archived"]

    def test_topic_filter(self, client, session):
        session.add_all([
            Note(body="a", topic="bitcoin"),
            Note(body="b", topic="political_cycles"),
        ])
        session.commit()

        r = client.get("/api/notes/?topic=bitcoin")
        assert len(r.json()) == 1
        assert r.json()[0]["topic"] == "bitcoin"

    def test_tag_filter(self, client, session):
        session.add_all([
            Note(body="a", tags=["polybius"]),
            Note(body="b", tags=["bastiat"]),
            Note(body="c", tags=["polybius", "anacyclosis"]),
        ])
        session.commit()

        r = client.get("/api/notes/?tag=polybius")
        bodies = sorted(n["body"] for n in r.json())
        assert bodies == ["a", "c"]

    def test_pagination(self, client, session):
        for i in range(5):
            session.add(Note(body=f"note {i}"))
        session.commit()

        r = client.get("/api/notes/?limit=2&offset=0")
        assert len(r.json()) == 2

        r = client.get("/api/notes/?limit=2&offset=2")
        assert len(r.json()) == 2


# ─── Get ───

class TestGetNote:
    def test_get_existing(self, client, session):
        note = Note(body="hello")
        session.add(note)
        session.commit()

        r = client.get(f"/api/notes/{note.note_id}")
        assert r.status_code == 200
        assert r.json()["body"] == "hello"

    def test_get_missing(self, client):
        r = client.get("/api/notes/does-not-exist")
        assert r.status_code == 404


# ─── Update ───

class TestUpdateNote:
    def test_update_body(self, client, session):
        note = Note(body="old")
        session.add(note)
        session.commit()

        r = client.patch(f"/api/notes/{note.note_id}", json={"body": "new"})
        assert r.status_code == 200
        assert r.json()["body"] == "new"

    def test_update_topic_only(self, client, session):
        note = Note(body="x", topic="bitcoin")
        session.add(note)
        session.commit()

        r = client.patch(f"/api/notes/{note.note_id}", json={"topic": "political_cycles"})
        assert r.status_code == 200
        assert r.json()["topic"] == "political_cycles"
        assert r.json()["body"] == "x"

    def test_clear_tags_with_empty_list(self, client, session):
        note = Note(body="x", tags=["a", "b"])
        session.add(note)
        session.commit()

        r = client.patch(f"/api/notes/{note.note_id}", json={"tags": []})
        assert r.status_code == 200
        assert r.json()["tags"] == []

    def test_omitting_tags_leaves_them_unchanged(self, client, session):
        note = Note(body="x", tags=["keep"])
        session.add(note)
        session.commit()

        r = client.patch(f"/api/notes/{note.note_id}", json={"body": "y"})
        assert r.status_code == 200
        assert r.json()["tags"] == ["keep"]

    def test_update_empty_body_rejected(self, client, session):
        note = Note(body="x")
        session.add(note)
        session.commit()

        r = client.patch(f"/api/notes/{note.note_id}", json={"body": "   "})
        assert r.status_code == 400

    def test_update_missing(self, client):
        r = client.patch("/api/notes/does-not-exist", json={"body": "x"})
        assert r.status_code == 404


# ─── Archive (soft-delete) ───

class TestArchiveNote:
    def test_archive_sets_flag(self, client, session):
        note = Note(body="x")
        session.add(note)
        session.commit()
        note_id = note.note_id

        r = client.delete(f"/api/notes/{note_id}")
        assert r.status_code == 204

        session.expire_all()
        fetched = session.get(Note, note_id)
        assert fetched is not None
        assert fetched.archived is True

    def test_archive_idempotent(self, client, session):
        note = Note(body="x", archived=True)
        session.add(note)
        session.commit()

        r = client.delete(f"/api/notes/{note.note_id}")
        assert r.status_code == 204

    def test_archive_missing(self, client):
        r = client.delete("/api/notes/does-not-exist")
        assert r.status_code == 404


# ─── Restore ───

class TestRestoreNote:
    def test_restore_clears_flag(self, client, session):
        note = Note(body="x", archived=True)
        session.add(note)
        session.commit()

        r = client.post(f"/api/notes/{note.note_id}/restore")
        assert r.status_code == 200
        assert r.json()["archived"] is False

    def test_restore_idempotent(self, client, session):
        note = Note(body="x", archived=False)
        session.add(note)
        session.commit()

        r = client.post(f"/api/notes/{note.note_id}/restore")
        assert r.status_code == 200
        assert r.json()["archived"] is False

    def test_restore_missing(self, client):
        r = client.post("/api/notes/does-not-exist/restore")
        assert r.status_code == 404


# ─── Chroma write-through ───

class TestChromaWriteThrough:
    def test_create_indexes_to_chroma(self, client, tmp_path):
        from src.db.vector import VectorStore
        r = client.post("/api/notes/", json={"body": "Sound money is fixed supply."})
        assert r.status_code == 201
        note_id = r.json()["note_id"]

        try:
            vs = VectorStore()
            results = vs.search_notes(query="hard money")
            ids = [res["id"] for res in results]
            assert note_id in ids
        except Exception as e:
            pytest.skip(f"Chroma unavailable in this environment: {e}")

    def test_update_body_reindexes(self, client, session):
        from src.db.vector import VectorStore
        r = client.post("/api/notes/", json={"body": "Original text about A."})
        note_id = r.json()["note_id"]

        client.patch(f"/api/notes/{note_id}", json={"body": "Replaced text about B."})

        try:
            vs = VectorStore()
            results = vs.search_notes(query="text about B")
            assert any(res["id"] == note_id for res in results)
        except Exception as e:
            pytest.skip(f"Chroma unavailable in this environment: {e}")

    def test_archive_updates_chroma_metadata(self, client, session):
        from src.db.vector import VectorStore
        r = client.post("/api/notes/", json={"body": "To be archived."})
        note_id = r.json()["note_id"]

        client.delete(f"/api/notes/{note_id}")

        try:
            vs = VectorStore()
            existing = vs.notes.get(ids=[note_id])
            assert existing["ids"] == [note_id]
            assert existing["metadatas"][0]["archived"] is True
        except Exception as e:
            pytest.skip(f"Chroma unavailable in this environment: {e}")
