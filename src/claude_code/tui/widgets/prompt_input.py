"""Prompt input widget -- text input with history and submission.

Maps to src/components/PromptInput/PromptInput.tsx in the TypeScript codebase.
"""

from __future__ import annotations

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Input, Static

from rich.text import Text


class PromptSubmitted(Message):
    """Posted when the user submits a prompt."""

    def __init__(self, text: str) -> None:
        super().__init__()
        self.text = text


class PromptInput(Widget):
    """Multi-line prompt input with history navigation."""

    # can_focus defaults to False -- focus passes through to the child Input widget

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.history: list[str] = []
        self.history_index: int = -1
        self._disabled = False

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Static(Text.from_markup("[bold green]>[/] "), classes="prompt-prefix"),
            Input(
                placeholder="Type a message... (Ctrl+D to quit)",
                id="prompt-text-input",
            ),
        )

    @on(Input.Submitted, "#prompt-text-input")
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key."""
        text = event.value.strip()
        if not text or self._disabled:
            return

        # Add to history
        if text and (not self.history or self.history[-1] != text):
            self.history.append(text)
        self.history_index = -1

        # Clear input
        event.input.value = ""

        # Post the submission message
        self.post_message(PromptSubmitted(text))

    def set_disabled(self, disabled: bool) -> None:
        """Enable/disable the input."""
        self._disabled = disabled
        try:
            input_widget = self.query_one("#prompt-text-input", Input)
            input_widget.disabled = disabled
        except Exception:
            pass

    def set_focus(self) -> None:
        """Focus the text input."""
        try:
            input_widget = self.query_one("#prompt-text-input", Input)
            input_widget.focus()
        except Exception:
            pass
