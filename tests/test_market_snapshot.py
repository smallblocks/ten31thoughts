"""
Tests for market snapshot capture functionality.
"""

import asyncio
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime, timezone

from src.markets.snapshot import capture_market_snapshot


def _make_response(status_code, json_data=None):
    """Create a mock httpx Response."""
    resp = MagicMock()
    resp.status_code = status_code
    if json_data is not None:
        resp.json.return_value = json_data
    return resp


class TestMarketSnapshot:
    """Test market snapshot capture functionality."""

    def test_capture_market_snapshot_success(self):
        """Test successful market snapshot capture with mocked HTTP responses."""

        btc_resp = _make_response(200, {
            "bitcoin": {"usd": 63500.0, "usd_24h_change": 2.45}
        })
        fg_resp = _make_response(200, {
            "data": [{"value": "75", "value_classification": "Greed"}]
        })

        mock_client = AsyncMock()
        async def mock_get(url, params=None):
            if "coingecko" in url:
                return btc_resp
            if "alternative.me" in url:
                return fg_resp
            return _make_response(404)

        mock_client.get = mock_get

        with patch('src.markets.snapshot.httpx.AsyncClient') as MockCls:
            MockCls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockCls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = asyncio.run(capture_market_snapshot())

        assert result is not None
        assert result["btc_price"] == 63500.0
        assert result["btc_change_24h"] == 2.45
        assert result["fear_greed"] == 75
        assert result["fear_greed_label"] == "Greed"
        assert "captured_at" in result

    def test_capture_market_snapshot_btc_fail(self):
        """Test snapshot capture when Bitcoin API fails — should return None."""

        btc_resp = _make_response(500)
        fg_resp = _make_response(200, {
            "data": [{"value": "50", "value_classification": "Neutral"}]
        })

        mock_client = AsyncMock()
        async def mock_get(url, params=None):
            if "coingecko" in url:
                return btc_resp
            if "alternative.me" in url:
                return fg_resp
            return _make_response(404)

        mock_client.get = mock_get

        with patch('src.markets.snapshot.httpx.AsyncClient') as MockCls:
            MockCls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockCls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = asyncio.run(capture_market_snapshot())

        assert result is None

    def test_capture_market_snapshot_timeout(self):
        """Test snapshot capture when HTTP requests timeout — should return None."""

        mock_client = AsyncMock()
        async def mock_get(url, params=None):
            raise Exception("Timeout")
        mock_client.get = mock_get

        with patch('src.markets.snapshot.httpx.AsyncClient') as MockCls:
            MockCls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockCls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = asyncio.run(capture_market_snapshot())

        assert result is None

    def test_capture_market_snapshot_fear_greed_optional(self):
        """Test snapshot when Fear & Greed fails but BTC succeeds — snapshot still returned."""

        btc_resp = _make_response(200, {
            "bitcoin": {"usd": 58000.0, "usd_24h_change": -1.23}
        })
        fg_resp = _make_response(500)

        mock_client = AsyncMock()
        async def mock_get(url, params=None):
            if "coingecko" in url:
                return btc_resp
            if "alternative.me" in url:
                return fg_resp
            return _make_response(404)

        mock_client.get = mock_get

        with patch('src.markets.snapshot.httpx.AsyncClient') as MockCls:
            MockCls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockCls.return_value.__aexit__ = AsyncMock(return_value=None)

            result = asyncio.run(capture_market_snapshot())

        assert result is not None
        assert result["btc_price"] == 58000.0
        assert result["btc_change_24h"] == -1.23
        assert "fear_greed" not in result
        assert "captured_at" in result
