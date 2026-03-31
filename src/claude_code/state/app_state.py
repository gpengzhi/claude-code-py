"""Application state.

Maps to src/state/AppStateStore.ts in the TypeScript codebase.
Central application state that flows through the entire system.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from claude_code.types.permissions import PermissionMode, ToolPermissionContext


class AppState(BaseModel):
    """The complete application state.

    Uses Pydantic's model_copy(update=...) for immutable updates.
    """

    # Settings
    verbose: bool = False
    main_loop_model: str = "claude-sonnet-4-20250514"
    fast_mode: bool = False
    thinking_enabled: bool = False
    effort_value: str = "high"

    # Permission
    tool_permission_context: ToolPermissionContext = Field(
        default_factory=ToolPermissionContext
    )

    # Session
    is_main_agent: bool = True
    mode: str = "code"  # code, plan

    # MCP
    mcp_clients: dict = Field(default_factory=dict)
    mcp_tools: list = Field(default_factory=list)

    # Tasks (mutable by design, matching TS codebase)
    tasks: dict = Field(default_factory=dict)

    # UI
    expanded_view: bool = False


def get_default_app_state(**overrides: object) -> AppState:
    """Create a default AppState, optionally with overrides."""
    return AppState(**overrides)  # type: ignore[arg-type]


def update_app_state(state: AppState, **updates: object) -> AppState:
    """Create a new AppState with the given updates (immutable update)."""
    return state.model_copy(update=updates)
