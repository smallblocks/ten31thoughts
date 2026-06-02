"""
Ten31 Thoughts - Monday Briefing Generator
Weekly review of predictions, calibration stats, and framework evolution.
Runs every Monday via scheduler.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import and_, or_, func
from sqlalchemy.orm import Session

from ..db.models import (
    Prediction, Framework, FrameworkLink, Note, Digest, gen_id,
)
from ..llm.router import LLMRouter

logger = logging.getLogger(__name__)


class MondayBriefing:
    """Generates the weekly prediction review and calibration report."""
    
    def __init__(self, session: Session, llm: Optional[LLMRouter] = None):
        self.session = session
        self.llm = llm
    
    def generate(self) -> dict:
        """
        Generate the Monday briefing data.
        
        Returns dict with:
        - due_predictions: predictions with timeline ending in next 30 days
        - expiring_soon: predictions expiring in next 7 days
        - recently_resolved: predictions resolved in last 7 days  
        - calibration: accuracy stats by conviction bucket
        - framework_activity: frameworks with recent changes
        - summary_stats: overall prediction health
        """
        now = datetime.now(timezone.utc)
        seven_days = now + timedelta(days=7)
        thirty_days = now + timedelta(days=30)
        week_ago = now - timedelta(days=7)
        
        # Due predictions (timeline ending within 30 days)
        due_predictions = self.session.query(Prediction).filter(
            and_(
                Prediction.status == "open",
                Prediction.timeline_end.isnot(None),
                Prediction.timeline_end <= thirty_days,
                Prediction.timeline_end >= now - timedelta(days=7),  # Include recently expired
            )
        ).order_by(Prediction.timeline_end.asc()).all()
        
        # Expiring this week
        expiring_soon = [p for p in due_predictions if p.timeline_end and p.timeline_end <= seven_days]
        
        # Recently resolved
        recently_resolved = self.session.query(Prediction).filter(
            and_(
                Prediction.status.in_(["confirmed", "invalidated", "expired"]),
                Prediction.status_changed_at >= week_ago,
            )
        ).all()
        
        # Calibration stats
        calibration = self._calculate_calibration()
        
        # Framework activity
        framework_activity = self.session.query(Framework).filter(
            Framework.updated_at >= week_ago
        ).all()
        
        # Summary stats
        total_open = self.session.query(func.count(Prediction.prediction_id)).filter(
            Prediction.status == "open"
        ).scalar() or 0
        
        total_confirmed = self.session.query(func.count(Prediction.prediction_id)).filter(
            Prediction.status == "confirmed"
        ).scalar() or 0
        
        total_invalidated = self.session.query(func.count(Prediction.prediction_id)).filter(
            Prediction.status == "invalidated"
        ).scalar() or 0
        
        total_expired = self.session.query(func.count(Prediction.prediction_id)).filter(
            Prediction.status == "expired"
        ).scalar() or 0
        
        return {
            "generated_at": now.isoformat(),
            "due_predictions": [self._serialize_prediction(p) for p in due_predictions],
            "expiring_soon": [self._serialize_prediction(p) for p in expiring_soon],
            "recently_resolved": [self._serialize_prediction(p) for p in recently_resolved],
            "calibration": calibration,
            "framework_activity": [
                {
                    "framework_id": f.framework_id,
                    "name": f.name,
                    "status": f.status,
                    "recent_evolution": (f.evolution_log or [])[-3:],  # Last 3 entries
                }
                for f in framework_activity
            ],
            "summary_stats": {
                "total_open": total_open,
                "total_confirmed": total_confirmed,
                "total_invalidated": total_invalidated,
                "total_expired": total_expired,
                "hit_rate": round(total_confirmed / max(total_confirmed + total_invalidated, 1) * 100, 1),
            }
        }
    
    def _calculate_calibration(self) -> list[dict]:
        """
        Calculate calibration by conviction bucket.
        Groups predictions into conviction ranges and compares predicted vs actual hit rates.
        """
        buckets = [
            (0.0, 0.2, "Very Low (0-20%)"),
            (0.2, 0.4, "Low (20-40%)"),
            (0.4, 0.6, "Medium (40-60%)"),
            (0.6, 0.8, "High (60-80%)"),
            (0.8, 1.01, "Very High (80-100%)"),
        ]
        
        resolved = self.session.query(Prediction).filter(
            Prediction.status.in_(["confirmed", "invalidated"])
        ).all()
        
        results = []
        for low, high, label in buckets:
            in_bucket = [p for p in resolved if p.conviction is not None and low <= p.conviction < high]
            if not in_bucket:
                results.append({
                    "bucket": label,
                    "predicted_rate": round((low + high) / 2 * 100, 0),
                    "actual_rate": None,
                    "count": 0,
                })
                continue
            
            confirmed = sum(1 for p in in_bucket if p.status == "confirmed")
            actual_rate = round(confirmed / len(in_bucket) * 100, 1)
            
            results.append({
                "bucket": label,
                "predicted_rate": round((low + high) / 2 * 100, 0),
                "actual_rate": actual_rate,
                "count": len(in_bucket),
            })
        
        return results
    
    def _serialize_prediction(self, p: Prediction) -> dict:
        return {
            "prediction_id": p.prediction_id,
            "claim": p.claim,
            "measurable_outcome": p.measurable_outcome,
            "timeline": p.timeline,
            "timeline_end": p.timeline_end.isoformat() if p.timeline_end else None,
            "conviction": p.conviction,
            "status": p.status,
            "status_evidence": p.status_evidence,
            "domain": p.domain,
            "note_id": p.note_id,
        }