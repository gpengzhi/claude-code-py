"""Spinner widget -- activity indicator during model calls.

Maps to src/components/Spinner.tsx in the TypeScript codebase.
"""

from __future__ import annotations

import time

from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from rich.text import Text


SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class Spinner(Widget):
    """Animated spinner with status text."""

    DEFAULT_CSS = """
    Spinner {
        height: auto;
        display: none;
    }
    Spinner.visible {
        display: block;
    }
    """

    _visible = reactive(False)
    _text = reactive("Thinking...")
    _frame = 0
    _start_time: float = 0.0
    _timer = None

    def compose(self):
        yield Static("", id="spinner-content")

    def show(self, text: str = "Thinking...") -> None:
        """Show the spinner with given text."""
        self._text = text
        self._visible = True
        self._start_time = time.monotonic()
        self._frame = 0
        self.add_class("visible")
        self._timer = self.set_interval(0.08, self._animate)

    def hide(self) -> None:
        """Hide the spinner."""
        self._visible = False
        self.remove_class("visible")
        if self._timer:
            self._timer.stop()
            self._timer = None

    def update_text(self, text: str) -> None:
        """Update the spinner text without resetting animation."""
        self._text = text
        self._render_frame()

    def _animate(self) -> None:
        """Advance the spinner animation."""
        self._frame = (self._frame + 1) % len(SPINNER_FRAMES)
        self._render_frame()

    def _render_frame(self) -> None:
        """Render the current spinner frame."""
        try:
            content = self.query_one("#spinner-content", Static)
            elapsed = time.monotonic() - self._start_time
            frame_char = SPINNER_FRAMES[self._frame]

            text = Text()
            text.append(f"  {frame_char} ", style="bold purple")
            text.append(self._text, style="purple")
            text.append(f"  ({elapsed:.1f}s)", style="dim")

            content.update(text)
        except Exception:
            pass
