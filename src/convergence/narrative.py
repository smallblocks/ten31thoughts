"""
Ten31 Thoughts - Narrative Evolution Tracker
Tracks how specific narratives evolve over time across both
our writing and external sources.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from collections import defaultdict

from sqlalchemy.orm import Session
from sqlalchemy import select, and_

from ..db.models import (
    ThesisElement, ExternalFramework, ContentItem, Feed,
    FeedCategory, gen_id
)
from ..llm.router import LLMRouter

logger = logging.getLogger(__name__)


THREADING_SYSTEM = """You are analyzing a series of thesis elements (positions/claims)
from a newsletter, ordered chronologically. Your job is to identify which elements
are part of the SAME evolving narrative thread.

A narrative thread is a recurring analytical position that develops over time.
For example: "Fed will be forced to cut" -> "Rate cuts priced in too aggressively" ->
"Labor data revisions confirm our view on cuts" are all part of a "Fed rate path" thread.

Group the elements into threads. Each thread should have:
1. thread_id: A short snake_case identifier (e.g., "fed_rate_path", "labor_data_integrity")
2. thread_name: Human-readable name
3. element_indices: Which elements (by index) belong to this thread
4. evolution_summary: How the position evolved over time (2-3 sentences)
5. direction: "strengthening" (conviction increasing), "weakening" (backing off),
   "pivoting" (changing view), "stable" (maintaining same position)

Elements can belong to only one thread. Some elements may not belong to any thread
(standalone observations).

Respond ONLY with a JSON array of thread objects. No preamble."""

THREADING_USER = """Group these thesis elements into narrative threads:

{elements}"""


class NarrativeTracker:
    """
    Tracks narrative evolution across newsletter editions and external sources.
    Identifies how positions strengthen, weaken, pivot, or remain stable over time.
    """

    def __init__(self, llm: LLMRouter, session: Session):
        self.llm = llm
        self.session = session

    async def update_thesis_threads(self, lookback_days: int = 90) -> dict:
        """
        Analyze recent thesis elements and group them into narrative threads.
        Updates the thread_id field on each ThesisElement.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

        elements = self.session.execute(
            select(ThesisElement, ContentItem.published_date, ContentItem.title)
            .join(ContentItem)
            .join(Feed)
            .where(and_(
                Feed.category == FeedCategory.OUR_THESIS,
                ContentItem.published_date >= cutoff,
                ThesisElement.is_prediction == False,
            ))
            .order_by(ContentItem.published_date.asc())
            .limit(100)
        ).all()

        if not elements:
            return {"threads": 0, "elements_threaded": 0}

        # Format elements for LLM
        formatted = []
        element_list = []
        for i, (elem, pub_date, title) in enumerate(elements):
            date_str = pub_date.strftime("%Y-%m-%d") if pub_date else "Unknown"
            formatted.append(
                f"[{i}] ({date_str}, {title[:40]})\n"
                f"  Topic: {elem.topic}\n"
                f"  Position: {elem.claim_text[:200]}"
            )
            element_list.append(elem)

        prompt = THREADING_USER.format(elements="\n\n".join(formatted))

        result = await self.llm.complete_json(
            task="analysis",
            messages=[{"role": "user", "content": prompt}],
            system=THREADING_SYSTEM,
        )

        if not isinstance(result, list):
            result = result.get("threads", [])

        stats = {"threads": len(result), "elements_threaded": 0}

        for thread in result:
            thread_id = thread.get("thread_id", "")
            if not thread_id:
                continue

            indices = thread.get("element_indices", [])
            for idx in indices:
                if isinstance(idx, int) and 0 <= idx < len(element_list):
                    element_list[idx].thread_id = thread_id
                    stats["elements_threaded"] += 1

        self.session.commit()
        logger.info(f"Threading complete: {stats['threads']} threads, {stats['elements_threaded']} elements")
        return stats

    def get_narrative_arcs(self, lookback_days: int = 180) -> list[dict]:
        """
        Get all narrative threads with their evolution arcs.
        Returns threads sorted by activity (most recent elements first).
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

        # Get all threaded elements
        elements = self.session.execute(
            select(ThesisElement, ContentItem.published_date, ContentItem.title)
            .join(ContentItem)
            .where(and_(
                ThesisElement.thread_id.isnot(None),
                ContentItem.published_date >= cutoff,
            ))
            .order_by(ContentItem.published_date.asc())
        ).all()

        # Group by thread
        threads = defaultdict(list)
        for elem, pub_date, title in elements:
            threads[elem.thread_id].append({
                "date": pub_date.isoformat() if pub_date else None,
                "source_title": title,
                "claim": elem.claim_text[:300],
                "topic": elem.topic,
                "conviction": elem.conviction.value if elem.conviction else "moderate",
            })

        # Build arcs
        arcs = []
        for thread_id, entries in threads.items():
            if len(entries) < 2:
                continue

            # Determine direction from conviction changes
            convictions = [e["conviction"] for e in entries]
            direction = self._detect_direction(convictions)

            arcs.append({
                "thread_id": thread_id,
                "entries": entries,
                "entry_count": len(entries),
                "first_date": entries[0]["date"],
                "last_date": entries[-1]["date"],
                "primary_topic": entries[-1]["topic"],
                "direction": direction,
                "latest_position": entries[-1]["claim"],
            })

        # Sort by most recent activity
        arcs.sort(key=lambda a: a["last_date"] or "", reverse=True)
        return arcs

    def get_narrative_summary(self, days: int = 30) -> dict:
        """Get narrative evolution summary for the weekly briefing."""
        arcs = self.get_narrative_arcs(lookback_days=days * 3)

        # Filter to arcs with recent activity
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        active_arcs = [a for a in arcs if a["last_date"] and a["last_date"] >= cutoff]

        strengthening = [a for a in active_arcs if a["direction"] == "strengthening"]
        weakening = [a for a in active_arcs if a["direction"] == "weakening"]
        pivoting = [a for a in active_arcs if a["direction"] == "pivoting"]
        stable = [a for a in active_arcs if a["direction"] == "stable"]

        return {
            "active_threads": len(active_arcs),
            "strengthening": [
                {"thread": a["thread_id"], "latest": a["latest_position"][:200]}
                for a in strengthening[:3]
            ],
            "weakening": [
                {"thread": a["thread_id"], "latest": a["latest_position"][:200]}
                for a in weakening[:3]
            ],
            "pivoting": [
                {"thread": a["thread_id"], "latest": a["latest_position"][:200]}
                for a in pivoting[:3]
            ],
            "total_threads": len(arcs),
        }

    def _detect_direction(self, convictions: list[str]) -> str:
        """Detect the direction of a narrative thread from conviction changes."""
        if len(convictions) < 2:
            return "stable"

        conviction_score = {"speculative": 1, "moderate": 2, "strong": 3}
        scores = [conviction_score.get(c, 2) for c in convictions]

        # Compare first half to second half
        mid = len(scores) // 2
        first_half = sum(scores[:mid]) / max(mid, 1)
        second_half = sum(scores[mid:]) / max(len(scores) - mid, 1)

        diff = second_half - first_half
        if diff > 0.5:
            return "strengthening"
        elif diff < -0.5:
            return "weakening"

        # Check for pivot: if the topic or direction changed significantly
        # (simplified: just check if there's a big swing)
        if len(scores) >= 3:
            max_score = max(scores)
            min_score = min(scores)
            if max_score - min_score >= 2:
                return "pivoting"

        return "stable"
