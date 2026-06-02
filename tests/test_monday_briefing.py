"""
Tests for Monday briefing generation functionality.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, MagicMock, patch, PropertyMock

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

        assert len(calibration) == 5
        for bucket in calibration:
            assert bucket["count"] == 0
            assert bucket["actual_rate"] is None

    def test_calibration_calculation_with_data(self):
        """Test calibration calculation with mock prediction data."""
        predictions = [
            # High conviction (60-80%): 0.6 <= x < 0.8
            Mock(conviction=0.7, status="confirmed"),
            Mock(conviction=0.75, status="confirmed"),
            Mock(conviction=0.65, status="invalidated"),

            # Very high conviction (80-100%): 0.8 <= x < 1.01
            Mock(conviction=0.85, status="confirmed"),

            # Medium conviction (40-60%): 0.4 <= x < 0.6
            Mock(conviction=0.5, status="confirmed"),
            Mock(conviction=0.45, status="invalidated"),

            # Low conviction (20-40%): 0.2 <= x < 0.4
            Mock(conviction=0.3, status="invalidated"),
        ]

        mock_session = Mock()
        mock_session.query.return_value.filter.return_value.all.return_value = predictions

        briefing = MondayBriefing(mock_session)
        calibration = briefing._calculate_calibration()

        high_bucket = next(b for b in calibration if "60-80" in b["bucket"])
        assert high_bucket["count"] == 3  # 0.7, 0.75, 0.65
        assert high_bucket["actual_rate"] == pytest.approx(66.7, abs=0.1)  # 2/3

        very_high_bucket = next(b for b in calibration if "80-100" in b["bucket"])
        assert very_high_bucket["count"] == 1
        assert very_high_bucket["actual_rate"] == 100.0

        medium_bucket = next(b for b in calibration if "40-60" in b["bucket"])
        assert medium_bucket["count"] == 2
        assert medium_bucket["actual_rate"] == 50.0

        low_bucket = next(b for b in calibration if "20-40" in b["bucket"])
        assert low_bucket["count"] == 1
        assert low_bucket["actual_rate"] == 0.0

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
        assert result["timeline_end"] == "2025-03-31T00:00:00+00:00"
        assert result["conviction"] == 0.8
        assert result["status"] == "open"

    def test_generate_briefing_structure(self):
        """Test that generate() returns the expected structure."""
        mock_session = Mock()

        mock_query = Mock()
        mock_query.filter.return_value.order_by.return_value.all.return_value = []
        mock_query.filter.return_value.all.return_value = []
        mock_query.filter.return_value.scalar.return_value = 0
        mock_session.query.return_value = mock_query

        briefing = MondayBriefing(mock_session)
        result = briefing.generate()

        required_fields = [
            "generated_at", "due_predictions", "expiring_soon",
            "recently_resolved", "calibration", "framework_activity",
            "summary_stats"
        ]
        for field in required_fields:
            assert field in result

        stats = result["summary_stats"]
        assert "total_open" in stats
        assert "total_confirmed" in stats
        assert "hit_rate" in stats

    def test_due_predictions_filtering(self):
        """Test that due predictions are filtered correctly by timeline."""
        now = datetime.now(timezone.utc)

        due_predictions = [
            Mock(
                prediction_id="due-1", claim="Due soon", measurable_outcome="m",
                timeline="Q1", timeline_end=now + timedelta(days=5),
                conviction=0.7, status="open", status_evidence=None,
                domain="bitcoin", note_id="n1",
            ),
            Mock(
                prediction_id="due-2", claim="Due later", measurable_outcome="m",
                timeline="Q2", timeline_end=now + timedelta(days=20),
                conviction=0.5, status="open", status_evidence=None,
                domain="fed_policy", note_id="n2",
            ),
        ]

        mock_session = Mock()

        # Chain: query(Prediction).filter(...).order_by(...).all() → due_predictions
        # Chain: query(Prediction).filter(...).all() → [] (recently_resolved)
        # Chain: query(func.count(...)).filter(...).scalar() → 0
        # Chain: query(Framework).filter(...).all() → []
        call_count = {"n": 0}

        def query_side_effect(*args):
            call_count["n"] += 1
            mock_q = Mock()
            # First query call: due predictions (chained with order_by)
            if call_count["n"] == 1:
                mock_q.filter.return_value.order_by.return_value.all.return_value = due_predictions
            else:
                mock_q.filter.return_value.order_by.return_value.all.return_value = []
                mock_q.filter.return_value.all.return_value = []
                mock_q.filter.return_value.scalar.return_value = 0
            return mock_q

        mock_session.query.side_effect = query_side_effect

        briefing = MondayBriefing(mock_session)
        result = briefing.generate()

        due_ids = [p["prediction_id"] for p in result["due_predictions"]]
        assert "due-1" in due_ids
        assert "due-2" in due_ids
