"""Search plugin — explicit web search regardless of sidebar toggle."""

from __future__ import annotations

from search import web_search
from plugins.base import BasePlugin, PluginContext


class SearchPlugin(BasePlugin):
    name = "search"
    trigger = "/search"
    description = "Web search — always active, results injected as LLM context"
    usage = "/search your query"
    direct_result = False  # results prepended to LLM context

    def run(self, args: str, ctx: PluginContext) -> str:
        if not args.strip():
            return "Usage: `/search your query here`"

        results = web_search(args.strip(), max_results=5)
        return (
            f"[WEB SEARCH for: '{args}']\n\n"
            f"{results}\n\n"
            f"[END SEARCH]\n\n"
            f"IMPORTANT: Use the search results above to answer. "
            f"Always cite source URLs."
        )
