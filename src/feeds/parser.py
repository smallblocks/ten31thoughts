"""
Ten31 Thoughts - Feed Parser
Universal RSS/Atom feed parsing with content extraction.
Handles Substack newsletters, podcast feeds, and generic blog RSS.
"""

import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional
from dataclasses import dataclass, field

import feedparser
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class ParsedItem:
    """A single parsed feed item ready for storage."""
    url: str
    title: str
    published_date: Optional[datetime]
    authors: list[str]
    summary: str
    content_text: str
    content_hash: str
    content_type: str  # article, podcast_transcript, audio
    audio_url: Optional[str] = None


@dataclass
class FeedMetadata:
    """Metadata about the feed itself."""
    title: str
    description: str
    link: str
    item_count: int


class FeedParser:
    """
    Parses RSS/Atom feeds and extracts clean content.

    Handles:
    - Substack newsletters (full HTML content in feed)
    - Podcast feeds (summary + enclosure audio links)
    - Generic blog RSS (full or partial content)
    """

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": "Ten31Thoughts/1.0 (Macro Intelligence Service)"
            }
        )

    def validate_feed(self, url: str) -> tuple[bool, Optional[FeedMetadata], Optional[str]]:
        """
        Validate that a URL points to a valid RSS/Atom feed.
        Returns (is_valid, metadata, error_message).
        """
        try:
            response = self.client.get(url)
            response.raise_for_status()
            parsed = feedparser.parse(response.text)

            if parsed.bozo and not parsed.entries:
                return False, None, f"Invalid feed: {parsed.bozo_exception}"

            metadata = FeedMetadata(
                title=parsed.feed.get("title", "Unknown"),
                description=parsed.feed.get("description", ""),
                link=parsed.feed.get("link", url),
                item_count=len(parsed.entries)
            )

            return True, metadata, None

        except httpx.HTTPError as e:
            return False, None, f"HTTP error fetching feed: {e}"
        except Exception as e:
            return False, None, f"Error validating feed: {e}"

    def fetch_and_parse(self, url: str, since: Optional[datetime] = None) -> list[ParsedItem]:
        """
        Fetch a feed and parse all items. Optionally filter to items after `since`.
        Returns list of ParsedItem objects ready for storage.
        """
        try:
            response = self.client.get(url)
            response.raise_for_status()
            parsed = feedparser.parse(response.text)

            items = []
            for entry in parsed.entries:
                try:
                    item = self._parse_entry(entry)
                    if item is None:
                        continue

                    # Filter by date if requested
                    if since and item.published_date and item.published_date <= since:
                        continue

                    items.append(item)
                except Exception as e:
                    logger.warning(f"Failed to parse entry '{entry.get('title', 'unknown')}': {e}")
                    continue

            logger.info(f"Parsed {len(items)} items from {url}")
            return items

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching feed {url}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error parsing feed {url}: {e}")
            raise

    def _parse_entry(self, entry: dict) -> Optional[ParsedItem]:
        """Parse a single feed entry into a ParsedItem."""
        url = entry.get("link", "")
        title = entry.get("title", "Untitled")

        if not url:
            return None

        # Extract published date
        published_date = self._parse_date(entry)

        # Extract authors
        authors = self._extract_authors(entry)

        # Extract content - try full content first, fall back to summary
        content_html = ""
        if "content" in entry and entry["content"]:
            content_html = entry["content"][0].get("value", "")
        elif "summary_detail" in entry:
            content_html = entry["summary_detail"].get("value", "")
        elif "summary" in entry:
            content_html = entry["summary"]

        # Clean HTML to plain text
        content_text = self._html_to_text(content_html)
        summary = self._extract_summary(entry, content_text)

        # Detect audio enclosures (podcast episodes)
        audio_url = self._extract_audio_url(entry)
        content_type = "audio" if audio_url and not content_text.strip() else "article"

        # Generate content hash for deduplication
        content_hash = hashlib.sha256(
            (url + content_text[:1000]).encode("utf-8")
        ).hexdigest()

        return ParsedItem(
            url=url,
            title=title,
            published_date=published_date,
            authors=authors,
            summary=summary,
            content_text=content_text,
            content_hash=content_hash,
            content_type=content_type,
            audio_url=audio_url,
        )

    def _parse_date(self, entry: dict) -> Optional[datetime]:
        """Extract and parse the publication date from a feed entry."""
        for date_field in ["published_parsed", "updated_parsed", "created_parsed"]:
            parsed_time = entry.get(date_field)
            if parsed_time:
                try:
                    from time import mktime
                    dt = datetime.fromtimestamp(mktime(parsed_time), tz=timezone.utc)
                    return dt
                except (ValueError, OverflowError):
                    continue

        # Try string date parsing as fallback
        for date_field in ["published", "updated", "created"]:
            date_str = entry.get(date_field)
            if date_str:
                try:
                    from dateutil.parser import parse as dateparse
                    return dateparse(date_str)
                except (ValueError, TypeError):
                    continue

        return None

    def _extract_authors(self, entry: dict) -> list[str]:
        """Extract author names from a feed entry."""
        authors = []

        if "author_detail" in entry and "name" in entry["author_detail"]:
            authors.append(entry["author_detail"]["name"])
        elif "author" in entry:
            authors.append(entry["author"])

        if "authors" in entry:
            for author in entry["authors"]:
                name = author.get("name", "")
                if name and name not in authors:
                    authors.append(name)

        return authors

    def _html_to_text(self, html: str) -> str:
        """
        Convert HTML content to clean plain text.
        Strips boilerplate, ads, and formatting while preserving structure.
        """
        if not html:
            return ""

        soup = BeautifulSoup(html, "lxml")

        # Remove script/style/nav elements
        for tag in soup.find_all(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        # Remove common Substack boilerplate patterns
        for tag in soup.find_all(class_=lambda c: c and any(
            pattern in str(c).lower()
            for pattern in ["subscribe", "share", "footer", "button", "social"]
        )):
            tag.decompose()

        # Remove "Subscribe" / "Share" links that are common in Substack
        for a_tag in soup.find_all("a"):
            text = a_tag.get_text(strip=True).lower()
            if text in ["subscribe", "share", "like", "comment", "restacks"]:
                a_tag.decompose()

        # Get text with paragraph breaks preserved
        text = soup.get_text(separator="\n")

        # Clean up whitespace
        lines = []
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped:
                lines.append(stripped)

        text = "\n\n".join(lines)

        # Remove duplicate whitespace
        while "\n\n\n" in text:
            text = text.replace("\n\n\n", "\n\n")

        return text.strip()

    def _extract_summary(self, entry: dict, full_text: str) -> str:
        """Extract a short summary from the entry."""
        if "summary" in entry:
            summary_text = self._html_to_text(entry["summary"])
            if len(summary_text) < 500:
                return summary_text

        # Fall back to first ~300 chars of content
        if full_text:
            return full_text[:300].rsplit(" ", 1)[0] + "..."

        return ""

    def _extract_audio_url(self, entry: dict) -> Optional[str]:
        """Extract audio enclosure URL from podcast feed entries."""
        # Check enclosures
        for enclosure in entry.get("enclosures", []):
            mime_type = enclosure.get("type", "")
            if mime_type.startswith("audio/"):
                return enclosure.get("href") or enclosure.get("url")

        # Check links for audio
        for link in entry.get("links", []):
            mime_type = link.get("type", "")
            if mime_type.startswith("audio/"):
                return link.get("href")

        return None

    def close(self):
        """Close the HTTP client."""
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
