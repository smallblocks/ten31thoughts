#!/usr/bin/env python3
"""
Ten31 Thoughts — Database Builder

Crawls MacroVoices + Timestamp archives, runs LLM analysis, builds seed database.

Usage:
    python3 tools/build_db.py crawl [--limit N]
    python3 tools/build_db.py analyze [--batch-size N] [--delay N] [--limit N] [--source SOURCE]
    python3 tools/build_db.py package
    python3 tools/build_db.py status
"""

import argparse
import asyncio
import hashlib
import logging
import os
import re
import sys
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import sessionmaker
from tqdm import tqdm

# Add project root to path so we can import src/
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.db.models import (
    Base, Feed, ContentItem, FeedCategory, FeedStatus, AnalysisStatus,
    Note, Connection, gen_id
)

OUTPUT_DIR = PROJECT_ROOT / "output"
DB_PATH = OUTPUT_DIR / "ten31thoughts.db"
CHROMADB_DIR = OUTPUT_DIR / "chromadb"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
)
logger = logging.getLogger("db-builder")


def get_db():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session(), engine


# ─────────────────────────────────────────────────────────────
# Crawlers
# ─────────────────────────────────────────────────────────────

class MacroVoicesCrawler:
    BASE_URL = "https://www.macrovoices.com/podcast-transcripts"
    HEADERS = {"User-Agent": "Ten31Thoughts-DBBuilder/1.0"}

    def __init__(self):
        self.client = httpx.Client(timeout=30, follow_redirects=True, headers=self.HEADERS)

    def get_transcript_urls(self, limit=None):
        urls = []
        start = 0
        page_size = 20

        logger.info("Crawling MacroVoices transcript index...")

        while True:
            url = f"{self.BASE_URL}?start={start}" if start > 0 else self.BASE_URL
            logger.info(f"  Fetching page at offset {start}...")

            try:
                resp = self.client.get(url)
                resp.raise_for_status()
            except Exception as e:
                logger.error(f"  Failed to fetch listing page: {e}")
                break

            soup = BeautifulSoup(resp.text, "lxml")

            found = []
            for link in soup.find_all("a", href=True):
                href = link["href"]
                if re.match(r"/podcast-transcripts/\d+-", href):
                    full_url = urljoin("https://www.macrovoices.com", href)
                    if full_url not in urls and full_url not in found:
                        found.append(full_url)

            if not found:
                logger.info(f"  No more transcripts found at offset {start}. Done.")
                break

            urls.extend(found)
            logger.info(f"  Found {len(found)} transcripts (total: {len(urls)})")

            if limit and len(urls) >= limit:
                urls = urls[:limit]
                break

            start += page_size
            time.sleep(0.5)

        return urls

    def fetch_transcript(self, url):
        try:
            resp = self.client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"  Failed to fetch {url}: {e}")
            return None

        soup = BeautifulSoup(resp.text, "lxml")

        title_tag = soup.find("h1") or soup.find("h2")
        title = title_tag.get_text(strip=True) if title_tag else url.split("/")[-1]

        date = None
        date_match = re.search(r"Created:\s*(\d{1,2}\s+\w+\s+\d{4})", soup.get_text())
        if date_match:
            try:
                from dateutil.parser import parse as dateparse
                date = dateparse(date_match.group(1))
            except Exception:
                pass

        content_div = (
            soup.find("div", class_="item-page") or
            soup.find("article") or
            soup.find("div", id="content")
        )

        if not content_div:
            logger.warning(f"  No content div found for {url}")
            return None

        for tag in content_div.find_all(["nav", "aside", "footer", "script", "style"]):
            tag.decompose()

        text = content_div.get_text(separator="\n")
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        text = "\n\n".join(lines)

        guest = None
        if ":" in title:
            guest = title.split(":")[0].strip()

        if len(text) < 200:
            logger.warning(f"  Content too short for {url} ({len(text)} chars)")
            return None

        return {
            "url": url, "title": title, "date": date, "guest": guest,
            "content": text, "content_type": "podcast_transcript",
        }

    def close(self):
        self.client.close()


class TimestampCrawler:
    ARCHIVE_URL = "https://www.ten31timestamp.com/archive"
    HEADERS = {"User-Agent": "Ten31Thoughts-DBBuilder/1.0"}

    def __init__(self):
        self.client = httpx.Client(timeout=30, follow_redirects=True, headers=self.HEADERS)

    def get_post_urls(self, limit=None):
        urls = []
        page = 1

        logger.info("Crawling Timestamp archive...")

        while True:
            url = f"{self.ARCHIVE_URL}?sort=new&page={page}" if page > 1 else self.ARCHIVE_URL
            logger.info(f"  Fetching archive page {page}...")

            try:
                resp = self.client.get(url)
                resp.raise_for_status()
            except Exception as e:
                logger.error(f"  Failed to fetch archive page: {e}")
                break

            soup = BeautifulSoup(resp.text, "lxml")

            found = []
            for link in soup.find_all("a", href=True):
                href = link["href"]
                if "/p/" in href and "ten31timestamp" in href:
                    if href not in urls and href not in found:
                        found.append(href)
                elif href.startswith("/p/"):
                    full = urljoin("https://www.ten31timestamp.com", href)
                    if full not in urls and full not in found:
                        found.append(full)

            if not found:
                logger.info(f"  No more posts found on page {page}. Done.")
                break

            urls.extend(found)
            logger.info(f"  Found {len(found)} posts (total: {len(urls)})")

            if limit and len(urls) >= limit:
                urls = urls[:limit]
                break

            page += 1
            time.sleep(0.5)

        return urls

    def fetch_post(self, url):
        try:
            resp = self.client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.warning(f"  Failed to fetch {url}: {e}")
            return None

        soup = BeautifulSoup(resp.text, "lxml")

        title_tag = soup.find("h1", class_="post-title") or soup.find("h1")
        title = title_tag.get_text(strip=True) if title_tag else url.split("/p/")[-1]

        date = None
        time_tag = soup.find("time")
        if time_tag and time_tag.get("datetime"):
            try:
                from dateutil.parser import parse as dateparse
                date = dateparse(time_tag["datetime"])
            except Exception:
                pass

        content_div = (
            soup.find("div", class_="body") or
            soup.find("div", class_="post-content") or
            soup.find("article") or
            soup.find("div", class_="available-content")
        )

        if not content_div:
            logger.warning(f"  No content div found for {url}")
            return None

        for selector in ["div.subscription-widget", "div.footer", "div.share-dialog",
                         "div.post-footer", "div.pencraft", "script", "style"]:
            for el in content_div.select(selector):
                el.decompose()

        text = content_div.get_text(separator="\n")
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        text = "\n\n".join(lines)

        if len(text) < 200:
            logger.warning(f"  Content too short for {url} ({len(text)} chars)")
            return None

        return {
            "url": url, "title": title, "date": date,
            "content": text, "content_type": "article",
        }

    def close(self):
        self.client.close()


# ─────────────────────────────────────────────────────────────
# Commands
# ─────────────────────────────────────────────────────────────

def cmd_crawl(args):
    session, engine = get_db()

    mv_feed = session.execute(select(Feed).where(Feed.url == "macrovoices-archive")).scalar_one_or_none()
    if not mv_feed:
        mv_feed = Feed(
            feed_id=gen_id(), url="macrovoices-archive",
            category=FeedCategory.EXTERNAL_INTERVIEW,
            display_name="MacroVoices (Historical Archive)",
            tags=["macro", "energy", "credit", "currencies", "geopolitics"],
            poll_interval_minutes=9999,
        )
        session.add(mv_feed)
        session.commit()

    ts_feed = session.execute(select(Feed).where(Feed.url == "timestamp-archive")).scalar_one_or_none()
    if not ts_feed:
        ts_feed = Feed(
            feed_id=gen_id(), url="timestamp-archive",
            category=FeedCategory.OUR_THESIS,
            display_name="Ten31 Timestamp (Historical Archive)",
            tags=["macro", "bitcoin", "fed", "fiscal", "labor"],
            poll_interval_minutes=9999,
        )
        session.add(ts_feed)
        session.commit()

    # Crawl MacroVoices
    logger.info("=" * 60)
    logger.info("CRAWLING MACROVOICES TRANSCRIPTS")
    logger.info("=" * 60)

    mv = MacroVoicesCrawler()
    mv_urls = mv.get_transcript_urls(limit=args.limit)
    logger.info(f"Found {len(mv_urls)} transcript URLs")

    mv_new = 0
    for url in tqdm(mv_urls, desc="Fetching MacroVoices"):
        existing = session.execute(select(ContentItem).where(ContentItem.url == url)).scalar_one_or_none()
        if existing:
            continue
        data = mv.fetch_transcript(url)
        if not data:
            continue
        item = ContentItem(
            item_id=gen_id(), feed_id=mv_feed.feed_id, url=data["url"],
            title=data["title"], published_date=data.get("date"),
            authors=[data["guest"]] if data.get("guest") else [],
            summary=data["content"][:300], content_text=data["content"],
            content_hash=hashlib.sha256(data["content"].encode()).hexdigest(),
            content_type=data["content_type"], analysis_status=AnalysisStatus.PENDING,
        )
        session.add(item)
        mv_new += 1
        if mv_new % 10 == 0:
            session.commit()
        time.sleep(0.3)
    session.commit()
    mv.close()
    logger.info(f"MacroVoices: {mv_new} new transcripts added")

    # Crawl Timestamp
    logger.info("=" * 60)
    logger.info("CRAWLING TIMESTAMP ARCHIVE")
    logger.info("=" * 60)

    ts = TimestampCrawler()
    ts_urls = ts.get_post_urls(limit=args.limit)
    logger.info(f"Found {len(ts_urls)} Timestamp post URLs")

    ts_new = 0
    for url in tqdm(ts_urls, desc="Fetching Timestamp"):
        existing = session.execute(select(ContentItem).where(ContentItem.url == url)).scalar_one_or_none()
        if existing:
            continue
        data = ts.fetch_post(url)
        if not data:
            continue
        item = ContentItem(
            item_id=gen_id(), feed_id=ts_feed.feed_id, url=data["url"],
            title=data["title"], published_date=data.get("date"),
            authors=["Ten31"], summary=data["content"][:300],
            content_text=data["content"],
            content_hash=hashlib.sha256(data["content"].encode()).hexdigest(),
            content_type=data["content_type"], analysis_status=AnalysisStatus.PENDING,
        )
        session.add(item)
        ts_new += 1
        if ts_new % 10 == 0:
            session.commit()
        time.sleep(0.3)
    session.commit()
    ts.close()
    logger.info(f"Timestamp: {ts_new} new posts added")

    _print_status(session)
    session.close()


def cmd_analyze(args):
    if not os.getenv("ANTHROPIC_API_KEY") and not os.getenv("OPENAI_API_KEY"):
        print("ERROR: Set ANTHROPIC_API_KEY or OPENAI_API_KEY")
        sys.exit(1)

    os.environ["DATABASE_URL"] = f"sqlite:///{DB_PATH.absolute()}"
    os.environ["CHROMADB_PERSIST_DIR"] = str(CHROMADB_DIR.absolute())

    session, engine = get_db()

    from src.llm.router import LLMRouter
    from src.analysis.note_extractor import NoteExtractor
    from src.analysis.connection_pass import ConnectionAnalyzer
    from src.db.vector import VectorStore

    llm = LLMRouter()
    vs = VectorStore()

    query = select(ContentItem).where(
        ContentItem.analysis_status == AnalysisStatus.PENDING
    ).order_by(ContentItem.published_date.asc())

    if args.source == "macrovoices":
        mv_feed = session.execute(select(Feed).where(Feed.display_name.contains("MacroVoices"))).scalar_one_or_none()
        if mv_feed:
            query = query.where(ContentItem.feed_id == mv_feed.feed_id)
    elif args.source == "timestamp":
        ts_feed = session.execute(select(Feed).where(Feed.display_name.contains("Timestamp"))).scalar_one_or_none()
        if ts_feed:
            query = query.where(ContentItem.feed_id == ts_feed.feed_id)

    if args.limit:
        query = query.limit(args.limit)

    pending = session.execute(query).scalars().all()
    total = len(pending)

    if total == 0:
        print("No pending items to analyze.")
        return

    print(f"\nAnalyzing {total} items (batch: {args.batch_size}, delay: {args.delay}s)\n")

    loop = asyncio.new_event_loop()
    analyzed = 0
    errors = 0

    try:
        for i, item in enumerate(pending):
            feed = session.get(Feed, item.feed_id)
            category = feed.category if feed else FeedCategory.EXTERNAL_INTERVIEW

            print(f"[{i+1}/{total}] {item.title[:60]}... ", end="", flush=True)

            try:
                item.analysis_status = AnalysisStatus.ANALYZING
                session.commit()

                if category == FeedCategory.OUR_THESIS:
                    extractor = NoteExtractor(llm, session)
                    result = loop.run_until_complete(extractor.extract(item.item_id))
                else:
                    analyzer = ConnectionAnalyzer(llm, session)
                    result = loop.run_until_complete(analyzer.analyze(item.item_id))

                # Vector index raw content chunks
                vs.index_content(
                    item_id=item.item_id, content=item.content_text,
                    metadata={
                        "item_id": item.item_id, "category": category.value,
                        "feed_id": item.feed_id, "title": item.title,
                        "date": item.published_date.isoformat() if item.published_date else "",
                    }
                )

                # Report what was extracted
                if category == FeedCategory.OUR_THESIS:
                    note_count = session.execute(
                        select(func.count(Note.note_id)).where(Note.source_item_id == item.item_id)
                    ).scalar()
                    print(f"OK — {note_count} notes")
                else:
                    conn_count = session.execute(
                        select(func.count(Connection.connection_id)).where(Connection.item_id == item.item_id)
                    ).scalar()
                    print(f"OK — {conn_count} connections")
                analyzed += 1

            except KeyboardInterrupt:
                print("\nInterrupted. Progress saved.")
                item.analysis_status = AnalysisStatus.PENDING
                session.commit()
                break
            except Exception as e:
                print(f"ERROR: {e}")
                item.analysis_status = AnalysisStatus.ERROR
                item.analysis_error = str(e)[:500]
                session.commit()
                errors += 1

            if (i + 1) % args.batch_size == 0 and i < total - 1:
                time.sleep(args.delay)

    finally:
        loop.close()

    print(f"\nDone: {analyzed} analyzed, {errors} errors, {total - analyzed - errors} remaining")
    _print_status(session)
    session.close()


def cmd_package(args):
    if not DB_PATH.exists():
        print(f"ERROR: No database at {DB_PATH}")
        sys.exit(1)
    output_tar = OUTPUT_DIR / "seed-data.tar.gz"
    print(f"Packaging...")
    with tarfile.open(output_tar, "w:gz") as tar:
        tar.add(DB_PATH, arcname="ten31thoughts.db")
        if CHROMADB_DIR.exists():
            tar.add(CHROMADB_DIR, arcname="chromadb")
    size_mb = output_tar.stat().st_size / 1024 / 1024
    print(f"Created: {output_tar} ({size_mb:.1f} MB)")


def cmd_status(args):
    if not DB_PATH.exists():
        print("No database found. Run 'crawl' first.")
        return
    session, _ = get_db()
    _print_status(session)
    session.close()


def _print_status(session):
    print("\n" + "=" * 60)
    print("DATABASE STATUS")
    print("=" * 60)
    feeds = session.execute(select(Feed)).scalars().all()
    for feed in feeds:
        count = session.execute(
            select(func.count(ContentItem.item_id)).where(ContentItem.feed_id == feed.feed_id)
        ).scalar()
        print(f"  {feed.display_name}: {count} items")
    for status in AnalysisStatus:
        count = session.execute(
            select(func.count(ContentItem.item_id)).where(ContentItem.analysis_status == status)
        ).scalar()
        if count > 0:
            print(f"    [{status.value}]: {count}")
    total = session.execute(select(func.count(ContentItem.item_id))).scalar()
    print(f"  TOTAL: {total}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Ten31 Thoughts Database Builder")
    sub = parser.add_subparsers(dest="command", required=True)

    crawl_p = sub.add_parser("crawl")
    crawl_p.add_argument("--limit", type=int, default=None)

    analyze_p = sub.add_parser("analyze")
    analyze_p.add_argument("--batch-size", type=int, default=10)
    analyze_p.add_argument("--delay", type=float, default=1.0)
    analyze_p.add_argument("--limit", type=int, default=None)
    analyze_p.add_argument("--source", choices=["macrovoices", "timestamp"], default=None)

    sub.add_parser("package")
    sub.add_parser("status")

    args = parser.parse_args()
    {"crawl": cmd_crawl, "analyze": cmd_analyze, "package": cmd_package, "status": cmd_status}[args.command](args)


if __name__ == "__main__":
    main()
