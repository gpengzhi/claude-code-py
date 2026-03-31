"""Hook events.

Maps to hook events from src/schemas/hooks.ts and src/types/hooks.ts.
Defines all hook event types that can be triggered during tool execution.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal


class HookEvent(str, Enum):
    """All supported hook events."""
    PRE_TOOL_USE = "PreToolUse"
    POST_TOOL_USE = "PostToolUse"
    POST_TOOL_USE_FAILURE = "PostToolUseFailure"
    USER_PROMPT_SUBMIT = "UserPromptSubmit"
    SESSION_START = "SessionStart"
    NOTIFICATION = "Notification"
    FILE_CHANGED = "FileChanged"


# Hook command types
HookType = Literal["command", "prompt", "http"]
