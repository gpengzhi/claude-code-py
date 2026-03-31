"""WebSearchTool -- Web search.

Maps to src/tools/WebSearchTool/WebSearchTool.ts in the TypeScript codebase.
"""

from __future__ import annotations

import logging
from typing import Optional

from pydantic import BaseModel, Field

from claude_code.tool.base import Tool, ToolResult, ToolUseContext

logger = logging.getLogger(__name__)


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
            "Searches the web and uses the results to inform responses.\n"
            "- Provides up-to-date information for current events and recent data\n"
            "- Returns search result information formatted as search result blocks\n"
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

        # Build a description of the search for logging
        parts = [f"Query: {query}"]
        if args.allowed_domains:
            parts.append(f"Allowed domains: {', '.join(args.allowed_domains)}")
        if args.blocked_domains:
            parts.append(f"Blocked domains: {', '.join(args.blocked_domains)}")

        logger.info("WebSearch: %s", " | ".join(parts))

        # Web search requires API integration (e.g., a search provider key).
        # Return a placeholder message indicating this.
        return ToolResult(
            data=(
                "Web search is not yet configured. "
                "This feature requires integration with a search API provider. "
                f"Attempted query: {query}"
            ),
            is_error=True,
        )
