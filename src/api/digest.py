"""
Ten31 Thoughts - Digest API Endpoints
Weekly digest retrieval and generation.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.session import get_db
from ..db.models import Digest

router = APIRouter(prefix="/api/digest", tags=["digest"])


@router.get("/latest")
def get_latest_digest(session: Session = Depends(get_db)):
    """Get the most recent weekly digest."""
    digest = session.execute(
        select(Digest)
        .order_by(Digest.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    if not digest:
        raise HTTPException(status_code=404, detail="No digests found")

    return _digest_to_dict(digest)


@router.get("/")
def list_digests(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db),
):
    """List all digests (paginated)."""
    total = session.execute(
        select(Digest.digest_id)
    ).all()

    digests = session.execute(
        select(Digest)
        .order_by(Digest.created_at.desc())
        .offset(offset)
        .limit(limit)
    ).scalars().all()

    return {
        "total": len(total),
        "offset": offset,
        "limit": limit,
        "digests": [_digest_to_dict(d) for d in digests],
    }


def _digest_to_dict(digest: Digest) -> dict:
    return {
        "digest_id": digest.digest_id,
        "period_start": digest.period_start.isoformat() if digest.period_start else None,
        "period_end": digest.period_end.isoformat() if digest.period_end else None,
        "html_content": digest.html_content,
        "created_at": digest.created_at.isoformat() if digest.created_at else None,
    }
