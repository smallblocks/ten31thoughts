"""
Ten31 Thoughts - Framework Ranker (First Principles)
Ranks frameworks by how well their underlying logic holds up against timeless
principles about money, governance, human nature, and property rights.

This is NOT an empirical track-record ranker. The question is:
"Does this framework reason from first principles, or from recent data patterns?"
"""

import logging
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import select, func

from ..db.models import (
    ExternalFramework, ContentItem, ConvergenceRecord,
    ThesisAlignment, gen_id
)
from ..llm.router import LLMRouter
from ..analysis.classical_reference import (
    CLASSICAL_DOMAINS, ALL_PRINCIPLES, format_principles_for_llm
)

logger = logging.getLogger(__name__)


RANKING_SYSTEM = """You are a classically trained macro analyst ranking analytical frameworks.

Your ranking criteria is grounded in FIRST PRINCIPLES, not empirical track records.
A framework that predicted correctly but reasons from flawed premises is ranked LOWER
than one that reasons soundly from timeless principles but hasn't played out yet.

The ranking dimensions (in order of importance):

1. FIRST PRINCIPLES GROUNDING (40%): Does the framework reason from timeless axioms
   about money, governance, human nature, and property rights? Or does it rely on
   recent patterns, technocratic assumptions, or narratives that historical experience
   contradicts?

2. INTELLECTUAL RIGOR (25%): Is the causal logic sound? Does the framework identify
   necessary conditions, acknowledge what must be true for it to work, and reason
   from causes to effects rather than pattern-matching?

3. CLASSICAL RESONANCE (20%): Does this framework echo insights that the great thinkers
   identified? Not as decoration — does it arrive at conclusions that Thucydides,
   Aristotle, Hayek, or Bastiat would recognize as sound? Reference specific parallels.

4. THESIS VALUE (15%): How useful is this framework for stress-testing or enriching
   our own thesis? Frameworks that challenge our assumptions from sound first principles
   are MORE valuable than those that confirm our views from weak premises.

For each framework provide:
- framework_name
- composite_score (0.0 to 1.0, weighted per above)
- first_principles_grounding (0.0-1.0)
- intellectual_rigor (0.0-1.0)
- classical_resonance (0.0-1.0)
- thesis_value (0.0-1.0)
- ranking_rationale: Why this framework ranks where it does, referencing specific
  principles and thinkers
- classical_parallel: The closest historical parallel or classical insight
- key_warning: If the framework violates first principles, what is the specific danger?

Respond with a JSON array sorted by composite_score descending. No preamble."""


RANKING_USER = """Rank these frameworks against first principles:

{frameworks_text}

CLASSICAL REFERENCE — the principles these frameworks are evaluated against:

{principles_summary}

Thesis alignment data:
{alignment_data}

Rank by soundness of underlying logic, not by predictive track record."""


class FrameworkRanker:
    """
    Ranks frameworks by first-principles grounding.
    The primary question: is the underlying logic sound when measured against
    timeless principles about human nature, political economy, and monetary history?
    """

    def __init__(self, llm: LLMRouter, session: Session):
        self.llm = llm
        self.session = session

    async def rank_frameworks(self, lookback_days: int = 90) -> list[dict]:
        """
        Rank all frameworks from the lookback period by first-principles grounding.
        Returns the Top 5.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

        frameworks = self.session.execute(
            select(ExternalFramework, ContentItem.published_date, ContentItem.title)
            .join(ContentItem)
            .where(ContentItem.published_date >= cutoff)
            .order_by(ContentItem.published_date.desc())
        ).all()

        if not frameworks:
            logger.info("No frameworks to rank")
            return []

        deduped = self._deduplicate_frameworks(frameworks)
        logger.info(f"Ranking {len(deduped)} unique frameworks by first principles")

        frameworks_text = self._format_frameworks(deduped)
        principles_summary = self._build_principles_summary()
        alignment_data = self._get_alignment_context(deduped)

        prompt = RANKING_USER.format(
            frameworks_text=frameworks_text,
            principles_summary=principles_summary,
            alignment_data=alignment_data,
        )

        result = await self.llm.complete_json(
            task="synthesis",
            messages=[{"role": "user", "content": prompt}],
            system=RANKING_SYSTEM,
        )

        if not isinstance(result, list):
            result = result.get("rankings", result.get("frameworks", []))

        ranked = []
        for i, item in enumerate(result[:10]):
            fw_name = item.get("framework_name", "")
            db_fw = self._find_framework_by_name(deduped, fw_name)

            entry = {
                "rank": i + 1,
                "framework_name": fw_name,
                "composite_score": round(float(item.get("composite_score", 0)), 3),
                "dimension_scores": {
                    "first_principles_grounding": item.get("first_principles_grounding", 0),
                    "intellectual_rigor": item.get("intellectual_rigor", 0),
                    "classical_resonance": item.get("classical_resonance", 0),
                    "thesis_value": item.get("thesis_value", 0),
                },
                "ranking_rationale": item.get("ranking_rationale", ""),
                "classical_parallel": item.get("classical_parallel", ""),
                "key_warning": item.get("key_warning", ""),
                "guest_name": db_fw["guest_name"] if db_fw else "Unknown",
                "source_date": db_fw["date"].isoformat() if db_fw and db_fw["date"] else None,
                "source_title": db_fw["title"] if db_fw else None,
                "thesis_alignment": db_fw["alignment"] if db_fw else "unrelated",
                "first_principles_score": db_fw["fp_score"] if db_fw else None,
                "frequency": db_fw["frequency"] if db_fw else 1,
            }
            ranked.append(entry)

        logger.info(
            "Top 5 frameworks (first principles): "
            + ", ".join(f"{r['framework_name']} ({r['composite_score']})" for r in ranked[:5])
        )
        return ranked[:5]

    def _build_principles_summary(self) -> str:
        """Build a concise summary of all domains for the ranking prompt."""
        lines = []
        for domain in CLASSICAL_DOMAINS:
            lines.append(f"\n--- {domain['title']} ---")
            for p in domain["principles"]:
                lines.append(f"  [{p['id']}] {p['axiom'][:200]}")
                lines.append(f"    Violation signals: {'; '.join(p['violation_signals'][:2])}")
        return "\n".join(lines)

    def _deduplicate_frameworks(self, frameworks: list) -> list[dict]:
        """Group by name, keep best instance."""
        groups = defaultdict(list)
        for fw, pub_date, title in frameworks:
            groups[fw.framework_name.lower().strip()].append({
                "framework": fw, "date": pub_date, "title": title,
            })

        deduped = []
        for name, instances in groups.items():
            best = max(instances, key=lambda x: (x["framework"].reasoning_score or 0, x["date"] or datetime.min))
            fw = best["framework"]
            deduped.append({
                "framework": fw,
                "date": best["date"],
                "title": best["title"],
                "guest_name": fw.guest_name,
                "alignment": fw.thesis_alignment.value if fw.thesis_alignment else "unrelated",
                "fp_score": fw.reasoning_score,  # This now holds first_principles_score
                "frequency": len(instances),
            })

        return deduped

    def _format_frameworks(self, deduped: list[dict]) -> str:
        """Format frameworks for the LLM ranking prompt."""
        lines = []
        for i, item in enumerate(deduped[:25]):
            fw = item["framework"]
            date_str = item["date"].strftime("%Y-%m-%d") if item["date"] else "Unknown"
            fp = fw.reasoning_score
            fp_str = f"{fp:.2f}" if fp is not None else "Not yet evaluated"
            lines.append(
                f"[{i+1}] {fw.framework_name} (by {fw.guest_name or 'Unknown'}, {date_str})\n"
                f"  Description: {fw.description[:400]}\n"
                f"  Causal chain: {fw.causal_chain or 'Not specified'}\n"
                f"  Time horizon: {fw.time_horizon or 'Not specified'}\n"
                f"  First principles score: {fp_str}\n"
                f"  Reasoning notes: {(fw.reasoning_notes or '')[:200]}\n"
                f"  Mentioned {item['frequency']} time(s)"
            )
        return "\n\n".join(lines)

    def _get_alignment_context(self, deduped: list[dict]) -> str:
        """Get thesis alignment data."""
        lines = []
        for item in deduped[:25]:
            fw = item["framework"]
            records = self.session.execute(
                select(ConvergenceRecord)
                .where(ConvergenceRecord.framework_id == fw.framework_id)
            ).scalars().all()

            if records:
                types = [r.alignment_type for r in records]
                type_summary = ", ".join(f"{t}: {types.count(t)}" for t in set(types))
                lines.append(f"- {fw.framework_name}: {type_summary}")
                for r in records:
                    if r.alignment_type == "diverge" and r.divergence_point:
                        lines.append(f"  Divergence: {r.divergence_point[:150]}")

        return "\n".join(lines) if lines else "No alignment data available yet."

    def _find_framework_by_name(self, deduped: list[dict], name: str) -> Optional[dict]:
        """Find framework by name (fuzzy match)."""
        name_lower = name.lower().strip()
        for item in deduped:
            if item["framework"].framework_name.lower().strip() == name_lower:
                return item
        for item in deduped:
            if name_lower in item["framework"].framework_name.lower():
                return item
            if item["framework"].framework_name.lower() in name_lower:
                return item
        return None
