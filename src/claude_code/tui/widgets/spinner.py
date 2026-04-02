"""Spinner widget -- activity indicator during model calls.

"""

from __future__ import annotations

import time

from textual.widget import Widget
from textual.widgets import Static

from rich.text import Text


SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class Spinner(Widget):
    """Animated spinner with real-time elapsed time."""

    DEFAULT_CSS = """
    Spinner {
        height: auto;
        display: none;
    }
    Spinner.visible {
        display: block;
    }
    """

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._text = "Thinking..."
        self._frame = 0
        self._start_time: float = 0.0
        self._timer = None
        self._visible = False

    def compose(self):
        yield Static("", id="spinner-content")

    def show(self, text: str = "Thinking...") -> None:
        """Show the spinner with given text."""
        self._text = text
        self._start_time = time.monotonic()
        self._frame = 0
        if not self._visible:
            self._visible = True
            self.add_class("visible")
            # Single timer — 200ms is fast enough for smooth display
            # and slow enough to not overwhelm Textual's refresh
            self._timer = self.set_interval(0.2, self._animate)

    def hide(self) -> None:
        """Hide the spinner."""
        if self._visible:
            self._visible = False
            self.remove_class("visible")
            if self._timer:
                self._timer.stop()
                self._timer = None

    def update_text(self, text: str) -> None:
        """Update the spinner text without resetting timer."""
        self._text = text
        self._render_frame()

    def _animate(self) -> None:
        """Advance the spinner animation and force screen refresh."""
        self._frame = (self._frame + 1) % len(SPINNER_FRAMES)
        self._render_frame()
        self.refresh()

    def _render_frame(self) -> None:
        """Render the current spinner frame with elapsed time."""
        try:
            content = self.query_one("#spinner-content", Static)
            elapsed = time.monotonic() - self._start_time
            frame_char = SPINNER_FRAMES[self._frame]

            text = Text()
            text.append(f"  {frame_char} ", style="bold #cba6f7")
            text.append(self._text, style="#cba6f7")
            text.append(f"  ({elapsed:.1f}s)", style="#6c7086")

            content.update(text)
        except Exception:
            pass
