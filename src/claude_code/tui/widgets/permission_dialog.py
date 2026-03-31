"""Permission dialog widget -- approve/deny tool execution.

Maps to src/components/permissions/PermissionRequest.tsx in the TypeScript codebase.
"""

from __future__ import annotations

import asyncio
from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, Static

from rich.text import Text


class PermissionResponse(Message):
    """Posted when user responds to a permission dialog."""

    def __init__(self, tool_use_id: str, allowed: bool, always_allow: bool = False) -> None:
        super().__init__()
        self.tool_use_id = tool_use_id
        self.allowed = allowed
        self.always_allow = always_allow


class PermissionDialog(Widget):
    """Inline permission dialog for tool approval."""

    DEFAULT_CSS = """
    PermissionDialog {
        dock: bottom;
        height: auto;
        max-height: 50%;
        background: $surface;
        border-top: tall $warning;
        padding: 1 2;
        display: none;
    }
    PermissionDialog.visible {
        display: block;
    }
    PermissionDialog .perm-title {
        text-style: bold;
        color: $warning;
        margin-bottom: 1;
    }
    PermissionDialog .perm-detail {
        color: $text-muted;
        margin-bottom: 1;
    }
    PermissionDialog .perm-buttons {
        layout: horizontal;
        height: 3;
    }
    PermissionDialog Button {
        margin: 0 1;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._tool_use_id = ""
        self._tool_name = ""
        self._tool_input: dict[str, Any] = {}

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("", classes="perm-title", id="perm-title")
            yield Static("", classes="perm-detail", id="perm-detail")
            with Widget(classes="perm-buttons"):
                yield Button("Allow (y)", id="btn-allow", variant="success")
                yield Button("Always Allow (a)", id="btn-always", variant="primary")
                yield Button("Deny (n)", id="btn-deny", variant="error")

    def show_permission(
        self,
        tool_use_id: str,
        tool_name: str,
        tool_input: dict[str, Any],
    ) -> None:
        """Show the permission dialog for a tool use."""
        self._tool_use_id = tool_use_id
        self._tool_name = tool_name
        self._tool_input = tool_input

        # Update title
        title = Text()
        title.append(f"Allow {tool_name}?", style="bold yellow")

        try:
            self.query_one("#perm-title", Static).update(title)
        except Exception:
            pass

        # Update detail
        detail = Text()
        if "command" in tool_input:
            detail.append(f"Command: {tool_input['command']}", style="dim")
        elif "file_path" in tool_input:
            action = "edit" if "old_string" in tool_input else "write"
            detail.append(f"File ({action}): {tool_input['file_path']}", style="dim")
        else:
            for k, v in list(tool_input.items())[:2]:
                detail.append(f"{k}: {str(v)[:80]}\n", style="dim")

        try:
            self.query_one("#perm-detail", Static).update(detail)
        except Exception:
            pass

        self.add_class("visible")
        # Focus the allow button
        try:
            self.query_one("#btn-allow", Button).focus()
        except Exception:
            pass

    def hide_permission(self) -> None:
        """Hide the dialog."""
        self.remove_class("visible")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-allow":
            self.post_message(
                PermissionResponse(self._tool_use_id, allowed=True)
            )
        elif event.button.id == "btn-always":
            self.post_message(
                PermissionResponse(self._tool_use_id, allowed=True, always_allow=True)
            )
        elif event.button.id == "btn-deny":
            self.post_message(
                PermissionResponse(self._tool_use_id, allowed=False)
            )
        self.hide_permission()

    def on_key(self, event: Any) -> None:
        """Handle keyboard shortcuts in the dialog."""
        if not self.has_class("visible"):
            return
        if event.key == "y":
            self.post_message(
                PermissionResponse(self._tool_use_id, allowed=True)
            )
            self.hide_permission()
            event.stop()
        elif event.key == "a":
            self.post_message(
                PermissionResponse(self._tool_use_id, allowed=True, always_allow=True)
            )
            self.hide_permission()
            event.stop()
        elif event.key == "n":
            self.post_message(
                PermissionResponse(self._tool_use_id, allowed=False)
            )
            self.hide_permission()
            event.stop()
