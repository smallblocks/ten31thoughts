"""
Ten31 Thoughts - Content Extractor
Fetches and extracts full content from URLs when RSS only provides partial content.
Handles Substack, podcast transcript pages, and generic web articles.
"""

import logging
from typing import Optional
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class ContentExtractor:
    """
    Extracts clean readable content from web pages.
    Used when RSS provides only a summary or partial content.
    """

    # Minimum content length (chars) to consider an RSS entry "complete"
    MIN_COMPLETE_LENGTH = 500

    def __init__(self, timeout: int = 30):
        self.client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": "Ten31Thoughts/1.0 (Macro Intelligence Service)"
            }
        )

    def needs_full_fetch(self, rss_content: str) -> bool:
        """Determine if we need to fetch the full page content."""
        if not rss_content:
            return True
        return len(rss_content.strip()) < self.MIN_COMPLETE_LENGTH

    def extract_from_url(self, url: str) -> Optional[str]:
        """
        Fetch a URL and extract the main readable content.
        Returns cleaned plain text or None on failure.
        """
        try:
            response = self.client.get(url)
            response.raise_for_status()
            html = response.text

            domain = urlparse(url).netloc.lower()

            # Route to specialized extractors
            if "substack.com" in domain or self._is_substack(html):
                return self._extract_substack(html)
            elif "macrovoices.com" in domain:
                return self._extract_macrovoices(html)
            else:
                return self._extract_generic(html)

        except httpx.HTTPError as e:
            logger.warning(f"HTTP error fetching {url}: {e}")
            return None
        except Exception as e:
            logger.warning(f"Error extracting content from {url}: {e}")
            return None

    def _is_substack(self, html: str) -> bool:
        """Check if a page is a Substack page."""
        return "substackcdn.com" in html or "substack-post-media" in html

    def _extract_substack(self, html: str) -> str:
        """Extract article content from a Substack page."""
        soup = BeautifulSoup(html, "lxml")

        # Substack stores main content in a specific div
        content_div = (
            soup.find("div", class_="body") or
            soup.find("div", class_="post-content") or
            soup.find("article") or
            soup.find("div", class_="available-content")
        )

        if not content_div:
            return self._extract_generic(html)

        # Remove boilerplate
        for selector in [
            "div.subscription-widget",
            "div.footer",
            "div.share-dialog",
            "div.post-footer",
            "div.pencraft",  # Substack UI components
        ]:
            for element in content_div.select(selector):
                element.decompose()

        return self._soup_to_text(content_div)

    def _extract_macrovoices(self, html: str) -> str:
        """Extract transcript content from a MacroVoices page."""
        soup = BeautifulSoup(html, "lxml")

        # MacroVoices typically has transcript in the main content area
        content = (
            soup.find("div", class_="item-page") or
            soup.find("article") or
            soup.find("div", id="content")
        )

        if not content:
            return self._extract_generic(html)

        # Remove navigation, sidebars, etc.
        for tag in content.find_all(["nav", "aside", "footer"]):
            tag.decompose()

        return self._soup_to_text(content)

    def _extract_generic(self, html: str) -> str:
        """
        Generic content extraction using readability-inspired heuristics.
        Falls back to largest text block if readability fails.
        """
        try:
            from readability import Document as ReadabilityDoc
            doc = ReadabilityDoc(html)
            readable_html = doc.summary()
            soup = BeautifulSoup(readable_html, "lxml")
            return self._soup_to_text(soup)
        except ImportError:
            pass
        except Exception as e:
            logger.debug(f"Readability extraction failed: {e}")

        # Fallback: find the largest text-containing element
        soup = BeautifulSoup(html, "lxml")

        # Remove noise
        for tag in soup.find_all(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        # Find the element with the most text content
        best_element = None
        best_length = 0

        for tag in soup.find_all(["article", "main", "div", "section"]):
            text = tag.get_text(strip=True)
            if len(text) > best_length:
                best_length = len(text)
                best_element = tag

        if best_element:
            return self._soup_to_text(best_element)

        return self._soup_to_text(soup)

    def _soup_to_text(self, soup) -> str:
        """Convert a BeautifulSoup element to clean plain text."""
        # Remove remaining scripts and styles
        for tag in soup.find_all(["script", "style"]):
            tag.decompose()

        text = soup.get_text(separator="\n")

        # Clean up
        lines = []
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped:
                lines.append(stripped)

        text = "\n\n".join(lines)

        while "\n\n\n" in text:
            text = text.replace("\n\n\n", "\n\n")

        return text.strip()

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
