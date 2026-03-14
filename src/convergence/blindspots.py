"""
Ten31 Thoughts - Mutual Blind Spot Detector
Identifies topics that BOTH our thesis and external sources systematically miss.
Cross-references gaps against the macro event landscape.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_

from ..db.models import (
    ContentItem, ThesisElement, ExternalFramework, BlindSpot,
    Feed, FeedCategory, FeedStatus, AnalysisStatus, gen_id
)
from ..llm.router import LLMRouter

logger = logging.getLogger(__name__)


# Comprehensive macro topic checklist
MACRO_TOPIC_CHECKLIST = [
    "monetary_policy",       # Fed decisions, rate path, balance sheet
    "fiscal_policy",         # Deficits, debt issuance, spending bills, tariffs
    "labor_market",          # Employment data, wage dynamics, participation
    "inflation_dynamics",    # CPI/PCE trends, expectations, supply vs demand
    "credit_conditions",     # Spreads, lending standards, default rates, CLOs
    "energy_markets",        # Oil, nat gas, renewables, OPEC decisions
    "currency_dynamics",     # DXY, EUR, JPY, CNY, EM currencies
    "geopolitical_risks",    # Conflict, sanctions, trade relationships, elections
    "financial_plumbing",    # Repo, collateral, shadow banking, liquidity
    "sovereign_debt",        # UST dynamics, JGB, global bond markets
    "housing_market",        # Existing/new home sales, mortgage rates, inventory
    "consumer_health",       # Sentiment, spending, savings rate, delinquencies
    "corporate_earnings",    # S&P earnings, margins, guidance trends
    "technology_disruption", # AI, automation, productivity implications
    "demographics",          # Immigration, aging, labor force structural shifts
    "commodity_supply",      # Metals, agriculture, supply chain constraints
    "positioning_sentiment", # Market positioning, VIX, put/call, fund flows
    "regulatory_changes",    # Financial regulation, crypto regulation, antitrust
    "central_bank_global",   # BOJ, ECB, PBOC, BOE policy divergence
    "private_credit",        # Private debt, leveraged loans, PE activity
]


BLIND_SPOT_SYSTEM = """You are a macro intelligence analyst. You have been given:
1. A list of topics that were discussed in our internal newsletter over the past week
2. A list of topics discussed by external interview guests over the past week
3. A comprehensive checklist of macro topics that SHOULD be monitored

Your job is to identify MUTUAL BLIND SPOTS — important macro topics that NEITHER
our newsletter NOR external guests are discussing, but that current macro conditions
suggest deserve attention.

For each blind spot, assess:
1. topic: The macro area being missed
2. description: Why this topic matters right now (2-3 sentences)
3. current_relevance: What specific developments make this important NOW?
4. potential_impact: What could happen if this continues to be ignored?
5. severity: "high" (could materially affect key thesis), "medium" (adds important nuance), "low" (worth monitoring)
6. recommended_action: What should we be watching or researching?

Only flag topics that are genuinely being under-discussed relative to their current
importance. Don't flag topics that are naturally lower priority right now.

Respond ONLY with a JSON array. No preamble."""

BLIND_SPOT_USER = """Identify mutual blind spots:

TOPICS COVERED BY OUR NEWSLETTER (last {days} days):
{our_topics}

TOPICS COVERED BY EXTERNAL GUESTS (last {days} days):
{external_topics}

MACRO TOPIC CHECKLIST (comprehensive list of topics that should be monitored):
{checklist}

Current date: {today}

What important macro topics are NEITHER side covering that they should be?"""


class BlindSpotDetector:
    """
    Detects mutual blind spots — topics that both our thesis and external
    sources systematically miss but that current macro conditions suggest matter.
    """

    def __init__(self, llm: LLMRouter, session: Session):
        self.llm = llm
        self.session = session

    async def detect_mutual_blind_spots(
        self,
        lookback_days: int = 14,
    ) -> list[BlindSpot]:
        """
        Run mutual blind spot detection.
        Compares discussed topics from both sources against the macro checklist.
        """
        logger.info(f"Running mutual blind spot detection (lookback: {lookback_days} days)")

        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

        # Gather topics discussed in our thesis
        our_topics = self._get_thesis_topics(cutoff)

        # Gather topics discussed by external sources
        external_topics = self._get_external_topics(cutoff)

        if not our_topics and not external_topics:
            logger.info("No recent content for blind spot detection")
            return []

        # Format for the LLM
        our_topics_str = self._format_topic_list(our_topics, "Our newsletter")
        external_topics_str = self._format_topic_list(external_topics, "External guests")
        checklist_str = "\n".join(f"- {topic}" for topic in MACRO_TOPIC_CHECKLIST)

        prompt = BLIND_SPOT_USER.format(
            days=lookback_days,
            our_topics=our_topics_str,
            external_topics=external_topics_str,
            checklist=checklist_str,
            today=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        )

        result = await self.llm.complete_json(
            task="synthesis",
            messages=[{"role": "user", "content": prompt}],
            system=BLIND_SPOT_SYSTEM,
        )

        if not isinstance(result, list):
            result = result.get("blind_spots", result.get("mutual_blind_spots", []))

        spots = []
        for raw in result:
            try:
                topic = raw.get("topic", "").strip()
                description = raw.get("description", "").strip()
                if not topic or not description:
                    continue

                severity = raw.get("severity", "medium").lower()
                if severity not in ("low", "medium", "high"):
                    severity = "medium"

                # Build detailed description
                full_desc = description
                relevance = raw.get("current_relevance", "")
                if relevance:
                    full_desc += f"\n\nCurrent relevance: {relevance}"
                impact = raw.get("potential_impact", "")
                if impact:
                    full_desc += f"\n\nPotential impact: {impact}"
                action = raw.get("recommended_action", "")
                if action:
                    full_desc += f"\n\nRecommended: {action}"

                # Create blind spot record (not attached to a specific content item)
                # We use a sentinel item_id for mutual blind spots
                spot = BlindSpot(
                    spot_id=gen_id(),
                    item_id=self._get_sentinel_item_id(),
                    topic=topic[:200],
                    description=full_desc[:5000],
                    event_date=datetime.now(timezone.utc),
                    severity=severity,
                    source_type="mutual",
                )

                self.session.add(spot)
                spots.append(spot)

            except Exception as e:
                logger.warning(f"Failed to parse blind spot: {e}")
                continue

        self.session.commit()
        logger.info(f"Detected {len(spots)} mutual blind spots")
        return spots

    def get_systematic_blind_spots(self, lookback_days: int = 90) -> list[dict]:
        """
        Identify topics that have been flagged as blind spots REPEATEDLY
        over the lookback period. These are systematic gaps in coverage.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

        # Count blind spot occurrences by topic
        topic_counts = self.session.execute(
            select(BlindSpot.topic, func.count(BlindSpot.spot_id))
            .where(and_(
                BlindSpot.created_at >= cutoff,
                BlindSpot.source_type == "mutual",
            ))
            .group_by(BlindSpot.topic)
            .having(func.count(BlindSpot.spot_id) >= 2)
            .order_by(func.count(BlindSpot.spot_id).desc())
        ).all()

        systematic = []
        for topic, count in topic_counts:
            # Get the most recent description
            latest = self.session.execute(
                select(BlindSpot)
                .where(and_(
                    BlindSpot.topic == topic,
                    BlindSpot.source_type == "mutual",
                ))
                .order_by(BlindSpot.created_at.desc())
                .limit(1)
            ).scalar_one_or_none()

            systematic.append({
                "topic": topic,
                "occurrences": count,
                "latest_description": latest.description if latest else "",
                "latest_severity": latest.severity if latest else "medium",
            })

        return systematic

    def get_blind_spot_summary(self, days: int = 30) -> dict:
        """Get a summary for the weekly briefing."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        # Recent blind spots
        recent = self.session.execute(
            select(BlindSpot)
            .where(BlindSpot.created_at >= cutoff)
            .order_by(BlindSpot.severity.desc(), BlindSpot.created_at.desc())
            .limit(20)
        ).scalars().all()

        by_source = {"mutual": [], "external": [], "our_thesis": []}
        for spot in recent:
            by_source.get(spot.source_type, []).append({
                "topic": spot.topic,
                "description": spot.description[:300],
                "severity": spot.severity,
            })

        # Systematic blind spots
        systematic = self.get_systematic_blind_spots()

        return {
            "recent_mutual": by_source.get("mutual", [])[:5],
            "recent_external": by_source.get("external", [])[:5],
            "systematic": systematic[:5],
            "total_mutual": len(by_source.get("mutual", [])),
            "total_external": len(by_source.get("external", [])),
        }

    # ─── Helpers ───

    def _get_thesis_topics(self, since: datetime) -> dict[str, list[str]]:
        """Get topics discussed in our thesis content since a date."""
        elements = self.session.execute(
            select(ThesisElement.topic, ThesisElement.claim_text)
            .join(ContentItem)
            .join(Feed)
            .where(and_(
                Feed.category == FeedCategory.OUR_THESIS,
                ContentItem.published_date >= since,
            ))
        ).all()

        topics = {}
        for topic, claim in elements:
            if topic not in topics:
                topics[topic] = []
            topics[topic].append(claim[:150])

        return topics

    def _get_external_topics(self, since: datetime) -> dict[str, list[str]]:
        """Get topics discussed in external content since a date."""
        frameworks = self.session.execute(
            select(ExternalFramework.framework_name, ExternalFramework.description,
                   ExternalFramework.guest_name)
            .join(ContentItem)
            .join(Feed)
            .where(and_(
                Feed.category == FeedCategory.EXTERNAL_INTERVIEW,
                ContentItem.published_date >= since,
            ))
        ).all()

        topics = {}
        for name, desc, guest in frameworks:
            key = name[:100]
            if key not in topics:
                topics[key] = []
            topics[key].append(f"{guest}: {desc[:150]}" if guest else desc[:150])

        return topics

    def _format_topic_list(self, topics: dict, source_name: str) -> str:
        """Format a topic dict into a readable string for the LLM."""
        if not topics:
            return f"No content from {source_name} in this period."

        lines = []
        for topic, claims in topics.items():
            lines.append(f"- {topic}:")
            for claim in claims[:3]:  # Max 3 examples per topic
                lines.append(f"    * {claim}")

        return "\n".join(lines)

    def _get_sentinel_item_id(self) -> str:
        """
        Get or create a sentinel content item for mutual blind spots
        that aren't attached to any specific source content.
        """
        sentinel_id = "sentinel_mutual_blindspots"

        existing = self.session.get(ContentItem, sentinel_id)
        if existing:
            return sentinel_id

        # Find or create a sentinel feed
        sentinel_feed_id = "sentinel_system_feed"
        feed = self.session.get(Feed, sentinel_feed_id)
        if not feed:
            feed = Feed(
                feed_id=sentinel_feed_id,
                url="internal://system",
                category=FeedCategory.OUR_THESIS,
                display_name="System (Internal)",
                status=FeedStatus.ACTIVE,
            )
            self.session.add(feed)
            self.session.flush()

        item = ContentItem(
            item_id=sentinel_id,
            feed_id=sentinel_feed_id,
            url="internal://mutual-blind-spots",
            title="Mutual Blind Spot Detections",
            content_text="Container for mutual blind spot records",
            analysis_status=AnalysisStatus.COMPLETE,
        )
        self.session.add(item)
        self.session.flush()

        return sentinel_id
