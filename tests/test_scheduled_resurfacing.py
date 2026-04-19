"""
Tests for the scheduled FSRS resurfacing trigger.
"""

import pytest
from datetime import datetime, timezone, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from src.db.models import (
    Base, Note, ResurfacingEvent, ResurfacingTrigger, gen_id,
)
from src.resurfacing.scheduled import fire_scheduled


@pytest.fixture
def db_session(tmp_path):
    """In-memory SQLite session with schema created."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _make_note(
    *,
    fsrs_due=None,
    fsrs_reps=0,
    archived=False,
    note_id=None,
):
    """Helper to create a Note with FSRS fields."""
    return Note(
        note_id=note_id or gen_id(),
        body="Test note body",
        topic="bitcoin",
        archived=archived,
        fsrs_due=fsrs_due,
        fsrs_reps=fsrs_reps,
    )


def _make_event(note_id, trigger, hours_ago):
    """Helper to create a ResurfacingEvent at a specific time in the past."""
    return ResurfacingEvent(
        event_id=gen_id(),
        note_id=note_id,
        trigger=trigger,
        surfaced_at=datetime.now(timezone.utc) - timedelta(hours=hours_ago),
    )


class TestFireScheduled:
    """Tests for fire_scheduled()."""

    def test_due_note_with_reps_creates_event(self, db_session):
        """Note with fsrs_due < now and fsrs_reps > 0 should get a SCHEDULED event."""
        note = _make_note(
            fsrs_due=datetime.now(timezone.utc) - timedelta(hours=1),
            fsrs_reps=3,
        )
        db_session.add(note)
        db_session.commit()

        count = fire_scheduled(db_session)

        assert count == 1
        events = db_session.execute(
            select(ResurfacingEvent).where(ResurfacingEvent.note_id == note.note_id)
        ).scalars().all()
        assert len(events) == 1
        assert events[0].trigger == ResurfacingTrigger.SCHEDULED

    def test_future_due_note_no_event(self, db_session):
        """Note with fsrs_due > now should NOT get an event."""
        note = _make_note(
            fsrs_due=datetime.now(timezone.utc) + timedelta(hours=24),
            fsrs_reps=3,
        )
        db_session.add(note)
        db_session.commit()

        count = fire_scheduled(db_session)

        assert count == 0

    def test_new_note_no_event(self, db_session):
        """Note with fsrs_due=None and fsrs_reps=0 (new) should NOT get an event."""
        note = _make_note(fsrs_due=None, fsrs_reps=0)
        db_session.add(note)
        db_session.commit()

        count = fire_scheduled(db_session)

        assert count == 0

    def test_archived_note_no_event(self, db_session):
        """Archived note should NOT get an event even if due."""
        note = _make_note(
            fsrs_due=datetime.now(timezone.utc) - timedelta(hours=1),
            fsrs_reps=3,
            archived=True,
        )
        db_session.add(note)
        db_session.commit()

        count = fire_scheduled(db_session)

        assert count == 0

    def test_recent_scheduled_event_prevents_duplicate(self, db_session):
        """Existing SCHEDULED event within 24h should block a new one."""
        note = _make_note(
            fsrs_due=datetime.now(timezone.utc) - timedelta(hours=1),
            fsrs_reps=3,
        )
        db_session.add(note)
        db_session.commit()

        # Add a SCHEDULED event from 12 hours ago
        event = _make_event(note.note_id, ResurfacingTrigger.SCHEDULED, hours_ago=12)
        db_session.add(event)
        db_session.commit()

        count = fire_scheduled(db_session)

        assert count == 0

    def test_old_scheduled_event_allows_new(self, db_session):
        """Existing SCHEDULED event older than 24h should NOT block a new one."""
        note = _make_note(
            fsrs_due=datetime.now(timezone.utc) - timedelta(hours=1),
            fsrs_reps=3,
        )
        db_session.add(note)
        db_session.commit()

        # Add a SCHEDULED event from 36 hours ago (outside cooldown)
        event = _make_event(note.note_id, ResurfacingTrigger.SCHEDULED, hours_ago=36)
        db_session.add(event)
        db_session.commit()

        count = fire_scheduled(db_session)

        assert count == 1
        events = db_session.execute(
            select(ResurfacingEvent).where(
                ResurfacingEvent.note_id == note.note_id,
                ResurfacingEvent.trigger == ResurfacingTrigger.SCHEDULED,
            )
        ).scalars().all()
        assert len(events) == 2  # old + new

    def test_semantic_event_does_not_block_scheduled(self, db_session):
        """Existing SEMANTIC_ON_WRITE event should NOT block a SCHEDULED event."""
        note = _make_note(
            fsrs_due=datetime.now(timezone.utc) - timedelta(hours=1),
            fsrs_reps=3,
        )
        db_session.add(note)
        db_session.commit()

        # Add a recent SEMANTIC_ON_WRITE event
        event = _make_event(note.note_id, ResurfacingTrigger.SEMANTIC_ON_WRITE, hours_ago=1)
        db_session.add(event)
        db_session.commit()

        count = fire_scheduled(db_session)

        assert count == 1
