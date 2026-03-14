"""
Ten31 Thoughts - Seed Script
Initialize the system with the core feeds:
  1. Ten31 Timestamp (Substack RSS) - our_thesis
  2. MacroVoices (podcast RSS) - external_interview
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db.models import get_engine, create_tables, get_session, FeedCategory
from src.feeds.manager import FeedManager


# ─── Default feeds to seed ───

SEED_FEEDS = [
    {
        "url": "https://www.ten31timestamp.com/feed",
        "category": FeedCategory.OUR_THESIS,
        "display_name": "Ten31 Timestamp",
        "tags": ["macro", "bitcoin", "fed", "fiscal", "labor"],
        "poll_interval_minutes": 60,  # Weekly newsletter, hourly poll is plenty
    },
    {
        "url": "https://www.macrovoices.com/rss/macrovoices",
        "category": FeedCategory.EXTERNAL_INTERVIEW,
        "display_name": "MacroVoices",
        "tags": ["macro", "energy", "credit", "currencies", "geopolitics"],
        "poll_interval_minutes": 120,  # Weekly podcast, 2hr poll
    },
]


def seed_feeds():
    """Add default feeds to the database."""
    print("=" * 60)
    print("Ten31 Thoughts - Feed Seeder")
    print("=" * 60)

    # Initialize database
    engine = get_engine()
    create_tables(engine)
    session = get_session(engine)

    manager = FeedManager(session)

    print(f"\nSeeding {len(SEED_FEEDS)} feeds...\n")

    for feed_config in SEED_FEEDS:
        name = feed_config["display_name"]
        url = feed_config["url"]
        category = feed_config["category"]

        print(f"  [{category.value}] {name}")
        print(f"    URL: {url}")

        feed, error = manager.add_feed(
            url=url,
            category=category,
            display_name=name,
            tags=feed_config.get("tags", []),
            poll_interval_minutes=feed_config.get("poll_interval_minutes", 30),
        )

        if error:
            if "already exists" in error:
                print(f"    -> Already exists, skipping")
            else:
                print(f"    -> ERROR: {error}")
        else:
            print(f"    -> Added successfully (ID: {feed.feed_id})")

            # Do initial poll to discover content
            print(f"    -> Running initial poll...")
            items = manager.poll_feed(feed)
            print(f"    -> Discovered {len(items)} items")

    # Print summary
    print("\n" + "=" * 60)
    stats = manager.get_content_stats()
    print(f"Total feeds: {stats['feeds_total']} ({stats['feeds_active']} active)")
    print(f"Total items: {stats['total_items']}")
    print(f"  Our thesis: {stats['by_category'].get('our_thesis', 0)}")
    print(f"  External:   {stats['by_category'].get('external_interview', 0)}")
    print(f"  Pending analysis: {stats['by_status'].get('pending', 0)}")
    print("=" * 60)

    session.close()


def add_feed_interactive():
    """Interactive prompt to add a new feed."""
    print("\n--- Add New Feed ---")
    url = input("Feed URL: ").strip()
    if not url:
        print("No URL provided, exiting.")
        return

    category_input = input("Category (1=our_thesis, 2=external_interview): ").strip()
    category = FeedCategory.OUR_THESIS if category_input == "1" else FeedCategory.EXTERNAL_INTERVIEW

    name = input("Display name (or press Enter for auto-detect): ").strip() or None
    tags_input = input("Tags (comma-separated, or press Enter for none): ").strip()
    tags = [t.strip() for t in tags_input.split(",") if t.strip()] if tags_input else []

    engine = get_engine()
    create_tables(engine)
    session = get_session(engine)
    manager = FeedManager(session)

    feed, error = manager.add_feed(
        url=url,
        category=category,
        display_name=name,
        tags=tags,
    )

    if error:
        print(f"Error: {error}")
    else:
        print(f"Added: {feed.display_name} ({feed.feed_id})")
        print("Running initial poll...")
        items = manager.poll_feed(feed)
        print(f"Discovered {len(items)} items")

    session.close()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "add":
        add_feed_interactive()
    else:
        seed_feeds()
