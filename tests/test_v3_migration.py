"""
Tests for the v3 migration script.

SKIPPED in v4: ThesisElement and ConvictionLevel models were removed.
The v3 migration is a historical concern — these tests are preserved
for reference but no longer executable.

Run with: pytest tests/test_v3_migration.py -v
"""

import pytest

pytestmark = pytest.mark.skip(reason="ThesisElement removed in v4 — v3 migration tests preserved for reference")

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


class TestCreatesTables:
    def test_creates_new_tables(self, engine):
        """Run migration on fresh DB, verify connections and unconnected_signals exist."""
        run_migration(engine, dry_run=False)

        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert "connections" in tables
        assert "unconnected_signals" in tables


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
