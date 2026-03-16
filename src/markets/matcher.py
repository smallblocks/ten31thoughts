"""
Ten31 Thoughts - Prediction Market Matcher
LLM-powered matching of thesis predictions to live market contracts.
Uses public APIs from Polymarket and Kalshi (no auth required for read).
"""

import logging
import httpx
from typing import Optional

from ..llm.router import LLMRouter

logger = logging.getLogger(__name__)

# Public API endpoints (no auth required)
POLYMARKET_API = "https://gamma-api.polymarket.com"
KALSHI_API = "https://api.elections.kalshi.com/trade-api/v2"


class PredictionMarketMatcher:
    """
    Matches thesis predictions to live prediction market contracts.
    Uses LLM to assess semantic similarity and determine our side.
    """

    def __init__(self, llm: LLMRouter):
        self.llm = llm
        self.client = httpx.Client(timeout=30.0)

    def close(self):
        """Close the HTTP client."""
        self.client.close()

    async def find_matches(
        self,
        prediction_text: str,
        topic: str,
        horizon: str,
        source: str,
    ) -> list[dict]:
        """
        Find prediction market contracts that match a thesis prediction.

        Args:
            prediction_text: The prediction claim text
            topic: Topic category (fed_policy, bitcoin, labor, etc.)
            horizon: Time horizon ("3 months", "end of year", etc.)
            source: Source of the prediction (newsletter title, etc.)

        Returns:
            List of matching markets with confidence scores
        """
        matches = []

        # Search both platforms
        try:
            polymarket_matches = await self._search_polymarket(prediction_text, topic)
            matches.extend(polymarket_matches)
        except Exception as e:
            logger.warning(f"Polymarket search failed: {e}")

        try:
            kalshi_matches = await self._search_kalshi(prediction_text, topic)
            matches.extend(kalshi_matches)
        except Exception as e:
            logger.warning(f"Kalshi search failed: {e}")

        if not matches:
            return []

        # Use LLM to rank and filter matches
        ranked = await self._rank_matches(prediction_text, topic, horizon, matches)
        return ranked

    async def _search_polymarket(self, prediction_text: str, topic: str) -> list[dict]:
        """Search Polymarket for relevant markets."""
        markets = []

        # Map topics to search terms
        search_terms = self._get_search_terms(topic, prediction_text)

        for term in search_terms[:3]:  # Limit searches
            try:
                # Polymarket gamma API for market search
                response = self.client.get(
                    f"{POLYMARKET_API}/markets",
                    params={
                        "closed": "false",
                        "limit": 10,
                    }
                )
                if response.status_code == 200:
                    data = response.json()
                    for market in data:
                        # Filter by relevance (basic keyword match)
                        question = market.get("question", "").lower()
                        if any(kw in question for kw in term.lower().split()):
                            markets.append({
                                "platform": "polymarket",
                                "market_id": market.get("condition_id", market.get("id", "")),
                                "market_slug": market.get("slug"),
                                "title": market.get("question", ""),
                                "market_url": f"https://polymarket.com/event/{market.get('slug', '')}",
                                "price": self._extract_polymarket_price(market),
                                "end_date": market.get("end_date_iso"),
                            })
            except Exception as e:
                logger.debug(f"Polymarket search for '{term}' failed: {e}")

        return markets

    async def _search_kalshi(self, prediction_text: str, topic: str) -> list[dict]:
        """Search Kalshi for relevant markets."""
        markets = []

        # Map topics to Kalshi series
        series_map = {
            "fed_policy": ["FED", "FOMC", "RATES"],
            "inflation": ["CPI", "INFLATION", "PCE"],
            "labor": ["JOBS", "UNEMPLOYMENT", "NFP"],
            "bitcoin": ["BTC", "BITCOIN"],
            "fiscal": ["DEBT", "DEFICIT", "TREASURY"],
            "geopolitics": ["CHINA", "UKRAINE", "SANCTIONS"],
        }

        series_tickers = series_map.get(topic, [])

        # Also search by keywords from prediction
        keywords = self._extract_keywords(prediction_text)

        try:
            # Get active markets
            response = self.client.get(
                f"{KALSHI_API}/markets",
                params={
                    "status": "open",
                    "limit": 50,
                }
            )
            if response.status_code == 200:
                data = response.json()
                for market in data.get("markets", []):
                    ticker = market.get("ticker", "").upper()
                    title = market.get("title", "").lower()

                    # Check if relevant
                    relevant = (
                        any(s in ticker for s in series_tickers) or
                        any(kw in title for kw in keywords)
                    )
                    if relevant:
                        markets.append({
                            "platform": "kalshi",
                            "market_id": market.get("ticker", ""),
                            "market_slug": market.get("ticker", "").lower(),
                            "title": market.get("title", ""),
                            "market_url": f"https://kalshi.com/markets/{market.get('ticker', '').lower()}",
                            "price": market.get("last_price", market.get("yes_bid")),
                            "end_date": market.get("close_time"),
                        })
        except Exception as e:
            logger.debug(f"Kalshi search failed: {e}")

        return markets

    def _get_search_terms(self, topic: str, prediction_text: str) -> list[str]:
        """Generate search terms from topic and prediction."""
        terms = []

        # Topic-based terms
        topic_terms = {
            "fed_policy": ["federal reserve", "interest rate", "fed cut", "fomc"],
            "inflation": ["inflation", "cpi", "pce", "prices"],
            "labor": ["jobs", "unemployment", "employment", "labor"],
            "bitcoin": ["bitcoin", "btc", "crypto"],
            "fiscal": ["deficit", "debt", "treasury", "spending"],
            "geopolitics": ["china", "tariff", "sanctions", "war"],
        }
        terms.extend(topic_terms.get(topic, []))

        # Extract key phrases from prediction
        keywords = self._extract_keywords(prediction_text)
        terms.extend(keywords[:3])

        return list(set(terms))

    def _extract_keywords(self, text: str) -> list[str]:
        """Extract relevant keywords from prediction text."""
        # Simple keyword extraction - could be enhanced with NLP
        stopwords = {"the", "a", "an", "is", "are", "will", "be", "to", "of", "in", "that", "this", "with"}
        words = text.lower().split()
        keywords = [w.strip(".,!?\"'") for w in words if len(w) > 3 and w not in stopwords]
        return keywords[:10]

    def _extract_polymarket_price(self, market: dict) -> Optional[float]:
        """Extract current probability from Polymarket market data."""
        # Polymarket stores prices in different formats
        if "outcomePrices" in market:
            prices = market["outcomePrices"]
            if isinstance(prices, list) and prices:
                return float(prices[0])
        if "price" in market:
            return float(market["price"])
        return None

    async def _rank_matches(
        self,
        prediction_text: str,
        topic: str,
        horizon: str,
        candidates: list[dict],
    ) -> list[dict]:
        """Use LLM to rank and filter market matches."""
        if not candidates:
            return []

        # Deduplicate by market_id
        seen = set()
        unique = []
        for c in candidates:
            key = f"{c['platform']}:{c['market_id']}"
            if key not in seen:
                seen.add(key)
                unique.append(c)

        # Format candidates for LLM
        candidates_text = "\n".join([
            f"{i+1}. [{c['platform']}] {c['title']} (price: {c.get('price', 'N/A')})"
            for i, c in enumerate(unique[:15])  # Limit to top 15
        ])

        prompt = f"""Match this prediction to the most relevant prediction market contracts.

PREDICTION: {prediction_text}
TOPIC: {topic}
TIME HORIZON: {horizon or "unspecified"}

CANDIDATE MARKETS:
{candidates_text}

For each good match, determine:
1. Match confidence (0.0-1.0) - how well does this market test our prediction?
2. Our side (yes/no) - if our prediction is correct, which side wins?
3. Brief rationale for the match

Return JSON array of matches (only include confidence >= 0.6):
[
  {{
    "index": 1,
    "match_confidence": 0.85,
    "our_side": "no",
    "match_rationale": "Market asks if Fed will cut; our prediction says they can't"
  }}
]

Return empty array [] if no good matches."""

        try:
            result = await self.llm.complete_json(
                task="analysis",
                messages=[{"role": "user", "content": prompt}],
                system="You are matching thesis predictions to prediction market contracts. Be precise about semantic alignment."
            )

            matches = []
            for match in result:
                idx = match.get("index", 0) - 1
                if 0 <= idx < len(unique):
                    candidate = unique[idx]
                    candidate["match_confidence"] = match.get("match_confidence")
                    candidate["our_side"] = match.get("our_side")
                    candidate["match_rationale"] = match.get("match_rationale")
                    matches.append(candidate)

            # Sort by confidence
            matches.sort(key=lambda x: -(x.get("match_confidence") or 0))
            return matches[:5]  # Return top 5 matches

        except Exception as e:
            logger.error(f"LLM ranking failed: {e}")
            return []
