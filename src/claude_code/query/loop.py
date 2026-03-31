"""Query loop -- the core agentic loop.

Maps to src/query.ts in the TypeScript codebase.
Implements the while(true) loop of: call model -> run tools -> append results -> repeat.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncGenerator

from claude_code.services.api.claude import query_model
from claude_code.tool.base import Tool, ToolUseContext
from claude_code.tool.executor import run_tools
from claude_code.types.message import (
    AssistantMessage,
    ToolUseBlock,
)

logger = logging.getLogger(__name__)


async def query_loop(
    messages: list[dict[str, Any]],
    system_prompt: str | list[dict[str, Any]],
    model: str,
    max_tokens: int = 16384,
    tools: list[Tool] | None = None,
    tool_use_context: ToolUseContext | None = None,
    abort_event: asyncio.Event | None = None,
    max_turns: int = 100,
) -> AsyncGenerator[AssistantMessage | dict[str, Any], None]:
    """Core agentic loop.

    Repeatedly calls the model and executes tools until:
    - The model stops (no tool_use blocks)
    - max_turns is reached
    - abort_event is set

    Yields AssistantMessage and stream events as they arrive.
    """
    from claude_code.services.compact.compact import AutoCompactTracker

    turn_count = 0
    working_messages = list(messages)
    active_tools = tools or []
    compact_tracker = AutoCompactTracker()

    while turn_count < max_turns:
        turn_count += 1

        # Check abort
        if abort_event and abort_event.is_set():
            return

        # Auto-compact check
        working_messages, did_compact = await compact_tracker.maybe_compact(
            working_messages, model
        )
        if did_compact:
            yield {"type": "system_event", "event": "compacted"}

        # Call the model
        assistant_message: AssistantMessage | None = None
        tool_use_blocks: list[ToolUseBlock] = []

        async for event in query_model(
            messages=working_messages,
            system_prompt=system_prompt,
            model=model,
            max_tokens=max_tokens,
            tools=active_tools,
            abort_event=abort_event,
        ):
            if isinstance(event, AssistantMessage):
                assistant_message = event
                yield event

                # Extract tool_use blocks
                for block in event.content:
                    if isinstance(block, ToolUseBlock):
                        tool_use_blocks.append(block)
            elif isinstance(event, dict):
                yield event

        if assistant_message is None:
            return

        # Append assistant message to working messages
        working_messages.append(
            assistant_message.model_dump(exclude_none=True)
        )

        # If no tool use, we're done
        if not tool_use_blocks:
            return

        # Execute tools using the executor
        if active_tools and tool_use_context:
            tool_results_blocks = await run_tools(
                tool_use_blocks, active_tools, tool_use_context
            )
            tool_results = [r.model_dump(exclude_none=True) for r in tool_results_blocks]

            # Yield tool results for display
            for result_block in tool_results_blocks:
                yield {
                    "type": "tool_result_display",
                    "tool_use_id": result_block.tool_use_id,
                    "content": result_block.content,
                    "is_error": result_block.is_error,
                }
        else:
            # No tools available - return error results
            from claude_code.types.message import ToolResultBlock

            tool_results = []
            for tool_block in tool_use_blocks:
                tool_results.append(
                    ToolResultBlock(
                        tool_use_id=tool_block.id,
                        content=f"Tool execution not available for {tool_block.name}",
                        is_error=True,
                    ).model_dump(exclude_none=True)
                )

        # Append tool results as a user message
        working_messages.append(
            {
                "role": "user",
                "content": tool_results,
            }
        )

        # Yield turn info
        yield {
            "type": "tool_results",
            "turn": turn_count,
            "count": len(tool_results),
        }
