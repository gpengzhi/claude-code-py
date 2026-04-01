"""Permission dialog -- modal screen for tool approval.

Maps to src/components/permissions/PermissionRequest.tsx in the TypeScript codebase.
Presented via app.push_screen_wait() and dismissed with True/False.
"""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from rich.text import Text


class PermissionDialog(ModalScreen[bool]):
    """Modal permission dialog for tool approval.

    Returns True (allowed) or False (denied) via self.dismiss().
    Used with: result = await app.push_screen_wait(PermissionDialog(...))
    """

    DEFAULT_CSS = """
    PermissionDialog {
        align: center middle;
    }
    #perm-container {
        width: 70;
        max-width: 90%;
        height: auto;
        max-height: 60%;
        background: $surface;
        border: tall $warning;
        padding: 1 2;
    }
    #perm-title {
        text-style: bold;
        color: $warning;
        margin-bottom: 1;
    }
    #perm-detail {
        color: $text-muted;
        margin-bottom: 1;
    }
    #perm-buttons {
        height: 3;
        align: center middle;
    }
    #perm-buttons Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        ("y", "allow", "Allow"),
        ("n", "deny", "Deny"),
        ("escape", "deny", "Deny"),
    ]

    def __init__(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        message: str = "",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._tool_name = tool_name
        self._tool_input = tool_input
        self._message = message

    def compose(self) -> ComposeResult:
        title = Text()
        title.append(f"Allow {self._tool_name}?", style="bold yellow")

        detail = Text()
        if self._message:
            detail.append(self._message, style="dim")
        elif "command" in self._tool_input:
            detail.append(f"Command: {self._tool_input['command']}", style="dim")
        elif "file_path" in self._tool_input:
            action = "edit" if "old_string" in self._tool_input else "write"
            detail.append(f"File ({action}): {self._tool_input['file_path']}", style="dim")
        else:
            for k, v in list(self._tool_input.items())[:3]:
                detail.append(f"{k}: {str(v)[:80]}\n", style="dim")

        with Vertical(id="perm-container"):
            yield Static(title, id="perm-title")
            yield Static(detail, id="perm-detail")
            with Horizontal(id="perm-buttons"):
                yield Button("Allow (y)", id="btn-allow", variant="success")
                yield Button("Deny (n)", id="btn-deny", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-allow":
            self.dismiss(True)
        elif event.button.id == "btn-deny":
            self.dismiss(False)

    def action_allow(self) -> None:
        self.dismiss(True)

    def action_deny(self) -> None:
        self.dismiss(False)
