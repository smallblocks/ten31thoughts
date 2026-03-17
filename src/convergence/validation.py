"""
Ten31 Thoughts - Prediction Validation Tracker
Tracks predictions from both thesis content and external frameworks,
scores them against outcomes, and maintains rolling scorecards.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_, or_

from ..db.models import (
    ThesisElement, ExternalFramework, ContentItem, Feed,
    FeedCategory, PredictionStatus, ConvictionLevel, gen_id
)
from ..llm.router import LLMRouter
from ..llm.date_context import get_date_context

logger = logging.getLogger(__name__)

_DATE_CTX = get_date_context()

VALIDATION_SYSTEM = _DATE_CTX + """You are a prediction accuracy analyst. Given a prediction that was made
on a specific date, and your knowledge of what actually happened in the macro landscape
since then, determine whether the prediction was validated, invalidated, or is still pending.

Evaluate based on:
1. Did the predicted outcome occur?
2. Did it occur within the stated time horizon?
3. Were the stated base assumptions correct?

Classify as:
- "validated": The prediction substantially came true
- "partially_validated": The direction was right but magnitude, timing, or mechanism differed
- "invalidated": The opposite occurred or the prediction clearly failed
- "pending": Not enough time has passed or the outcome is still unclear
- "expired": The time horizon has passed without a clear resolution either way

Provide:
1. status: One of the above
2. outcome_description: What actually happened (2-3 sentences)
3. accuracy_notes: How close was the prediction to reality?
4. score: 0.0 to 1.0 (0 = completely wrong, 0.5 = directionally right but off on details, 1.0 = nailed it)

Respond ONLY with a JSON object. No preamble."""

VALIDATION_USER = """Evaluate this prediction:

Prediction made on {date}:
"{prediction_text}"

Testable outcome: {testable_outcome}
Time horizon: {time_horizon}
Source: {source}

Today's date: {today}
Time elapsed since prediction: {elapsed}

Based on what has happened in the macro landscape since this prediction was made,
how did it turn out?"""


class ValidationTracker:
    """
    Tracks and validates predictions from both thesis content and external frameworks.
    Produces rolling scorecards for the weekly briefing.
    """

    def __init__(self, llm: LLMRouter, session: Session):
        self.llm = llm
        self.session = session

    async def validate_due_predictions(self, min_age_days: int = 30) -> dict:
        """
        Find predictions old enough to evaluate and run validation.
        Only evaluates predictions that are still in 'pending' status
        and are at least min_age_days old.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=min_age_days)

        # Get pending thesis predictions
        thesis_preds = self.session.execute(
            select(ThesisElement)
            .join(ContentItem)
            .where(and_(
                ThesisElement.is_prediction == True,
                ThesisElement.prediction_status == PredictionStatus.PENDING,
                ContentItem.published_date <= cutoff,
            ))
            .order_by(ContentItem.published_date.asc())
            .limit(20)
        ).scalars().all()

        stats = {
            "thesis_evaluated": 0,
            "external_evaluated": 0,
            "validated": 0,
            "partially_validated": 0,
            "invalidated": 0,
            "expired": 0,
            "still_pending": 0,
        }

        # Validate thesis predictions
        for pred in thesis_preds:
            item = self.session.get(ContentItem, pred.item_id)
            result = await self._validate_thesis_prediction(pred, item)
            if result:
                stats["thesis_evaluated"] += 1
                stats[result] = stats.get(result, 0) + 1

        # Validate external predictions embedded in frameworks
        frameworks_with_preds = self.session.execute(
            select(ExternalFramework)
            .join(ContentItem)
            .where(and_(
                ExternalFramework.predictions.isnot(None),
                ContentItem.published_date <= cutoff,
            ))
            .limit(20)
        ).scalars().all()

        for fw in frameworks_with_preds:
            item = self.session.get(ContentItem, fw.item_id)
            evaluated = await self._validate_framework_predictions(fw, item)
            stats["external_evaluated"] += evaluated

        self.session.commit()

        logger.info(
            f"Validation complete: {stats['thesis_evaluated']} thesis, "
            f"{stats['external_evaluated']} external predictions evaluated"
        )
        return stats

    async def _validate_thesis_prediction(
        self, element: ThesisElement, item: Optional[ContentItem]
    ) -> Optional[str]:
        """Validate a single thesis prediction."""
        try:
            pub_date = item.published_date if item else None
            if not pub_date:
                return None

            today = datetime.now(timezone.utc)
            elapsed = today - pub_date
            elapsed_str = f"{elapsed.days} days ({elapsed.days // 30} months)"

            prompt = VALIDATION_USER.format(
                date=pub_date.strftime("%Y-%m-%d"),
                prediction_text=element.claim_text,
                testable_outcome=element.prediction_outcome or "Not specifically defined",
                time_horizon=element.prediction_horizon or "Not specified",
                source="Ten31 Timestamp (our thesis)",
                today=today.strftime("%Y-%m-%d"),
                elapsed=elapsed_str,
            )

            result = await self.llm.complete_json(
                task="analysis",
                messages=[{"role": "user", "content": prompt}],
                system=VALIDATION_SYSTEM,
            )

            status_str = result.get("status", "pending")
            status_map = {
                "validated": PredictionStatus.VALIDATED,
                "partially_validated": PredictionStatus.PARTIALLY_VALIDATED,
                "invalidated": PredictionStatus.INVALIDATED,
                "expired": PredictionStatus.EXPIRED,
                "pending": PredictionStatus.PENDING,
            }

            new_status = status_map.get(status_str, PredictionStatus.PENDING)
            element.prediction_status = new_status

            # Store outcome description
            outcome = result.get("outcome_description", "")
            if outcome:
                element.prediction_outcome = (
                    (element.prediction_outcome or "") + f"\n[Validated {today.strftime('%Y-%m-%d')}]: {outcome}"
                )[:3000]

            self.session.flush()
            return status_str

        except Exception as e:
            logger.warning(f"Failed to validate prediction {element.element_id}: {e}")
            return None

    async def _validate_framework_predictions(
        self, framework: ExternalFramework, item: Optional[ContentItem]
    ) -> int:
        """Validate predictions embedded in an external framework."""
        if not framework.predictions or not isinstance(framework.predictions, list):
            return 0

        pub_date = item.published_date if item else None
        if not pub_date:
            return 0

        today = datetime.now(timezone.utc)
        elapsed = today - pub_date
        elapsed_str = f"{elapsed.days} days ({elapsed.days // 30} months)"

        evaluated = 0
        updated_preds = []

        for pred in framework.predictions:
            if not isinstance(pred, dict):
                updated_preds.append(pred)
                continue

            if pred.get("status", "pending") != "pending":
                updated_preds.append(pred)
                continue

            try:
                prompt = VALIDATION_USER.format(
                    date=pub_date.strftime("%Y-%m-%d"),
                    prediction_text=pred.get("text", ""),
                    testable_outcome=pred.get("reasoning", "Not specified"),
                    time_horizon=pred.get("time_horizon", "Not specified"),
                    source=f"{framework.guest_name} ({framework.framework_name})",
                    today=today.strftime("%Y-%m-%d"),
                    elapsed=elapsed_str,
                )

                result = await self.llm.complete_json(
                    task="analysis",
                    messages=[{"role": "user", "content": prompt}],
                    system=VALIDATION_SYSTEM,
                )

                pred["status"] = result.get("status", "pending")
                pred["outcome"] = result.get("outcome_description", "")
                pred["score"] = result.get("score", 0.5)
                pred["validated_at"] = today.isoformat()
                evaluated += 1

            except Exception as e:
                logger.warning(f"Failed to validate framework prediction: {e}")

            updated_preds.append(pred)

        framework.predictions = updated_preds
        self.session.flush()
        return evaluated

    # ─── Scorecard Generation ───

    def generate_scorecard(self, days: Optional[int] = None) -> dict:
        """
        Generate prediction accuracy scorecards.
        Returns separate scorecards for thesis predictions and external guests.
        """
        # Thesis predictions scorecard
        thesis_query = select(ThesisElement).where(
            ThesisElement.is_prediction == True
        )
        if days:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            thesis_query = thesis_query.join(ContentItem).where(
                ContentItem.published_date >= cutoff
            )

        thesis_preds = self.session.execute(thesis_query).scalars().all()

        thesis_card = self._compute_scorecard(thesis_preds, "Ten31 Timestamp")

        # External guest scorecards
        guest_cards = {}
        frameworks = self.session.execute(
            select(ExternalFramework)
            .where(ExternalFramework.predictions.isnot(None))
        ).scalars().all()

        for fw in frameworks:
            if not fw.predictions or not isinstance(fw.predictions, list):
                continue
            guest = fw.guest_name or "Unknown"
            if guest not in guest_cards:
                guest_cards[guest] = {
                    "total": 0, "validated": 0, "partially_validated": 0,
                    "invalidated": 0, "expired": 0, "pending": 0,
                    "avg_score": 0, "scores": [],
                }

            for pred in fw.predictions:
                if not isinstance(pred, dict):
                    continue
                status = pred.get("status", "pending")
                guest_cards[guest]["total"] += 1
                guest_cards[guest][status] = guest_cards[guest].get(status, 0) + 1
                score = pred.get("score")
                if score is not None:
                    guest_cards[guest]["scores"].append(float(score))

        # Compute averages
        for guest, card in guest_cards.items():
            if card["scores"]:
                card["avg_score"] = round(sum(card["scores"]) / len(card["scores"]), 3)
            del card["scores"]

        # Sort guests by accuracy
        sorted_guests = sorted(
            guest_cards.items(),
            key=lambda x: x[1].get("avg_score", 0),
            reverse=True,
        )

        return {
            "thesis": thesis_card,
            "external_guests": dict(sorted_guests),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "lookback_days": days,
        }

    def _compute_scorecard(self, predictions: list[ThesisElement], source: str) -> dict:
        """Compute accuracy scorecard from a list of thesis prediction elements."""
        card = {
            "source": source,
            "total": len(predictions),
            "validated": 0,
            "partially_validated": 0,
            "invalidated": 0,
            "expired": 0,
            "pending": 0,
            "by_conviction": {},
            "by_topic": {},
        }

        for pred in predictions:
            status = pred.prediction_status.value if pred.prediction_status else "pending"
            card[status] = card.get(status, 0) + 1

            # Track by conviction level
            conv = pred.conviction.value if pred.conviction else "moderate"
            if conv not in card["by_conviction"]:
                card["by_conviction"][conv] = {"total": 0, "validated": 0, "invalidated": 0}
            card["by_conviction"][conv]["total"] += 1
            if status in ("validated", "partially_validated"):
                card["by_conviction"][conv]["validated"] += 1
            elif status == "invalidated":
                card["by_conviction"][conv]["invalidated"] += 1

            # Track by topic
            topic = pred.topic
            if topic not in card["by_topic"]:
                card["by_topic"][topic] = {"total": 0, "validated": 0, "invalidated": 0}
            card["by_topic"][topic]["total"] += 1
            if status in ("validated", "partially_validated"):
                card["by_topic"][topic]["validated"] += 1
            elif status == "invalidated":
                card["by_topic"][topic]["invalidated"] += 1

        # Compute accuracy rate (excluding pending and expired)
        resolved = card["validated"] + card["partially_validated"] + card["invalidated"]
        if resolved > 0:
            card["accuracy_rate"] = round(
                (card["validated"] + 0.5 * card["partially_validated"]) / resolved, 3
            )
        else:
            card["accuracy_rate"] = None

        return card
