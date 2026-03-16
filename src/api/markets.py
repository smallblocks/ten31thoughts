"""
Ten31 Thoughts - Prediction Markets API
Endpoints for linking predictions to markets and tracking resolutions.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from ..db.models import PredictionMarketLink, ThesisElement, ExternalFramework, gen_id
from ..db.session import get_db
from ..llm.router import LLMRouter
from ..markets.matcher import PredictionMarketMatcher
from ..markets.resolver import MarketResolver

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/markets", tags=["prediction-markets"])


@router.get("/links")
def get_all_links(
    status: Optional[str] = Query(None, description="Filter by market_status: open, closed, resolved"),
    platform: Optional[str] = Query(None, description="Filter by platform: polymarket, kalshi"),
    limit: int = Query(50, le=200),
    session: Session = Depends(get_db),
):
    """Get all prediction market links with their current status."""
    query = select(PredictionMarketLink).order_by(PredictionMarketLink.created_at.desc())

    if status:
        query = query.where(PredictionMarketLink.market_status == status)
    if platform:
        query = query.where(PredictionMarketLink.platform == platform)

    query = query.limit(limit)
    links = session.execute(query).scalars().all()

    results = []
    for link in links:
        # Get the prediction text
        prediction_text = ""
        if link.element_id:
            elem = session.get(ThesisElement, link.element_id)
            if elem:
                prediction_text = elem.claim_text

        results.append({
            "link_id": link.link_id,
            "prediction": prediction_text[:200],
            "platform": link.platform,
            "market_title": link.market_title,
            "market_url": link.market_url,
            "our_side": link.our_side,
            "price_at_link": link.price_at_link,
            "current_price": link.current_price,
            "market_status": link.market_status,
            "market_result": link.market_result,
            "match_confidence": link.match_confidence,
            "match_rationale": link.match_rationale,
            "resolved_at": link.resolved_at.isoformat() if link.resolved_at else None,
            "created_at": link.created_at.isoformat() if link.created_at else None,
        })

    return results


@router.post("/match/{element_id}")
async def match_prediction_to_markets(
    element_id: str,
    session: Session = Depends(get_db),
):
    """Manually trigger market matching for a specific prediction."""
    element = session.get(ThesisElement, element_id)
    if not element:
        raise HTTPException(status_code=404, detail="Prediction not found")

    if not element.is_prediction:
        raise HTTPException(status_code=400, detail="Element is not a prediction")

    llm = LLMRouter()
    matcher = PredictionMarketMatcher(llm)

    item = element.content_item
    source = item.title if item else ""

    matches = await matcher.find_matches(
        prediction_text=element.claim_text,
        topic=element.topic,
        horizon=element.prediction_horizon or "",
        source=source,
    )

    # Create links for matches
    created = []
    for match in matches:
        link = PredictionMarketLink(
            link_id=gen_id(),
            element_id=element_id,
            platform=match["platform"],
            market_id=match["market_id"],
            market_slug=match.get("market_slug"),
            market_title=match["title"],
            market_url=match.get("market_url"),
            price_at_link=match.get("price"),
            current_price=match.get("price"),
            market_status="open",
            our_side=match.get("our_side", "yes"),
            match_confidence=match.get("match_confidence"),
            match_rationale=match.get("match_rationale"),
        )
        session.add(link)
        created.append({
            "platform": link.platform,
            "market_title": link.market_title,
            "our_side": link.our_side,
            "price_at_link": link.price_at_link,
            "confidence": link.match_confidence,
        })

    session.commit()
    matcher.close()

    return {
        "element_id": element_id,
        "prediction": element.claim_text[:200],
        "matches_found": len(created),
        "links": created,
    }


@router.post("/check-resolutions")
def check_all_resolutions(session: Session = Depends(get_db)):
    """Manually trigger resolution check on all open market links."""
    resolver = MarketResolver(session)
    stats = resolver.check_all_linked_markets()
    resolver.close()
    return stats


@router.post("/match-all-pending")
async def match_all_pending_predictions(
    limit: int = Query(20, le=100),
    session: Session = Depends(get_db),
):
    """Match all unlinked predictions to prediction markets."""
    # Find predictions without market links
    linked_ids = session.execute(
        select(PredictionMarketLink.element_id)
        .where(PredictionMarketLink.element_id.isnot(None))
    ).scalars().all()

    query = select(ThesisElement).where(and_(
        ThesisElement.is_prediction == True,
        ThesisElement.element_id.notin_(linked_ids) if linked_ids else True,
    )).limit(limit)

    unlinked = session.execute(query).scalars().all()

    llm = LLMRouter()
    matcher = PredictionMarketMatcher(llm)

    stats = {"checked": 0, "matched": 0, "no_match": 0}

    for element in unlinked:
        item = element.content_item
        source = item.title if item else ""

        matches = await matcher.find_matches(
            prediction_text=element.claim_text,
            topic=element.topic,
            horizon=element.prediction_horizon or "",
            source=source,
        )

        stats["checked"] += 1

        if matches:
            for match in matches[:2]:  # Max 2 links per prediction
                link = PredictionMarketLink(
                    link_id=gen_id(),
                    element_id=element.element_id,
                    platform=match["platform"],
                    market_id=match["market_id"],
                    market_slug=match.get("market_slug"),
                    market_title=match["title"],
                    market_url=match.get("market_url"),
                    price_at_link=match.get("price"),
                    current_price=match.get("price"),
                    market_status="open",
                    our_side=match.get("our_side", "yes"),
                    match_confidence=match.get("match_confidence"),
                    match_rationale=match.get("match_rationale"),
                )
                session.add(link)
            stats["matched"] += 1
        else:
            stats["no_match"] += 1

    session.commit()
    matcher.close()

    return stats


@router.get("/dashboard")
def get_market_dashboard(session: Session = Depends(get_db)):
    """
    Dashboard view: all linked predictions with market prices and resolution status.
    Designed for the db.ten31.ai dashboard to pull via cron.
    """
    links = session.execute(
        select(PredictionMarketLink)
        .order_by(PredictionMarketLink.created_at.desc())
        .limit(100)
    ).scalars().all()

    open_links = [l for l in links if l.market_status == "open"]
    resolved_links = [l for l in links if l.market_status == "resolved"]

    # Calculate stats
    total_resolved = len(resolved_links)
    correct = len([l for l in resolved_links if l.market_result == l.our_side])
    accuracy = round(correct / total_resolved, 3) if total_resolved > 0 else None

    # Market probability vs our conviction
    active = []
    for link in open_links:
        elem = session.get(ThesisElement, link.element_id) if link.element_id else None
        price_delta = None
        if link.current_price is not None and link.price_at_link is not None:
            price_delta = round(link.current_price - link.price_at_link, 3)

        active.append({
            "prediction": elem.claim_text[:150] if elem else "Unknown",
            "topic": elem.topic if elem else "unknown",
            "conviction": elem.conviction.value if elem and elem.conviction else "moderate",
            "platform": link.platform,
            "market_title": link.market_title,
            "market_url": link.market_url,
            "our_side": link.our_side,
            "market_probability": link.current_price,
            "price_when_called": link.price_at_link,
            "price_delta": price_delta,
        })

    resolved = []
    for link in resolved_links:
        elem = session.get(ThesisElement, link.element_id) if link.element_id else None
        won = link.market_result == link.our_side if link.market_result and link.our_side else None
        resolved.append({
            "prediction": elem.claim_text[:150] if elem else "Unknown",
            "platform": link.platform,
            "market_title": link.market_title,
            "our_side": link.our_side,
            "market_result": link.market_result,
            "correct": won,
            "resolved_at": link.resolved_at.isoformat() if link.resolved_at else None,
        })

    return {
        "summary": {
            "total_linked": len(links),
            "active": len(open_links),
            "resolved": total_resolved,
            "accuracy": accuracy,
            "correct": correct,
            "incorrect": total_resolved - correct if total_resolved > 0 else 0,
        },
        "active_predictions": active,
        "resolved_predictions": resolved,
    }
