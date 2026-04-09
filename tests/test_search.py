"""
Tests for search.py — SearXNG primary + DuckDuckGo fallback.

All network calls are mocked; no real HTTP requests are made.
"""

from __future__ import annotations

import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

import search as search_module
from search import _ddgs, _searxng, web_search


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_searxng_response(results: list[dict]) -> MagicMock:
    """Build a mock urllib response that returns the given SearXNG results dict."""
    body = json.dumps({"results": results}).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = body
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


# ── _searxng ───────────────────────────────────────────────────────────────────

class TestSearxng:
    def test_returns_none_when_url_not_configured(self):
        """_searxng must return None immediately when SEARXNG_URL is empty."""
        with patch.object(search_module, "_SEARXNG_URL", ""):
            result = _searxng("python tutorial", max_results=3)
        assert result is None

    def test_returns_none_when_server_unreachable(self):
        """_searxng must return None when urllib raises URLError (container down)."""
        with patch.object(search_module, "_SEARXNG_URL", "http://localhost:8889"):
            with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
                result = _searxng("python tutorial", max_results=3)
        assert result is None

    def test_returns_none_when_oserror(self):
        """_searxng must return None on OSError (socket-level failure)."""
        with patch.object(search_module, "_SEARXNG_URL", "http://localhost:8889"):
            with patch("urllib.request.urlopen", side_effect=OSError("network unreachable")):
                result = _searxng("test query", max_results=3)
        assert result is None

    def test_returns_none_when_empty_results(self):
        """_searxng must return None when SearXNG responds with an empty results list."""
        mock_resp = _make_searxng_response([])
        with patch.object(search_module, "_SEARXNG_URL", "http://localhost:8889"):
            with patch("urllib.request.urlopen", return_value=mock_resp):
                result = _searxng("rare query no results", max_results=3)
        assert result is None

    def test_returns_formatted_string_with_source_header(self):
        """_searxng should return a string starting with 'Source: SearXNG' on success."""
        fake_results = [
            {"title": "Python Tutorial", "content": "Learn Python here.", "url": "https://example.com/py"},
            {"title": "Python Docs", "content": "Official documentation.", "url": "https://docs.python.org"},
        ]
        mock_resp = _make_searxng_response(fake_results)
        with patch.object(search_module, "_SEARXNG_URL", "http://localhost:8889"):
            with patch("urllib.request.urlopen", return_value=mock_resp):
                result = _searxng("python", max_results=5)

        assert result is not None
        assert result.startswith("Source: SearXNG")
        assert "Python Tutorial" in result
        assert "https://example.com/py" in result

    def test_respects_max_results(self):
        """_searxng must not return more results than max_results."""
        fake_results = [
            {"title": f"Result {i}", "content": f"Body {i}", "url": f"https://ex.com/{i}"}
            for i in range(10)
        ]
        mock_resp = _make_searxng_response(fake_results)
        with patch.object(search_module, "_SEARXNG_URL", "http://localhost:8889"):
            with patch("urllib.request.urlopen", return_value=mock_resp):
                result = _searxng("query", max_results=3)

        assert result is not None
        # Only [1], [2], [3] prefixes expected
        assert "[4]" not in result
        assert "[3]" in result


# ── _ddgs ──────────────────────────────────────────────────────────────────────

class TestDdgs:
    def _make_ddgs_results(self, n: int = 2) -> list[dict]:
        return [
            {"title": f"DuckDuckGo Result {i}", "body": f"Snippet {i}", "href": f"https://ddg.example/{i}"}
            for i in range(1, n + 1)
        ]

    def test_returns_string_with_duckduckgo_source(self):
        """_ddgs result must contain 'Source: DuckDuckGo'."""
        fake_results = self._make_ddgs_results(2)
        mock_ddgs_instance = MagicMock()
        mock_ddgs_instance.__enter__ = lambda s: s
        mock_ddgs_instance.__exit__ = MagicMock(return_value=False)
        mock_ddgs_instance.text.return_value = fake_results

        with patch.dict("sys.modules", {"ddgs": MagicMock(DDGS=MagicMock(return_value=mock_ddgs_instance))}):
            result = _ddgs("python async", max_results=3)

        assert "Source: DuckDuckGo" in result

    def test_includes_result_titles_and_urls(self):
        """_ddgs must include title and URL for each result."""
        fake_results = self._make_ddgs_results(2)
        mock_ddgs_instance = MagicMock()
        mock_ddgs_instance.__enter__ = lambda s: s
        mock_ddgs_instance.__exit__ = MagicMock(return_value=False)
        mock_ddgs_instance.text.return_value = fake_results

        with patch.dict("sys.modules", {"ddgs": MagicMock(DDGS=MagicMock(return_value=mock_ddgs_instance))}):
            result = _ddgs("python async", max_results=3)

        assert "DuckDuckGo Result 1" in result
        assert "https://ddg.example/1" in result

    def test_returns_no_results_message_on_empty(self):
        """_ddgs must return a 'No results' message when DDGS returns empty list."""
        mock_ddgs_instance = MagicMock()
        mock_ddgs_instance.__enter__ = lambda s: s
        mock_ddgs_instance.__exit__ = MagicMock(return_value=False)
        mock_ddgs_instance.text.return_value = []

        with patch.dict("sys.modules", {"ddgs": MagicMock(DDGS=MagicMock(return_value=mock_ddgs_instance))}):
            result = _ddgs("something obscure", max_results=3)

        assert "No results" in result

    def test_returns_install_message_when_ddgs_not_installed(self):
        """_ddgs must suggest pip install when ddgs package is missing."""
        with patch.dict("sys.modules", {"ddgs": None, "duckduckgo_search": None}):
            with patch("builtins.__import__", side_effect=ImportError("No module named 'ddgs'")):
                result = _ddgs("test", max_results=3)
        assert "pip install" in result or "not available" in result.lower()

    def test_returns_error_string_on_exception(self):
        """_ddgs must return an error string (not raise) when DDGS raises."""
        mock_ddgs_instance = MagicMock()
        mock_ddgs_instance.__enter__ = lambda s: s
        mock_ddgs_instance.__exit__ = MagicMock(return_value=False)
        mock_ddgs_instance.text.side_effect = RuntimeError("rate limited")

        with patch.dict("sys.modules", {"ddgs": MagicMock(DDGS=MagicMock(return_value=mock_ddgs_instance))}):
            result = _ddgs("test", max_results=3)

        assert "Search error" in result or "rate limited" in result


# ── web_search — orchestration logic ──────────────────────────────────────────

class TestWebSearch:
    def test_uses_searxng_when_available(self):
        """web_search must return SearXNG result without calling _ddgs when searxng succeeds."""
        with patch("search._searxng", return_value="Source: SearXNG | 2026-04-09\n\n[1] Result") as mock_sx:
            with patch("search._ddgs") as mock_ddg:
                result = web_search("test query")

        mock_sx.assert_called_once_with("test query", 4)
        mock_ddg.assert_not_called()
        assert "SearXNG" in result

    def test_falls_back_to_ddgs_when_searxng_returns_none(self):
        """web_search must call _ddgs when _searxng returns None."""
        with patch("search._searxng", return_value=None):
            with patch("search._ddgs", return_value="Source: DuckDuckGo | 2026-04-09\n\n[1] Result") as mock_ddg:
                result = web_search("test query")

        mock_ddg.assert_called_once_with("test query", 4)
        assert "DuckDuckGo" in result

    def test_passes_max_results_to_both_backends(self):
        """web_search must forward the max_results parameter."""
        with patch("search._searxng", return_value=None) as mock_sx:
            with patch("search._ddgs", return_value="Source: DuckDuckGo | ok") as mock_ddg:
                web_search("query", max_results=7)

        mock_sx.assert_called_once_with("query", 7)
        mock_ddg.assert_called_once_with("query", 7)

    def test_default_max_results_is_four(self):
        """web_search default max_results should be 4."""
        with patch("search._searxng", return_value=None) as mock_sx:
            with patch("search._ddgs", return_value="ok"):
                web_search("default test")

        _, kwargs = mock_sx.call_args
        positional_arg = mock_sx.call_args[0][1]  # second positional arg
        assert positional_arg == 4
