"""
Tests for the v3 migration script.
Run with: pytest tests/test_v3_migration.py -v
"""

import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from src.db.models import (
    Base,
    Feed,
    FeedCategory,
    FeedStatus,
    ContentItem,
    AnalysisStatus,
    ThesisElement,
    ConvictionLevel,
    Note,
    create_tables,
)
from scripts.migrate_v3 import run_migration


@pytest.fixture
def engine():
    """Create an in-memory SQLite engine with all tables."""
    eng = create_engine("sqlite:///:memory:", echo=False)
    create_tables(eng)
    return eng


@pytest.fixture
def session(engine):
    """Create a session bound to the test engine."""
    Session = sessionmaker(bind=engine)
    sess = Session()
    yield sess
    sess.close()


def _seed_feed(session, category=FeedCategory.OUR_THESIS, feed_id="feed-1"):
    """Helper to create a feed."""
    feed = Feed(
        feed_id=feed_id,
        url=f"https://example.com/{feed_id}",
        category=category,
        display_name=f"Test Feed ({feed_id})",
        status=FeedStatus.ACTIVE,
    )
    session.add(feed)
    session.commit()
    return feed


def _seed_content_item(session, feed_id="feed-1", item_id="item-1",
                       status=AnalysisStatus.PENDING):
    """Helper to create a content item."""
    item = ContentItem(
        item_id=item_id,
        feed_id=feed_id,
        url=f"https://example.com/{item_id}",
        title=f"Test Item {item_id}",
        analysis_status=status,
    )
    session.add(item)
    session.commit()
    return item


def _seed_thesis_element(session, item_id="item-1", element_id=None,
                         claim_text="Test claim", topic="bitcoin",
                         thread_id=None, created_at=None):
    """Helper to create a thesis element."""
    elem = ThesisElement(
        element_id=element_id or f"elem-{claim_text[:10]}",
        item_id=item_id,
        claim_text=claim_text,
        topic=topic,
        conviction=ConvictionLevel.MODERATE,
        thread_id=thread_id,
        created_at=created_at or datetime.now(timezone.utc),
    )
    session.add(elem)
    session.commit()
    return elem


class TestCreatesTables:
    def test_creates_new_tables(self, engine):
        """Run migration on fresh DB, verify connections and unconnected_signals exist."""
        run_migration(engine, dry_run=False)

        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert "connections" in tables
        assert "unconnected_signals" in tables


class TestMigratesThesisElements:
    def test_migrates_thesis_elements(self, engine, session):
        """Seed DB with 3 ThesisElements, run migration, verify 3 Notes created."""
        feed = _seed_feed(session)
        item = _seed_content_item(session, feed_id=feed.feed_id)

        ts1 = datetime(2025, 1, 1, tzinfo=timezone.utc)
        ts2 = datetime(2025, 2, 1, tzinfo=timezone.utc)
        ts3 = datetime(2025, 3, 1, tzinfo=timezone.utc)

        _seed_thesis_element(session, item_id=item.item_id, element_id="e1",
                             claim_text="Bitcoin will decouple from equities",
                             topic="bitcoin", created_at=ts1)
        _seed_thesis_element(session, item_id=item.item_id, element_id="e2",
                             claim_text="Fed will pivot by Q3",
                             topic="fed_policy", thread_id="thread-1", created_at=ts2)
        _seed_thesis_element(session, item_id=item.item_id, element_id="e3",
                             claim_text="Labor market is weaker than reported",
                             topic="labor", created_at=ts3)

        run_migration(engine, dry_run=False)

        notes = session.query(Note).filter(Note.source == "timestamp").all()
        assert len(notes) == 3

        # Check fields are correctly mapped
        note_map = {n.body: n for n in notes}

        btc_note = note_map["Bitcoin will decouple from equities"]
        assert btc_note.topic == "bitcoin"
        assert btc_note.source == "timestamp"
        assert btc_note.source_item_id == item.item_id
        # SQLite drops tzinfo, so compare naive
        assert btc_note.created_at.replace(tzinfo=None) == ts1.replace(tzinfo=None)

        fed_note = note_map["Fed will pivot by Q3"]
        assert fed_note.topic == "fed_policy"
        assert "thread:thread-1" in fed_note.tags

        labor_note = note_map["Labor market is weaker than reported"]
        assert labor_note.created_at.replace(tzinfo=None) == ts3.replace(tzinfo=None)


class TestIdempotent:
    def test_idempotent(self, engine, session):
        """Run migration twice, verify same number of Notes (no duplicates)."""
        feed = _seed_feed(session)
        item = _seed_content_item(session, feed_id=feed.feed_id)
        _seed_thesis_element(session, item_id=item.item_id, element_id="e1",
                             claim_text="Sats flow is the new revenue model",
                             topic="bitcoin")
        _seed_thesis_element(session, item_id=item.item_id, element_id="e2",
                             claim_text="Proof of work over proof of stake",
                             topic="bitcoin")

        results1 = run_migration(engine, dry_run=False)
        count_after_first = session.query(Note).filter(Note.source == "timestamp").count()

        results2 = run_migration(engine, dry_run=False)
        count_after_second = session.query(Note).filter(Note.source == "timestamp").count()

        assert count_after_first == 2
        assert count_after_second == 2
        assert results2["thesis_elements"]["migrated"] == 0
        assert results2["thesis_elements"]["skipped"] == 2


class TestMarksExternalSkipped:
    def test_marks_external_skipped(self, engine, session):
        """Seed DB with external ContentItems (PENDING), verify they're SKIPPED."""
        ext_feed = _seed_feed(session, category=FeedCategory.EXTERNAL_INTERVIEW,
                              feed_id="ext-feed")
        _seed_content_item(session, feed_id=ext_feed.feed_id, item_id="ext-1",
                           status=AnalysisStatus.PENDING)
        _seed_content_item(session, feed_id=ext_feed.feed_id, item_id="ext-2",
                           status=AnalysisStatus.ANALYZING)

        run_migration(engine, dry_run=False)

        items = session.query(ContentItem).filter(
            ContentItem.item_id.in_(["ext-1", "ext-2"])
        ).all()
        for item in items:
            assert item.analysis_status == AnalysisStatus.SKIPPED


class TestPreservesCompleteItems:
    def test_preserves_complete_items(self, engine, session):
        """Seed DB with COMPLETE ContentItems, verify they stay COMPLETE."""
        ext_feed = _seed_feed(session, category=FeedCategory.EXTERNAL_INTERVIEW,
                              feed_id="ext-feed")
        _seed_content_item(session, feed_id=ext_feed.feed_id, item_id="complete-1",
                           status=AnalysisStatus.COMPLETE)

        run_migration(engine, dry_run=False)

        item = session.query(ContentItem).filter_by(item_id="complete-1").one()
        assert item.analysis_status == AnalysisStatus.COMPLETE


class TestDryRun:
    def test_dry_run(self, engine, session):
        """Run with dry_run=True, verify no DB changes."""
        feed = _seed_feed(session)
        item = _seed_content_item(session, feed_id=feed.feed_id)
        _seed_thesis_element(session, item_id=item.item_id, element_id="e1",
                             claim_text="Dry run should not create notes",
                             topic="bitcoin")

        ext_feed = _seed_feed(session, category=FeedCategory.EXTERNAL_INTERVIEW,
                              feed_id="ext-feed")
        _seed_content_item(session, feed_id=ext_feed.feed_id, item_id="ext-1",
                           status=AnalysisStatus.PENDING)

        results = run_migration(engine, dry_run=True)

        # No notes created
        note_count = session.query(Note).filter(Note.source == "timestamp").count()
        assert note_count == 0

        # No items marked SKIPPED
        ext_item = session.query(ContentItem).filter_by(item_id="ext-1").one()
        assert ext_item.analysis_status == AnalysisStatus.PENDING

        # But stats should report what would happen
        assert results["dry_run"] is True
        assert results["thesis_elements"]["migrated"] == 1
        assert results["items_skipped"] == 1
