"""
Ten31 Thoughts - External Analysis Pipeline
4-pass analysis for 'external_interview' content (MacroVoices, Real Vision, etc.).

Pass 1: Framework extraction (mental models, analytical lenses)
Pass 2: Prediction & conviction mapping
Pass 3: Blind spot detection
Pass 4: Reasoning quality assessment
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from ..db.models import (
    ContentItem, ExternalFramework, BlindSpot, AnalysisStatus,
    ThesisAlignment, gen_id
)
from ..llm.router import LLMRouter
from .prompts.templates import (
    EXTERNAL_PASS_1_SYSTEM, EXTERNAL_PASS_1_USER,
    EXTERNAL_PASS_2_SYSTEM, EXTERNAL_PASS_2_USER,
    EXTERNAL_PASS_3_SYSTEM, EXTERNAL_PASS_3_USER,
    EXTERNAL_PASS_4_SYSTEM, EXTERNAL_PASS_4_USER,
)

logger = logging.getLogger(__name__)


class ExternalAnalyzer:
    """
    Runs the 4-pass external analysis pipeline on interview/commentary content.
    """

    def __init__(self, llm: LLMRouter, session: Session):
        self.llm = llm
        self.session = session

    async def analyze(self, item: ContentItem) -> dict:
        """
        Run all 4 passes on a content item.
        Returns summary stats of what was extracted.
        """
        if not item.content_text or len(item.content_text.strip()) < 100:
            logger.warning(f"Skipping external analysis for {item.item_id}: content too short")
            item.analysis_status = AnalysisStatus.ERROR
            item.analysis_error = "Content too short for analysis"
            self.session.commit()
            return {"error": "Content too short"}

        item.analysis_status = AnalysisStatus.ANALYZING
        self.session.commit()

        stats = {
            "item_id": item.item_id,
            "title": item.title,
            "frameworks": 0,
            "predictions": 0,
            "blind_spots": 0,
            "reasoning_score": None,
            "first_principles_score": None,
            "errors": [],
        }

        try:
            # Pass 1: Framework extraction
            frameworks = await self._pass_1_frameworks(item)
            stats["frameworks"] = len(frameworks)

            # Pass 2: Prediction mapping
            predictions = await self._pass_2_predictions(item, frameworks)
            stats["predictions"] = predictions

            # Pass 3: Blind spot detection
            blind_spots = await self._pass_3_blind_spots(item)
            stats["blind_spots"] = len(blind_spots)

            # Pass 4: Reasoning quality (structural assessment)
            reasoning = await self._pass_4_reasoning(item, frameworks)
            stats["reasoning_score"] = reasoning

            # Pass 5: FIRST PRINCIPLES EVALUATION (primary score)
            # This is the core evaluation — does the framework align with
            # timeless principles about money, governance, and human nature?
            from .first_principles import FirstPrinciplesEvaluator
            fp_evaluator = FirstPrinciplesEvaluator(self.llm, self.session)
            for framework in frameworks:
                fp_result = await fp_evaluator.evaluate_framework(framework)
                fp_score = fp_result.get("first_principles_score")
                if fp_score is not None:
                    stats["first_principles_score"] = fp_score

            # Mark complete
            item.analysis_status = AnalysisStatus.COMPLETE
            item.analyzed_at = datetime.now(timezone.utc)
            self.session.commit()

            logger.info(
                f"External analysis complete for '{item.title[:50]}': "
                f"{stats['frameworks']} frameworks, {stats['predictions']} predictions, "
                f"{stats['blind_spots']} blind spots, reasoning={stats['reasoning_score']:.2f}"
                if stats['reasoning_score'] else
                f"External analysis complete for '{item.title[:50]}': "
                f"{stats['frameworks']} frameworks, {stats['predictions']} predictions, "
                f"{stats['blind_spots']} blind spots"
            )

        except Exception as e:
            logger.error(f"External analysis failed for {item.item_id}: {e}")
            item.analysis_status = AnalysisStatus.ERROR
            item.analysis_error = str(e)[:500]
            self.session.commit()
            stats["errors"].append(str(e))

        return stats

    async def _pass_1_frameworks(self, item: ContentItem) -> list[ExternalFramework]:
        """
        Pass 1: Extract mental models, decision frameworks, and analytical lenses.
        """
        logger.info(f"Pass 1 (frameworks): {item.title[:50]}")

        prompt = EXTERNAL_PASS_1_USER.format(
            title=item.title,
            date=item.published_date.strftime("%Y-%m-%d") if item.published_date else "Unknown",
            authors=", ".join(item.authors) if item.authors else "Unknown guest",
            content=self._truncate_content(item.content_text),
        )

        result = await self.llm.complete_json(
            task="analysis",
            messages=[{"role": "user", "content": prompt}],
            system=EXTERNAL_PASS_1_SYSTEM,
        )

        if not isinstance(result, list):
            result = result.get("frameworks", [])

        frameworks = []
        for raw in result:
            try:
                name = raw.get("framework_name", "").strip()
                if not name:
                    continue

                # Parse causal chain
                causal_chain = raw.get("causal_chain")
                if isinstance(causal_chain, str):
                    causal_chain = {"description": causal_chain}

                framework = ExternalFramework(
                    framework_id=gen_id(),
                    item_id=item.item_id,
                    framework_name=name[:500],
                    description=raw.get("description", "")[:3000],
                    guest_name=raw.get("guest_name", self._extract_guest(item))[:200],
                    causal_chain=causal_chain,
                    key_indicators=raw.get("key_indicators", []),
                    time_horizon=raw.get("time_horizon", "")[:100],
                    thesis_alignment=ThesisAlignment.UNRELATED,  # Updated by convergence engine
                    reasoning_score=None,  # Updated by Pass 4
                )

                self.session.add(framework)
                frameworks.append(framework)

            except Exception as e:
                logger.warning(f"Failed to parse framework: {e}")
                continue

        self.session.flush()
        logger.info(f"Pass 1 extracted {len(frameworks)} frameworks")
        return frameworks

    async def _pass_2_predictions(
        self, item: ContentItem, frameworks: list[ExternalFramework]
    ) -> int:
        """
        Pass 2: Extract predictions and map conviction levels.
        Attaches predictions to their parent frameworks where possible.
        """
        logger.info(f"Pass 2 (predictions): {item.title[:50]}")

        prompt = EXTERNAL_PASS_2_USER.format(
            title=item.title,
            date=item.published_date.strftime("%Y-%m-%d") if item.published_date else "Unknown",
            authors=", ".join(item.authors) if item.authors else "Unknown guest",
            content=self._truncate_content(item.content_text),
        )

        result = await self.llm.complete_json(
            task="analysis",
            messages=[{"role": "user", "content": prompt}],
            system=EXTERNAL_PASS_2_SYSTEM,
        )

        if not isinstance(result, list):
            result = result.get("predictions", [])

        count = 0
        for raw in result:
            try:
                prediction = {
                    "text": raw.get("prediction_text", "")[:1000],
                    "confidence": raw.get("confidence", "medium"),
                    "reasoning": raw.get("reasoning", "")[:1000],
                    "base_assumptions": raw.get("base_assumptions", []),
                    "time_horizon": raw.get("time_horizon", "unspecified"),
                    "hedging_language": raw.get("hedging_language", ""),
                    "status": "pending",
                }

                if not prediction["text"]:
                    continue

                # Try to attach to the most relevant framework
                best_framework = self._match_prediction_to_framework(
                    prediction["text"], frameworks
                )
                if best_framework:
                    preds = best_framework.predictions or []
                    preds.append(prediction)
                    best_framework.predictions = preds
                elif frameworks:
                    # Attach to first framework as fallback
                    preds = frameworks[0].predictions or []
                    preds.append(prediction)
                    frameworks[0].predictions = preds

                count += 1

            except Exception as e:
                logger.warning(f"Failed to parse prediction: {e}")
                continue

        self.session.flush()
        logger.info(f"Pass 2 extracted {count} predictions")
        return count

    async def _pass_3_blind_spots(self, item: ContentItem) -> list[BlindSpot]:
        """
        Pass 3: Detect what was NOT discussed that should have mattered.
        """
        logger.info(f"Pass 3 (blind spots): {item.title[:50]}")

        # Get macro events context for the episode date
        macro_events = self._get_macro_events_context(item.published_date)

        prompt = EXTERNAL_PASS_3_USER.format(
            title=item.title,
            date=item.published_date.strftime("%Y-%m-%d") if item.published_date else "Unknown",
            authors=", ".join(item.authors) if item.authors else "Unknown guest",
            macro_events=macro_events,
            content=self._truncate_content(item.content_text),
        )

        result = await self.llm.complete_json(
            task="analysis",
            messages=[{"role": "user", "content": prompt}],
            system=EXTERNAL_PASS_3_SYSTEM,
        )

        if not isinstance(result, list):
            result = result.get("blind_spots", [])

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

                spot = BlindSpot(
                    spot_id=gen_id(),
                    item_id=item.item_id,
                    topic=topic[:200],
                    description=description[:3000],
                    macro_event=raw.get("potential_impact", "")[:2000],
                    event_date=item.published_date,
                    severity=severity,
                    source_type="external",
                )

                self.session.add(spot)
                spots.append(spot)

            except Exception as e:
                logger.warning(f"Failed to parse blind spot: {e}")
                continue

        self.session.flush()
        logger.info(f"Pass 3 identified {len(spots)} blind spots")
        return spots

    async def _pass_4_reasoning(
        self, item: ContentItem, frameworks: list[ExternalFramework]
    ) -> Optional[float]:
        """
        Pass 4: Assess reasoning quality and attach scores to frameworks.
        """
        logger.info(f"Pass 4 (reasoning quality): {item.title[:50]}")

        prompt = EXTERNAL_PASS_4_USER.format(
            title=item.title,
            date=item.published_date.strftime("%Y-%m-%d") if item.published_date else "Unknown",
            authors=", ".join(item.authors) if item.authors else "Unknown guest",
            content=self._truncate_content(item.content_text),
        )

        result = await self.llm.complete_json(
            task="analysis",
            messages=[{"role": "user", "content": prompt}],
            system=EXTERNAL_PASS_4_SYSTEM,
        )

        if not isinstance(result, dict):
            logger.warning("Pass 4 returned non-dict result")
            return None

        overall = result.get("overall_score")
        if overall is None:
            # Compute from individual scores
            scores = []
            for key in ["first_principles", "probabilistic_thinking", "intellectual_honesty",
                        "evidence_quality", "internal_consistency", "track_record_awareness"]:
                val = result.get(key)
                if isinstance(val, (int, float)):
                    scores.append(float(val))
            overall = sum(scores) / len(scores) if scores else None

        if overall is not None:
            overall = max(0.0, min(1.0, float(overall)))

        # Build reasoning notes
        notes_parts = []
        strongest = result.get("strongest_aspect", "")
        weakest = result.get("weakest_aspect", "")
        if strongest:
            notes_parts.append(f"Strongest: {strongest}")
        if weakest:
            notes_parts.append(f"Weakest: {weakest}")

        reasoning_notes = " | ".join(notes_parts) if notes_parts else None

        # Attach score to all frameworks from this item
        for framework in frameworks:
            framework.reasoning_score = overall
            framework.reasoning_notes = reasoning_notes[:2000] if reasoning_notes else None

        self.session.flush()
        logger.info(f"Pass 4 overall reasoning score: {overall}")
        return overall

    # ─── Helpers ───

    def _truncate_content(self, text: str, max_chars: int = 80000) -> str:
        """Truncate content to fit within LLM context limits."""
        if len(text) <= max_chars:
            return text
        half = max_chars // 2
        return text[:half] + "\n\n[... content truncated ...]\n\n" + text[-half:]

    def _extract_guest(self, item: ContentItem) -> str:
        """Extract the guest name from item metadata."""
        if item.authors:
            # Filter out common host names
            hosts = {"erik townsend", "patrick ceresna", "macrovoices"}
            guests = [a for a in item.authors if a.lower() not in hosts]
            if guests:
                return guests[0]
            return item.authors[0]
        return "Unknown"

    def _match_prediction_to_framework(
        self, prediction_text: str, frameworks: list[ExternalFramework]
    ) -> Optional[ExternalFramework]:
        """Find the framework most relevant to a prediction using keyword overlap."""
        if not frameworks:
            return None

        pred_words = set(prediction_text.lower().split())
        best_match = None
        best_score = 0

        for fw in frameworks:
            fw_words = set(fw.description.lower().split()) if fw.description else set()
            fw_words |= set(fw.framework_name.lower().split())
            overlap = len(pred_words & fw_words)
            if overlap > best_score:
                best_score = overlap
                best_match = fw

        return best_match if best_score >= 3 else None

    def _get_macro_events_context(self, date: Optional[datetime]) -> str:
        """
        Build a context string of macro events around the given date.
        For now uses a general prompt; Phase 3 will integrate a real event timeline.
        """
        if not date:
            return "Date unknown - analyze based on topics discussed."

        date_str = date.strftime("%B %d, %Y")
        return (
            f"This interview was recorded around {date_str}. "
            f"Consider what major economic events, data releases, central bank decisions, "
            f"geopolitical developments, and market moves were occurring at that time. "
            f"Use your knowledge of the macro landscape around this date to identify "
            f"topics that should have been discussed but were not."
        )
