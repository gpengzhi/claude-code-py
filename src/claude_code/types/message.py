"""Message types.

Maps to the internal Message types and SDK message types from the TypeScript codebase.
These are the core message types that flow through the query engine.
"""

from __future__ import annotations

import uuid as uuid_mod
from typing import Any, Literal

from pydantic import BaseModel, Field


def make_uuid() -> str:
    return str(uuid_mod.uuid4())


# Content block types (matching Anthropic API)
class TextBlock(BaseModel):
    type: Literal["text"] = "text"
    text: str


class ToolUseBlock(BaseModel):
    type: Literal["tool_use"] = "tool_use"
    id: str
    name: str
    input: dict[str, Any] = Field(default_factory=dict)


class ToolResultBlock(BaseModel):
    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str
    content: str | list[TextBlock] = ""
    is_error: bool = False


class ThinkingBlock(BaseModel):
    type: Literal["thinking"] = "thinking"
    thinking: str


class ImageBlock(BaseModel):
    type: Literal["image"] = "image"
    source: dict[str, Any]


ContentBlock = TextBlock | ToolUseBlock | ToolResultBlock | ThinkingBlock | ImageBlock


# Internal message types
class UserMessage(BaseModel):
    """A user message in the conversation."""

    role: Literal["user"] = "user"
    content: list[ContentBlock] | str
    uuid: str = Field(default_factory=make_uuid)
    is_meta: bool = False
    tool_use_result: Any | None = None


class AssistantMessage(BaseModel):
    """An assistant (model) message in the conversation."""

    role: Literal["assistant"] = "assistant"
    content: list[ContentBlock]
    model: str = ""
    stop_reason: str | None = None
    cost_usd: float = 0.0
    uuid: str = Field(default_factory=make_uuid)
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


class SystemMessage(BaseModel):
    """A system-level message (compact boundary, error, informational)."""

    role: Literal["system"] = "system"
    type: str = "informational"  # compact_boundary, api_error, informational, etc.
    content: str = ""
    uuid: str = Field(default_factory=make_uuid)
    level: str = "info"  # info, warning, error


class ProgressMessage(BaseModel):
    """A tool progress message."""

    role: Literal["progress"] = "progress"
    tool_use_id: str = ""
    tool_name: str = ""
    content: Any = None
    uuid: str = Field(default_factory=make_uuid)


Message = UserMessage | AssistantMessage | SystemMessage | ProgressMessage


# Usage tracking
class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cost_usd: float = 0.0


EMPTY_USAGE = Usage()
