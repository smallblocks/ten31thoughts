"""
Ten31 Thoughts - v3 Migration Script
Migrates from the multi-pass architecture to connection-first.

Operations:
1. Create new tables (Connection, UnconnectedSignal) if they don't exist
2. Add new columns to Note (source, source_item_id) if they don't exist
3. Add SKIPPED to AnalysisStatus if needed
4. Migrate ThesisElement rows → Note rows (source="timestamp")
5. Mark all existing external content items as SKIPPED
6. Index migrated notes in ChromaDB vector store
7. Report migration stats

Zero LLM cost. Idempotent — safe to run multiple times.

Usage: PYTHONPATH=. python scripts/migrate_v3.py [--db-path <path>] [--dry-run]
"""

import argparse
import logging
import time
from datetime import datetime, timezone

from sqlalchemy import text, inspect
from sqlalchemy.orm import Session, sessionmaker

from src.db.models import (
    Base,
    ThesisElement,
    ContentItem,
    Feed,
    FeedCategory,
    AnalysisStatus,
    Note,
    Connection,
    UnconnectedSignal,
    create_tables,
    get_engine,
)

logger = logging.getLogger(__name__)


def _column_exists(engine, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a SQLite table."""
    with engine.connect() as conn:
        result = conn.execute(text(f"PRAGMA table_info({table_name})"))
        columns = [row[1] for row in result]
        return column_name in columns


def _add_note_columns(engine, dry_run: bool = False) -> list[str]:
    """Add missing v3 columns to the notes table. Returns list of columns added."""
    added = []
    for col_name, col_def in [
        ("source", "TEXT"),
        ("source_item_id", "TEXT REFERENCES content_items(item_id)"),
    ]:
        if not _column_exists(engine, "notes", col_name):
            if dry_run:
                logger.info(f"[DRY RUN] Would add column notes.{col_name}")
            else:
                with engine.connect() as conn:
                    conn.execute(text(
                        f"ALTER TABLE notes ADD COLUMN {col_name} {col_def}"
                    ))
                    conn.commit()
                logger.info(f"Added column notes.{col_name}")
            added.append(col_name)
    return added


def _migrate_thesis_elements(session: Session, dry_run: bool = False) -> dict:
    """Migrate ThesisElement rows to Note rows. Returns stats dict."""
    elements = session.query(ThesisElement).all()
    stats = {"found": len(elements), "migrated": 0, "skipped": 0}

    if not elements:
        return stats

    # Pre-fetch existing note bodies for idempotency check
    existing_bodies = set(
        row[0] for row in session.query(Note.body).filter(Note.source == "timestamp").all()
    )

    batch = []
    for elem in elements:
        if elem.claim_text in existing_bodies:
            stats["skipped"] += 1
            continue

        if dry_run:
            stats["migrated"] += 1
            continue

        note = Note(
            body=elem.claim_text,
            topic=elem.topic,
            source="timestamp",
            source_item_id=elem.item_id,
            tags=[],
            created_at=elem.created_at,
        )
        if elem.thread_id:
            # Carry thread_id as a tag for traceability
            note.tags = [f"thread:{elem.thread_id}"]

        batch.append(note)
        stats["migrated"] += 1

        if len(batch) >= 50:
            session.add_all(batch)
            session.flush()
            batch = []

    if batch and not dry_run:
        session.add_all(batch)
        session.flush()

    if not dry_run:
        session.commit()

    return stats


def _mark_external_skipped(session: Session, dry_run: bool = False) -> int:
    """Mark external (non-OUR_THESIS) content items as SKIPPED. Returns count updated."""
    # Get items from external feeds that are not COMPLETE and not already SKIPPED
    items = (
        session.query(ContentItem)
        .join(Feed, ContentItem.feed_id == Feed.feed_id)
        .filter(Feed.category != FeedCategory.OUR_THESIS)
        .filter(ContentItem.analysis_status != AnalysisStatus.COMPLETE)
        .filter(ContentItem.analysis_status != AnalysisStatus.SKIPPED)
        .all()
    )

    if dry_run:
        return len(items)

    for item in items:
        item.analysis_status = AnalysisStatus.SKIPPED

    if items:
        session.commit()

    return len(items)


def _index_migrated_notes(session: Session, dry_run: bool = False) -> dict:
    """Index migrated notes in ChromaDB vector store. Returns stats dict."""
    notes = session.query(Note).filter(Note.source == "timestamp").all()
    stats = {"total": len(notes), "indexed": 0, "failed": 0}

    if dry_run or not notes:
        return stats

    try:
        from src.db.vector import VectorStore
        vector_store = VectorStore()
    except Exception as e:
        logger.warning(f"Could not connect to ChromaDB, skipping indexing: {e}")
        stats["failed"] = len(notes)
        return stats

    for note in notes:
        try:
            metadata = {
                "topic": note.topic or "",
                "source": note.source or "",
                "note_id": note.note_id,
            }
            vector_store.index_note(
                note_id=note.note_id,
                body=note.body,
                metadata=metadata,
            )
            stats["indexed"] += 1
        except Exception as e:
            logger.warning(f"Failed to index note {note.note_id}: {e}")
            stats["failed"] += 1

    return stats


def run_migration(engine, dry_run: bool = False) -> dict:
    """
    Run the full v3 migration.

    Returns a stats dict with all migration results.
    """
    start_time = time.time()
    prefix = "[DRY RUN] " if dry_run else ""

    logger.info(f"{prefix}Starting v3 migration...")

    # Step 1: Create new tables (Connection, UnconnectedSignal)
    if not dry_run:
        create_tables(engine)
    logger.info(f"{prefix}Step 1: Tables ensured")

    # Step 2: Add missing columns to notes table
    inspector = inspect(engine)
    if "notes" in inspector.get_table_names():
        columns_added = _add_note_columns(engine, dry_run)
    else:
        columns_added = []
    logger.info(f"{prefix}Step 2: Columns checked ({len(columns_added)} added)")

    # Steps 3-5 need a session
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        # Step 3: Migrate ThesisElement → Note
        thesis_stats = _migrate_thesis_elements(session, dry_run)
        logger.info(
            f"{prefix}Step 3: ThesisElements — "
            f"{thesis_stats['found']} found, "
            f"{thesis_stats['migrated']} migrated, "
            f"{thesis_stats['skipped']} skipped"
        )

        # Step 4: Mark external content as SKIPPED
        skipped_count = _mark_external_skipped(session, dry_run)
        logger.info(f"{prefix}Step 4: {skipped_count} external items marked SKIPPED")

        # Step 5: Index migrated notes in vector store
        index_stats = _index_migrated_notes(session, dry_run)
        logger.info(
            f"{prefix}Step 5: Vector indexing — "
            f"{index_stats['indexed']} indexed, "
            f"{index_stats['failed']} failed"
        )

    finally:
        session.close()

    elapsed = time.time() - start_time

    results = {
        "dry_run": dry_run,
        "columns_added": columns_added,
        "thesis_elements": thesis_stats,
        "items_skipped": skipped_count,
        "vector_index": index_stats,
        "elapsed_seconds": round(elapsed, 2),
    }

    logger.info(f"{prefix}Migration complete in {elapsed:.2f}s")
    return results


def main():
    parser = argparse.ArgumentParser(description="Ten31 Thoughts v3 Migration")
    parser.add_argument(
        "--db-path",
        default="sqlite:///data/ten31thoughts.db",
        help="Database URL (default: sqlite:///data/ten31thoughts.db)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would happen without writing",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    engine = get_engine(args.db_path)
    results = run_migration(engine, dry_run=args.dry_run)

    # Print summary
    prefix = "[DRY RUN] " if results["dry_run"] else ""
    print(f"\n{'=' * 60}")
    print(f"{prefix}v3 Migration Summary")
    print(f"{'=' * 60}")
    print(f"Columns added:         {len(results['columns_added'])}")
    te = results["thesis_elements"]
    print(f"ThesisElements found:  {te['found']}")
    print(f"  → Migrated to Notes: {te['migrated']}")
    print(f"  → Skipped (exist):   {te['skipped']}")
    print(f"Items marked SKIPPED:  {results['items_skipped']}")
    vi = results["vector_index"]
    print(f"Notes indexed (vector):{vi['indexed']}")
    print(f"Notes index failed:    {vi['failed']}")
    print(f"Time elapsed:          {results['elapsed_seconds']}s")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
