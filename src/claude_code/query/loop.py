"""Query loop -- the core agentic loop.

Implements the while(true) loop of: call model -> run tools -> append results -> repeat.
- Auto-compact when approaching context limit
- max_output_tokens recovery (resume mid-thought)
- Tool result budget truncation
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

# Recovery constants (matching TS)
MAX_OUTPUT_TOKENS_RECOVERY_ATTEMPTS = 3
TOOL_RESULT_BUDGET_CHARS = 800_000  # ~200K tokens


def apply_tool_result_budget(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Truncate oversized tool results in older messages to fit budget.

    Truncate oversized tool results in older messages to fit budget..
    Walks messages from newest to oldest, tracking total chars.
    When budget is exceeded, replaces old tool results with stubs.
    """
    total_chars = 0
    # Walk from end to start
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        content = msg.get("content", "")
        if isinstance(content, list):
            for j, block in enumerate(content):
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    block_content = block.get("content", "")
                    block_size = len(str(block_content))
                    total_chars += block_size
                    if total_chars > TOOL_RESULT_BUDGET_CHARS:
                        # Replace with stub
                        messages[i]["content"][j] = {
                            **block,
                            "content": "[Tool result truncated to save context space]",
                        }
        elif isinstance(content, str):
            total_chars += len(content)

    return messages


async def query_loop(
    messages: list[dict[str, Any]],
    system_prompt: str | list[dict[str, Any]],
    model: str,
    max_tokens: int = 16384,
    tools: list[Tool] | None = None,
    tool_use_context: ToolUseContext | None = None,
    abort_event: asyncio.Event | None = None,
    max_turns: int = 100,
    hooks_config: dict | None = None,
    cumulative_cost_usd: float = 0.0,
    thinking: bool = False,
) -> AsyncGenerator[AssistantMessage | dict[str, Any], None]:
    """Core agentic loop.

    Repeatedly calls the model and executes tools until:
    - The model stops (no tool_use blocks)
    - max_turns is reached
    - abort_event is set
    - Cost limit exceeded ($25)

    Recovery paths:
    - Auto-compact when context is too long
    - max_output_tokens recovery (up to 3 retries with resume message)
    - Tool result budget truncation for older messages
    """
    from claude_code.services.api.errors import check_cost_threshold
    from claude_code.services.compact.compact import AutoCompactTracker

    turn_count = 0
    session_cost = cumulative_cost_usd
    # Operate directly on the caller's message list so QueryEngine stays in sync
    working_messages = messages
    active_tools = tools or []
    compact_tracker = AutoCompactTracker()
    max_output_recovery_count = 0

    while turn_count < max_turns:
        turn_count += 1

        # Check abort -- emit interruption message (matches TS createUserInterruptionMessage)
        if abort_event and abort_event.is_set():
            yield {
                "type": "system_event",
                "event": "aborted",
                "message": "The user has interrupted the conversation.",
            }
            return

        # Apply tool result budget (truncate old results)
        working_messages = apply_tool_result_budget(working_messages)

        # Auto-compact check
        working_messages, did_compact = await compact_tracker.maybe_compact(
            working_messages, model
        )
        if did_compact:
            yield {"type": "system_event", "event": "compacted"}

        # Call the model with streaming tool execution
        assistant_message: AssistantMessage | None = None
        tool_use_blocks: list[ToolUseBlock] = []

        # Create streaming executor if we have tools
        streaming_executor = None
        if active_tools and tool_use_context:
            from claude_code.tool.streaming_executor import StreamingToolExecutor
            streaming_executor = StreamingToolExecutor(
                active_tools, tool_use_context, hooks_config
            )

        thinking_config = {"type": "enabled", "budget_tokens": 10000} if thinking else None

        async for event in query_model(
            messages=working_messages,
            system_prompt=system_prompt,
            model=model,
            max_tokens=max_tokens,
            tools=active_tools,
            abort_event=abort_event,
            thinking=thinking_config,
        ):
            if isinstance(event, AssistantMessage):
                assistant_message = event
                yield event

                # Extract tool_use blocks and start streaming execution
                for block in event.content:
                    if isinstance(block, ToolUseBlock):
                        tool_use_blocks.append(block)
                        if streaming_executor:
                            streaming_executor.submit(block)
            elif isinstance(event, dict):
                yield event

        if assistant_message is None:
            return

        # --- Cost threshold check ---
        session_cost += assistant_message.cost_usd
        cost_warning = check_cost_threshold(session_cost)
        if cost_warning:
            yield {"type": "system_event", "event": "cost_warning", "message": cost_warning}
            if "limit" in cost_warning.lower():
                return  # Hard stop at cost limit

        # --- Recovery: max_output_tokens ---
        if (
            assistant_message.stop_reason == "max_tokens"
            and not tool_use_blocks
            and max_output_recovery_count < MAX_OUTPUT_TOKENS_RECOVERY_ATTEMPTS
        ):
            max_output_recovery_count += 1
            logger.info(
                "max_output_tokens recovery attempt %d/%d",
                max_output_recovery_count,
                MAX_OUTPUT_TOKENS_RECOVERY_ATTEMPTS,
            )
            # Append assistant message and a "continue" user message
            working_messages.append(
                assistant_message.model_dump(exclude_none=True)
            )
            working_messages.append({
                "role": "user",
                "content": (
                    "Output token limit hit. Resume directly — no apology, no recap of what "
                    "you were doing. Pick up mid-thought if that is where the cut happened. "
                    "Break remaining work into smaller pieces."
                ),
                "is_meta": True,
            })
            yield {"type": "system_event", "event": "max_tokens_recovery", "attempt": max_output_recovery_count}
            continue

        # Append assistant message to working messages
        working_messages.append(
            assistant_message.model_dump(exclude_none=True)
        )

        # If no tool use, we're done
        if not tool_use_blocks:
            return

        # Reset recovery counter on successful tool use
        max_output_recovery_count = 0

        # Execute tools -- use streaming executor results if available
        if active_tools and tool_use_context and streaming_executor:
            tool_results_blocks = await streaming_executor.get_results(tool_use_blocks)
            tool_results = [r.model_dump(exclude_none=True) for r in tool_results_blocks]
            for result_block in tool_results_blocks:
                yield {
                    "type": "tool_result_display",
                    "tool_use_id": result_block.tool_use_id,
                    "content": result_block.content,
                    "is_error": result_block.is_error,
                }
        elif active_tools and tool_use_context:
            tool_results_blocks = await run_tools(
                tool_use_blocks, active_tools, tool_use_context, hooks_config
            )
            tool_results = [r.model_dump(exclude_none=True) for r in tool_results_blocks]
            for result_block in tool_results_blocks:
                yield {
                    "type": "tool_result_display",
                    "tool_use_id": result_block.tool_use_id,
                    "content": result_block.content,
                    "is_error": result_block.is_error,
                }
        else:
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
