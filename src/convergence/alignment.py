"""
Ten31 Thoughts - Alignment Mapper
Maps agreement and divergence between thesis elements (our content)
and external frameworks (MacroVoices, etc.).

Produces ConvergenceRecords that classify how your views relate to each
external voice: agree via different reasoning, agree via same reasoning,
partial agreement with caveats, or direct divergence.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from ..db.models import (
    ThesisElement, ExternalFramework, ConvergenceRecord, ContentItem, Feed,
    FeedCategory, ThesisAlignment, gen_id
)
from ..llm.router import LLMRouter

logger = logging.getLogger(__name__)


ALIGNMENT_SYSTEM = """You are an expert macro analyst comparing two analytical positions.
You will be given a THESIS ELEMENT (from our internal newsletter) and an EXTERNAL FRAMEWORK
(from a podcast guest or external commentator).

Your job is to determine how these two positions relate to each other.

Classify the relationship as one of:
- "agree_diff_reasoning": Both reach the same conclusion but through different analytical paths. This is the highest-conviction signal.
- "agree_same_reasoning": Both reach the same conclusion through similar logic. Confirms the view but adds less new information.
- "partial_agree": Directionally aligned but with meaningful caveats, conditions, or scope differences that matter.
- "diverge": Directly contradictory conclusions or opposing positions on the same topic.
- "unrelated": The two positions address different topics or have no meaningful overlap.

For each classification, provide:
1. alignment_type: One of the above categories
2. divergence_point: If diverging or partially agreeing, what is the PRECISE point where the views split? What assumption differs?
3. competing_assumptions: What does each side assume that the other doesn't?
4. information_value: What can we learn from this comparison? What should we investigate further?
5. confidence: How confident are you in this classification? (high/medium/low)

Respond ONLY with a JSON object. No preamble."""

ALIGNMENT_USER = """Compare these two positions:

THESIS ELEMENT (our position, from {thesis_date}):
Topic: {thesis_topic}
Conviction: {thesis_conviction}
Position: {thesis_claim}

EXTERNAL FRAMEWORK (from {guest_name}, {external_date}):
Framework: {framework_name}
Description: {framework_description}
Causal chain: {causal_chain}
Time horizon: {time_horizon}"""


class AlignmentMapper:
    """
    Maps agreement/divergence between thesis elements and external frameworks.
    Runs both batch (weekly synthesis) and incremental (new content) modes.
    """

    def __init__(self, llm: LLMRouter, session: Session):
        self.llm = llm
        self.session = session

    async def run_alignment_batch(
        self,
        lookback_days: int = 30,
        max_comparisons: int = 100,
    ) -> dict:
        """
        Run alignment mapping across recent thesis elements and frameworks.
        Used during weekly synthesis.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

        # Get recent thesis elements
        thesis_elements = self.session.execute(
            select(ThesisElement)
            .join(ContentItem)
            .where(ContentItem.published_date >= cutoff)
            .where(ThesisElement.is_prediction == False)
            .order_by(ContentItem.published_date.desc())
            .limit(50)
        ).scalars().all()

        # Get recent external frameworks
        frameworks = self.session.execute(
            select(ExternalFramework)
            .join(ContentItem)
            .where(ContentItem.published_date >= cutoff)
            .order_by(ContentItem.published_date.desc())
            .limit(50)
        ).scalars().all()

        if not thesis_elements or not frameworks:
            logger.info("No recent content for alignment mapping")
            return {"comparisons": 0, "skipped": 0}

        # Find relevant pairings using topic overlap
        pairs = self._find_relevant_pairs(thesis_elements, frameworks)
        logger.info(f"Found {len(pairs)} relevant thesis-framework pairs to compare")

        stats = {"comparisons": 0, "skipped": 0, "by_type": {}}

        for element, framework in pairs[:max_comparisons]:
            # Skip if already compared
            existing = self.session.execute(
                select(ConvergenceRecord).where(and_(
                    ConvergenceRecord.thesis_element_id == element.element_id,
                    ConvergenceRecord.framework_id == framework.framework_id,
                ))
            ).scalar_one_or_none()

            if existing:
                stats["skipped"] += 1
                continue

            record = await self._compare_pair(element, framework)
            if record:
                stats["comparisons"] += 1
                atype = record.alignment_type
                stats["by_type"][atype] = stats["by_type"].get(atype, 0) + 1

                # Update framework's thesis_alignment field
                alignment_map = {
                    "agree_diff_reasoning": ThesisAlignment.AGREE,
                    "agree_same_reasoning": ThesisAlignment.AGREE,
                    "partial_agree": ThesisAlignment.PARTIAL,
                    "diverge": ThesisAlignment.DIVERGE,
                    "unrelated": ThesisAlignment.UNRELATED,
                }
                framework.thesis_alignment = alignment_map.get(
                    atype, ThesisAlignment.UNRELATED
                )

        self.session.commit()

        logger.info(
            f"Alignment batch complete: {stats['comparisons']} comparisons, "
            f"{stats['skipped']} skipped. Distribution: {stats['by_type']}"
        )
        return stats

    async def align_new_framework(self, framework: ExternalFramework) -> list[ConvergenceRecord]:
        """
        When a new framework is extracted, compare it against recent thesis elements.
        Used in incremental mode when new external content is analyzed.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=90)

        thesis_elements = self.session.execute(
            select(ThesisElement)
            .join(ContentItem)
            .where(ContentItem.published_date >= cutoff)
            .order_by(ContentItem.published_date.desc())
            .limit(30)
        ).scalars().all()

        relevant = [
            elem for elem in thesis_elements
            if self._topics_related(elem.topic, framework)
        ]

        records = []
        for element in relevant[:5]:  # Top 5 most relevant
            record = await self._compare_pair(element, framework)
            if record:
                records.append(record)

        self.session.commit()
        return records

    async def _compare_pair(
        self,
        element: ThesisElement,
        framework: ExternalFramework,
    ) -> Optional[ConvergenceRecord]:
        """Compare a single thesis element against a single external framework."""
        try:
            # Get dates from parent content items
            thesis_item = self.session.get(ContentItem, element.item_id)
            framework_item = self.session.get(ContentItem, framework.item_id)

            thesis_date = (
                thesis_item.published_date.strftime("%Y-%m-%d")
                if thesis_item and thesis_item.published_date else "Unknown"
            )
            external_date = (
                framework_item.published_date.strftime("%Y-%m-%d")
                if framework_item and framework_item.published_date else "Unknown"
            )

            causal_str = ""
            if framework.causal_chain:
                if isinstance(framework.causal_chain, dict):
                    parts = []
                    for k, v in framework.causal_chain.items():
                        parts.append(f"{k}: {v}")
                    causal_str = "; ".join(parts)
                else:
                    causal_str = str(framework.causal_chain)

            prompt = ALIGNMENT_USER.format(
                thesis_date=thesis_date,
                thesis_topic=element.topic,
                thesis_conviction=element.conviction.value if element.conviction else "moderate",
                thesis_claim=element.claim_text,
                guest_name=framework.guest_name or "Unknown",
                external_date=external_date,
                framework_name=framework.framework_name,
                framework_description=framework.description,
                causal_chain=causal_str or "Not specified",
                time_horizon=framework.time_horizon or "Not specified",
            )

            result = await self.llm.complete_json(
                task="analysis",
                messages=[{"role": "user", "content": prompt}],
                system=ALIGNMENT_SYSTEM,
            )

            alignment_type = result.get("alignment_type", "unrelated")
            valid_types = {
                "agree_diff_reasoning", "agree_same_reasoning",
                "partial_agree", "diverge", "unrelated"
            }
            if alignment_type not in valid_types:
                alignment_type = "unrelated"

            # Build notes
            notes_parts = []
            info_value = result.get("information_value", "")
            if info_value:
                notes_parts.append(f"Insight: {info_value}")
            confidence = result.get("confidence", "")
            if confidence:
                notes_parts.append(f"Confidence: {confidence}")

            record = ConvergenceRecord(
                record_id=gen_id(),
                thesis_element_id=element.element_id,
                framework_id=framework.framework_id,
                alignment_type=alignment_type,
                divergence_point=result.get("divergence_point", "")[:2000] or None,
                competing_assumptions=result.get("competing_assumptions"),
                notes=" | ".join(notes_parts)[:3000] if notes_parts else None,
            )

            self.session.add(record)
            self.session.flush()

            logger.debug(
                f"Alignment: '{element.claim_text[:40]}' vs "
                f"'{framework.framework_name}' -> {alignment_type}"
            )
            return record

        except Exception as e:
            logger.warning(
                f"Failed to compare element {element.element_id} "
                f"with framework {framework.framework_id}: {e}"
            )
            return None

    def _find_relevant_pairs(
        self,
        elements: list[ThesisElement],
        frameworks: list[ExternalFramework],
    ) -> list[tuple[ThesisElement, ExternalFramework]]:
        """
        Find thesis-framework pairs that are likely to be topically related.
        Uses topic matching and keyword overlap to avoid wasting LLM calls
        on obviously unrelated comparisons.
        """
        pairs = []

        for element in elements:
            for framework in frameworks:
                if self._topics_related(element.topic, framework):
                    pairs.append((element, framework))

        # Sort by likely relevance: keyword overlap in claim/description
        def relevance_score(pair):
            elem, fw = pair
            elem_words = set(elem.claim_text.lower().split())
            fw_words = set(fw.description.lower().split())
            fw_words |= set(fw.framework_name.lower().split())
            return len(elem_words & fw_words)

        pairs.sort(key=relevance_score, reverse=True)
        return pairs

    def _topics_related(self, thesis_topic: str, framework: ExternalFramework) -> bool:
        """Check if a thesis topic and framework are likely related."""
        # Topic adjacency map: topics that are analytically connected
        adjacencies = {
            "fed_policy": {"inflation", "credit_markets", "currencies", "financial_plumbing", "labor_market"},
            "labor_market": {"fed_policy", "inflation", "fiscal_policy"},
            "fiscal_policy": {"fed_policy", "geopolitics", "bitcoin", "currencies", "inflation"},
            "bitcoin": {"fiscal_policy", "currencies", "inflation", "financial_plumbing", "regulatory"},
            "inflation": {"fed_policy", "labor_market", "energy", "currencies", "fiscal_policy"},
            "credit_markets": {"fed_policy", "financial_plumbing", "fiscal_policy"},
            "currencies": {"fed_policy", "geopolitics", "fiscal_policy", "inflation"},
            "energy": {"inflation", "geopolitics", "currencies"},
            "geopolitics": {"currencies", "energy", "fiscal_policy"},
            "financial_plumbing": {"fed_policy", "credit_markets", "bitcoin"},
            "regulatory": {"bitcoin", "fiscal_policy"},
            "demographics": {"labor_market", "fiscal_policy"},
            "technology": {"bitcoin", "regulatory"},
        }

        # Check framework description for topic keywords
        fw_text = f"{framework.framework_name} {framework.description}".lower()

        topic_keywords = {
            "fed_policy": ["fed", "rate", "powell", "fomc", "monetary", "central bank"],
            "labor_market": ["jobs", "payroll", "employment", "labor", "unemployment", "hiring"],
            "fiscal_policy": ["deficit", "debt", "treasury", "fiscal", "spending", "tariff", "government"],
            "bitcoin": ["bitcoin", "btc", "digital", "crypto"],
            "inflation": ["inflation", "cpi", "deflation", "prices", "pce"],
            "credit_markets": ["credit", "spread", "bond", "yield", "default", "corporate"],
            "currencies": ["dollar", "yen", "euro", "currency", "dxy", "fx"],
            "energy": ["oil", "energy", "gas", "opec", "petroleum"],
            "geopolitics": ["china", "russia", "war", "sanctions", "geopolitical"],
            "financial_plumbing": ["repo", "liquidity", "reserve", "balance sheet"],
        }

        # Direct topic match
        if thesis_topic in topic_keywords:
            for kw in topic_keywords[thesis_topic]:
                if kw in fw_text:
                    return True

        # Adjacent topic match
        adjacent = adjacencies.get(thesis_topic, set())
        for adj_topic in adjacent:
            if adj_topic in topic_keywords:
                for kw in topic_keywords[adj_topic]:
                    if kw in fw_text:
                        return True

        return False

    # ─── Query methods for the API and briefing ───

    def get_convergence_summary(self, days: int = 30) -> dict:
        """
        Get a summary of convergence patterns over the last N days.
        Used in the weekly briefing.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        records = self.session.execute(
            select(ConvergenceRecord)
            .where(ConvergenceRecord.created_at >= cutoff)
        ).scalars().all()

        summary = {
            "total_comparisons": len(records),
            "by_type": {},
            "key_agreements": [],
            "key_divergences": [],
        }

        for record in records:
            atype = record.alignment_type
            summary["by_type"][atype] = summary["by_type"].get(atype, 0) + 1

            if atype == "agree_diff_reasoning":
                element = self.session.get(ThesisElement, record.thesis_element_id)
                framework = self.session.get(ExternalFramework, record.framework_id)
                if element and framework:
                    summary["key_agreements"].append({
                        "our_position": element.claim_text[:200],
                        "their_framework": framework.framework_name,
                        "guest": framework.guest_name,
                        "notes": record.notes,
                    })

            elif atype == "diverge":
                element = self.session.get(ThesisElement, record.thesis_element_id)
                framework = self.session.get(ExternalFramework, record.framework_id)
                if element and framework:
                    summary["key_divergences"].append({
                        "our_position": element.claim_text[:200],
                        "their_framework": framework.framework_name,
                        "guest": framework.guest_name,
                        "divergence_point": record.divergence_point,
                        "competing_assumptions": record.competing_assumptions,
                    })

        # Keep top 5 of each
        summary["key_agreements"] = summary["key_agreements"][:5]
        summary["key_divergences"] = summary["key_divergences"][:5]

        return summary
