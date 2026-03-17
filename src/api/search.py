"""
Ten31 Thoughts - Search API
Proxies to local SearXNG instance for web searches.
"""

import logging
from typing import Optional
import httpx
from bs4 import BeautifulSoup

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/search", tags=["search"])

# SearXNG on StartOS
SEARXNG_URL = "http://searxng.embassy:8080/search"


class SearchRequest(BaseModel):
    query: str = Field(..., description="Search query")
    count: int = Field(5, ge=1, le=20, description="Number of results")


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    source: str = "searxng"


async def execute_search(query: str, count: int = 5) -> list[dict]:
    """
    Execute a search against SearXNG.
    Returns list of {title, url, snippet} dicts.
    """
    results = []
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            # Try JSON API first
            resp = await client.post(
                SEARXNG_URL,
                data={"q": query, "format": "json"},
                headers={"Accept": "application/json"},
            )
            
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    for r in data.get("results", [])[:count]:
                        results.append({
                            "title": r.get("title", ""),
                            "url": r.get("url", ""),
                            "snippet": r.get("content", "")[:300],
                        })
                    if results:
                        return results
                except Exception:
                    pass  # Fall through to HTML parsing
            
            # Fallback: HTML parsing
            resp = await client.post(SEARXNG_URL, data={"q": query})
            if resp.status_code != 200:
                logger.warning(f"SearXNG returned {resp.status_code}")
                return []
            
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # Parse result articles
            for article in soup.select("article.result")[:count]:
                title_el = article.select_one("h3 a, h4 a")
                url_el = article.select_one("a.url_header, a[href]")
                snippet_el = article.select_one("p.content, .content")
                
                if title_el:
                    results.append({
                        "title": title_el.get_text(strip=True),
                        "url": url_el.get("href", "") if url_el else "",
                        "snippet": snippet_el.get_text(strip=True)[:300] if snippet_el else "",
                    })
    
    except httpx.TimeoutException:
        logger.warning(f"SearXNG search timed out for query: {query}")
    except Exception as e:
        logger.error(f"SearXNG search failed: {e}")
    
    return results


@router.post("/", response_model=SearchResponse)
async def search(request: SearchRequest):
    """Search the web via SearXNG."""
    results = await execute_search(request.query, request.count)
    
    return SearchResponse(
        query=request.query,
        results=[SearchResult(**r) for r in results],
    )


@router.get("/health")
async def search_health():
    """Check if SearXNG is reachable."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get("http://searxng.embassy:8080/")
            return {
                "status": "healthy" if resp.status_code == 200 else "degraded",
                "searxng_status": resp.status_code,
            }
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
