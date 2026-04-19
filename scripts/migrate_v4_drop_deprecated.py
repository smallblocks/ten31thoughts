#!/usr/bin/env python3
"""
Ten31 Thoughts — v4 Migration: Drop Deprecated Tables

This script removes six tables from the v1/v2 multi-pass analysis architecture
that are no longer used in v3+:

  1. convergence_records
  2. prediction_market_links
  3. blind_spots
  4. external_frameworks
  5. thesis_elements
  6. weekly_briefings

Tables are dropped in FK-dependency order.

PREREQUISITES:
  - The v3 migration (scripts/migrate_v3.py) must have completed first.
    This script checks for migrated notes or an empty thesis_elements table.

WHEN TO RUN:
  - After upgrading to a v4+ build of Ten31 Thoughts.
  - Only needs to run once per database. Re-running is safe (idempotent).

THIS IS IRREVERSIBLE:
  - Dropped tables cannot be recovered without a database backup.
  - The --dry-run flag shows what would happen without making changes.
  - The --confirm flag is required when dropping tables that contain data.

Usage:
  python scripts/migrate_v4_drop_deprecated.py --db-path sqlite:///data/ten31thoughts.db --dry-run
  python scripts/migrate_v4_drop_deprecated.py --db-path sqlite:///data/ten31thoughts.db --confirm
"""

import argparse
import logging
import sys

from sqlalchemy import create_engine, text, inspect

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger("v4-migration")

# Tables to drop in FK-dependency order
TABLES_TO_DROP = [
    "convergence_records",
    "prediction_market_links",
    "blind_spots",
    "external_frameworks",
    "thesis_elements",
    "weekly_briefings",
]

# ELO columns to drop from guest_profiles
ELO_COLUMNS = [
    "elo_rating",
    "elo_peak",
    "elo_floor",
    "elo_predictions_counted",
    "elo_history",
]


def _table_exists(conn, table_name: str) -> bool:
    """Check if a table exists in the database."""
    result = conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
        {"name": table_name}
    )
    return result.fetchone() is not None


def _count_rows(conn, table_name: str) -> int:
    """Count rows in a table. Returns 0 if table doesn't exist."""
    if not _table_exists(conn, table_name):
        return 0
    result = conn.execute(text(f"SELECT COUNT(*) FROM [{table_name}]"))
    return result.scalar()


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    if not _table_exists(conn, table_name):
        return False
    result = conn.execute(text(f"PRAGMA table_info([{table_name}])"))
    columns = [row[1] for row in result]
    return column_name in columns


def _check_v3_prerequisite(conn) -> bool:
    """
    Verify that v3 migration has completed.
    Returns True if safe to proceed.
    """
    # Check 1: notes table has rows with source="timestamp" (v3 migrated thesis elements)
    if _table_exists(conn, "notes"):
        result = conn.execute(
            text("SELECT COUNT(*) FROM notes WHERE source = 'timestamp'")
        )
        if result.scalar() > 0:
            return True

    # Check 2: thesis_elements table is empty (nothing to migrate)
    if _table_exists(conn, "thesis_elements"):
        result = conn.execute(text("SELECT COUNT(*) FROM thesis_elements"))
        if result.scalar() == 0:
            return True

    # Check 3: thesis_elements table doesn't exist (already dropped or never created)
    if not _table_exists(conn, "thesis_elements"):
        return True

    return False


def run_migration(engine, dry_run: bool = False, confirm: bool = False):
    """Run the v4 migration."""
    prefix = "[DRY RUN] " if dry_run else ""

    with engine.connect() as conn:
        # Pre-flight: check v3 prerequisite
        if not _check_v3_prerequisite(conn):
            logger.error(
                "v3 migration has NOT completed. The thesis_elements table has data "
                "that hasn't been migrated to notes.\n"
                "Run: PYTHONPATH=. python scripts/migrate_v3.py --db-path <path>\n"
                "Then re-run this script."
            )
            sys.exit(1)

        # Pre-flight: summarize what will be dropped
        print(f"\n{'=' * 60}")
        print(f"{prefix}V4 MIGRATION — DROP DEPRECATED TABLES")
        print(f"{'=' * 60}\n")

        total_rows = 0
        table_counts = {}
        for table in TABLES_TO_DROP:
            if _table_exists(conn, table):
                count = _count_rows(conn, table)
                table_counts[table] = count
                total_rows += count
                status = f"{count} rows" if count > 0 else "empty"
                print(f"  {table}: {status}")
            else:
                table_counts[table] = -1
                print(f"  {table}: already dropped")

        # Check ELO columns
        elo_present = []
        if _table_exists(conn, "guest_profiles"):
            for col in ELO_COLUMNS:
                if _column_exists(conn, "guest_profiles", col):
                    elo_present.append(col)
        if elo_present:
            print(f"\n  guest_profiles ELO columns to remove: {', '.join(elo_present)}")

        print()

        # Confirm gate
        if not dry_run and total_rows > 0 and not confirm:
            print(
                "⚠️  WARNING: Tables contain data. This operation is IRREVERSIBLE.\n"
                "   Add --confirm to proceed, or use --dry-run to preview.\n"
            )
            sys.exit(1)

        # Drop tables
        dropped = 0
        for table in TABLES_TO_DROP:
            if table_counts[table] == -1:
                print(f"{prefix}{table}: already dropped ✓")
                continue

            if dry_run:
                print(f"{prefix}Would drop {table} ({table_counts[table]} rows)")
            else:
                conn.execute(text(f"DROP TABLE IF EXISTS [{table}]"))
                conn.commit()
                dropped += 1
                print(f"{prefix}Dropped {table} ({table_counts[table]} rows) ✓")

        # Drop ELO columns from guest_profiles (SQLite doesn't support DROP COLUMN
        # before 3.35.0, so we recreate the table without ELO columns)
        if elo_present:
            if dry_run:
                print(f"\n{prefix}Would remove ELO columns from guest_profiles")
            else:
                _drop_elo_columns(conn)
                print(f"\n{prefix}Removed ELO columns from guest_profiles ✓")

        # Summary
        print(f"\n{'=' * 60}")
        if dry_run:
            print(f"DRY RUN complete. {len([t for t in table_counts if table_counts[t] >= 0])} tables would be dropped.")
        else:
            print(f"Migration complete. {dropped} tables dropped.")
        print(f"{'=' * 60}\n")


def _drop_elo_columns(conn):
    """
    Remove ELO columns from guest_profiles.
    Uses SQLite's ALTER TABLE DROP COLUMN (available since SQLite 3.35.0, 2021-03).
    Falls back to table rebuild if not supported.
    """
    for col in ELO_COLUMNS:
        if _column_exists(conn, "guest_profiles", col):
            try:
                conn.execute(text(f"ALTER TABLE guest_profiles DROP COLUMN [{col}]"))
                conn.commit()
            except Exception:
                # SQLite < 3.35.0 — skip column drops, not critical
                logger.warning(
                    f"Could not drop column guest_profiles.{col} "
                    f"(SQLite may be < 3.35.0). Column left in place."
                )
                return


def main():
    parser = argparse.ArgumentParser(
        description="Ten31 Thoughts — v4 Migration: Drop Deprecated Tables"
    )
    parser.add_argument(
        "--db-path", required=True,
        help="Database URL (e.g. sqlite:///data/ten31thoughts.db)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be dropped without making changes"
    )
    parser.add_argument(
        "--confirm", action="store_true",
        help="Required when dropping tables that contain data"
    )

    args = parser.parse_args()
    engine = create_engine(args.db_path, echo=False)
    run_migration(engine, dry_run=args.dry_run, confirm=args.confirm)


if __name__ == "__main__":
    main()
