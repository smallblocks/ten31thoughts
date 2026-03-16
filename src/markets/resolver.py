"""
Ten31 Thoughts - Market Resolver
Checks prediction market outcomes and auto-resolves linked predictions.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import PredictionMarketLink, ThesisElement, PredictionStatus

logger = logging.getLogger(__name__)

# Public API endpoints
POLYMARKET_API = "https://gamma-api.polymarket.com"
KALSHI_API = "https://api.elections.kalshi.com/trade-api/v2"


class MarketResolver:
    """
    Checks prediction market outcomes and updates linked predictions.
    Runs periodically to auto-validate/invalidate predictions based on market results.
    """

    def __init__(self, session: Session):
        self.session = session
        self.client = httpx.Client(timeout=30.0)

    def close(self):
        """Close the HTTP client."""
        self.client.close()

    def check_all_linked_markets(self) -> dict:
        """
        Check all open market links for resolution.

        Returns:
            Stats dict with counts of checked, resolved, updated
        """
        stats = {
            "checked": 0,
            "resolved": 0,
            "prices_updated": 0,
            "errors": 0,
        }

        # Get all open market links
        open_links = self.session.execute(
            select(PredictionMarketLink)
            .where(PredictionMarketLink.market_status == "open")
        ).scalars().all()

        logger.info(f"Checking {len(open_links)} open market links for resolution")

        for link in open_links:
            try:
                stats["checked"] += 1

                if link.platform == "polymarket":
                    result = self._check_polymarket(link)
                elif link.platform == "kalshi":
                    result = self._check_kalshi(link)
                else:
                    logger.warning(f"Unknown platform: {link.platform}")
                    continue

                if result:
                    if result.get("resolved"):
                        self._resolve_link(link, result)
                        stats["resolved"] += 1
                    elif result.get("price") is not None:
                        # Update current price
                        old_price = link.current_price
                        link.current_price = result["price"]
                        if old_price != link.current_price:
                            stats["prices_updated"] += 1

            except Exception as e:
                logger.error(f"Error checking link {link.link_id}: {e}")
                stats["errors"] += 1

        self.session.commit()
        logger.info(f"Market check complete: {stats}")
        return stats

    def _check_polymarket(self, link: PredictionMarketLink) -> Optional[dict]:
        """Check a Polymarket market for resolution status."""
        try:
            # Try to get market by condition_id or slug
            market_id = link.market_id
            response = self.client.get(
                f"{POLYMARKET_API}/markets/{market_id}"
            )

            if response.status_code != 200:
                # Try by slug if ID fails
                if link.market_slug:
                    response = self.client.get(
                        f"{POLYMARKET_API}/markets",
                        params={"slug": link.market_slug}
                    )
                    if response.status_code == 200:
                        data = response.json()
                        if isinstance(data, list) and data:
                            market = data[0]
                        else:
                            return None
                    else:
                        return None
                else:
                    return None
            else:
                market = response.json()

            # Check if resolved
            is_resolved = market.get("resolved", False) or market.get("closed", False)

            result = {
                "resolved": is_resolved,
                "price": self._extract_polymarket_price(market),
            }

            if is_resolved:
                # Determine outcome
                resolution_value = market.get("resolution")
                if resolution_value is not None:
                    # Polymarket: resolution is typically 0 or 1
                    result["outcome"] = "yes" if float(resolution_value) > 0.5 else "no"
                else:
                    # Check winning outcome prices
                    prices = market.get("outcomePrices", [])
                    if prices and len(prices) >= 2:
                        result["outcome"] = "yes" if float(prices[0]) > float(prices[1]) else "no"

            return result

        except Exception as e:
            logger.debug(f"Polymarket check failed for {link.market_id}: {e}")
            return None

    def _check_kalshi(self, link: PredictionMarketLink) -> Optional[dict]:
        """Check a Kalshi market for resolution status."""
        try:
            ticker = link.market_id
            response = self.client.get(
                f"{KALSHI_API}/markets/{ticker}"
            )

            if response.status_code != 200:
                return None

            data = response.json()
            market = data.get("market", data)

            # Check market status
            status = market.get("status", "").lower()
            is_resolved = status in ["settled", "finalized", "closed"]

            result = {
                "resolved": is_resolved,
                "price": market.get("last_price") or market.get("yes_bid"),
            }

            if is_resolved:
                # Kalshi provides result directly
                market_result = market.get("result")
                if market_result is not None:
                    result["outcome"] = "yes" if market_result == "yes" or market_result == 1 else "no"
                else:
                    # Infer from settlement price
                    settlement = market.get("settlement_value")
                    if settlement is not None:
                        result["outcome"] = "yes" if float(settlement) > 0.5 else "no"

            return result

        except Exception as e:
            logger.debug(f"Kalshi check failed for {link.market_id}: {e}")
            return None

    def _extract_polymarket_price(self, market: dict) -> Optional[float]:
        """Extract current probability from Polymarket market data."""
        if "outcomePrices" in market:
            prices = market["outcomePrices"]
            if isinstance(prices, list) and prices:
                return float(prices[0])
        if "price" in market:
            return float(market["price"])
        return None

    def _resolve_link(self, link: PredictionMarketLink, result: dict):
        """
        Resolve a market link and update the linked prediction.
        """
        link.market_status = "resolved"
        link.market_result = result.get("outcome")
        link.resolved_at = datetime.now(timezone.utc)

        if result.get("price") is not None:
            link.current_price = result["price"]

        # Update the linked thesis element if we have an outcome
        if link.element_id and link.market_result and link.our_side:
            element = self.session.get(ThesisElement, link.element_id)
            if element and element.is_prediction:
                # Determine if our prediction was correct
                our_prediction_correct = link.market_result == link.our_side

                if our_prediction_correct:
                    element.prediction_status = PredictionStatus.VALIDATED
                    element.prediction_outcome = (
                        f"Market resolved: {link.market_result}. "
                        f"Our call ({link.our_side}) was correct. "
                        f"Platform: {link.platform}, Market: {link.market_title}"
                    )
                else:
                    element.prediction_status = PredictionStatus.INVALIDATED
                    element.prediction_outcome = (
                        f"Market resolved: {link.market_result}. "
                        f"Our call ({link.our_side}) was incorrect. "
                        f"Platform: {link.platform}, Market: {link.market_title}"
                    )

                logger.info(
                    f"Prediction {link.element_id} {'VALIDATED' if our_prediction_correct else 'INVALIDATED'} "
                    f"via {link.platform} market {link.market_id}"
                )

    def update_prices(self) -> dict:
        """
        Update current prices for all open market links.
        Lightweight operation that doesn't check for resolution.
        """
        stats = {"updated": 0, "errors": 0}

        open_links = self.session.execute(
            select(PredictionMarketLink)
            .where(PredictionMarketLink.market_status == "open")
        ).scalars().all()

        for link in open_links:
            try:
                if link.platform == "polymarket":
                    result = self._check_polymarket(link)
                elif link.platform == "kalshi":
                    result = self._check_kalshi(link)
                else:
                    continue

                if result and result.get("price") is not None:
                    link.current_price = result["price"]
                    stats["updated"] += 1

            except Exception as e:
                logger.debug(f"Price update failed for {link.link_id}: {e}")
                stats["errors"] += 1

        self.session.commit()
        return stats
