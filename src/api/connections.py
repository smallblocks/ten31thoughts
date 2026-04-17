"""
Ten31 Thoughts - Connections & Signals API
REST endpoints for reviewing, rating, dismissing, and promoting connections and signals.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..db.models import (
    Connection, UnconnectedSignal, Note, ContentItem, gen_id,
)
from ..db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/connections", tags=["connections"])
signals_router = APIRouter(prefix="/api/signals", tags=["signals"])


# ─── Response Models ───

class ConnectionResponse(BaseModel):
    connection_id: str
    item_id: str
    note_id: str
    relation: str
    articulation: str
    excerpt: Optional[str] = None
    excerpt_location: Optional[str] = None
    principles_invoked: list = Field(default_factory=list)
    user_rating: Optional[int] = None
    user_promoted_to_note: bool
    user_dismissed: bool
    strength: float
    created_at: str
    # Denormalized
    item_title: Optional[str] = None
    item_url: Optional[str] = None
    note_body: Optional[str] = None
    note_title: Optional[str] = None

    class Config:
        from_attributes = True


class UnconnectedSignalResponse(BaseModel):
    signal_id: str
    item_id: str
    topic_summary: str
    why_it_matters: str
    excerpt: Optional[str] = None
    user_dismissed: bool
    user_promoted_to_note: bool
    created_at: str
    # Denormalized
    item_title: Optional[str] = None
    item_url: Optional[str] = None

    class Config:
        from_attributes = True


class NoteResponse(BaseModel):
    note_id: str
    title: Optional[str] = None
    body: str
    topic: Optional[str] = None
    tags: list = Field(default_factory=list)
    source: Optional[str] = None
    source_item_id: Optional[str] = None
    source_url: Optional[str] = None
    created_at: str

    class Config:
        from_attributes = True


class RatingRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)


# ─── Helpers ───

def _connection_to_response(conn: Connection) -> ConnectionResponse:
    item = conn.item
    note = conn.note
    return ConnectionResponse(
        connection_id=conn.connection_id,
        item_id=conn.item_id,
        note_id=conn.note_id,
        relation=conn.relation if isinstance(conn.relation, str) else conn.relation.value,
        articulation=conn.articulation,
        excerpt=conn.excerpt,
        excerpt_location=conn.excerpt_location,
        principles_invoked=conn.principles_invoked or [],
        user_rating=conn.user_rating,
        user_promoted_to_note=conn.user_promoted_to_note,
        user_dismissed=conn.user_dismissed,
        strength=conn.strength,
        created_at=conn.created_at.isoformat(),
        item_title=item.title if item else None,
        item_url=item.url if item else None,
        note_body=note.body if note else None,
        note_title=note.title if note else None,
    )


def _signal_to_response(signal: UnconnectedSignal) -> UnconnectedSignalResponse:
    item = signal.item
    return UnconnectedSignalResponse(
        signal_id=signal.signal_id,
        item_id=signal.item_id,
        topic_summary=signal.topic_summary,
        why_it_matters=signal.why_it_matters,
        excerpt=signal.excerpt,
        user_dismissed=signal.user_dismissed,
        user_promoted_to_note=signal.user_promoted_to_note,
        created_at=signal.created_at.isoformat(),
        item_title=item.title if item else None,
        item_url=item.url if item else None,
    )


def _note_to_response(note: Note) -> NoteResponse:
    return NoteResponse(
        note_id=note.note_id,
        title=note.title,
        body=note.body,
        topic=note.topic,
        tags=note.tags or [],
        source=note.source,
        source_item_id=note.source_item_id,
        source_url=note.source_url,
        created_at=note.created_at.isoformat(),
    )


def _index_note_lenient(note: Note):
    """Best-effort ChromaDB indexing — warn on failure, never raise."""
    try:
        from ..db.vector import VectorStore
        vs = VectorStore()
        vs.index_note(
            note_id=note.note_id,
            body=note.body,
            metadata={
                "topic": note.topic or "",
                "source": note.source or "",
            },
        )
    except Exception as exc:
        logger.warning("ChromaDB index_note failed (non-fatal): %s", exc)


# ─── Connection Endpoints ───

@router.get("/", response_model=list[ConnectionResponse])
def list_connections(
    item_id: Optional[str] = None,
    note_id: Optional[str] = None,
    relation: Optional[str] = None,
    min_strength: Optional[float] = None,
    unrated: Optional[bool] = None,
    dismissed: bool = False,
    limit: int = 50,
    offset: int = 0,
    session: Session = Depends(get_db),
):
    """List connections with optional filters."""
    q = session.query(Connection)

    if not dismissed:
        q = q.filter(Connection.user_dismissed == False)
    if item_id:
        q = q.filter(Connection.item_id == item_id)
    if note_id:
        q = q.filter(Connection.note_id == note_id)
    if relation:
        q = q.filter(Connection.relation == relation)
    if min_strength is not None:
        q = q.filter(Connection.strength >= min_strength)
    if unrated:
        q = q.filter(Connection.user_rating == None)

    q = q.order_by(Connection.strength.desc())
    q = q.offset(offset).limit(limit)

    connections = q.all()
    return [_connection_to_response(c) for c in connections]


@router.get("/{connection_id}", response_model=ConnectionResponse)
def get_connection(
    connection_id: str,
    session: Session = Depends(get_db),
):
    """Get a single connection by ID."""
    conn = session.query(Connection).filter(
        Connection.connection_id == connection_id
    ).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")
    return _connection_to_response(conn)


@router.patch("/{connection_id}/rating", response_model=ConnectionResponse)
def rate_connection(
    connection_id: str,
    body: RatingRequest,
    session: Session = Depends(get_db),
):
    """Rate a connection 1-5."""
    conn = session.query(Connection).filter(
        Connection.connection_id == connection_id
    ).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")

    conn.user_rating = body.rating
    session.commit()
    session.refresh(conn)
    return _connection_to_response(conn)


@router.post("/{connection_id}/promote", response_model=NoteResponse, status_code=201)
def promote_connection(
    connection_id: str,
    session: Session = Depends(get_db),
):
    """Promote a connection to a new Note."""
    conn = session.query(Connection).filter(
        Connection.connection_id == connection_id
    ).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")

    item = session.query(ContentItem).filter(
        ContentItem.item_id == conn.item_id
    ).first()

    note = Note(
        note_id=gen_id(),
        body=conn.articulation,
        source="promoted_from_connection",
        source_item_id=conn.item_id,
        source_url=item.url if item else None,
    )
    session.add(note)

    conn.user_promoted_to_note = True
    session.commit()
    session.refresh(note)

    _index_note_lenient(note)

    return _note_to_response(note)


@router.delete("/{connection_id}", status_code=204)
def dismiss_connection(
    connection_id: str,
    session: Session = Depends(get_db),
):
    """Dismiss a connection (soft delete)."""
    conn = session.query(Connection).filter(
        Connection.connection_id == connection_id
    ).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connection not found")

    conn.user_dismissed = True
    session.commit()


# ─── Signal Endpoints ───

@signals_router.get("/", response_model=list[UnconnectedSignalResponse])
def list_signals(
    dismissed: bool = False,
    limit: int = 50,
    offset: int = 0,
    session: Session = Depends(get_db),
):
    """List unconnected signals."""
    q = session.query(UnconnectedSignal)

    if not dismissed:
        q = q.filter(UnconnectedSignal.user_dismissed == False)

    q = q.order_by(UnconnectedSignal.created_at.desc())
    q = q.offset(offset).limit(limit)

    signals = q.all()
    return [_signal_to_response(s) for s in signals]


@signals_router.patch("/{signal_id}/dismiss", status_code=204)
def dismiss_signal(
    signal_id: str,
    session: Session = Depends(get_db),
):
    """Dismiss a signal."""
    signal = session.query(UnconnectedSignal).filter(
        UnconnectedSignal.signal_id == signal_id
    ).first()
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")

    signal.user_dismissed = True
    session.commit()


@signals_router.post("/{signal_id}/promote", response_model=NoteResponse, status_code=201)
def promote_signal(
    signal_id: str,
    session: Session = Depends(get_db),
):
    """Promote a signal to a new Note."""
    signal = session.query(UnconnectedSignal).filter(
        UnconnectedSignal.signal_id == signal_id
    ).first()
    if not signal:
        raise HTTPException(status_code=404, detail="Signal not found")

    note = Note(
        note_id=gen_id(),
        body=signal.topic_summary + "\n\n" + signal.why_it_matters,
        source="promoted_from_signal",
        source_item_id=signal.item_id,
    )
    session.add(note)

    signal.user_promoted_to_note = True
    session.commit()
    session.refresh(note)

    _index_note_lenient(note)

    return _note_to_response(note)
