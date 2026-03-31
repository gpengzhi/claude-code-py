"""Query engine -- manages conversation state across turns.

Maps to src/QueryEngine.ts in the TypeScript codebase.
Owns the message history, usage tracking, and orchestrates the query loop.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, AsyncGenerator

from claude_code.query.loop import query_loop
from claude_code.tool.base import Tool, ToolUseContext
from claude_code.types.message import AssistantMessage, Usage

logger = logging.getLogger(__name__)


class QueryEngine:
    """Manages a conversation session with the Claude API.

    One QueryEngine per conversation. State (messages, usage) persists
    across multiple submit_message() calls.
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        system_prompt: str | list[dict[str, Any]] = "",
        max_tokens: int = 16384,
        tools: list[Tool] | None = None,
        cwd: Path | None = None,
    ) -> None:
        self.model = model
        self.system_prompt = system_prompt
        self.max_tokens = max_tokens
        self.tools = tools or []
        self.cwd = cwd or Path.cwd()
        self.messages: list[dict[str, Any]] = []
        self.total_usage = Usage()
        self.abort_event = asyncio.Event()
        self.turn_count = 0

        # Create tool use context
        self.tool_use_context = ToolUseContext(
            cwd=self.cwd,
            tools=self.tools,
            abort_event=self.abort_event,
        )

    def abort(self) -> None:
        """Abort the current query."""
        self.abort_event.set()

    def reset_abort(self) -> None:
        """Reset the abort event for a new query."""
        self.abort_event = asyncio.Event()
        self.tool_use_context.abort_event = self.abort_event

    async def submit_message(
        self,
        prompt: str,
        *,
        max_turns: int = 100,
    ) -> AsyncGenerator[AssistantMessage | dict[str, Any], None]:
        """Submit a user message and yield streaming responses."""
        self.reset_abort()

        # Add user message
        user_msg = {"role": "user", "content": prompt}
        self.messages.append(user_msg)

        # Run the query loop
        async for event in query_loop(
            messages=self.messages,
            system_prompt=self.system_prompt,
            model=self.model,
            max_tokens=self.max_tokens,
            tools=self.tools,
            tool_use_context=self.tool_use_context,
            abort_event=self.abort_event,
            max_turns=max_turns,
        ):
            if isinstance(event, AssistantMessage):
                # Track usage
                self.total_usage.input_tokens += event.input_tokens
                self.total_usage.output_tokens += event.output_tokens
                self.total_usage.cache_read_input_tokens += event.cache_read_input_tokens
                self.total_usage.cache_creation_input_tokens += event.cache_creation_input_tokens
                self.total_usage.cost_usd += event.cost_usd
                self.turn_count += 1

                # Add to conversation history
                self.messages.append(event.model_dump(exclude_none=True))

            elif isinstance(event, dict) and event.get("type") == "tool_results":
                # Tool results already added by query_loop to working_messages,
                # but we need to sync our messages list
                pass

            yield event
