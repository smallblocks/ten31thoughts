"""
Ten31 Thoughts - Classical Principles API
Endpoints for browsing the classical reference library.
"""

from typing import Optional

from fastapi import APIRouter

router = APIRouter(prefix="/api/principles", tags=["principles"])


@router.get("/")
def list_principles(domain: Optional[str] = None, topic: Optional[str] = None):
    """
    Query the classical reference library.
    Filter by domain (sound_money, political_cycles, human_nature, property_rights)
    or by macro topic (fed_policy, labor_market, etc.).
    """
    from ..analysis.classical_reference import (
        CLASSICAL_DOMAINS, ALL_PRINCIPLES, get_principles_for_topic
    )

    if topic:
        return get_principles_for_topic(topic)
    if domain:
        for d in CLASSICAL_DOMAINS:
            if d["domain"] == domain:
                return d
        return {"error": f"Domain '{domain}' not found"}
    return {"domains": [d["domain"] for d in CLASSICAL_DOMAINS], "total_principles": len(ALL_PRINCIPLES)}


@router.get("/domains")
def list_domains():
    """List all classical domains with their principle counts."""
    from ..analysis.classical_reference import CLASSICAL_DOMAINS
    return [
        {
            "domain": d["domain"],
            "title": d["title"],
            "principle_count": len(d["principles"]),
            "applies_to": d["applies_to"],
        }
        for d in CLASSICAL_DOMAINS
    ]
