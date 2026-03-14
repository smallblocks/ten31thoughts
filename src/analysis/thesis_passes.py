"""
Ten31 Thoughts - Thesis Analysis Pipeline
3-pass analysis for 'our_thesis' content (Ten31 Timestamp editions).

Pass A: Thesis element extraction (positions, claims, views)
Pass B: Data skepticism mapping (questioning official data)
Pass C: Prediction logging (explicit and implied predictions)
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from ..db.models import (
    ContentItem, ThesisElement, AnalysisStatus,
    ConvictionLevel, PredictionStatus, gen_id
)
from ..llm.router import LLMRouter
from .prompts.templates import (
    THESIS_PASS_A_SYSTEM, THESIS_PASS_A_USER,
    THESIS_PASS_B_SYSTEM, THESIS_PASS_B_USER,
    THESIS_PASS_C_SYSTEM, THESIS_PASS_C_USER,
)

logger = logging.getLogger(__name__)


CONVICTION_MAP = {
    "strong": ConvictionLevel.STRONG,
    "moderate": ConvictionLevel.MODERATE,
    "speculative": ConvictionLevel.SPECULATIVE,
}

# Valid topic tags
VALID_TOPICS = {
    "fed_policy", "labor_market", "fiscal_policy", "geopolitics",
    "bitcoin", "credit_markets", "energy", "currencies", "inflation",
    "financial_plumbing", "regulatory", "demographics", "technology",
}


class ThesisAnalyzer:
    """
    Runs the 3-pass thesis analysis pipeline on Ten31 Timestamp content.
    Each pass uses a tailored LLM prompt to extract structured data.
    """

    def __init__(self, llm: LLMRouter, session: Session):
        self.llm = llm
        self.session = session

    async def analyze(self, item: ContentItem) -> dict:
        """
        Run all 3 passes on a content item.
        Returns summary stats of what was extracted.
        """
        if not item.content_text or len(item.content_text.strip()) < 100:
            logger.warning(f"Skipping thesis analysis for {item.item_id}: content too short")
            item.analysis_status = AnalysisStatus.ERROR
            item.analysis_error = "Content too short for analysis"
            self.session.commit()
            return {"error": "Content too short"}

        item.analysis_status = AnalysisStatus.ANALYZING
        self.session.commit()

        stats = {
            "item_id": item.item_id,
            "title": item.title,
            "thesis_elements": 0,
            "data_skepticism_signals": 0,
            "predictions": 0,
            "errors": [],
        }

        try:
            # Pass A: Thesis element extraction
            elements = await self._pass_a_thesis_elements(item)
            stats["thesis_elements"] = len(elements)

            # Pass B: Data skepticism mapping
            skepticism_count = await self._pass_b_data_skepticism(item, elements)
            stats["data_skepticism_signals"] = skepticism_count

            # Pass C: Prediction logging
            predictions = await self._pass_c_predictions(item)
            stats["predictions"] = len(predictions)

            # Mark complete
            item.analysis_status = AnalysisStatus.COMPLETE
            item.analyzed_at = datetime.now(timezone.utc)
            self.session.commit()

            logger.info(
                f"Thesis analysis complete for '{item.title[:50]}': "
                f"{stats['thesis_elements']} elements, "
                f"{stats['data_skepticism_signals']} skepticism signals, "
                f"{stats['predictions']} predictions"
            )

        except Exception as e:
            logger.error(f"Thesis analysis failed for {item.item_id}: {e}")
            item.analysis_status = AnalysisStatus.ERROR
            item.analysis_error = str(e)[:500]
            self.session.commit()
            stats["errors"].append(str(e))

        return stats

    async def _pass_a_thesis_elements(self, item: ContentItem) -> list[ThesisElement]:
        """
        Pass A: Extract discrete thesis elements (positions, claims, views).
        """
        logger.info(f"Pass A (thesis elements): {item.title[:50]}")

        prompt = THESIS_PASS_A_USER.format(
            title=item.title,
            date=item.published_date.strftime("%Y-%m-%d") if item.published_date else "Unknown",
            authors=", ".join(item.authors) if item.authors else "Ten31 Team",
            content=self._truncate_content(item.content_text),
        )

        result = await self.llm.complete_json(
            task="analysis",
            messages=[{"role": "user", "content": prompt}],
            system=THESIS_PASS_A_SYSTEM,
        )

        elements = []
        if not isinstance(result, list):
            result = result.get("elements", result.get("thesis_elements", []))

        for raw in result:
            try:
                topic = raw.get("topic", "").lower().replace(" ", "_")
                if topic not in VALID_TOPICS:
                    topic = self._closest_topic(topic)

                conviction_str = raw.get("conviction", "moderate").lower()
                conviction = CONVICTION_MAP.get(conviction_str, ConvictionLevel.MODERATE)

                element = ThesisElement(
                    element_id=gen_id(),
                    item_id=item.item_id,
                    claim_text=raw.get("claim_text", "")[:2000],
                    topic=topic,
                    conviction=conviction,
                    is_prediction=False,  # Pass C handles predictions
                    is_data_skepticism=False,  # Pass B marks these
                    raw_excerpt=raw.get("raw_excerpt", "")[:3000],
                )

                self.session.add(element)
                elements.append(element)

            except Exception as e:
                logger.warning(f"Failed to parse thesis element: {e}")
                continue

        self.session.flush()
        logger.info(f"Pass A extracted {len(elements)} thesis elements")
        return elements

    async def _pass_b_data_skepticism(
        self, item: ContentItem, existing_elements: list[ThesisElement]
    ) -> int:
        """
        Pass B: Identify data skepticism signals and update/create thesis elements.
        """
        logger.info(f"Pass B (data skepticism): {item.title[:50]}")

        prompt = THESIS_PASS_B_USER.format(
            title=item.title,
            date=item.published_date.strftime("%Y-%m-%d") if item.published_date else "Unknown",
            content=self._truncate_content(item.content_text),
        )

        result = await self.llm.complete_json(
            task="analysis",
            messages=[{"role": "user", "content": prompt}],
            system=THESIS_PASS_B_SYSTEM,
        )

        if not isinstance(result, list):
            result = result.get("signals", result.get("data_skepticism", []))

        count = 0
        for raw in result:
            try:
                data_series = raw.get("data_series", "").strip()
                critique = raw.get("critique", "").strip()
                alt_interp = raw.get("alternative_interpretation", "").strip()
                excerpt = raw.get("raw_excerpt", "").strip()

                if not data_series or not critique:
                    continue

                # Check if this matches an existing element from Pass A
                matched = False
                for element in existing_elements:
                    if self._texts_overlap(element.raw_excerpt, excerpt):
                        element.is_data_skepticism = True
                        element.data_series = data_series[:200]
                        element.alternative_interpretation = alt_interp[:2000]
                        matched = True
                        break

                # If no match, create a new element
                if not matched:
                    element = ThesisElement(
                        element_id=gen_id(),
                        item_id=item.item_id,
                        claim_text=f"Data skepticism: {critique}"[:2000],
                        topic=self._data_series_to_topic(data_series),
                        conviction=ConvictionLevel.MODERATE,
                        is_prediction=False,
                        is_data_skepticism=True,
                        data_series=data_series[:200],
                        alternative_interpretation=alt_interp[:2000],
                        raw_excerpt=excerpt[:3000],
                    )
                    self.session.add(element)

                count += 1

            except Exception as e:
                logger.warning(f"Failed to parse skepticism signal: {e}")
                continue

        self.session.flush()
        logger.info(f"Pass B identified {count} data skepticism signals")
        return count

    async def _pass_c_predictions(self, item: ContentItem) -> list[ThesisElement]:
        """
        Pass C: Extract testable predictions (explicit and implied).
        """
        logger.info(f"Pass C (predictions): {item.title[:50]}")

        prompt = THESIS_PASS_C_USER.format(
            title=item.title,
            date=item.published_date.strftime("%Y-%m-%d") if item.published_date else "Unknown",
            content=self._truncate_content(item.content_text),
        )

        result = await self.llm.complete_json(
            task="analysis",
            messages=[{"role": "user", "content": prompt}],
            system=THESIS_PASS_C_SYSTEM,
        )

        if not isinstance(result, list):
            result = result.get("predictions", [])

        predictions = []
        for raw in result:
            try:
                prediction_text = raw.get("prediction_text", "").strip()
                if not prediction_text:
                    continue

                conviction_str = raw.get("conviction", "moderate").lower()
                conviction = CONVICTION_MAP.get(conviction_str, ConvictionLevel.MODERATE)

                testable = raw.get("testable_outcome", "")
                horizon = raw.get("time_horizon", "unspecified")

                element = ThesisElement(
                    element_id=gen_id(),
                    item_id=item.item_id,
                    claim_text=prediction_text[:2000],
                    topic=self._infer_topic_from_text(prediction_text),
                    conviction=conviction,
                    is_prediction=True,
                    prediction_status=PredictionStatus.PENDING,
                    prediction_outcome=testable[:2000] if testable else None,
                    prediction_horizon=horizon[:100] if horizon else None,
                    is_data_skepticism=False,
                    raw_excerpt=raw.get("raw_excerpt", "")[:3000],
                )

                self.session.add(element)
                predictions.append(element)

            except Exception as e:
                logger.warning(f"Failed to parse prediction: {e}")
                continue

        self.session.flush()
        logger.info(f"Pass C extracted {len(predictions)} predictions")
        return predictions

    # ─── Helpers ───

    def _truncate_content(self, text: str, max_chars: int = 80000) -> str:
        """Truncate content to fit within LLM context limits."""
        if len(text) <= max_chars:
            return text
        # Keep beginning and end for context
        half = max_chars // 2
        return text[:half] + "\n\n[... content truncated ...]\n\n" + text[-half:]

    def _closest_topic(self, topic: str) -> str:
        """Map a free-form topic string to the closest valid topic."""
        topic_lower = topic.lower().replace(" ", "_")

        # Common aliases
        aliases = {
            "fed": "fed_policy", "federal_reserve": "fed_policy", "monetary": "fed_policy",
            "rates": "fed_policy", "interest_rates": "fed_policy", "fomc": "fed_policy",
            "labor": "labor_market", "employment": "labor_market", "jobs": "labor_market",
            "payroll": "labor_market", "nfp": "labor_market", "unemployment": "labor_market",
            "fiscal": "fiscal_policy", "government": "fiscal_policy", "debt": "fiscal_policy",
            "deficit": "fiscal_policy", "spending": "fiscal_policy", "tariffs": "fiscal_policy",
            "trade": "geopolitics", "china": "geopolitics", "war": "geopolitics",
            "international": "geopolitics", "foreign_policy": "geopolitics",
            "btc": "bitcoin", "crypto": "bitcoin", "digital_assets": "bitcoin",
            "credit": "credit_markets", "bonds": "credit_markets", "spreads": "credit_markets",
            "lending": "credit_markets",
            "oil": "energy", "natural_gas": "energy", "commodities": "energy",
            "dollar": "currencies", "fx": "currencies", "yen": "currencies", "euro": "currencies",
            "cpi": "inflation", "pce": "inflation", "prices": "inflation",
            "repo": "financial_plumbing", "liquidity": "financial_plumbing",
            "balance_sheet": "financial_plumbing", "qe": "financial_plumbing",
            "regulation": "regulatory", "legislation": "regulatory", "law": "regulatory",
            "ai": "technology", "tech": "technology",
        }

        if topic_lower in aliases:
            return aliases[topic_lower]

        # Fuzzy match: check if any valid topic is a substring
        for valid in VALID_TOPICS:
            if valid in topic_lower or topic_lower in valid:
                return valid

        return "fiscal_policy"  # reasonable default for macro content

    def _data_series_to_topic(self, data_series: str) -> str:
        """Map a data series name to a topic category."""
        series_lower = data_series.lower()
        if any(w in series_lower for w in ["payroll", "employment", "jobs", "labor", "unemployment"]):
            return "labor_market"
        if any(w in series_lower for w in ["cpi", "pce", "inflation", "price"]):
            return "inflation"
        if any(w in series_lower for w in ["gdp", "growth", "output"]):
            return "fiscal_policy"
        if any(w in series_lower for w in ["rate", "fed", "fomc"]):
            return "fed_policy"
        return "fiscal_policy"

    def _infer_topic_from_text(self, text: str) -> str:
        """Infer the topic from prediction text using keyword matching."""
        text_lower = text.lower()
        topic_keywords = {
            "fed_policy": ["fed", "rate cut", "rate hike", "powell", "fomc", "monetary"],
            "labor_market": ["jobs", "payroll", "employment", "unemployment", "labor"],
            "bitcoin": ["bitcoin", "btc", "sats", "mining", "halving"],
            "inflation": ["inflation", "cpi", "deflation", "prices"],
            "fiscal_policy": ["deficit", "debt", "treasury", "fiscal", "government spending", "tariff"],
            "credit_markets": ["credit", "spread", "bond", "yield", "default"],
            "geopolitics": ["china", "russia", "war", "tariff", "sanctions", "trade war"],
            "currencies": ["dollar", "yen", "euro", "currency", "dxy"],
            "energy": ["oil", "energy", "gas", "opec"],
            "financial_plumbing": ["repo", "liquidity", "reserve", "balance sheet", "qe", "qt"],
        }

        best_topic = "fiscal_policy"
        best_count = 0
        for topic, keywords in topic_keywords.items():
            count = sum(1 for kw in keywords if kw in text_lower)
            if count > best_count:
                best_count = count
                best_topic = topic

        return best_topic

    def _texts_overlap(self, text_a: str, text_b: str, threshold: int = 50) -> bool:
        """Check if two text excerpts overlap significantly."""
        if not text_a or not text_b:
            return False

        # Simple substring check on the first N chars
        a_chunk = text_a[:threshold].lower().strip()
        b_chunk = text_b[:threshold].lower().strip()

        if not a_chunk or not b_chunk:
            return False

        # Check if the shorter is contained in the longer
        shorter = a_chunk if len(a_chunk) <= len(b_chunk) else b_chunk
        longer = b_chunk if len(a_chunk) <= len(b_chunk) else a_chunk

        return shorter[:30] in longer
