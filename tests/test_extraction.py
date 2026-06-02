"""
Tests for the extraction engine — predictions, frameworks, and API endpoints.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from src.db.models import Base, Note, Prediction, Framework, FrameworkLink, gen_id, get_engine, create_tables, get_session
from src.analysis.extraction_engine import ExtractionEngine
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
    return TestClient(app)


class TestPredictionModel:
    """Test Prediction model creation and relationships."""
    
    def test_prediction_creation(self, session):
        # Create a test note
        note = Note(
            note_id=gen_id(),
            title="Test Note",
            body="This is a test prediction about bitcoin reaching $100k by Q3 2026",
            topic="bitcoin"
        )
        session.add(note)
        session.commit()
        
        # Create a prediction
        prediction = Prediction(
            prediction_id=gen_id(),
            note_id=note.note_id,
            claim="Bitcoin will reach $100k",
            measurable_outcome="Bitcoin price hits $100,000 USD",
            timeline="Q3 2026",
            conviction=0.7,
            conviction_reasoning="Strong institutional adoption trends",
            domain="bitcoin",
            status="open"
        )
        session.add(prediction)
        session.commit()
        
        # Test relationship
        assert prediction.note == note
        assert len(note.predictions) == 1
        assert note.predictions[0] == prediction


class TestFrameworkModel:
    """Test Framework and FrameworkLink models."""
    
    def test_framework_creation(self, session):
        framework = Framework(
            framework_id=gen_id(),
            name="Currency Stack",
            description="A framework for understanding monetary hierarchies",
            domain="bitcoin_monetary",
            status="active"
        )
        session.add(framework)
        session.commit()
        
        assert framework.name == "Currency Stack"
        assert framework.status == "active"
    
    def test_framework_link(self, session):
        # Create note and framework
        note = Note(
            note_id=gen_id(),
            title="Test Note",
            body="Test content",
            topic="bitcoin"
        )
        session.add(note)
        
        framework = Framework(
            framework_id=gen_id(),
            name="Test Framework",
            description="Test description",
            status="active"
        )
        session.add(framework)
        session.commit()
        
        # Create link
        link = FrameworkLink(
            link_id=gen_id(),
            framework_id=framework.framework_id,
            note_id=note.note_id,
            relation="applies",
            context="This note applies the framework"
        )
        session.add(link)
        session.commit()
        
        assert link.framework == framework
        assert link.note == note


class TestExtractionEngine:
    """Test extraction engine functionality."""
    
    @pytest.fixture
    def mock_llm(self):
        llm = MagicMock()
        llm.complete_json = AsyncMock()
        return llm
    
    @pytest.fixture
    def extraction_engine(self, mock_llm, session):
        return ExtractionEngine(mock_llm, session)
    
    @pytest.mark.anyio
    async def test_extract_predictions_from_note(self, extraction_engine, mock_llm, session):
        # Create a test note
        note = Note(
            note_id=gen_id(),
            title="Bitcoin Prediction",
            body="I believe bitcoin will reach $100k by Q3 2026 with high confidence",
            topic="bitcoin",
            conviction_tier="thesis"
        )
        session.add(note)
        session.commit()
        
        # Mock LLM response
        mock_llm.complete_json.return_value = {
            "predictions": [
                {
                    "claim": "Bitcoin will reach $100k by Q3 2026",
                    "measurable_outcome": "Bitcoin price hits $100,000 USD on major exchanges",
                    "timeline": "Q3 2026",
                    "conviction": 0.8,
                    "conviction_reasoning": "Strong institutional adoption and halvening cycle",
                    "domain": "bitcoin"
                }
            ],
            "framework_references": []
        }
        
        # Run extraction
        result = await extraction_engine.extract_from_note(note.note_id)
        
        assert result["predictions_created"] == 1
        assert result["framework_links_created"] == 0
        
        # Verify prediction was created
        predictions = session.query(Prediction).filter_by(note_id=note.note_id).all()
        assert len(predictions) == 1
        assert predictions[0].claim == "Bitcoin will reach $100k by Q3 2026"
        assert predictions[0].conviction == 0.8
    
    @pytest.mark.anyio
    async def test_extract_frameworks_from_note(self, extraction_engine, mock_llm, session):
        # Create a test note
        note = Note(
            note_id=gen_id(),
            title="Framework Discussion",
            body="The Currency Stack framework explains monetary hierarchies",
            topic="bitcoin_monetary"
        )
        session.add(note)
        session.commit()
        
        # Mock LLM response
        mock_llm.complete_json.return_value = {
            "predictions": [],
            "framework_references": [
                {
                    "framework_name": "new: Currency Stack",
                    "relation": "defines",
                    "context": "This note introduces and defines the Currency Stack framework"
                }
            ]
        }
        
        # Run extraction
        result = await extraction_engine.extract_from_note(note.note_id)
        
        assert result["predictions_created"] == 0
        assert result["framework_links_created"] == 1
        assert result["new_frameworks_created"] == 1
        
        # Verify framework and link were created
        frameworks = session.query(Framework).all()
        assert len(frameworks) == 1
        assert frameworks[0].name == "Currency Stack"
        
        links = session.query(FrameworkLink).filter_by(note_id=note.note_id).all()
        assert len(links) == 1
        assert links[0].relation == "defines"
    
    def test_timeline_parsing(self, extraction_engine):
        # Test Q1 2026
        start, end = extraction_engine._parse_timeline("Q1 2026")
        assert start == datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert end == datetime(2026, 3, 31, tzinfo=timezone.utc)
        
        # Test Q3 2025
        start, end = extraction_engine._parse_timeline("Q3 2025")
        assert start == datetime(2025, 7, 1, tzinfo=timezone.utc)
        assert end == datetime(2025, 9, 30, tzinfo=timezone.utc)
        
        # Test "by year-end"
        start, end = extraction_engine._parse_timeline("by year-end")
        assert end.month == 12
        assert end.day == 31
        
        # Test "6 months"
        start, end = extraction_engine._parse_timeline("6 months")
        assert end > start
        assert (end - start).days == 180


class TestExtractionAPI:
    """Test extraction API endpoints."""
    
    def test_list_predictions(self, client, session):
        # Create test data
        note = Note(note_id=gen_id(), title="Test", body="Test note", topic="bitcoin")
        session.add(note)
        session.commit()
        
        prediction = Prediction(
            prediction_id=gen_id(),
            note_id=note.note_id,
            claim="Test prediction",
            status="open",
            domain="bitcoin"
        )
        session.add(prediction)
        session.commit()
        
        # Test API
        response = client.get("/api/predictions/")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["claim"] == "Test prediction"
    
    def test_update_prediction_status(self, client, session):
        # Create test data
        note = Note(note_id=gen_id(), title="Test", body="Test note")
        session.add(note)
        session.commit()
        
        prediction = Prediction(
            prediction_id=gen_id(),
            note_id=note.note_id,
            claim="Test prediction",
            status="open"
        )
        session.add(prediction)
        session.commit()
        
        # Update status
        response = client.put(
            f"/api/predictions/{prediction.prediction_id}/status",
            json={"status": "confirmed", "evidence": "Market reached target"}
        )
        assert response.status_code == 200
        
        # Verify update
        session.refresh(prediction)
        assert prediction.status == "confirmed"
        assert prediction.status_evidence == "Market reached target"
    
    def test_predictions_scorecard(self, client, session):
        # Create test predictions with different statuses
        note = Note(note_id=gen_id(), title="Test", body="Test note")
        session.add(note)
        session.commit()
        
        predictions_data = [
            {"status": "confirmed", "conviction": 0.8},
            {"status": "confirmed", "conviction": 0.6},
            {"status": "invalidated", "conviction": 0.9},
            {"status": "open", "conviction": 0.5}
        ]
        
        for pred_data in predictions_data:
            prediction = Prediction(
                prediction_id=gen_id(),
                note_id=note.note_id,
                claim=f"Test prediction {pred_data['status']}",
                status=pred_data["status"],
                conviction=pred_data["conviction"]
            )
            session.add(prediction)
        
        session.commit()
        
        # Test scorecard API
        response = client.get("/api/predictions/scorecard")
        assert response.status_code == 200
        
        data = response.json()
        assert data["total_predictions"] == 4
        assert data["confirmed"] == 2
        assert data["invalidated"] == 1
        assert data["open"] == 1
        assert data["accuracy_rate"] == 2/3  # 2 confirmed out of 3 resolved
    
    def test_create_framework(self, client, session):
        response = client.post(
            "/api/frameworks/",
            json={
                "name": "Test Framework",
                "description": "A test framework for testing",
                "domain": "test"
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["name"] == "Test Framework"
        assert data["status"] == "active"
        
        # Verify in database
        framework = session.query(Framework).filter_by(name="Test Framework").first()
        assert framework is not None
        assert framework.description == "A test framework for testing"
    
    def test_get_framework_with_links(self, client, session):
        # Create framework, note, and link
        framework = Framework(
            framework_id=gen_id(),
            name="Test Framework",
            description="Test description",
            status="active"
        )
        session.add(framework)
        
        note = Note(note_id=gen_id(), title="Test Note", body="Test content")
        session.add(note)
        session.commit()
        
        link = FrameworkLink(
            link_id=gen_id(),
            framework_id=framework.framework_id,
            note_id=note.note_id,
            relation="applies",
            context="Test context"
        )
        session.add(link)
        session.commit()
        
        # Test API
        response = client.get(f"/api/frameworks/{framework.framework_id}")
        assert response.status_code == 200
        
        data = response.json()
        assert data["name"] == "Test Framework"
        assert data["linked_notes_count"] == 1
        assert len(data["linked_notes"]) == 1
        assert data["linked_notes"][0]["relation"] == "applies"