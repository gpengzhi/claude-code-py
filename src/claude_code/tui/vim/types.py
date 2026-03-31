"""Vim mode types.

Maps to src/vim/types.ts in the TypeScript codebase.
Defines the vim state machine types.
"""

from __future__ import annotations

from enum import Enum
from dataclasses import dataclass, field
from typing import Any


class VimMode(str, Enum):
    NORMAL = "normal"
    INSERT = "insert"
    VISUAL = "visual"


class CommandType(str, Enum):
    IDLE = "idle"
    COUNT = "count"
    OPERATOR = "operator"
    FIND = "find"
    REPLACE = "replace"


@dataclass
class VimState:
    """Current vim mode state."""
    mode: VimMode = VimMode.INSERT  # Start in insert mode
    command_type: CommandType = CommandType.IDLE
    count: int = 0
    operator: str = ""
    register: str = '"'  # Default register
    cursor: int = 0
    last_find: str = ""
    last_find_direction: str = ""  # 'f', 'F', 't', 'T'

    def reset_command(self) -> None:
        self.command_type = CommandType.IDLE
        self.count = 0
        self.operator = ""
