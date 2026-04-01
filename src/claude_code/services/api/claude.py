"""Core model query and streaming.

Maps to src/services/api/claude.ts in the TypeScript codebase.
Handles the actual API call, SSE streaming, and message assembly.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, AsyncGenerator

from claude_code.services.api.client import get_anthropic_client
from claude_code.types.message import (
    AssistantMessage,
    ContentBlock,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
    Usage,
    make_uuid,
)

logger = logging.getLogger(__name__)

# Cost per token for common models (USD)
MODEL_COSTS: dict[str, dict[str, float]] = {
    "claude-sonnet-4-20250514": {
        "input": 3.0 / 1_000_000,
        "output": 15.0 / 1_000_000,
        "cache_read": 0.3 / 1_000_000,
        "cache_write": 3.75 / 1_000_000,
    },
    "claude-opus-4-20250514": {
        "input": 15.0 / 1_000_000,
        "output": 75.0 / 1_000_000,
        "cache_read": 1.5 / 1_000_000,
        "cache_write": 18.75 / 1_000_000,
    },
    "claude-haiku-4-5-20251001": {
        "input": 0.80 / 1_000_000,
        "output": 4.0 / 1_000_000,
        "cache_read": 0.08 / 1_000_000,
        "cache_write": 1.0 / 1_000_000,
    },
}

# Fallback cost
DEFAULT_COSTS = {
    "input": 3.0 / 1_000_000,
    "output": 15.0 / 1_000_000,
    "cache_read": 0.3 / 1_000_000,
    "cache_write": 3.75 / 1_000_000,
}


def calculate_cost(model: str, usage: Usage) -> float:
    """Calculate USD cost from token usage."""
    costs = DEFAULT_COSTS
    for model_prefix, model_costs in MODEL_COSTS.items():
        if model.startswith(model_prefix.rsplit("-", 1)[0]):
            costs = model_costs
            break

    return (
        usage.input_tokens * costs["input"]
        + usage.output_tokens * costs["output"]
        + usage.cache_read_input_tokens * costs["cache_read"]
        + usage.cache_creation_input_tokens * costs["cache_write"]
    )


def build_api_messages(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert internal messages to Anthropic API format."""
    api_messages: list[dict[str, Any]] = []

    for msg in messages:
        role = msg.get("role")
        if role not in ("user", "assistant"):
            continue

        content = msg.get("content", "")
        if isinstance(content, str):
            api_messages.append({"role": role, "content": content})
        elif isinstance(content, list):
            # Convert Pydantic models to dicts
            blocks = []
            for block in content:
                if hasattr(block, "model_dump"):
                    blocks.append(block.model_dump(exclude_none=True))
                elif isinstance(block, dict):
                    blocks.append(block)
                else:
                    blocks.append({"type": "text", "text": str(block)})
            api_messages.append({"role": role, "content": blocks})

    return api_messages


def build_tool_schemas(tools: list[Any]) -> list[dict[str, Any]]:
    """Convert Tool objects to Anthropic API tool schema format."""
    schemas = []
    for tool in tools:
        # Use get_tool_schema() if available (our Tool base class)
        if hasattr(tool, "get_tool_schema"):
            schemas.append(tool.get_tool_schema())
        else:
            schema: dict[str, Any] = {
                "name": tool.name,
                "description": "",
                "input_schema": {"type": "object", "properties": {}},
            }
            if hasattr(tool, "get_description"):
                schema["description"] = tool.get_description()
            if hasattr(tool, "input_model") and hasattr(
                tool.input_model, "model_json_schema"
            ):
                json_schema = tool.input_model.model_json_schema()
                json_schema.pop("title", None)
                schema["input_schema"] = json_schema
            schemas.append(schema)
    return schemas


async def query_model(
    messages: list[dict[str, Any]],
    system_prompt: str | list[dict[str, Any]],
    model: str,
    max_tokens: int = 16384,
    tools: list[Any] | None = None,
    abort_event: asyncio.Event | None = None,
    thinking: dict[str, Any] | None = None,
) -> AsyncGenerator[AssistantMessage | dict[str, Any], None]:
    """Stream a response from the Anthropic API.

    This is the core API integration point. It:
    1. Builds the API request parameters
    2. Makes the streaming API call
    3. Processes SSE events into AssistantMessage objects

    Yields AssistantMessage for each completed content block,
    and raw stream events for progress tracking.
    """
    client = get_anthropic_client()

    # Build API messages
    api_messages = build_api_messages(messages)

    # Build request params (stream is handled by the .stream() method, not a param)
    params: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": api_messages,
    }

    # System prompt
    if isinstance(system_prompt, str):
        params["system"] = system_prompt
    elif isinstance(system_prompt, list):
        params["system"] = system_prompt

    # Tools
    if tools:
        tool_schemas = build_tool_schemas(tools)
        if tool_schemas:
            params["tools"] = tool_schemas

    # Extended thinking
    if thinking:
        params["thinking"] = thinking

    # Retry configuration
    max_retries = 3
    retry_delay_base = 1.0  # seconds

    for attempt in range(max_retries + 1):
        try:
            async for event in _execute_stream(params, model, abort_event):
                yield event
            return  # Success -- exit retry loop
        except Exception as e:
            from claude_code.services.api.errors import classify_error
            api_error = classify_error(e)

            if not api_error.retryable or attempt >= max_retries:
                logger.error("API call failed (attempt %d/%d): %s", attempt + 1, max_retries + 1, e)
                yield {"type": "api_error", "error": str(e), "error_type": type(e).__name__}
                return

            delay = retry_delay_base * (2 ** attempt)
            logger.warning("API call failed (attempt %d/%d), retrying in %.1fs: %s", attempt + 1, max_retries + 1, delay, e)
            yield {"type": "api_retry", "attempt": attempt + 1, "delay": delay, "error": str(e)}
            await asyncio.sleep(delay)


async def _execute_stream(
    params: dict[str, Any],
    model: str,
    abort_event: asyncio.Event | None = None,
) -> AsyncGenerator[AssistantMessage | dict[str, Any], None]:
    """Execute a single streaming API call (no retry)."""
    client = get_anthropic_client()

    # Track timing
    start_time = time.monotonic()
    ttft_ms: float | None = None

    # Content blocks being assembled
    content_blocks: list[ContentBlock] = []
    current_block: dict[str, Any] | None = None
    usage = Usage()

    try:
        async with client.messages.stream(**params) as stream:
            async for event in stream:
                # Check abort
                if abort_event and abort_event.is_set():
                    logger.debug("Query aborted by abort_event")
                    return

                event_type = event.type

                if event_type == "message_start":
                    if ttft_ms is None:
                        ttft_ms = (time.monotonic() - start_time) * 1000

                elif event_type == "content_block_start":
                    cb = event.content_block
                    current_block = {"type": cb.type}
                    if cb.type == "text":
                        current_block["text"] = ""
                    elif cb.type == "tool_use":
                        current_block["id"] = cb.id
                        current_block["name"] = cb.name
                        current_block["input_json"] = ""
                    elif cb.type == "thinking":
                        current_block["thinking"] = ""

                elif event_type == "content_block_delta":
                    if current_block is None:
                        continue
                    delta = event.delta
                    if delta.type == "text_delta":
                        current_block["text"] += delta.text
                        # Yield streaming text event for real-time display
                        yield {
                            "type": "stream_event",
                            "event_type": "text_delta",
                            "text": delta.text,
                        }
                    elif delta.type == "input_json_delta":
                        current_block["input_json"] += delta.partial_json
                    elif delta.type == "thinking_delta":
                        current_block["thinking"] += delta.thinking

                elif event_type == "content_block_stop":
                    if current_block is None:
                        continue
                    # Assemble completed content block
                    block_type = current_block["type"]
                    if block_type == "text":
                        content_blocks.append(
                            TextBlock(text=current_block["text"])
                        )
                    elif block_type == "tool_use":
                        import json

                        try:
                            input_data = json.loads(
                                current_block.get("input_json", "{}")
                            )
                        except json.JSONDecodeError:
                            input_data = {}
                        content_blocks.append(
                            ToolUseBlock(
                                id=current_block["id"],
                                name=current_block["name"],
                                input=input_data,
                            )
                        )
                    elif block_type == "thinking":
                        content_blocks.append(
                            ThinkingBlock(thinking=current_block["thinking"])
                        )
                    current_block = None

                elif event_type == "message_delta":
                    # Final usage and stop_reason
                    msg_usage = getattr(event, "usage", None)
                    if msg_usage:
                        usage.output_tokens = getattr(
                            msg_usage, "output_tokens", 0
                        )

                elif event_type == "message_stop":
                    pass

            # Get final message for usage
            final_message = await stream.get_final_message()
            if final_message and final_message.usage:
                usage.input_tokens = final_message.usage.input_tokens
                usage.output_tokens = final_message.usage.output_tokens
                usage.cache_read_input_tokens = getattr(
                    final_message.usage, "cache_read_input_tokens", 0
                ) or 0
                usage.cache_creation_input_tokens = getattr(
                    final_message.usage, "cache_creation_input_tokens", 0
                ) or 0

            cost = calculate_cost(model, usage)
            stop_reason = (
                final_message.stop_reason if final_message else None
            )

    except Exception as e:
        logger.error("API call failed: %s", e)
        # Yield error as a system message
        yield {
            "type": "api_error",
            "error": str(e),
            "error_type": type(e).__name__,
        }
        return

    # Yield the completed assistant message
    if content_blocks:
        yield AssistantMessage(
            content=content_blocks,
            model=model,
            stop_reason=stop_reason,
            cost_usd=cost,
            uuid=make_uuid(),
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_input_tokens=usage.cache_read_input_tokens,
            cache_creation_input_tokens=usage.cache_creation_input_tokens,
        )
