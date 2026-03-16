"""
Ten31 Thoughts - Feed Management API
REST endpoints for managing RSS feeds and viewing content.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db.models import (
    Feed, ContentItem, FeedCategory, FeedStatus, AnalysisStatus
)
from ..db.session import get_db
from ..feeds.manager import FeedManager

router = APIRouter(prefix="/api/feeds", tags=["feeds"])


# ─── Dependency injection ───


def get_feed_manager(session: Session = Depends(get_db)):
    return FeedManager(session)


# ─── Request/Response Models ───

class AddFeedRequest(BaseModel):
    url: str = Field(..., description="RSS/Atom feed URL")
    category: str = Field(..., description="'our_thesis' or 'external_interview'")
    display_name: Optional[str] = Field(None, description="Human-readable name")
    tags: Optional[list[str]] = Field(default_factory=list, description="Topic tags")
    poll_interval_minutes: int = Field(1440, description="Minutes between polls (default: daily)")


class UpdateFeedRequest(BaseModel):
    display_name: Optional[str] = None
    tags: Optional[list[str]] = None
    category: Optional[str] = None
    poll_interval_minutes: Optional[int] = None
    status: Optional[str] = None


class FeedResponse(BaseModel):
    feed_id: str
    url: str
    category: str
    display_name: str
    tags: list[str]
    poll_interval_minutes: int
    status: str
    last_fetched: Optional[str]
    last_error: Optional[str]
    error_count: int
    created_at: str
    item_count: Optional[int] = None

    class Config:
        from_attributes = True


class ContentItemResponse(BaseModel):
    item_id: str
    feed_id: str
    url: str
    title: str
    published_date: Optional[str]
    authors: list[str]
    summary: str
    content_type: str
    analysis_status: str
    created_at: str

    class Config:
        from_attributes = True


class PollResponse(BaseModel):
    feeds_polled: int
    new_items: int
    errors: int
    our_thesis_items: int
    external_items: int


class StatsResponse(BaseModel):
    total_items: int
    by_status: dict
    by_category: dict
    feeds_active: int
    feeds_total: int


# ─── Helper ───

def feed_to_response(feed: Feed, session: Session) -> FeedResponse:
    from sqlalchemy import func, select
    count = session.execute(
        select(func.count(ContentItem.item_id))
        .where(ContentItem.feed_id == feed.feed_id)
    ).scalar()

    return FeedResponse(
        feed_id=feed.feed_id,
        url=feed.url,
        category=feed.category.value,
        display_name=feed.display_name,
        tags=feed.tags or [],
        poll_interval_minutes=feed.poll_interval_minutes,
        status=feed.status.value,
        last_fetched=feed.last_fetched.isoformat() if feed.last_fetched else None,
        last_error=feed.last_error,
        error_count=feed.error_count,
        created_at=feed.created_at.isoformat(),
        item_count=count,
    )


def item_to_response(item: ContentItem) -> ContentItemResponse:
    return ContentItemResponse(
        item_id=item.item_id,
        feed_id=item.feed_id,
        url=item.url,
        title=item.title,
        published_date=item.published_date.isoformat() if item.published_date else None,
        authors=item.authors or [],
        summary=item.summary or "",
        content_type=item.content_type,
        analysis_status=item.analysis_status.value,
        created_at=item.created_at.isoformat(),
    )


# ─── Endpoints ───

@router.post("/", response_model=FeedResponse, status_code=201)
def add_feed(
    request: AddFeedRequest,
    manager: FeedManager = Depends(get_feed_manager),
    session: Session = Depends(get_db),
):
    """Add a new RSS feed to the system."""
    try:
        category = FeedCategory(request.category)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category: {request.category}. Must be 'our_thesis' or 'external_interview'"
        )

    feed, error = manager.add_feed(
        url=request.url,
        category=category,
        display_name=request.display_name,
        tags=request.tags,
        poll_interval_minutes=request.poll_interval_minutes,
    )

    if error:
        raise HTTPException(status_code=400, detail=error)

    return feed_to_response(feed, session)


@router.get("/", response_model=list[FeedResponse])
def list_feeds(
    category: Optional[str] = None,
    status: Optional[str] = None,
    manager: FeedManager = Depends(get_feed_manager),
    session: Session = Depends(get_db),
):
    """List all feeds, optionally filtered by category or status."""
    cat = FeedCategory(category) if category else None
    stat = FeedStatus(status) if status else None
    feeds = manager.list_feeds(category=cat, status=stat)
    return [feed_to_response(f, session) for f in feeds]


@router.get("/stats", response_model=StatsResponse)
def get_stats(manager: FeedManager = Depends(get_feed_manager)):
    """Get overall content and feed statistics."""
    return manager.get_content_stats()


@router.get("/{feed_id}", response_model=FeedResponse)
def get_feed(
    feed_id: str,
    manager: FeedManager = Depends(get_feed_manager),
    session: Session = Depends(get_db),
):
    """Get details for a specific feed."""
    feed = manager.get_feed(feed_id)
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")
    return feed_to_response(feed, session)


@router.patch("/{feed_id}", response_model=FeedResponse)
def update_feed(
    feed_id: str,
    request: UpdateFeedRequest,
    manager: FeedManager = Depends(get_feed_manager),
    session: Session = Depends(get_db),
):
    """Update feed configuration."""
    kwargs = {}
    if request.display_name is not None:
        kwargs["display_name"] = request.display_name
    if request.tags is not None:
        kwargs["tags"] = request.tags
    if request.category is not None:
        kwargs["category"] = FeedCategory(request.category)
    if request.poll_interval_minutes is not None:
        kwargs["poll_interval_minutes"] = request.poll_interval_minutes
    if request.status is not None:
        kwargs["status"] = FeedStatus(request.status)

    feed = manager.update_feed(feed_id, **kwargs)
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")
    return feed_to_response(feed, session)


@router.delete("/{feed_id}", status_code=204)
def delete_feed(
    feed_id: str,
    manager: FeedManager = Depends(get_feed_manager),
):
    """Delete a feed and all its content."""
    if not manager.delete_feed(feed_id):
        raise HTTPException(status_code=404, detail="Feed not found")


@router.get("/{feed_id}/items", response_model=list[ContentItemResponse])
def get_feed_items(
    feed_id: str,
    limit: int = 50,
    offset: int = 0,
    manager: FeedManager = Depends(get_feed_manager),
):
    """Get content items for a specific feed."""
    items = manager.get_items_for_feed(feed_id, limit=limit, offset=offset)
    return [item_to_response(i) for i in items]


@router.post("/poll", response_model=PollResponse)
def trigger_poll(manager: FeedManager = Depends(get_feed_manager)):
    """Manually trigger polling of all due feeds."""
    stats = manager.poll_all_due()
    return PollResponse(**stats)


@router.post("/{feed_id}/poll", response_model=PollResponse)
def trigger_feed_poll(
    feed_id: str,
    manager: FeedManager = Depends(get_feed_manager),
):
    """Manually trigger polling of a specific feed."""
    feed = manager.get_feed(feed_id)
    if not feed:
        raise HTTPException(status_code=404, detail="Feed not found")

    new_items = manager.poll_feed(feed)
    category = feed.category
    return PollResponse(
        feeds_polled=1,
        new_items=len(new_items),
        errors=1 if feed.last_error else 0,
        our_thesis_items=len(new_items) if category == FeedCategory.OUR_THESIS else 0,
        external_items=len(new_items) if category == FeedCategory.EXTERNAL_INTERVIEW else 0,
    )
