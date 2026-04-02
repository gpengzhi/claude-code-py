"""Query engine -- manages conversation state across turns.

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

    One QueryEngine per conversation. The query_loop mutates self.messages
    directly (it receives a reference), so messages stay in sync across turns.
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        system_prompt: str | list[dict[str, Any]] = "",
        max_tokens: int = 16384,
        tools: list[Tool] | None = None,
        cwd: Path | None = None,
        hooks_config: dict | None = None,
        permission_callback: Any | None = None,
        thinking: bool = False,
        permission_mode: str = "default",
        perm_rules: dict | None = None,
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
        self.hooks_config = hooks_config
        self.permission_callback = permission_callback
        self.thinking = thinking
        self.permission_mode = permission_mode

        # Create tool use context
        self.tool_use_context = ToolUseContext(
            cwd=self.cwd,
            tools=self.tools,
            abort_event=self.abort_event,
            permission_callback=permission_callback,
            model=self.model,
        )
        # Set permission mode and rules on app state
        from claude_code.types.permissions import ToolPermissionContext, PermissionRuleValue
        app_state = self.tool_use_context.get_app_state()

        allow_rules: list[PermissionRuleValue] = []
        deny_rules: list[PermissionRuleValue] = []
        if perm_rules:
            from claude_code.permissions.check import parse_permission_rule_string
            for rule_str in perm_rules.get("allow", []):
                allow_rules.append(parse_permission_rule_string(rule_str))
            for rule_str in perm_rules.get("deny", []):
                deny_rules.append(parse_permission_rule_string(rule_str))

        app_state.tool_permission_context = ToolPermissionContext(
            mode=permission_mode,
            always_allow_rules={"userSettings": allow_rules} if allow_rules else {},
            always_deny_rules={"userSettings": deny_rules} if deny_rules else {},
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
        """Submit a user message and yield streaming responses.

        The query_loop receives self.messages by reference and appends
        assistant messages / tool results directly, keeping history in sync.
        """
        self.reset_abort()

        # Add user message
        user_msg = {"role": "user", "content": prompt}
        self.messages.append(user_msg)

        # Run the query loop -- it mutates self.messages in place
        async for event in query_loop(
            messages=self.messages,
            system_prompt=self.system_prompt,
            model=self.model,
            max_tokens=self.max_tokens,
            tools=self.tools,
            tool_use_context=self.tool_use_context,
            abort_event=self.abort_event,
            max_turns=max_turns,
            hooks_config=self.hooks_config,
            thinking=self.thinking,
        ):
            if isinstance(event, AssistantMessage):
                # Track usage
                self.total_usage.input_tokens += event.input_tokens
                self.total_usage.output_tokens += event.output_tokens
                self.total_usage.cache_read_input_tokens += event.cache_read_input_tokens
                self.total_usage.cache_creation_input_tokens += event.cache_creation_input_tokens
                self.turn_count += 1

            yield event
