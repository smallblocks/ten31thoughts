"""
Ten31 Thoughts - Episodes API
Basic episode listing (title, date, feed, status).
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import select

from ..db.models import ContentItem, Feed, AnalysisStatus
from ..db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/episodes", tags=["episodes"])


@router.get("/")
def list_episodes(
    category: Optional[str] = Query(None, description="our_thesis or external_interview"),
    limit: int = Query(50, le=200),
    offset: int = 0,
    session: Session = Depends(get_db),
):
    """
    List analyzed episodes/editions with basic metadata.
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
        episodes.append({
            "item_id": item.item_id,
            "title": item.title,
            "url": item.url,
            "date": item.published_date.isoformat() if item.published_date else None,
            "category": feed.category.value if feed else "unknown",
            "authors": item.authors or [],
            "status": item.analysis_status.value,
        })

    return episodes


@router.get("/{item_id}")
def get_episode(
    item_id: str,
    session: Session = Depends(get_db),
):
    """Get basic details for a single episode."""
    item = session.get(ContentItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Episode not found")

    feed = session.get(Feed, item.feed_id)

    return {
        "item_id": item.item_id,
        "title": item.title,
        "url": item.url,
        "date": item.published_date.isoformat() if item.published_date else None,
        "category": feed.category.value if feed else "unknown",
        "authors": item.authors or [],
        "summary": item.summary,
        "status": item.analysis_status.value,
    }
