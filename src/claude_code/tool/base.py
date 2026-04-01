"""Tool base abstraction.

Maps to src/Tool.ts in the TypeScript codebase.
Defines the Tool protocol, ToolUseContext, ToolResult, and build_tool() factory.
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Awaitable

from pydantic import BaseModel

from claude_code.types.permissions import (
    PermissionAllowDecision,
    PermissionResult,
)

# Type for the async permission callback: receives (tool_name, tool_input, message) -> allow/deny
PermissionCallback = Callable[[str, dict[str, Any], str], Awaitable[bool]]


class ToolResult(BaseModel):
    """Result returned by a tool's call() method."""

    data: Any = None
    new_messages: list[Any] = []
    is_error: bool = False


@dataclass
class ToolUseContext:
    """Dependency-injection bag for tool execution.

    Maps to ToolUseContext in the TypeScript codebase.
    Passed to every tool's call() method.
    """

    cwd: Path = field(default_factory=Path.cwd)
    tools: list[Tool] = field(default_factory=list)
    abort_event: asyncio.Event = field(default_factory=asyncio.Event)
    messages: list[Any] = field(default_factory=list)
    read_file_state: dict[str, Any] = field(default_factory=dict)
    agent_id: str | None = None
    agent_type: str | None = None
    # Async callback for permission "ask" decisions; if None, defaults to deny
    permission_callback: PermissionCallback | None = None
    # Async callback for AskUserQuestion: receives (formatted_question) -> user_response_str
    user_question_callback: Any | None = None
    # Shared mutable app state -- direct reference, no React-style updater
    _app_state: Any = field(default=None)

    def get_app_state(self) -> Any:
        """Get current app state. Creates default if none set."""
        if self._app_state is None:
            from claude_code.state.app_state import AppState
            self._app_state = AppState()
        return self._app_state

    def set_app_state(self, updater: Callable) -> None:
        """Update app state via updater function for backwards compat."""
        current = self.get_app_state()
        self._app_state = updater(current)


class Tool(ABC):
    """Base class for all tools.

    Each tool must define:
    - name: The tool's canonical name
    - input_model: A Pydantic BaseModel class for input validation
    - call(): The actual tool execution logic
    - get_description(): Short description for the model
    - get_prompt(): Full prompt/instructions for the system prompt
    """

    name: str = ""
    aliases: list[str] = []
    max_result_size_chars: int = 100_000

    # Pydantic model class for input validation
    input_model: type[BaseModel] = BaseModel

    def is_enabled(self) -> bool:
        return True

    def is_concurrency_safe(self, input_data: BaseModel) -> bool:
        return False

    def is_read_only(self, input_data: BaseModel) -> bool:
        return False

    def is_destructive(self, input_data: BaseModel) -> bool:
        return False

    @abstractmethod
    async def call(
        self,
        args: BaseModel,
        context: ToolUseContext,
    ) -> ToolResult:
        """Execute the tool with validated arguments."""
        ...

    def get_description(self) -> str:
        """Short one-line description for the model."""
        return ""

    def get_prompt(self) -> str:
        """Full instructions for the system prompt."""
        return ""

    async def check_permissions(
        self,
        input_data: BaseModel,
        context: ToolUseContext,
    ) -> PermissionResult:
        """Tool-specific permission check. Default: allow."""
        return PermissionAllowDecision(updated_input=input_data)

    async def validate_input(
        self,
        input_data: BaseModel,
        context: ToolUseContext,
    ) -> str | None:
        """Validate input before permission check. Returns error string or None."""
        return None

    def get_tool_schema(self) -> dict[str, Any]:
        """Get the Anthropic API tool schema for this tool."""
        schema = self.input_model.model_json_schema()
        # Clean up Pydantic's JSON schema for Anthropic API compatibility
        schema.pop("title", None)
        return {
            "name": self.name,
            "description": self.get_description(),
            "input_schema": schema,
        }

    def format_result(self, result: ToolResult) -> str | list[dict[str, Any]]:
        """Format tool result for the API response."""
        if result.is_error:
            return str(result.data) if result.data else "Tool execution failed"
        if result.data is None:
            return ""
        return str(result.data)

    def user_facing_name(self, input_data: BaseModel | None = None) -> str:
        """Human-readable name for this tool (used in UI)."""
        return self.name
