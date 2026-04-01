"""Token counting utilities.

Maps to src/utils/tokens.ts in the TypeScript codebase.
Provides token estimation and tracking for context window management.
"""

from __future__ import annotations

from typing import Any


def estimate_tokens_from_text(text: str) -> int:
    """Rough token estimate: ~4 chars per token."""
    return len(text) // 4


def estimate_tokens_from_content(content: Any) -> int:
    """Estimate tokens from message content (string or block list)."""
    if isinstance(content, str):
        return estimate_tokens_from_text(content)
    if isinstance(content, list):
        total = 0
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    total += estimate_tokens_from_text(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    total += estimate_tokens_from_text(str(block.get("input", {})))
                elif block.get("type") == "tool_result":
                    result_content = block.get("content", "")
                    if isinstance(result_content, str):
                        total += estimate_tokens_from_text(result_content)
                    elif isinstance(result_content, list):
                        total += estimate_tokens_from_content(result_content)
                elif block.get("type") == "thinking":
                    total += estimate_tokens_from_text(block.get("thinking", ""))
            elif isinstance(block, str):
                total += estimate_tokens_from_text(block)
            elif hasattr(block, "text"):
                total += estimate_tokens_from_text(str(getattr(block, "text", "")))
        return total
    return 0


def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    """Estimate total tokens across all messages.

    Maps to tokenCountWithEstimation() in TS.
    """
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        total += estimate_tokens_from_content(content)
        # Add overhead per message (~4 tokens for role/formatting)
        total += 4
    return total


def get_token_count_from_usage(usage: dict[str, Any]) -> int:
    """Get total context window size from a usage record."""
    return (
        usage.get("input_tokens", 0)
        + usage.get("output_tokens", 0)
        + usage.get("cache_creation_input_tokens", 0)
        + usage.get("cache_read_input_tokens", 0)
    )


def get_usage_from_messages(messages: list[dict[str, Any]]) -> dict[str, int] | None:
    """Get the usage from the last assistant message with real API usage."""
    for msg in reversed(messages):
        if msg.get("role") == "assistant" and msg.get("input_tokens"):
            return {
                "input_tokens": msg.get("input_tokens", 0),
                "output_tokens": msg.get("output_tokens", 0),
                "cache_creation_input_tokens": msg.get("cache_creation_input_tokens", 0),
                "cache_read_input_tokens": msg.get("cache_read_input_tokens", 0),
            }
    return None


def exceeds_context_window(
    messages: list[dict[str, Any]],
    context_window: int = 200_000,
    threshold: float = 0.95,
) -> bool:
    """Check if messages likely exceed the context window."""
    # First try exact usage from last API response
    usage = get_usage_from_messages(messages)
    if usage:
        total = get_token_count_from_usage(usage)
        return total > context_window * threshold

    # Fallback to estimation
    estimated = estimate_messages_tokens(messages)
    return estimated > context_window * threshold
