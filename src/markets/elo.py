"""
Ten31 Thoughts - Conviction-Weighted ELO Rating System

Rates guests based on prediction accuracy weighted by market sentiment at time of call.

Contrarian correct calls earn more. Consensus wrong calls hurt more.
The prediction market price at time of the call is the difficulty multiplier.

Standard ELO formula:
    expected = market_probability_of_our_side
    actual = 1.0 if correct, 0.0 if wrong
    delta = K * (actual - expected)
    new_rating = old_rating + delta

K-factor scales with conviction level:
    strong conviction = K * 1.5 (you put your reputation on it)
    moderate = K * 1.0
    speculative = K * 0.7 (you hedged, so less reward/punishment)
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import select

from ..db.models import (
    GuestProfile, PredictionMarketLink, ExternalFramework,
    ThesisElement, ContentItem
)

logger = logging.getLogger(__name__)

# Base K-factor (like chess: 32 is standard)
BASE_K = 40

# Conviction multipliers
CONVICTION_K = {
    "strong": 1.5,
    "moderate": 1.0,
    "speculative": 0.7,
}

# Starting ELO
STARTING_ELO = 1500.0


def compute_elo_delta(
    market_price_our_side: float,
    is_correct: bool,
    conviction: str = "moderate",
) -> float:
    """
    Compute ELO rating change for a single resolved prediction.

    Args:
        market_price_our_side: probability the market assigned to our side (0-1)
                               at the time the call was made
        is_correct: whether the prediction was correct
        conviction: "strong", "moderate", or "speculative"

    Returns:
        ELO delta (positive = gain, negative = loss)
    """
    expected = max(0.01, min(0.99, market_price_our_side))  # clamp to avoid div/zero
    actual = 1.0 if is_correct else 0.0
    k = BASE_K * CONVICTION_K.get(conviction, 1.0)

    delta = k * (actual - expected)
    return round(delta, 2)


class ELOCalculator:
    """Manages ELO ratings for guests based on market-resolved predictions."""

    def __init__(self, session: Session):
        self.session = session

    def recalculate_all(self) -> dict:
        """
        Recalculate ELO ratings for all guests from scratch based on all
        resolved prediction market links. Call this to rebuild after changes.
        """
        # Reset all ratings
        profiles = self.session.execute(select(GuestProfile)).scalars().all()
        for profile in profiles:
            profile.elo_rating = STARTING_ELO
            profile.elo_peak = STARTING_ELO
            profile.elo_floor = STARTING_ELO
            profile.elo_predictions_counted = 0
            profile.elo_history = []

        # Get all resolved market links ordered by resolution date
        resolved_links = self.session.execute(
            select(PredictionMarketLink)
            .where(PredictionMarketLink.market_status == "resolved")
            .where(PredictionMarketLink.market_result.isnot(None))
            .where(PredictionMarketLink.price_at_link.isnot(None))
            .order_by(PredictionMarketLink.resolved_at.asc())
        ).scalars().all()

        stats = {"processed": 0, "guests_updated": set(), "errors": 0}

        for link in resolved_links:
            try:
                self._process_link(link, stats)
            except Exception as e:
                logger.error(f"ELO processing failed for link {link.link_id}: {e}")
                stats["errors"] += 1

        self.session.commit()

        return {
            "processed": stats["processed"],
            "guests_updated": len(stats["guests_updated"]),
            "errors": stats["errors"],
        }

    def process_new_resolution(self, link: PredictionMarketLink) -> Optional[dict]:
        """Process a single newly resolved market link and update ELO."""
        if not link.market_result or not link.price_at_link:
            return None

        stats = {"processed": 0, "guests_updated": set(), "errors": 0}
        result = self._process_link(link, stats)
        self.session.commit()
        return result

    def _process_link(self, link: PredictionMarketLink, stats: dict) -> Optional[dict]:
        """Process a single link and update the guest's ELO."""
        # Find the guest name
        guest_name = None
        conviction = "moderate"

        if link.element_id:
            element = self.session.get(ThesisElement, link.element_id)
            if element:
                item = self.session.get(ContentItem, element.item_id)
                if item and item.authors and isinstance(item.authors, list):
                    guest_name = item.authors[0] if item.authors else None
                conviction = element.conviction.value if element and element.conviction else "moderate"

        if link.framework_id:
            fw = self.session.get(ExternalFramework, link.framework_id)
            if fw:
                guest_name = fw.guest_name

        if not guest_name:
            return None

        # Ensure guest profile exists
        profile = self.session.get(GuestProfile, guest_name)
        if not profile:
            profile = GuestProfile(
                guest_name=guest_name,
                elo_rating=STARTING_ELO,
                elo_peak=STARTING_ELO,
                elo_floor=STARTING_ELO,
                elo_predictions_counted=0,
                elo_history=[],
            )
            self.session.add(profile)

        # Compute the market probability for our side at time of call
        if link.our_side == "yes":
            market_price_our_side = link.price_at_link
        else:
            market_price_our_side = 1.0 - link.price_at_link

        # Determine if correct
        is_correct = (link.market_result == link.our_side)

        # Compute delta
        delta = compute_elo_delta(market_price_our_side, is_correct, conviction)

        # Update rating
        old_rating = profile.elo_rating or STARTING_ELO
        new_rating = old_rating + delta

        profile.elo_rating = round(new_rating, 1)
        profile.elo_peak = max(profile.elo_peak or STARTING_ELO, new_rating)
        profile.elo_floor = min(profile.elo_floor or STARTING_ELO, new_rating)
        profile.elo_predictions_counted = (profile.elo_predictions_counted or 0) + 1

        # Append to history
        history = profile.elo_history or []
        history.append({
            "date": link.resolved_at.isoformat() if link.resolved_at else datetime.now(timezone.utc).isoformat(),
            "old_rating": round(old_rating, 1),
            "new_rating": round(new_rating, 1),
            "delta": delta,
            "prediction": link.market_title,
            "our_side": link.our_side,
            "market_result": link.market_result,
            "market_price_at_call": link.price_at_link,
            "market_price_our_side": round(market_price_our_side, 3),
            "conviction": conviction,
            "correct": is_correct,
            "platform": link.platform,
        })
        profile.elo_history = history

        stats["processed"] += 1
        stats["guests_updated"].add(guest_name)

        logger.info(
            f"ELO update: {guest_name} {old_rating:.0f} → {new_rating:.0f} "
            f"(Δ{delta:+.1f}) {'✓' if is_correct else '✗'} "
            f"{link.market_title} (market: {market_price_our_side:.0%} our side)"
        )

        return {
            "guest": guest_name,
            "old_rating": round(old_rating, 1),
            "new_rating": round(new_rating, 1),
            "delta": delta,
            "correct": is_correct,
            "market_price_our_side": round(market_price_our_side, 3),
            "conviction": conviction,
        }

    def get_leaderboard(self) -> list[dict]:
        """Get all guests ranked by ELO rating."""
        profiles = self.session.execute(
            select(GuestProfile)
            .where(GuestProfile.elo_predictions_counted > 0)
            .order_by(GuestProfile.elo_rating.desc())
        ).scalars().all()

        return [
            {
                "guest_name": p.guest_name,
                "display_name": p.display_name,
                "elo_rating": round(p.elo_rating, 1) if p.elo_rating else STARTING_ELO,
                "elo_peak": round(p.elo_peak, 1) if p.elo_peak else STARTING_ELO,
                "elo_floor": round(p.elo_floor, 1) if p.elo_floor else STARTING_ELO,
                "predictions_counted": p.elo_predictions_counted or 0,
                "x_handle": p.x_handle,
                "linkedin_url": p.linkedin_url,
                "bio": p.bio,
                "recent_history": (p.elo_history or [])[-5:],
            }
            for p in profiles
        ]
