"""
Tests for Monday briefing generation functionality.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock

from src.synthesis.monday_briefing import MondayBriefing
from src.db.models import Prediction, Framework, gen_id


class TestMondayBriefing:
    """Test Monday briefing generation functionality."""

    def test_calibration_calculation_empty(self):
        """Test calibration calculation with no predictions."""
        
        mock_session = Mock()
        mock_session.query.return_value.filter.return_value.all.return_value = []
        
        briefing = MondayBriefing(mock_session)
        calibration = briefing._calculate_calibration()
        
        assert len(calibration) == 5  # Five conviction buckets
        
        # All buckets should be empty
        for bucket in calibration:
            assert bucket["count"] == 0
            assert bucket["actual_rate"] is None
            assert "bucket" in bucket
            assert "predicted_rate" in bucket

    def test_calibration_calculation_with_data(self):
        """Test calibration calculation with mock prediction data."""
        
        # Create mock predictions with different conviction levels
        predictions = [
            # High conviction predictions (60-80% bucket)
            Mock(conviction=0.7, status="confirmed"),
            Mock(conviction=0.75, status="confirmed"),
            Mock(conviction=0.65, status="invalidated"),
            Mock(conviction=0.8, status="confirmed"),
            
            # Medium conviction predictions (40-60% bucket)
            Mock(conviction=0.5, status="confirmed"),
            Mock(conviction=0.45, status="invalidated"),
            
            # Low conviction predictions (20-40% bucket)
            Mock(conviction=0.3, status="invalidated"),
        ]
        
        mock_session = Mock()
        mock_session.query.return_value.filter.return_value.all.return_value = predictions
        
        briefing = MondayBriefing(mock_session)
        calibration = briefing._calculate_calibration()
        
        # Find the high conviction bucket (60-80%)
        high_bucket = next(b for b in calibration if "60-80" in b["bucket"])
        assert high_bucket["count"] == 4
        assert high_bucket["actual_rate"] == 75.0  # 3 confirmed out of 4
        
        # Find the medium conviction bucket (40-60%)
        medium_bucket = next(b for b in calibration if "40-60" in b["bucket"])
        assert medium_bucket["count"] == 2
        assert medium_bucket["actual_rate"] == 50.0  # 1 confirmed out of 2
        
        # Find the low conviction bucket (20-40%)
        low_bucket = next(b for b in calibration if "20-40" in b["bucket"])
        assert low_bucket["count"] == 1
        assert low_bucket["actual_rate"] == 0.0  # 0 confirmed out of 1

    def test_serialize_prediction(self):
        """Test prediction serialization."""
        
        mock_prediction = Mock()
        mock_prediction.prediction_id = "test-id"
        mock_prediction.claim = "Test claim"
        mock_prediction.measurable_outcome = "Test outcome"
        mock_prediction.timeline = "Q1 2025"
        mock_prediction.timeline_end = datetime(2025, 3, 31, tzinfo=timezone.utc)
        mock_prediction.conviction = 0.8
        mock_prediction.status = "open"
        mock_prediction.status_evidence = None
        mock_prediction.domain = "bitcoin"
        mock_prediction.note_id = "note-123"
        
        briefing = MondayBriefing(Mock())
        result = briefing._serialize_prediction(mock_prediction)
        
        assert result["prediction_id"] == "test-id"
        assert result["claim"] == "Test claim"
        assert result["measurable_outcome"] == "Test outcome"
        assert result["timeline"] == "Q1 2025"
        assert result["timeline_end"] == "2025-03-31T00:00:00+00:00"
        assert result["conviction"] == 0.8
        assert result["status"] == "open"
        assert result["domain"] == "bitcoin"
        assert result["note_id"] == "note-123"

    def test_generate_briefing_structure(self):
        """Test that generate() returns the expected structure."""
        
        mock_session = Mock()
        
        # Mock empty query results
        mock_query = Mock()
        mock_query.filter.return_value.order_by.return_value.all.return_value = []
        mock_query.filter.return_value.all.return_value = []
        mock_query.filter.return_value.scalar.return_value = 0
        mock_session.query.return_value = mock_query
        
        briefing = MondayBriefing(mock_session)
        result = briefing.generate()
        
        # Check required fields
        required_fields = [
            "generated_at", "due_predictions", "expiring_soon",
            "recently_resolved", "calibration", "framework_activity",
            "summary_stats"
        ]
        
        for field in required_fields:
            assert field in result
        
        # Check summary stats structure
        stats = result["summary_stats"]
        assert "total_open" in stats
        assert "total_confirmed" in stats
        assert "total_invalidated" in stats
        assert "total_expired" in stats
        assert "hit_rate" in stats
        
        # Check that generated_at is a valid ISO timestamp
        generated_at = datetime.fromisoformat(result["generated_at"].replace('Z', '+00:00'))
        assert generated_at.tzinfo == timezone.utc

    def test_due_predictions_filtering(self):
        """Test that due predictions are filtered correctly by timeline."""
        
        now = datetime.now(timezone.utc)
        
        # Create mock predictions with different timeline_end dates
        predictions = [
            Mock(
                status="open",
                timeline_end=now + timedelta(days=5),  # Due soon
                prediction_id="due-1"
            ),
            Mock(
                status="open", 
                timeline_end=now + timedelta(days=20),  # Due within 30 days
                prediction_id="due-2"
            ),
            Mock(
                status="open",
                timeline_end=now + timedelta(days=40),  # Too far out
                prediction_id="not-due"
            ),
            Mock(
                status="open",
                timeline_end=now - timedelta(days=2),  # Recently expired
                prediction_id="recently-expired"
            ),
        ]
        
        mock_session = Mock()
        
        # The query should filter by the date range, so we'll return only the ones that should match
        def mock_filter(*args):
            # Return predictions that would match the filter criteria
            filtered = [p for p in predictions if p.prediction_id in ["due-1", "due-2", "recently-expired"]]
            mock_result = Mock()
            mock_result.order_by.return_value.all.return_value = filtered
            return mock_result
        
        mock_session.query.return_value.filter = mock_filter
        
        # Mock other queries to return empty results
        mock_empty = Mock()
        mock_empty.filter.return_value.all.return_value = []
        mock_empty.filter.return_value.scalar.return_value = 0
        
        # Patch the session.query to return our mock for Prediction queries
        original_query = mock_session.query
        def query_side_effect(model):
            if model == Prediction:
                return Mock(filter=mock_filter)
            else:
                return mock_empty
        mock_session.query.side_effect = query_side_effect
        
        briefing = MondayBriefing(mock_session)
        result = briefing.generate()
        
        # Should include predictions due within 30 days plus recently expired
        due_ids = [p["prediction_id"] for p in result["due_predictions"]]
        assert "due-1" in due_ids
        assert "due-2" in due_ids
        assert "recently-expired" in due_ids
        assert "not-due" not in due_ids