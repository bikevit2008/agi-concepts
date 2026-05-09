"""Web search tool — capability-gated.

Default implementation uses DuckDuckGo's HTML interface (no API key
needed) when `requests` is available. If the network is unreachable,
returns an error rather than failing the loop.

For production: swap with a managed provider (Tavily, Serper, Brave
Search) that supports rate-limited keys + DPoP-bound tokens.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import structlog

from src.contracts.tools import ITool, ToolCall, ToolResult

logger = structlog.get_logger("consciousness.tools.web_search")


@dataclass
class WebSearchTool:
    """ITool implementation for web search.

    Args:
        backend: "duckduckgo" (default), "stub" (returns canned results
            for tests), or "callable" (custom Python callable).
        custom_search: when backend="callable", the function to call.
        timeout_seconds: HTTP timeout.
    """

    backend: str = "duckduckgo"
    custom_search: Optional[Any] = None
    timeout_seconds: float = 5.0

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return (
            "Search the web for relevant pages. "
            "Args: {query: str, max_results: int (1..10)}"
        )

    @property
    def required_capability(self) -> str:
        return "tools:web_search"

    def execute(self, call: ToolCall) -> ToolResult:
        query = str(call.args.get("query", "")).strip()
        if not query:
            return ToolResult(success=False, error="query is required")
        max_results = int(call.args.get("max_results", 5))
        max_results = max(1, min(10, max_results))

        if self.backend == "stub":
            return ToolResult(
                success=True,
                output=[
                    {"title": f"Stub result {i+1} for {query}", "url": f"https://example.com/{i}"}
                    for i in range(max_results)
                ],
            )
        if self.backend == "callable" and callable(self.custom_search):
            try:
                results = self.custom_search(query=query, max_results=max_results)
            except Exception as e:
                return ToolResult(success=False, error=f"custom_search error: {e}")
            return ToolResult(success=True, output=results)

        if self.backend == "duckduckgo":
            return self._duckduckgo(query, max_results)

        return ToolResult(success=False, error=f"unknown backend: {self.backend}")

    def _duckduckgo(self, query: str, max_results: int) -> ToolResult:
        try:
            import requests
            from urllib.parse import quote_plus
        except ImportError as e:
            return ToolResult(success=False, error=f"requests not installed: {e}")

        try:
            r = requests.get(
                f"https://duckduckgo.com/?q={quote_plus(query)}&format=json&no_redirect=1",
                timeout=self.timeout_seconds,
                headers={"User-Agent": "agi-consciousness/0.1"},
            )
            r.raise_for_status()
            data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        except Exception as e:
            return ToolResult(success=False, error=f"http error: {e}")

        results: List[Dict[str, Any]] = []
        # DDG instant answer API
        if data.get("AbstractText"):
            results.append(
                {
                    "title": data.get("Heading", ""),
                    "url": data.get("AbstractURL", ""),
                    "snippet": data.get("AbstractText", ""),
                }
            )
        for topic in (data.get("RelatedTopics") or [])[:max_results]:
            if isinstance(topic, dict) and topic.get("FirstURL"):
                results.append(
                    {
                        "title": topic.get("Text", "")[:80],
                        "url": topic.get("FirstURL", ""),
                        "snippet": topic.get("Text", ""),
                    }
                )
        return ToolResult(success=True, output=results[:max_results])


__all__ = ["WebSearchTool"]
