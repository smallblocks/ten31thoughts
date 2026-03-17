"""
Ten31 Thoughts - PDF Upload API
Upload PDFs (paid newsletters, research reports) directly into the analysis pipeline.
"""

import hashlib
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from ..db.models import (
    Feed, ContentItem, FeedCategory, FeedStatus, AnalysisStatus, gen_id
)
from ..db.session import get_db
from ..feeds.pdf_extractor import PDFExtractor

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/upload", tags=["upload"])

# Max file size: 50 MB
MAX_FILE_SIZE = 50 * 1024 * 1024

# Directory to store uploaded PDFs
UPLOAD_DIR = "/data/uploads"


def _ensure_upload_feed(session: Session, category: str, source_name: str) -> Feed:
    """Get or create a feed for uploaded documents from a specific source."""
    feed_url = f"upload://{source_name.lower().replace(' ', '-')}"

    feed = session.execute(
        select(Feed).where(Feed.url == feed_url)
    ).scalar_one_or_none()

    if not feed:
        cat = FeedCategory.OUR_THESIS if category == "our_thesis" else FeedCategory.EXTERNAL_INTERVIEW
        feed = Feed(
            feed_id=gen_id(),
            url=feed_url,
            category=cat,
            display_name=f"{source_name} (uploads)",
            tags=["uploaded", "pdf"],
            poll_interval_minutes=99999,  # Never auto-poll
            status=FeedStatus.ACTIVE,
        )
        session.add(feed)
        session.commit()

    return feed


@router.post("/pdf")
async def upload_pdf(
    file: UploadFile = File(...),
    category: str = Form("external_interview", description="our_thesis or external_interview"),
    source_name: str = Form("Uploaded PDFs", description="Source name (e.g. 'MacroAlf', 'Bridgewater')"),
    author: Optional[str] = Form(None, description="Author name if known"),
    title: Optional[str] = Form(None, description="Override title if auto-detect fails"),
    tags: Optional[str] = Form(None, description="Comma-separated tags"),
    session: Session = Depends(get_db),
):
    """
    Upload a PDF document for analysis.

    The PDF will be:
    1. Text-extracted
    2. Stored as a ContentItem
    3. Queued for analysis (3-pass for our_thesis, 4-pass for external)
    4. Indexed into ChromaDB for RAG search

    Use this for paid newsletters (MacroAlf, etc), research reports, investor letters.
    """
    # Validate file type
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    # Read file
    pdf_bytes = await file.read()
    if len(pdf_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail=f"File too large. Max {MAX_FILE_SIZE // 1024 // 1024}MB")

    if len(pdf_bytes) < 100:
        raise HTTPException(status_code=400, detail="File appears to be empty")

    # Check for duplicate
    content_hash = hashlib.sha256(pdf_bytes).hexdigest()
    existing = session.execute(
        select(ContentItem).where(ContentItem.content_hash == content_hash)
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"This PDF has already been uploaded (item: {existing.item_id}, title: {existing.title})"
        )

    # Extract text
    extractor = PDFExtractor()
    result = extractor.extract_from_bytes(pdf_bytes, filename=file.filename)

    if not result:
        raise HTTPException(status_code=422, detail="Could not extract text from PDF. File may be image-only or corrupted.")

    # Save the PDF to disk for reference
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    pdf_path = os.path.join(UPLOAD_DIR, f"{gen_id()}_{file.filename}")
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)

    # Get or create the upload feed
    feed = _ensure_upload_feed(session, category, source_name)

    # Create content item
    tag_list = [t.strip() for t in tags.split(",")] if tags else []

    item = ContentItem(
        item_id=gen_id(),
        feed_id=feed.feed_id,
        url=f"file://{pdf_path}",
        title=title or result["title"],
        published_date=result.get("date") or datetime.now(timezone.utc),
        authors=[author] if author else ([result["author"]] if result.get("author") else []),
        summary=result["content"][:300],
        content_text=result["content"],
        content_hash=result["content_hash"],
        content_type="pdf_upload",
        analysis_status=AnalysisStatus.PENDING,
    )
    session.add(item)
    session.commit()

    logger.info(
        f"PDF uploaded: '{item.title}' ({result['page_count']} pages, "
        f"{len(result['content'])} chars) → queued for analysis"
    )

    return {
        "item_id": item.item_id,
        "title": item.title,
        "author": item.authors,
        "pages": result["page_count"],
        "content_length": len(result["content"]),
        "category": category,
        "source": source_name,
        "feed_id": feed.feed_id,
        "analysis_status": "pending",
        "message": f"PDF queued for analysis. The scheduler will process it within 5 minutes.",
    }


@router.post("/pdf/batch")
async def upload_pdf_batch(
    files: list[UploadFile] = File(...),
    category: str = Form("external_interview"),
    source_name: str = Form("Uploaded PDFs"),
    author: Optional[str] = Form(None),
    session: Session = Depends(get_db),
):
    """
    Upload multiple PDFs at once. All go to the same source feed.
    Useful for bulk importing a newsletter's back-catalog.
    """
    feed = _ensure_upload_feed(session, category, source_name)
    extractor = PDFExtractor()

    results = []
    for file in files:
        if not file.filename or not file.filename.lower().endswith('.pdf'):
            results.append({"filename": file.filename, "status": "skipped", "reason": "not a PDF"})
            continue

        pdf_bytes = await file.read()
        if len(pdf_bytes) > MAX_FILE_SIZE:
            results.append({"filename": file.filename, "status": "skipped", "reason": "too large"})
            continue

        # Check duplicate
        content_hash = hashlib.sha256(pdf_bytes).hexdigest()
        existing = session.execute(
            select(ContentItem).where(ContentItem.content_hash == content_hash)
        ).scalar_one_or_none()
        if existing:
            results.append({"filename": file.filename, "status": "duplicate", "existing_id": existing.item_id})
            continue

        result = extractor.extract_from_bytes(pdf_bytes, filename=file.filename)
        if not result:
            results.append({"filename": file.filename, "status": "failed", "reason": "no text extracted"})
            continue

        # Save PDF
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        pdf_path = os.path.join(UPLOAD_DIR, f"{gen_id()}_{file.filename}")
        with open(pdf_path, "wb") as f:
            f.write(pdf_bytes)

        item = ContentItem(
            item_id=gen_id(),
            feed_id=feed.feed_id,
            url=f"file://{pdf_path}",
            title=result["title"],
            published_date=result.get("date") or datetime.now(timezone.utc),
            authors=[author] if author else ([result["author"]] if result.get("author") else []),
            summary=result["content"][:300],
            content_text=result["content"],
            content_hash=result["content_hash"],
            content_type="pdf_upload",
            analysis_status=AnalysisStatus.PENDING,
        )
        session.add(item)
        results.append({
            "filename": file.filename,
            "status": "queued",
            "item_id": item.item_id,
            "title": result["title"],
            "pages": result["page_count"],
        })

    session.commit()

    queued = len([r for r in results if r["status"] == "queued"])
    logger.info(f"Batch PDF upload: {queued}/{len(files)} queued for analysis")

    return {
        "total": len(files),
        "queued": queued,
        "results": results,
    }


@router.get("/sources")
def list_upload_sources(session: Session = Depends(get_db)):
    """List all upload sources (auto-created feeds from PDF uploads)."""
    feeds = session.execute(
        select(Feed).where(Feed.url.startswith("upload://"))
    ).scalars().all()

    results = []
    for feed in feeds:
        count = session.execute(
            select(func.count(ContentItem.item_id))
            .where(ContentItem.feed_id == feed.feed_id)
        ).scalar()
        results.append({
            "feed_id": feed.feed_id,
            "source_name": feed.display_name,
            "category": feed.category.value,
            "item_count": count,
            "created_at": feed.created_at.isoformat(),
        })

    return results
