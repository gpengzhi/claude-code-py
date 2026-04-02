"""WebSearchTool -- search the web via DuckDuckGo.

Maps to src/tools/WebSearchTool/WebSearchTool.ts in the TypeScript codebase.
Uses DuckDuckGo (no API key required) instead of Anthropic's server-side search.
"""

from __future__ import annotations

import logging
from typing import Optional

from pydantic import BaseModel, Field

from claude_code.tool.base import Tool, ToolResult, ToolUseContext

logger = logging.getLogger(__name__)

MAX_RESULTS = 10


class WebSearchInput(BaseModel):
    query: str = Field(description="The search query to use", min_length=2)
    allowed_domains: Optional[list[str]] = Field(
        default=None,
        description="Only include search results from these domains",
    )
    blocked_domains: Optional[list[str]] = Field(
        default=None,
        description="Never include search results from these domains",
    )


class WebSearchTool(Tool):
    name = "WebSearch"
    aliases = ["web_search", "search"]
    input_model = WebSearchInput
    max_result_size_chars = 100_000

    def get_description(self) -> str:
        return "Searches the web and returns results to inform responses."

    def get_prompt(self) -> str:
        return (
            "Searches the web using DuckDuckGo and returns results.\n"
            "- Provides up-to-date information for current events and recent data\n"
            "- Returns titles, URLs, and snippets for each result\n"
            "- Domain filtering is supported to include or block specific websites"
        )

    def is_read_only(self, input_data: BaseModel) -> bool:
        return True

    def is_concurrency_safe(self, input_data: BaseModel) -> bool:
        return True

    async def call(
        self,
        args: BaseModel,
        context: ToolUseContext,
    ) -> ToolResult:
        assert isinstance(args, WebSearchInput)

        query = args.query.strip()
        if not query:
            return ToolResult(data="Error: query is required", is_error=True)

        logger.info("WebSearch: %s", query)

        try:
            from ddgs import DDGS

            with DDGS() as ddgs:
                raw_results = list(ddgs.text(query, max_results=MAX_RESULTS))

            if not raw_results:
                return ToolResult(data=f"No results found for: {query}")

            # Apply domain filters
            results = raw_results
            if args.allowed_domains:
                results = [
                    r for r in results
                    if any(d in r.get("href", "") for d in args.allowed_domains)
                ]
            if args.blocked_domains:
                results = [
                    r for r in results
                    if not any(d in r.get("href", "") for d in args.blocked_domains)
                ]

            if not results:
                return ToolResult(data=f"No results after filtering for: {query}")

            # Format results
            parts = [f"Search results for: {query}\n"]
            for i, r in enumerate(results, 1):
                title = r.get("title", "")
                url = r.get("href", "")
                snippet = r.get("body", "")
                parts.append(f"{i}. {title}\n   {url}\n   {snippet}\n")

            return ToolResult(data="\n".join(parts))

        except ImportError:
            return ToolResult(
                data="WebSearch requires the ddgs package: pip install ddgs",
                is_error=True,
            )
        except Exception as e:
            logger.error("WebSearch error: %s", e)
            return ToolResult(data=f"Search failed: {e}", is_error=True)
