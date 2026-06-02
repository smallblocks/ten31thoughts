"""
Ten31 Thoughts - Market Snapshot
Captures current market state for attaching to notes at creation time.
Lightweight — only calls free APIs, designed to be fast (<5s).
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

COINGECKO_URL = "https://api.coingecko.com/api/v3/simple/price"
FEAR_GREED_URL = "https://api.alternative.me/fti/"


async def capture_market_snapshot() -> Optional[dict]:
    """
    Capture current market state. Returns dict or None on failure.
    Designed to be fast and non-blocking — failures are silent.
    """
    snapshot = {"captured_at": datetime.now(timezone.utc).isoformat()}
    
    async with httpx.AsyncClient(timeout=5.0) as client:
        # Bitcoin price
        try:
            resp = await client.get(COINGECKO_URL, params={
                "ids": "bitcoin",
                "vs_currencies": "usd",
                "include_24hr_change": "true"
            })
            if resp.status_code == 200:
                data = resp.json().get("bitcoin", {})
                snapshot["btc_price"] = data.get("usd")
                snapshot["btc_change_24h"] = round(data.get("usd_24h_change", 0), 2)
        except Exception as e:
            logger.debug(f"BTC price fetch failed: {e}")
        
        # Fear & Greed
        try:
            resp = await client.get(FEAR_GREED_URL, params={"limit": "1"})
            if resp.status_code == 200:
                items = resp.json().get("data", [])
                if items:
                    snapshot["fear_greed"] = int(items[0].get("value", 0))
                    snapshot["fear_greed_label"] = items[0].get("value_classification", "")
        except Exception as e:
            logger.debug(f"Fear & Greed fetch failed: {e}")
    
    # Only return if we got at least BTC price
    if "btc_price" in snapshot:
        return snapshot
    return None