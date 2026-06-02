"""
Ten31 Thoughts - Extraction Engine
Extracts predictions and framework references from notes using LLM analysis.
"""

import logging
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import (
    Note, Prediction, Framework, FrameworkLink,
    gen_id,
)
from ..llm.router import LLMRouter
from .prompts.extraction import EXTRACTION_SYSTEM, EXTRACTION_USER

logger = logging.getLogger(__name__)


class ExtractionEngine:
    """
    Extracts predictions and framework references from notes.
    """

    def __init__(self, llm: LLMRouter, session: Session):
        self.llm = llm
        self.session = session

    async def extract_from_note(self, note_id: str) -> Dict[str, Any]:
        """
        Extract predictions and frameworks from a note.
        
        Returns: {
            "predictions_created": int,
            "framework_links_created": int,
            "new_frameworks_created": int,
            "note_id": str
        }
        """
        # Load the note
        note = self.session.get(Note, note_id)
        if not note:
            logger.warning(f"Note {note_id} not found")
            return {"predictions_created": 0, "framework_links_created": 0, "new_frameworks_created": 0, "note_id": note_id, "error": "Note not found"}

        # Skip if already has predictions (avoid re-extraction)
        existing_predictions = self.session.execute(
            select(Prediction).where(Prediction.note_id == note_id)
        ).scalars().all()
        
        if existing_predictions:
            logger.info(f"Note {note_id} already has {len(existing_predictions)} predictions, skipping")
            return {"predictions_created": 0, "framework_links_created": 0, "new_frameworks_created": 0, "note_id": note_id, "skipped": True}

        try:
            # Get existing frameworks
            frameworks = self._get_existing_frameworks()
            
            # Format the user prompt
            user_prompt = self._format_user_prompt(note, frameworks)
            
            # LLM call
            result = await self.llm.complete_json(
                task="analysis",
                messages=[{"role": "user", "content": user_prompt}],
                system=EXTRACTION_SYSTEM,
            )

            # Process results
            predictions_created = 0
            framework_links_created = 0
            new_frameworks_created = 0

            # Extract predictions
            for pred_data in result.get("predictions", []):
                prediction = self._create_prediction(note_id, pred_data)
                if prediction:
                    predictions_created += 1

            # Extract framework references
            for fw_ref in result.get("framework_references", []):
                framework_id, is_new = await self._ensure_framework_exists(fw_ref["framework_name"])
                if is_new:
                    new_frameworks_created += 1
                
                if framework_id:
                    link = self._create_framework_link(framework_id, note_id, None, fw_ref)
                    if link:
                        framework_links_created += 1

            self.session.commit()
            
            logger.info(f"Extracted from note {note_id}: {predictions_created} predictions, {framework_links_created} framework links, {new_frameworks_created} new frameworks")
            
            return {
                "predictions_created": predictions_created,
                "framework_links_created": framework_links_created,
                "new_frameworks_created": new_frameworks_created,
                "note_id": note_id
            }

        except Exception as e:
            logger.error(f"Extraction failed for note {note_id}: {e}")
            self.session.rollback()
            return {"predictions_created": 0, "framework_links_created": 0, "new_frameworks_created": 0, "note_id": note_id, "error": str(e)}

    def _get_existing_frameworks(self) -> List[Framework]:
        """Get all active frameworks for prompt context."""
        return self.session.execute(
            select(Framework).where(Framework.status == "active")
        ).scalars().all()

    def _format_user_prompt(self, note: Note, frameworks: List[Framework]) -> str:
        """Format the extraction prompt with note and framework data."""
        frameworks_text = "No existing frameworks."
        if frameworks:
            frameworks_text = "\\n".join([
                f"- **{fw.name}**: {fw.description[:200]}..." if len(fw.description) > 200 else f"- **{fw.name}**: {fw.description}"
                for fw in frameworks
            ])

        return EXTRACTION_USER.format(
            title=note.title or "Untitled",
            topic=note.topic or "General",
            conviction_tier=note.conviction_tier or "observation",
            body=note.body,
            frameworks=frameworks_text
        )

    def _create_prediction(self, note_id: str, pred_data: Dict[str, Any]) -> Optional[Prediction]:
        """Create a prediction from extracted data."""
        try:
            # Parse timeline if provided
            timeline_start, timeline_end = self._parse_timeline(pred_data.get("timeline"))
            
            prediction = Prediction(
                prediction_id=gen_id(),
                note_id=note_id,
                claim=pred_data["claim"],
                measurable_outcome=pred_data.get("measurable_outcome"),
                timeline=pred_data.get("timeline"),
                timeline_start=timeline_start,
                timeline_end=timeline_end,
                conviction=pred_data.get("conviction"),
                conviction_reasoning=pred_data.get("conviction_reasoning"),
                domain=pred_data.get("domain"),
                tags=[],
                status="open"
            )
            
            self.session.add(prediction)
            return prediction
            
        except Exception as e:
            logger.error(f"Failed to create prediction: {e}")
            return None

    def _parse_timeline(self, timeline_text: Optional[str]) -> tuple[Optional[datetime], Optional[datetime]]:
        """Parse natural language timeline into start/end dates."""
        if not timeline_text:
            return None, None

        timeline_lower = timeline_text.lower()
        now = datetime.now(timezone.utc)
        
        try:
            # Simple patterns - can be enhanced later
            if "q1" in timeline_lower and any(year in timeline_lower for year in ["2025", "2026", "2027"]):
                year_match = re.search(r"(202[5-9])", timeline_lower)
                if year_match:
                    year = int(year_match.group(1))
                    return datetime(year, 1, 1, tzinfo=timezone.utc), datetime(year, 3, 31, tzinfo=timezone.utc)
            
            elif "q2" in timeline_lower and any(year in timeline_lower for year in ["2025", "2026", "2027"]):
                year_match = re.search(r"(202[5-9])", timeline_lower)
                if year_match:
                    year = int(year_match.group(1))
                    return datetime(year, 4, 1, tzinfo=timezone.utc), datetime(year, 6, 30, tzinfo=timezone.utc)
            
            elif "q3" in timeline_lower and any(year in timeline_lower for year in ["2025", "2026", "2027"]):
                year_match = re.search(r"(202[5-9])", timeline_lower)
                if year_match:
                    year = int(year_match.group(1))
                    return datetime(year, 7, 1, tzinfo=timezone.utc), datetime(year, 9, 30, tzinfo=timezone.utc)
            
            elif "q4" in timeline_lower and any(year in timeline_lower for year in ["2025", "2026", "2027"]):
                year_match = re.search(r"(202[5-9])", timeline_lower)
                if year_match:
                    year = int(year_match.group(1))
                    return datetime(year, 10, 1, tzinfo=timezone.utc), datetime(year, 12, 31, tzinfo=timezone.utc)
            
            elif "by end of year" in timeline_lower or "by year-end" in timeline_lower:
                return now, datetime(now.year, 12, 31, tzinfo=timezone.utc)
            
            elif "6 months" in timeline_lower or "six months" in timeline_lower:
                from datetime import timedelta
                return now, now + timedelta(days=180)
            
            elif "12 months" in timeline_lower or "1 year" in timeline_lower or "one year" in timeline_lower:
                from datetime import timedelta
                return now, now + timedelta(days=365)
                
        except Exception as e:
            logger.warning(f"Failed to parse timeline '{timeline_text}': {e}")
            
        return None, None

    async def _ensure_framework_exists(self, framework_name: str) -> tuple[Optional[str], bool]:
        """Ensure framework exists, create if it's new. Returns (framework_id, is_new)."""
        if framework_name.startswith("new: "):
            # Create new framework
            name = framework_name[5:].strip()
            description = f"Framework extracted from note analysis: {name}"
            
            framework = Framework(
                framework_id=gen_id(),
                name=name,
                description=description,
                domain=None,
                status="active",
                evolution_log=[]
            )
            
            self.session.add(framework)
            return framework.framework_id, True
        else:
            # Look for existing framework
            existing = self.session.execute(
                select(Framework).where(Framework.name == framework_name, Framework.status == "active")
            ).scalar_one_or_none()
            
            if existing:
                return existing.framework_id, False
            else:
                logger.warning(f"Referenced framework '{framework_name}' not found and not marked as new")
                return None, False

    def _create_framework_link(self, framework_id: str, note_id: Optional[str], prediction_id: Optional[str], fw_ref: Dict[str, Any]) -> Optional[FrameworkLink]:
        """Create a framework link."""
        try:
            link = FrameworkLink(
                link_id=gen_id(),
                framework_id=framework_id,
                note_id=note_id,
                prediction_id=prediction_id,
                relation=fw_ref["relation"],
                context=fw_ref.get("context")
            )
            
            self.session.add(link)
            return link
            
        except Exception as e:
            logger.error(f"Failed to create framework link: {e}")
            return None

    async def extract_pending_notes(self) -> Dict[str, Any]:
        """Extract from all notes that don't have predictions yet."""
        # Find notes without predictions
        subquery = select(Prediction.note_id).distinct()
        notes_without_predictions = self.session.execute(
            select(Note).where(~Note.note_id.in_(subquery), Note.archived == False)
        ).scalars().all()

        total_processed = 0
        total_predictions = 0
        total_frameworks = 0
        total_links = 0

        for note in notes_without_predictions:
            result = await self.extract_from_note(note.note_id)
            if not result.get("error") and not result.get("skipped"):
                total_processed += 1
                total_predictions += result.get("predictions_created", 0)
                total_frameworks += result.get("new_frameworks_created", 0) 
                total_links += result.get("framework_links_created", 0)

        logger.info(f"Batch extraction complete: {total_processed} notes processed, {total_predictions} predictions, {total_frameworks} new frameworks, {total_links} framework links")
        
        return {
            "notes_processed": total_processed,
            "predictions_created": total_predictions,
            "new_frameworks_created": total_frameworks,
            "framework_links_created": total_links
        }