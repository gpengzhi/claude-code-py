"""Auto-compact -- automatic conversation compaction.

Maps to src/services/compact/ in the TypeScript codebase.
Detects when the conversation is approaching token limits and compacts messages.
"""

from __future__ import annotations

import logging
from typing import Any

from claude_code.services.api.claude import query_model
from claude_code.types.message import AssistantMessage, TextBlock

logger = logging.getLogger(__name__)

# Token thresholds
DEFAULT_CONTEXT_WINDOW = 200_000
COMPACT_TRIGGER_RATIO = 0.80  # Compact when 80% of context is used
COMPACT_TARGET_RATIO = 0.50   # Target 50% after compaction


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    """Rough token estimate from messages (4 chars ≈ 1 token)."""
    total_chars = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total_chars += len(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    total_chars += len(str(block))
                elif isinstance(block, str):
                    total_chars += len(block)
    return total_chars // 4


def should_auto_compact(
    messages: list[dict[str, Any]],
    context_window: int = DEFAULT_CONTEXT_WINDOW,
) -> bool:
    """Check if auto-compaction should trigger."""
    estimated = estimate_tokens(messages)
    threshold = int(context_window * COMPACT_TRIGGER_RATIO)
    return estimated > threshold


async def compact_messages(
    messages: list[dict[str, Any]],
    model: str,
    context_window: int = DEFAULT_CONTEXT_WINDOW,
) -> list[dict[str, Any]]:
    """Compact messages by summarizing earlier conversation.

    Keeps the most recent messages intact and summarizes older ones.
    Returns a new message list with a summary message prepended.
    """
    if len(messages) < 4:
        return messages  # Nothing to compact

    # Split: summarize first 2/3, keep last 1/3
    split_point = len(messages) * 2 // 3
    to_summarize = messages[:split_point]
    to_keep = messages[split_point:]

    # Build summary prompt
    summary_parts: list[str] = []
    for msg in to_summarize:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if isinstance(content, str):
            summary_parts.append(f"[{role}]: {content[:200]}")
        elif isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", "")[:100])
                    elif block.get("type") == "tool_use":
                        text_parts.append(f"[tool: {block.get('name', '')}]")
                    elif block.get("type") == "tool_result":
                        text_parts.append("[tool result]")
            if text_parts:
                summary_parts.append(f"[{role}]: {' '.join(text_parts)}")

    conversation_text = "\n".join(summary_parts)

    # Ask the model to summarize
    summary_prompt = [
        {
            "role": "user",
            "content": (
                "Summarize this conversation concisely, preserving key decisions, "
                "file paths mentioned, and current task state:\n\n"
                f"{conversation_text[:8000]}"
            ),
        }
    ]

    summary_text = ""
    try:
        async for event in query_model(
            messages=summary_prompt,
            system_prompt="You are a conversation summarizer. Be very concise.",
            model=model,
            max_tokens=2000,
        ):
            if isinstance(event, AssistantMessage):
                for block in event.content:
                    if isinstance(block, TextBlock):
                        summary_text += block.text
    except Exception as e:
        logger.error("Compaction summarization failed: %s", e)
        # Fallback: just truncate instead of summarizing
        summary_text = f"[Conversation compacted. {len(to_summarize)} messages summarized.]"

    # Build new message list
    compact_boundary = {
        "role": "user",
        "content": f"[Conversation compacted]\n\nSummary of earlier conversation:\n{summary_text}",
        "is_meta": True,
    }

    return [compact_boundary] + to_keep


class AutoCompactTracker:
    """Tracks token usage and triggers auto-compact when needed."""

    def __init__(
        self,
        context_window: int = DEFAULT_CONTEXT_WINDOW,
        trigger_ratio: float = COMPACT_TRIGGER_RATIO,
    ) -> None:
        self.context_window = context_window
        self.trigger_ratio = trigger_ratio
        self.compact_count = 0

    def should_compact(self, messages: list[dict[str, Any]]) -> bool:
        """Check if we should trigger auto-compact."""
        return should_auto_compact(messages, self.context_window)

    async def maybe_compact(
        self,
        messages: list[dict[str, Any]],
        model: str,
    ) -> tuple[list[dict[str, Any]], bool]:
        """Compact if needed. Returns (messages, did_compact)."""
        if not self.should_compact(messages):
            return messages, False

        logger.info(
            "Auto-compact triggered (estimated %d tokens, threshold %d)",
            estimate_tokens(messages),
            int(self.context_window * self.trigger_ratio),
        )

        compacted = await compact_messages(messages, model, self.context_window)
        self.compact_count += 1
        return compacted, True
