"""
Tests for market snapshot capture functionality.
"""

import asyncio
import pytest
from unittest.mock import patch, AsyncMock
from datetime import datetime, timezone

from src.markets.snapshot import capture_market_snapshot


class TestMarketSnapshot:
    """Test market snapshot capture functionality."""

    def test_capture_market_snapshot_success(self):
        """Test successful market snapshot capture with mocked HTTP responses."""
        
        # Mock successful responses
        mock_btc_response = AsyncMock()
        mock_btc_response.status_code = 200
        mock_btc_response.json.return_value = {
            "bitcoin": {
                "usd": 63500.0,
                "usd_24h_change": 2.45
            }
        }
        
        mock_fear_response = AsyncMock()
        mock_fear_response.status_code = 200
        mock_fear_response.json.return_value = {
            "data": [
                {
                    "value": "75",
                    "value_classification": "Greed"
                }
            ]
        }
        
        async def mock_get(url, params=None):
            if "coingecko" in url:
                return mock_btc_response
            elif "alternative.me" in url:
                return mock_fear_response
            return AsyncMock(status_code=404)
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(return_value=AsyncMock(get=mock_get))
            mock_context.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_context
            
            # Run the async function
            result = asyncio.run(capture_market_snapshot())
        
        assert result is not None
        assert "btc_price" in result
        assert result["btc_price"] == 63500.0
        assert result["btc_change_24h"] == 2.45
        assert result["fear_greed"] == 75
        assert result["fear_greed_label"] == "Greed"
        assert "captured_at" in result
        
        # Verify captured_at is a valid ISO timestamp
        captured_at = datetime.fromisoformat(result["captured_at"].replace('Z', '+00:00'))
        assert captured_at.tzinfo == timezone.utc

    def test_capture_market_snapshot_btc_fail(self):
        """Test snapshot capture when Bitcoin API fails."""
        
        mock_btc_response = AsyncMock()
        mock_btc_response.status_code = 500
        
        mock_fear_response = AsyncMock()
        mock_fear_response.status_code = 200
        mock_fear_response.json.return_value = {
            "data": [{"value": "50", "value_classification": "Neutral"}]
        }
        
        async def mock_get(url, params=None):
            if "coingecko" in url:
                return mock_btc_response
            elif "alternative.me" in url:
                return mock_fear_response
            return AsyncMock(status_code=404)
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(return_value=AsyncMock(get=mock_get))
            mock_context.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_context
            
            result = asyncio.run(capture_market_snapshot())
        
        # Should return None because BTC price is required
        assert result is None

    def test_capture_market_snapshot_timeout(self):
        """Test snapshot capture when HTTP requests timeout."""
        
        async def mock_timeout(*args, **kwargs):
            raise Exception("Timeout")
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(return_value=AsyncMock(get=mock_timeout))
            mock_context.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_context
            
            result = asyncio.run(capture_market_snapshot())
        
        assert result is None

    def test_capture_market_snapshot_fear_greed_optional(self):
        """Test snapshot capture when Fear & Greed API fails but BTC succeeds."""
        
        mock_btc_response = AsyncMock()
        mock_btc_response.status_code = 200
        mock_btc_response.json.return_value = {
            "bitcoin": {
                "usd": 58000.0,
                "usd_24h_change": -1.23
            }
        }
        
        mock_fear_response = AsyncMock()
        mock_fear_response.status_code = 500
        
        async def mock_get(url, params=None):
            if "coingecko" in url:
                return mock_btc_response
            elif "alternative.me" in url:
                return mock_fear_response
            return AsyncMock(status_code=404)
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_context = AsyncMock()
            mock_context.__aenter__ = AsyncMock(return_value=AsyncMock(get=mock_get))
            mock_context.__aexit__ = AsyncMock(return_value=None)
            mock_client.return_value = mock_context
            
            result = asyncio.run(capture_market_snapshot())
        
        assert result is not None
        assert result["btc_price"] == 58000.0
        assert result["btc_change_24h"] == -1.23
        assert "fear_greed" not in result
        assert "fear_greed_label" not in result
        assert "captured_at" in result