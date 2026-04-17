"""
Ten31 Thoughts - Notes API
CRUD endpoints for personal notes used by the resurfacing engine.
Every create, update, archive, and restore writes through to ChromaDB so
notes remain searchable for the semantic-on-write and news-driven triggers.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session

from ..db.models import Note, gen_id
from ..db.session import get_db
from ..db.vector import VectorStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/notes", tags=["notes"])


# ─── Request/Response Models ───

class CreateNoteRequest(BaseModel):
    body: str = Field(..., min_length=1, description="Note content (required)")
    title: Optional[str] = Field(None, max_length=500)
    topic: Optional[str] = Field(None, description="Same vocabulary as ThesisElement.topic")
    tags: list[str] = Field(default_factory=list)
    source_url: Optional[str] = None


class UpdateNoteRequest(BaseModel):
    body: Optional[str] = Field(None, min_length=1)
    title: Optional[str] = None
    topic: Optional[str] = None
    tags: Optional[list[str]] = None
    source_url: Optional[str] = None


class NoteResponse(BaseModel):
    note_id: str
    title: Optional[str]
    body: str
    topic: Optional[str]
    tags: list[str]
    source_url: Optional[str]
    archived: bool
    created_at: str
    updated_at: str
    fsrs_due: Optional[str]
    fsrs_state: int
    fsrs_reps: int

    class Config:
        from_attributes = True


# ─── Helpers ───

def note_to_response(note: Note) -> NoteResponse:
    return NoteResponse(
        note_id=note.note_id,
        title=note.title,
        body=note.body,
        topic=note.topic,
        tags=note.tags or [],
        source_url=note.source_url,
        archived=note.archived,
        created_at=note.created_at.isoformat(),
        updated_at=note.updated_at.isoformat(),
        fsrs_due=note.fsrs_due.isoformat() if note.fsrs_due else None,
        fsrs_state=note.fsrs_state,
        fsrs_reps=note.fsrs_reps,
    )


def _build_note_metadata(note: Note) -> dict:
    """Metadata sent to ChromaDB for a note. Kept minimal."""
    return {
        "topic": note.topic or "",
        "archived": note.archived,
        "created_at": note.created_at.isoformat(),
    }


def _index_note_lenient(note: Note) -> None:
    """
    Write-through to ChromaDB. Lenient: failures log a warning but do not
    raise. Mirrors the pattern in src/worker/scheduler.py.
    """
    try:
        vs = VectorStore()
        vs.index_note(
            note_id=note.note_id,
            body=note.body,
            metadata=_build_note_metadata(note),
        )
    except Exception as e:
        logger.warning(
            f"Chroma write-through failed for note {note.note_id}: {e}. "
            f"Note exists in SQL but is not yet indexed for semantic search."
        )


# ─── Endpoints ───

@router.post("/", response_model=NoteResponse, status_code=201)
def create_note(
    request: CreateNoteRequest,
    session: Session = Depends(get_db),
):
    """Create a new note. Writes through to ChromaDB."""
    body = request.body.strip()
    if not body:
        raise HTTPException(status_code=400, detail="Body cannot be empty or whitespace only")

    title = request.title.strip() if request.title else None
    if title == "":
        title = None

    note = Note(
        note_id=gen_id(),
        title=title,
        body=body,
        topic=request.topic,
        tags=request.tags,
        source_url=request.source_url,
        archived=False,
    )
    session.add(note)
    session.commit()
    session.refresh(note)

    _index_note_lenient(note)

    return note_to_response(note)


@router.get("/", response_model=list[NoteResponse])
def list_notes(
    topic: Optional[str] = None,
    tag: Optional[str] = None,
    archived: bool = False,
    limit: int = 50,
    offset: int = 0,
    session: Session = Depends(get_db),
):
    """
    List notes. Filterable by topic, single tag, and archived status.
    Default returns active (non-archived) notes only.
    """
    query = select(Note).where(Note.archived == archived)
    if topic:
        query = query.where(Note.topic == topic)
    query = query.order_by(Note.updated_at.desc()).limit(limit).offset(offset)

    notes = list(session.execute(query).scalars().all())

    if tag:
        notes = [n for n in notes if n.tags and tag in n.tags]

    return [note_to_response(n) for n in notes]


@router.get("/{note_id}", response_model=NoteResponse)
def get_note(
    note_id: str,
    session: Session = Depends(get_db),
):
    """Get a single note by ID."""
    note = session.get(Note, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")
    return note_to_response(note)


@router.patch("/{note_id}", response_model=NoteResponse)
def update_note(
    note_id: str,
    request: UpdateNoteRequest,
    session: Session = Depends(get_db),
):
    """
    Partial update. Only fields present in the request body are modified.
    Write-through to Chroma fires only when body or topic changed.
    """
    note = session.get(Note, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    needs_reindex = False

    if request.body is not None:
        new_body = request.body.strip()
        if not new_body:
            raise HTTPException(status_code=400, detail="Body cannot be empty or whitespace only")
        if new_body != note.body:
            note.body = new_body
            needs_reindex = True

    if request.title is not None:
        new_title = request.title.strip() if request.title else None
        note.title = new_title or None

    if request.topic is not None:
        if request.topic != note.topic:
            note.topic = request.topic
            needs_reindex = True

    if request.tags is not None:
        note.tags = request.tags

    if request.source_url is not None:
        note.source_url = request.source_url or None

    session.commit()
    session.refresh(note)

    if needs_reindex:
        _index_note_lenient(note)

    return note_to_response(note)


@router.delete("/{note_id}", status_code=204)
def archive_note(
    note_id: str,
    session: Session = Depends(get_db),
):
    """Soft-delete: sets archived=True."""
    note = session.get(Note, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    if note.archived:
        return

    note.archived = True
    session.commit()
    session.refresh(note)

    _index_note_lenient(note)


@router.post("/{note_id}/restore", response_model=NoteResponse)
def restore_note(
    note_id: str,
    session: Session = Depends(get_db),
):
    """Un-archive a note. Updates Chroma metadata."""
    note = session.get(Note, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Note not found")

    if not note.archived:
        return note_to_response(note)

    note.archived = False
    session.commit()
    session.refresh(note)

    _index_note_lenient(note)

    return note_to_response(note)
