"""Core model query and streaming.

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

CACHE_CONTROL_EPHEMERAL = {"type": "ephemeral"}


def build_system_prompt_blocks(system_prompt: str) -> list[dict[str, Any]]:
    """Convert system prompt string to cache-annotated text blocks.

    Places a cache_control breakpoint on the last system block so the entire
    system prompt is eligible for caching.
    """
    # Split into meaningful sections for caching granularity
    # The key insight: put cache_control on the last block so the entire
    # system prompt prefix is cached as one unit
    return [
        {
            "type": "text",
            "text": system_prompt,
            "cache_control": CACHE_CONTROL_EPHEMERAL,
        }
    ]


def add_cache_breakpoint_to_messages(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Add a cache_control breakpoint to the last message.

    Places exactly one cache_control marker on the last message's last content block.
    """
    if not messages:
        return messages

    # Work on a copy
    messages = [dict(m) for m in messages]
    last_msg = messages[-1]
    content = last_msg.get("content")

    if isinstance(content, str):
        # Wrap string content in a text block with cache_control
        last_msg["content"] = [
            {"type": "text", "text": content, "cache_control": CACHE_CONTROL_EPHEMERAL}
        ]
    elif isinstance(content, list) and content:
        # Add cache_control to the last content block
        content = [dict(b) if isinstance(b, dict) else b for b in content]
        last_block = content[-1]
        if isinstance(last_block, dict):
            last_block["cache_control"] = CACHE_CONTROL_EPHEMERAL
        last_msg["content"] = content

    messages[-1] = last_msg
    return messages


def build_api_messages(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert internal messages to Anthropic API format.

    Strips internal-only fields (model, cost_usd, uuid, etc.) and
    ensures only role + content are sent to the API.
    """
    api_messages: list[dict[str, Any]] = []

    for msg in messages:
        role = msg.get("role")
        if role not in ("user", "assistant"):
            continue

        content = msg.get("content", "")
        if isinstance(content, str):
            api_messages.append({"role": role, "content": content})
        elif isinstance(content, list):
            # Convert Pydantic models to dicts, keeping only API-relevant fields
            blocks = []
            for block in content:
                if hasattr(block, "model_dump"):
                    block_dict = block.model_dump(exclude_none=True)
                elif isinstance(block, dict):
                    block_dict = block
                else:
                    block_dict = {"type": "text", "text": str(block)}
                # Strip internal fields from content blocks
                blocks.append({
                    k: v for k, v in block_dict.items()
                    if k in ("type", "text", "id", "name", "input",
                             "tool_use_id", "content", "is_error",
                             "thinking", "cache_control")
                })
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


def get_extra_headers(model: str) -> dict[str, str]:
    """Build extra HTTP headers for beta features.

    In SDK v0.87+, thinking and prompt caching are first-class params.
    Extended context is handled by the API automatically for supported models.
    Only send beta headers when using the direct Anthropic API (not proxies).
    """
    import os
    headers: dict[str, str] = {}

    # Only send beta headers to the official Anthropic API.
    # Proxies may hang or reject unknown beta headers.
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "")
    if base_url and "api.anthropic.com" not in base_url:
        return headers

    # Extended context (1M) for supported models on the direct API
    if "opus" in model or "sonnet" in model:
        headers["anthropic-beta"] = "extended-context-2025-04-15"

    return headers


async def query_model(
    messages: list[dict[str, Any]],
    system_prompt: str | list[dict[str, Any]],
    model: str,
    max_tokens: int = 16384,
    tools: list[Any] | None = None,
    abort_event: asyncio.Event | None = None,
    thinking: dict[str, Any] | None = None,
    temperature: float | None = None,
) -> AsyncGenerator[AssistantMessage | dict[str, Any], None]:
    """Stream a response from the Anthropic API.

    This is the core API integration point. It:
    1. Builds the API request parameters with beta headers
    2. Makes the streaming API call with retry
    3. Processes SSE events into AssistantMessage objects

    Yields AssistantMessage for each completed content block,
    and raw stream events for progress tracking.
    """
    client = get_anthropic_client()

    # Build API messages with cache breakpoint on last message
    api_messages = build_api_messages(messages)
    api_messages = add_cache_breakpoint_to_messages(api_messages)

    # Build request params
    params: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": api_messages,
    }

    # Extra headers for beta features
    extra_headers = get_extra_headers(model)
    if extra_headers:
        params["extra_headers"] = extra_headers

    # System prompt with prompt caching
    if isinstance(system_prompt, str) and system_prompt:
        params["system"] = build_system_prompt_blocks(system_prompt)
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

    # Temperature (TS sends 1 when thinking is disabled)
    if temperature is not None:
        params["temperature"] = temperature
    elif not thinking:
        params["temperature"] = 1

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
    stop_reason: str | None = None

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
                    # Capture input usage from message_start
                    msg = getattr(event, "message", None)
                    if msg and hasattr(msg, "usage") and msg.usage:
                        usage.input_tokens = getattr(msg.usage, "input_tokens", 0) or 0
                        usage.cache_read_input_tokens = getattr(msg.usage, "cache_read_input_tokens", 0) or 0
                        usage.cache_creation_input_tokens = getattr(msg.usage, "cache_creation_input_tokens", 0) or 0

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
                    # Capture output usage and stop_reason
                    msg_usage = getattr(event, "usage", None)
                    if msg_usage:
                        usage.output_tokens = getattr(msg_usage, "output_tokens", 0) or 0
                    delta = getattr(event, "delta", None)
                    if delta and hasattr(delta, "stop_reason") and delta.stop_reason:
                        stop_reason = delta.stop_reason

                elif event_type == "message_stop":
                    pass


    except Exception:
        # Re-raise so query_model's retry loop can handle it
        raise

    # Yield the completed assistant message
    if content_blocks:
        yield AssistantMessage(
            content=content_blocks,
            model=model,
            stop_reason=stop_reason,
            cost_usd=0.0,
            uuid=make_uuid(),
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_input_tokens=usage.cache_read_input_tokens,
            cache_creation_input_tokens=usage.cache_creation_input_tokens,
        )
