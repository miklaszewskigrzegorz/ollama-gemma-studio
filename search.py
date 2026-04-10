"""
Web search — SearXNG (self-hosted) with DuckDuckGo fallback.

Priority:
  1. SearXNG at SEARXNG_URL (set in .env) — self-hosted via Docker, no API key
  2. DuckDuckGo via ddgs — free fallback, no API key

To enable SearXNG:
    docker compose -f docker-compose.searxng.yml up -d
    # add to .env: SEARXNG_URL=http://localhost:8889
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

# Set SEARXNG_URL in .env to enable self-hosted search
_SEARXNG_URL = os.getenv("SEARXNG_URL", "").rstrip("/")
_TIMEOUT = 8


def _searxng(query: str, max_results: int) -> str | None:
    """
    Query local SearXNG instance.
    Returns formatted results string, or None if SearXNG is unavailable.
    """
    if not _SEARXNG_URL:
        return None

    params = urllib.parse.urlencode({
        "q": query,
        "format": "json",
        "language": "en",
        "safesearch": "0",
    })
    url = f"{_SEARXNG_URL}/search?{params}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "local-llm-assistant/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.URLError, OSError):
        return None  # SearXNG not reachable — fall through to ddgs

    results = data.get("results", [])[:max_results]
    if not results:
        return None

    today = datetime.now().strftime("%Y-%m-%d")
    parts = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "")
        body = r.get("content", "")
        href = r.get("url", "")
        parts.append(f"[{i}] **{title}**\n{body}\nURL: {href}")

    return f"Source: SearXNG | {today}\n\n" + "\n\n---\n\n".join(parts)


def _ddgs(query: str, max_results: int) -> str:
    """Query DuckDuckGo via ddgs package (fallback)."""
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS  # legacy package name

        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results, region="wt-wt"))

        if not results:
            return "No results found."

        today = datetime.now().strftime("%Y-%m-%d")
        parts = []
        for i, r in enumerate(results, 1):
            title = r.get("title", "")
            body = r.get("body", "")
            href = r.get("href", "")
            parts.append(f"[{i}] **{title}**\n{body}\nURL: {href}")

        return f"Source: DuckDuckGo | {today}\n\n" + "\n\n---\n\n".join(parts)

    except ImportError:
        return "Web search not available — install: pip install ddgs"
    except Exception as e:
        return f"Search error: {e}"


def web_search(query: str, max_results: int = 4) -> str:
    """
    Search the web and return formatted results.

    Uses SearXNG if SEARXNG_URL is set in .env and the container is running.
    Falls back to DuckDuckGo automatically if SearXNG is unavailable.
    """
    result = _searxng(query, max_results)
    if result is not None:
        return result
    return _ddgs(query, max_results)
