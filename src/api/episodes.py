"""
Ten31 Thoughts - Episode Reasoning Map API
Per-episode deep analytical view showing the full logical fingerprint.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_

from ..db.models import (
    ContentItem, Feed, FeedCategory, AnalysisStatus,
    ThesisElement, ExternalFramework, BlindSpot, GuestProfile,
)
from ..db.session import get_db
from ..analysis.classical_reference import (
    CLASSICAL_DOMAINS, ALL_PRINCIPLES, TOPIC_TO_DOMAINS, get_principles_for_topic
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/episodes", tags=["episodes"])


@router.get("/")
def list_analyzed_episodes(
    category: Optional[str] = Query(None, description="our_thesis or external_interview"),
    guest: Optional[str] = Query(None, description="Filter by guest name"),
    min_score: Optional[float] = Query(None, description="Minimum first-principles score"),
    limit: int = Query(50, le=200),
    offset: int = 0,
    session: Session = Depends(get_db),
):
    """
    List all analyzed episodes/editions with summary scores.
    Sortable, filterable — designed for a browse view on db.ten31.ai.
    """
    query = (
        select(ContentItem)
        .where(ContentItem.analysis_status == AnalysisStatus.COMPLETE)
        .order_by(ContentItem.published_date.desc())
    )

    if category:
        query = query.join(Feed).where(Feed.category == category)

    results = session.execute(query.limit(limit).offset(offset)).scalars().all()

    episodes = []
    for item in results:
        feed = session.get(Feed, item.feed_id)

        # Get primary guest
        guest_name = None
        avg_score = None
        framework_count = len(item.external_frameworks)

        if item.external_frameworks:
            scores = [fw.reasoning_score for fw in item.external_frameworks if fw.reasoning_score is not None]
            avg_score = round(sum(scores) / len(scores), 3) if scores else None
            # Get primary guest (most frameworks)
            guest_names = [fw.guest_name for fw in item.external_frameworks if fw.guest_name]
            if guest_names:
                guest_name = max(set(guest_names), key=guest_names.count)

        # Apply filters
        if guest and guest_name and guest.lower() not in guest_name.lower():
            continue
        if min_score is not None and (avg_score is None or avg_score < min_score):
            continue

        episodes.append({
            "item_id": item.item_id,
            "title": item.title,
            "url": item.url,
            "date": item.published_date.isoformat() if item.published_date else None,
            "category": feed.category.value if feed else "unknown",
            "guest": guest_name,
            "first_principles_score": avg_score,
            "framework_count": framework_count,
            "thesis_element_count": len(item.thesis_elements),
            "blind_spot_count": len(item.blind_spots),
            "prediction_count": len([e for e in item.thesis_elements if e.is_prediction]),
        })

    return episodes


@router.get("/{item_id}/reasoning-map")
def get_reasoning_map(
    item_id: str,
    session: Session = Depends(get_db),
):
    """
    Full reasoning map for a single episode.

    Returns the complete logical fingerprint:
    - Domain heatmap (which classical domains were triggered)
    - Axiom-level detail (aligned/violated/neutral with thinker citations)
    - Causal chains from each framework
    - First-principles scores and grades
    - Logical vulnerabilities
    - Predictions extracted
    - Blind spots detected
    - Thesis convergence/divergence
    """
    item = session.get(ContentItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Episode not found")

    feed = session.get(Feed, item.feed_id)
    category = feed.category.value if feed else "unknown"

    # Get primary guest
    guest_name = None
    if item.authors and isinstance(item.authors, list) and item.authors:
        guest_name = item.authors[0]
    if not guest_name:
        for fw in item.external_frameworks:
            if fw.guest_name:
                guest_name = fw.guest_name
                break

    # ── Build domain heatmap ──
    domain_hits = {
        d["domain"]: {
            "title": d["title"],
            "alignments": 0,
            "violations": 0,
            "neutral": 0,
            "axioms": []
        }
        for d in CLASSICAL_DOMAINS
    }

    # ── Parse axiom-level results from framework reasoning notes ──
    axiom_details = []
    for fw in item.external_frameworks:
        notes = fw.reasoning_notes or ""

        # Parse the stored evaluation data
        for principle in ALL_PRINCIPLES:
            axiom_id = principle["id"]
            domain = principle["domain"]

            # Check if this axiom appears in the reasoning notes
            if axiom_id in notes:
                alignment = "neutral"
                # Check context around the axiom mention
                if "violation" in notes.lower() and axiom_id in notes:
                    alignment = "violated"
                    domain_hits[domain]["violations"] += 1
                elif "align" in notes.lower() and axiom_id in notes:
                    alignment = "aligned"
                    domain_hits[domain]["alignments"] += 1
                else:
                    domain_hits[domain]["neutral"] += 1

                axiom_details.append({
                    "axiom_id": axiom_id,
                    "domain": domain,
                    "domain_title": principle["domain_title"],
                    "axiom": principle["axiom"][:150],
                    "thinkers": principle["source_thinkers"],
                    "alignment": alignment,
                    "framework": fw.framework_name,
                    "guest": fw.guest_name,
                })
                domain_hits[domain]["axioms"].append(axiom_id)

    # If no axiom-level detail found in notes, reconstruct from topic mapping
    if not axiom_details:
        for fw in item.external_frameworks:
            # Use the framework's topic/indicators to infer which domains apply
            topics_covered = set()
            if fw.key_indicators:
                for indicator in fw.key_indicators:
                    ind_lower = str(indicator).lower()
                    for topic, domains in TOPIC_TO_DOMAINS.items():
                        if topic.replace("_", " ") in ind_lower or any(kw in ind_lower for kw in topic.split("_")):
                            topics_covered.update(domains)

            # If we still have nothing, use the framework description to guess
            if not topics_covered:
                desc_lower = (fw.description or "").lower()
                for domain_dict in CLASSICAL_DOMAINS:
                    for topic in domain_dict["applies_to"]:
                        if topic.replace("_", " ") in desc_lower:
                            topics_covered.add(domain_dict["domain"])

            score = fw.reasoning_score
            for domain_name in topics_covered:
                if domain_name in domain_hits:
                    if score and score >= 0.7:
                        domain_hits[domain_name]["alignments"] += 1
                    elif score and score < 0.4:
                        domain_hits[domain_name]["violations"] += 1
                    else:
                        domain_hits[domain_name]["neutral"] += 1

    # ── Frameworks detail ──
    frameworks = []
    for fw in item.external_frameworks:
        # Parse causal chain
        causal = fw.causal_chain
        if isinstance(causal, dict):
            causal_str = " → ".join(f"{v}" for v in causal.values() if v)
        elif isinstance(causal, list):
            causal_str = " → ".join(str(c) for c in causal)
        else:
            causal_str = str(causal) if causal else None

        frameworks.append({
            "framework_name": fw.framework_name,
            "guest": fw.guest_name,
            "description": fw.description,
            "first_principles_score": fw.reasoning_score,
            "reasoning_grade": _score_to_grade(fw.reasoning_score),
            "thesis_alignment": fw.thesis_alignment.value if fw.thesis_alignment else "unrelated",
            "alignment_notes": fw.alignment_notes,
            "causal_chain": causal_str,
            "causal_chain_raw": fw.causal_chain,
            "key_indicators": fw.key_indicators or [],
            "time_horizon": fw.time_horizon,
            "predictions": fw.predictions or [],
        })

    # ── Thesis elements (for our_thesis content) ──
    thesis_elements = []
    for elem in item.thesis_elements:
        thesis_elements.append({
            "claim": elem.claim_text,
            "topic": elem.topic,
            "conviction": elem.conviction.value if elem.conviction else "moderate",
            "is_prediction": elem.is_prediction,
            "prediction_status": elem.prediction_status.value if elem.prediction_status else None,
            "prediction_horizon": elem.prediction_horizon,
            "is_data_skepticism": elem.is_data_skepticism,
            "data_series": elem.data_series,
            "alternative_interpretation": elem.alternative_interpretation,
        })

    # ── Blind spots ──
    blind_spots = []
    for spot in item.blind_spots:
        blind_spots.append({
            "topic": spot.topic,
            "description": spot.description,
            "severity": spot.severity,
            "source_type": spot.source_type,
            "macro_event": spot.macro_event,
        })

    # ── Predictions ──
    predictions = [e for e in thesis_elements if e["is_prediction"]]

    # ── Overall scores ──
    all_scores = [fw.reasoning_score for fw in item.external_frameworks if fw.reasoning_score is not None]
    avg_score = round(sum(all_scores) / len(all_scores), 3) if all_scores else None

    # ── Domain heatmap (clean for output) ──
    heatmap = []
    for domain_name, data in domain_hits.items():
        total = data["alignments"] + data["violations"] + data["neutral"]
        if total > 0:
            health = "mixed"
            if data["alignments"] > data["violations"]:
                health = "strong"
            elif data["violations"] > data["alignments"]:
                health = "weak"

            heatmap.append({
                "domain": domain_name,
                "title": data["title"],
                "total_references": total,
                "alignments": data["alignments"],
                "violations": data["violations"],
                "neutral": data["neutral"],
                "health": health,
            })

    heatmap.sort(key=lambda x: -x["total_references"])

    return {
        "item_id": item.item_id,
        "title": item.title,
        "url": item.url,
        "date": item.published_date.isoformat() if item.published_date else None,
        "category": category,
        "guest": guest_name,

        # Scores
        "first_principles_score": avg_score,
        "reasoning_grade": _score_to_grade(avg_score),

        # Reasoning Map
        "domain_heatmap": heatmap,
        "axiom_details": axiom_details,

        # Frameworks
        "frameworks": frameworks,

        # Thesis
        "thesis_elements": thesis_elements,

        # Predictions
        "predictions": predictions,
        "prediction_count": len(predictions),

        # Blind Spots
        "blind_spots": blind_spots,

        # Convergence
        "convergence_summary": {
            "aligned": len([fw for fw in item.external_frameworks if fw.thesis_alignment and fw.thesis_alignment.value == "agree"]),
            "partial": len([fw for fw in item.external_frameworks if fw.thesis_alignment and fw.thesis_alignment.value == "partial"]),
            "divergent": len([fw for fw in item.external_frameworks if fw.thesis_alignment and fw.thesis_alignment.value == "diverge"]),
        },
    }


@router.get("/guests")
def list_all_guests(
    min_appearances: int = Query(1, description="Minimum number of appearances"),
    session: Session = Depends(get_db),
):
    """List all guests with summary stats, ranked by average first-principles score."""
    guests = session.execute(
        select(
            ExternalFramework.guest_name,
            func.count(func.distinct(ExternalFramework.item_id)).label("appearances"),
            func.count(ExternalFramework.framework_id).label("frameworks"),
            func.avg(ExternalFramework.reasoning_score).label("avg_score"),
            func.min(ExternalFramework.reasoning_score).label("min_score"),
            func.max(ExternalFramework.reasoning_score).label("max_score"),
        )
        .where(ExternalFramework.guest_name.isnot(None))
        .group_by(ExternalFramework.guest_name)
        .having(func.count(func.distinct(ExternalFramework.item_id)) >= min_appearances)
        .order_by(func.avg(ExternalFramework.reasoning_score).desc())
    ).all()

    results = []
    for name, appearances, frameworks, avg, worst, best in guests:
        profile = session.get(GuestProfile, name)
        results.append({
            "guest_name": name,
            "display_name": profile.display_name if profile else None,
            "appearances": appearances,
            "total_frameworks": frameworks,
            "avg_first_principles_score": round(float(avg), 3) if avg else None,
            "best_score": round(float(best), 3) if best else None,
            "worst_score": round(float(worst), 3) if worst else None,
            "reasoning_grade": _score_to_grade(float(avg) if avg else None),
            "consistency": round(float(best) - float(worst), 3) if best and worst else None,
            "x_handle": profile.x_handle if profile else None,
            "linkedin_url": profile.linkedin_url if profile else None,
            "website_url": profile.website_url if profile else None,
            "bio": profile.bio if profile else None,
        })
    return results


@router.get("/guests/by-topic/{topic}")
def list_guests_by_topic(
    topic: str,
    min_appearances: int = Query(1),
    session: Session = Depends(get_db),
):
    """
    Rank guests by their first-principles score on a specific topic.
    Topics: fed_policy, labor_market, fiscal_policy, geopolitics, bitcoin,
    credit_markets, energy, currencies, inflation, financial_plumbing,
    regulatory, demographics, technology
    """
    # Get frameworks where key_indicators or description mentions the topic
    frameworks = session.execute(
        select(ExternalFramework)
        .where(ExternalFramework.guest_name.isnot(None))
    ).scalars().all()

    # Filter to frameworks relevant to this topic
    topic_keywords = topic.replace("_", " ").split()
    guest_scores = {}

    for fw in frameworks:
        relevant = False
        # Check description
        desc = (fw.description or "").lower()
        notes = (fw.reasoning_notes or "").lower()
        indicators = str(fw.key_indicators or []).lower()

        if any(kw in desc or kw in notes or kw in indicators for kw in topic_keywords):
            relevant = True

        if relevant and fw.reasoning_score is not None:
            if fw.guest_name not in guest_scores:
                guest_scores[fw.guest_name] = []
            guest_scores[fw.guest_name].append(fw.reasoning_score)

    results = []
    for name, scores in guest_scores.items():
        if len(scores) < min_appearances:
            continue
        profile = session.get(GuestProfile, name)
        avg = sum(scores) / len(scores)
        results.append({
            "guest_name": name,
            "topic": topic,
            "avg_score": round(avg, 3),
            "reasoning_grade": _score_to_grade(avg),
            "sample_size": len(scores),
            "x_handle": profile.x_handle if profile else None,
        })

    results.sort(key=lambda x: -(x["avg_score"] or 0))
    return results


@router.put("/guests/{guest_name}/profile")
def update_guest_profile(
    guest_name: str,
    x_handle: Optional[str] = None,
    linkedin_url: Optional[str] = None,
    website_url: Optional[str] = None,
    bio: Optional[str] = None,
    display_name: Optional[str] = None,
    session: Session = Depends(get_db),
):
    """
    Set or update a guest's social links and profile info.
    Call this to attach X/LinkedIn handles to a guest for verification.
    """
    profile = session.get(GuestProfile, guest_name)
    if not profile:
        profile = GuestProfile(guest_name=guest_name)
        session.add(profile)

    if x_handle is not None:
        profile.x_handle = x_handle.lstrip("@")
    if linkedin_url is not None:
        profile.linkedin_url = linkedin_url
    if website_url is not None:
        profile.website_url = website_url
    if bio is not None:
        profile.bio = bio
    if display_name is not None:
        profile.display_name = display_name

    session.commit()
    return {
        "guest_name": profile.guest_name,
        "display_name": profile.display_name,
        "x_handle": profile.x_handle,
        "linkedin_url": profile.linkedin_url,
        "website_url": profile.website_url,
        "bio": profile.bio,
    }


@router.get("/guests/{guest_name}/profile")
def get_guest_profile(
    guest_name: str,
    session: Session = Depends(get_db),
):
    """Get a guest's profile with social links."""
    profile = session.get(GuestProfile, guest_name)
    if not profile:
        return {"guest_name": guest_name, "x_handle": None, "linkedin_url": None, "website_url": None, "bio": None}

    return {
        "guest_name": profile.guest_name,
        "display_name": profile.display_name,
        "x_handle": profile.x_handle,
        "linkedin_url": profile.linkedin_url,
        "website_url": profile.website_url,
        "bio": profile.bio,
    }


@router.get("/guests/{guest_name}/scorecard")
def get_guest_scorecard(
    guest_name: str,
    session: Session = Depends(get_db),
):
    """
    Full scorecard for a guest across all appearances.

    Returns:
    - Score trend over time (per episode)
    - Framework evolution (how their thinking has changed)
    - Axiom alignment/violation patterns
    - Thesis convergence history
    - Strongest and weakest reasoning areas
    - Prediction track record (if any)
    """
    frameworks = session.execute(
        select(ExternalFramework, ContentItem.title, ContentItem.published_date, ContentItem.url)
        .join(ContentItem)
        .where(ExternalFramework.guest_name.ilike(f"%{guest_name}%"))
        .order_by(ContentItem.published_date.asc())
    ).all()

    if not frameworks:
        raise HTTPException(status_code=404, detail=f"No data found for guest: {guest_name}")

    # Normalize guest name from results
    actual_name = frameworks[0][0].guest_name
    profile = session.get(GuestProfile, actual_name)

    # ── Score trend ──
    score_trend = []
    all_scores = []
    for fw, title, pub_date, url in frameworks:
        entry = {
            "date": pub_date.isoformat() if pub_date else None,
            "episode": title,
            "url": url,
            "framework": fw.framework_name,
            "first_principles_score": fw.reasoning_score,
            "reasoning_grade": _score_to_grade(fw.reasoning_score),
            "thesis_alignment": fw.thesis_alignment.value if fw.thesis_alignment else "unrelated",
            "time_horizon": fw.time_horizon,
        }
        score_trend.append(entry)
        if fw.reasoning_score is not None:
            all_scores.append(fw.reasoning_score)

    # ── Trend direction ──
    trend = "stable"
    if len(all_scores) >= 3:
        first_half = all_scores[:len(all_scores)//2]
        second_half = all_scores[len(all_scores)//2:]
        first_avg = sum(first_half) / len(first_half)
        second_avg = sum(second_half) / len(second_half)
        if second_avg - first_avg > 0.05:
            trend = "improving"
        elif first_avg - second_avg > 0.05:
            trend = "declining"

    # ── Thesis alignment distribution ──
    alignment_dist = {"agree": 0, "partial": 0, "diverge": 0, "unrelated": 0}
    for fw, _, _, _ in frameworks:
        alignment = fw.thesis_alignment.value if fw.thesis_alignment else "unrelated"
        alignment_dist[alignment] = alignment_dist.get(alignment, 0) + 1

    # ── Domain strengths/weaknesses from reasoning notes ──
    domain_scores = {}
    for fw, _, _, _ in frameworks:
        if fw.reasoning_score is None:
            continue
        notes = (fw.reasoning_notes or "").lower()
        for domain_dict in CLASSICAL_DOMAINS:
            domain_name = domain_dict["domain"]
            # Check if domain was referenced
            if domain_name.replace("_", " ") in notes or any(
                p["id"] in (fw.reasoning_notes or "") for p in domain_dict["principles"]
            ):
                if domain_name not in domain_scores:
                    domain_scores[domain_name] = []
                domain_scores[domain_name].append(fw.reasoning_score)

    strengths = []
    weaknesses = []
    for domain_name, scores in domain_scores.items():
        avg = sum(scores) / len(scores)
        domain_title = next((d["title"] for d in CLASSICAL_DOMAINS if d["domain"] == domain_name), domain_name)
        entry = {"domain": domain_name, "title": domain_title, "avg_score": round(avg, 3), "sample_size": len(scores)}
        if avg >= 0.7:
            strengths.append(entry)
        elif avg < 0.5:
            weaknesses.append(entry)

    strengths.sort(key=lambda x: -x["avg_score"])
    weaknesses.sort(key=lambda x: x["avg_score"])

    # ── Predictions by this guest ──
    guest_predictions = []
    for fw, title, pub_date, _ in frameworks:
        if fw.predictions:
            for pred in fw.predictions:
                if isinstance(pred, dict):
                    guest_predictions.append({
                        "prediction": pred.get("claim", pred.get("prediction", str(pred)))[:200],
                        "episode": title,
                        "date": pub_date.isoformat() if pub_date else None,
                        "status": pred.get("status", "pending"),
                    })

    # ── Key frameworks (most notable) ──
    top_frameworks = sorted(
        [fw for fw, _, _, _ in frameworks if fw.reasoning_score is not None],
        key=lambda x: -(x.reasoning_score or 0)
    )[:5]

    worst_frameworks = sorted(
        [fw for fw, _, _, _ in frameworks if fw.reasoning_score is not None],
        key=lambda x: (x.reasoning_score or 1)
    )[:3]

    return {
        "guest_name": actual_name,
        "display_name": profile.display_name if profile else None,
        "x_handle": profile.x_handle if profile else None,
        "x_url": f"https://x.com/{profile.x_handle}" if profile and profile.x_handle else None,
        "linkedin_url": profile.linkedin_url if profile else None,
        "website_url": profile.website_url if profile else None,
        "bio": profile.bio if profile else None,
        "total_appearances": len(set(fw.item_id for fw, _, _, _ in frameworks)),
        "total_frameworks": len(frameworks),

        # Scores
        "avg_first_principles_score": round(sum(all_scores) / len(all_scores), 3) if all_scores else None,
        "best_score": round(max(all_scores), 3) if all_scores else None,
        "worst_score": round(min(all_scores), 3) if all_scores else None,
        "reasoning_grade": _score_to_grade(sum(all_scores) / len(all_scores) if all_scores else None),
        "trend": trend,

        # Timeline
        "score_trend": score_trend,

        # Thesis alignment
        "thesis_alignment_distribution": alignment_dist,
        "primary_alignment": max(alignment_dist, key=alignment_dist.get) if any(alignment_dist.values()) else "unrelated",

        # Domain analysis
        "strongest_domains": strengths[:3],
        "weakest_domains": weaknesses[:3],

        # Standout frameworks
        "best_frameworks": [
            {"name": fw.framework_name, "score": fw.reasoning_score, "description": fw.description[:200] if fw.description else None}
            for fw in top_frameworks
        ],
        "weakest_frameworks": [
            {"name": fw.framework_name, "score": fw.reasoning_score, "description": fw.description[:200] if fw.description else None}
            for fw in worst_frameworks
        ],

        # Predictions
        "predictions": guest_predictions,
        "prediction_count": len(guest_predictions),
    }


def _score_to_grade(score: Optional[float]) -> Optional[str]:
    """Convert a 0-1 first-principles score to a letter grade."""
    if score is None:
        return None
    if score >= 0.9:
        return "A"
    if score >= 0.8:
        return "A-"
    if score >= 0.7:
        return "B+"
    if score >= 0.6:
        return "B"
    if score >= 0.5:
        return "B-"
    if score >= 0.4:
        return "C+"
    if score >= 0.3:
        return "C"
    if score >= 0.2:
        return "D"
    return "F"
