"""
Ten31 Thoughts - Daily Intelligence Brief Generator
Generates structured daily reports with first-principles verdicts and reasoning maps.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session

from ..db.models import (
    ContentItem, ExternalFramework, ThesisElement, BlindSpot,
    AnalysisStatus, PredictionStatus,
)
from ..llm.router import LLMRouter

logger = logging.getLogger(__name__)


# Classical axioms for reasoning evaluation
CLASSICAL_AXIOMS = {
    "first_principles": "Derives conclusions from fundamental truths, not analogies or conventions",
    "falsifiability": "Makes claims that can be proven wrong with specific evidence",
    "causal_mechanism": "Explains the 'why' through clear cause-effect chains",
    "time_horizon_clarity": "Specifies when predictions should materialize",
    "alternative_consideration": "Acknowledges and addresses competing hypotheses",
    "data_skepticism": "Questions official statistics and considers measurement issues",
    "incentive_analysis": "Considers what actors are incentivized to do, not just say",
    "second_order_effects": "Traces consequences beyond the immediate impact",
    "base_rate_awareness": "Anchors predictions in historical frequencies",
    "position_transparency": "Discloses personal stakes that might bias analysis",
}


class DailyBriefGenerator:
    """
    Generates the daily intelligence brief by analyzing recent content
    through a first-principles lens and tracking reasoning quality.
    """

    def __init__(self, llm: LLMRouter, session: Session):
        self.llm = llm
        self.session = session

    async def generate_daily_brief(self, lookback_hours: int = 24) -> dict:
        """
        Generate the complete daily intelligence brief.

        Returns structured JSON with:
        - verdicts: first-principles verdicts on each new piece of content
        - reasoning_map: which classical axioms were triggered
        - guest_scorecards: cumulative scores for guests in new content
        - prediction_tracker: new predictions + resolved predictions
        - blind_spot_radar: what nobody is talking about
        - convergence_signals: where new content agrees/diverges with thesis
        """
        since = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)

        # Get recently analyzed content
        recent_items = self.session.execute(
            select(ContentItem)
            .where(and_(
                ContentItem.analyzed_at >= since,
                ContentItem.analysis_status == AnalysisStatus.COMPLETE,
            ))
            .order_by(ContentItem.analyzed_at.desc())
        ).scalars().all()

        logger.info(f"Generating daily brief for {len(recent_items)} items since {since}")

        # Build each section
        verdicts = await self._build_verdicts(recent_items)
        reasoning_map = self._build_reasoning_map(recent_items)
        guest_scorecards = self._build_guest_scorecards(recent_items)
        prediction_tracker = self._build_prediction_tracker(since)
        blind_spot_radar = self._build_blind_spot_radar(since)
        convergence_signals = self._build_convergence_signals(recent_items)

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "lookback_hours": lookback_hours,
            "items_analyzed": len(recent_items),
            "verdicts": verdicts,
            "reasoning_map": reasoning_map,
            "guest_scorecards": guest_scorecards,
            "prediction_tracker": prediction_tracker,
            "blind_spot_radar": blind_spot_radar,
            "convergence_signals": convergence_signals,
        }

    async def _build_verdicts(self, items: list[ContentItem]) -> list[dict]:
        """Generate first-principles verdicts for each content item."""
        verdicts = []

        for item in items:
            try:
                verdict = await self._generate_verdict(item)
                verdicts.append(verdict)
            except Exception as e:
                logger.error(f"Failed to generate verdict for {item.item_id}: {e}")
                verdicts.append({
                    "item_id": item.item_id,
                    "title": item.title,
                    "error": str(e),
                })

        return verdicts

    async def _generate_verdict(self, item: ContentItem) -> dict:
        """Generate a first-principles verdict for a single content item."""
        # Gather context
        frameworks = list(item.external_frameworks)
        thesis_elements = list(item.thesis_elements)
        blind_spots = list(item.blind_spots)

        context_parts = []
        if frameworks:
            context_parts.append(f"Frameworks extracted: {len(frameworks)}")
            for fw in frameworks[:5]:
                context_parts.append(f"- {fw.framework_name} (guest: {fw.guest_name}, score: {fw.reasoning_score})")
        if thesis_elements:
            context_parts.append(f"Thesis elements: {len(thesis_elements)}")
            for te in thesis_elements[:5]:
                context_parts.append(f"- {te.claim_text[:100]}... (topic: {te.topic})")
        if blind_spots:
            context_parts.append(f"Blind spots detected: {len(blind_spots)}")

        context = "\n".join(context_parts) if context_parts else "No analysis data available"

        prompt = f"""Analyze this content through a first-principles lens.

TITLE: {item.title}
DATE: {item.published_date.isoformat() if item.published_date else 'Unknown'}
CONTENT SUMMARY: {item.summary or item.content_text[:500] if item.content_text else 'No content'}

ANALYSIS DATA:
{context}

CLASSICAL AXIOMS TO EVALUATE:
{chr(10).join(f'- {k}: {v}' for k, v in CLASSICAL_AXIOMS.items())}

Provide a verdict in JSON format:
{{
    "reasoning_grade": "A/B/C/D/F based on classical axiom adherence",
    "axioms_demonstrated": ["list of axiom keys that were clearly demonstrated"],
    "axioms_violated": ["list of axiom keys that were violated or missing"],
    "key_vulnerability": "the weakest point in the reasoning",
    "strongest_insight": "the most valuable takeaway",
    "thesis_convergence": "agree/partial/diverge/unrelated - how this aligns with Ten31 thesis",
    "actionable_signal": "what, if anything, should be acted upon",
    "confidence": 0.0-1.0
}}"""

        try:
            result = await self.llm.complete_json(
                task="analysis",
                messages=[{"role": "user", "content": prompt}],
                system="You are a rigorous first-principles analyst. Evaluate reasoning quality objectively."
            )

            return {
                "item_id": item.item_id,
                "title": item.title,
                "published_date": item.published_date.isoformat() if item.published_date else None,
                "feed_name": item.feed.display_name if item.feed else None,
                "verdict": result,
            }
        except Exception as e:
            logger.error(f"Verdict generation failed for {item.item_id}: {e}")
            raise

    def _build_reasoning_map(self, items: list[ContentItem]) -> dict:
        """Map which classical axioms are being triggered across all content."""
        axiom_counts = {k: 0 for k in CLASSICAL_AXIOMS.keys()}
        axiom_examples = {k: [] for k in CLASSICAL_AXIOMS.keys()}

        for item in items:
            for fw in item.external_frameworks:
                # Use reasoning_notes to infer axiom adherence
                notes = (fw.reasoning_notes or "").lower()
                for axiom in CLASSICAL_AXIOMS.keys():
                    # Simple keyword matching - could be enhanced with LLM
                    if axiom.replace("_", " ") in notes or axiom.replace("_", "-") in notes:
                        axiom_counts[axiom] += 1
                        if len(axiom_examples[axiom]) < 3:
                            axiom_examples[axiom].append({
                                "framework": fw.framework_name,
                                "guest": fw.guest_name,
                                "item_title": item.title,
                            })

        return {
            "axiom_frequency": axiom_counts,
            "total_frameworks_analyzed": sum(len(item.external_frameworks) for item in items),
            "most_common": sorted(axiom_counts.items(), key=lambda x: -x[1])[:5],
            "least_common": sorted(axiom_counts.items(), key=lambda x: x[1])[:5],
            "examples": axiom_examples,
        }

    def _build_guest_scorecards(self, recent_items: list[ContentItem]) -> list[dict]:
        """Build scorecards for guests appearing in recent content."""
        guest_names = set()
        for item in recent_items:
            for fw in item.external_frameworks:
                if fw.guest_name:
                    guest_names.add(fw.guest_name)

        scorecards = []
        for guest in guest_names:
            # Get ALL frameworks by this guest (not just recent)
            all_frameworks = self.session.execute(
                select(ExternalFramework)
                .where(ExternalFramework.guest_name == guest)
                .order_by(ExternalFramework.created_at.desc())
            ).scalars().all()

            scores = [fw.reasoning_score for fw in all_frameworks if fw.reasoning_score is not None]
            appearances = len(set(fw.item_id for fw in all_frameworks))

            # Get their recent frameworks
            recent_fws = [
                fw for fw in all_frameworks
                if fw.item_id in [item.item_id for item in recent_items]
            ]

            scorecards.append({
                "guest_name": guest,
                "total_appearances": appearances,
                "total_frameworks": len(all_frameworks),
                "avg_reasoning_score": round(sum(scores) / len(scores), 3) if scores else None,
                "best_score": round(max(scores), 3) if scores else None,
                "worst_score": round(min(scores), 3) if scores else None,
                "recent_frameworks": [
                    {
                        "name": fw.framework_name,
                        "score": fw.reasoning_score,
                        "alignment": fw.thesis_alignment.value if fw.thesis_alignment else "unrelated",
                    }
                    for fw in recent_fws[:5]
                ],
            })

        return sorted(scorecards, key=lambda x: -(x["avg_reasoning_score"] or 0))

    def _build_prediction_tracker(self, since: datetime) -> dict:
        """Track new and recently resolved predictions."""
        # New predictions logged
        new_predictions = self.session.execute(
            select(ThesisElement)
            .where(and_(
                ThesisElement.is_prediction == True,
                ThesisElement.created_at >= since,
            ))
        ).scalars().all()

        # Recently validated/invalidated
        recently_resolved = self.session.execute(
            select(ThesisElement)
            .where(and_(
                ThesisElement.is_prediction == True,
                ThesisElement.prediction_status.in_([
                    PredictionStatus.VALIDATED,
                    PredictionStatus.INVALIDATED,
                    PredictionStatus.PARTIALLY_VALIDATED,
                ]),
            ))
            .order_by(ThesisElement.created_at.desc())
            .limit(10)
        ).scalars().all()

        # Overall accuracy
        total_resolved = self.session.execute(
            select(func.count(ThesisElement.element_id))
            .where(and_(
                ThesisElement.is_prediction == True,
                ThesisElement.prediction_status.in_([
                    PredictionStatus.VALIDATED,
                    PredictionStatus.INVALIDATED,
                ]),
            ))
        ).scalar() or 0

        validated_count = self.session.execute(
            select(func.count(ThesisElement.element_id))
            .where(and_(
                ThesisElement.is_prediction == True,
                ThesisElement.prediction_status == PredictionStatus.VALIDATED,
            ))
        ).scalar() or 0

        pending_count = self.session.execute(
            select(func.count(ThesisElement.element_id))
            .where(and_(
                ThesisElement.is_prediction == True,
                ThesisElement.prediction_status == PredictionStatus.PENDING,
            ))
        ).scalar() or 0

        return {
            "new_predictions_today": [
                {
                    "claim": p.claim_text[:200],
                    "topic": p.topic,
                    "conviction": p.conviction.value if p.conviction else "moderate",
                    "horizon": p.prediction_horizon,
                }
                for p in new_predictions
            ],
            "recently_resolved": [
                {
                    "claim": p.claim_text[:200],
                    "topic": p.topic,
                    "status": p.prediction_status.value if p.prediction_status else "pending",
                    "outcome": p.prediction_outcome,
                }
                for p in recently_resolved
            ],
            "accuracy_rate": round(validated_count / total_resolved, 3) if total_resolved > 0 else None,
            "total_validated": validated_count,
            "total_invalidated": total_resolved - validated_count,
            "total_pending": pending_count,
        }

    def _build_blind_spot_radar(self, since: datetime) -> dict:
        """What's not being talked about that should be."""
        recent_spots = self.session.execute(
            select(BlindSpot)
            .where(BlindSpot.created_at >= since)
            .order_by(BlindSpot.severity.desc())
        ).scalars().all()

        # Systematic blind spots (topics with multiple detections)
        systematic = self.session.execute(
            select(BlindSpot.topic, func.count(BlindSpot.spot_id))
            .group_by(BlindSpot.topic)
            .having(func.count(BlindSpot.spot_id) >= 3)
            .order_by(func.count(BlindSpot.spot_id).desc())
        ).all()

        return {
            "new_today": [
                {
                    "topic": s.topic,
                    "description": s.description[:200],
                    "severity": s.severity,
                    "source_type": s.source_type,
                }
                for s in recent_spots[:10]
            ],
            "systematic": [
                {"topic": topic, "detection_count": count}
                for topic, count in systematic[:10]
            ],
        }

    def _build_convergence_signals(self, items: list[ContentItem]) -> dict:
        """Where new content agrees or diverges with the Ten31 thesis."""
        agreements = []
        divergences = []

        for item in items:
            for fw in item.external_frameworks:
                if fw.thesis_alignment and fw.thesis_alignment.value == "agree":
                    agreements.append({
                        "framework": fw.framework_name,
                        "guest": fw.guest_name,
                        "score": fw.reasoning_score,
                        "notes": fw.alignment_notes[:200] if fw.alignment_notes else None,
                    })
                elif fw.thesis_alignment and fw.thesis_alignment.value == "diverge":
                    divergences.append({
                        "framework": fw.framework_name,
                        "guest": fw.guest_name,
                        "score": fw.reasoning_score,
                        "notes": fw.alignment_notes[:200] if fw.alignment_notes else None,
                    })

        return {
            "agreements": agreements,
            "divergences": divergences,
            "agreement_count": len(agreements),
            "divergence_count": len(divergences),
        }
