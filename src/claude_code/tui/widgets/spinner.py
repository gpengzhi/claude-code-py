"""Spinner widget -- activity indicator with real-time elapsed time.

Inspired by Claude Code's SpinnerAnimationRow which recomputes elapsed
time from Date.now() on every 50ms render cycle.
"""

from __future__ import annotations

import time

from textual.widget import Widget
from textual.widgets import Static

from rich.text import Text


SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


def _format_duration(ms: float) -> str:
    """Format milliseconds into human-readable duration."""
    seconds = int(ms / 1000)
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    secs = seconds % 60
    return f"{minutes}m {secs}s"


class Spinner(Widget):
    """Animated spinner with real-time elapsed time counter.

    Elapsed time is recomputed from wall clock on every render (not stored
    in state), matching Claude Code's approach. The timer fires every 200ms
    to drive re-renders.
    """

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
        self._is_visible = False

    def compose(self):
        yield Static("", id="spinner-content")

    def show(self, text: str = "Thinking...") -> None:
        """Show the spinner. Resets elapsed time."""
        self._text = text
        self._start_time = time.monotonic()
        self._frame = 0
        if not self._is_visible:
            self._is_visible = True
            self.add_class("visible")
        # Always ensure timer is running
        if self._timer is None:
            self._timer = self.set_interval(0.2, self._tick)
        self._render_frame()

    def hide(self) -> None:
        """Hide the spinner and stop the timer."""
        if self._is_visible:
            self._is_visible = False
            self.remove_class("visible")
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

    def update_text(self, text: str) -> None:
        """Update status text without resetting elapsed time."""
        self._text = text
        self._render_frame()

    def _tick(self) -> None:
        """Timer callback — advance animation frame and refresh."""
        if not self._is_visible:
            return
        self._frame = (self._frame + 1) % len(SPINNER_FRAMES)
        self._render_frame()

    def _render_frame(self) -> None:
        """Render spinner with elapsed time recomputed from wall clock."""
        try:
            content = self.query_one("#spinner-content", Static)

            # Elapsed time recomputed from wall clock every render
            elapsed_ms = (time.monotonic() - self._start_time) * 1000
            elapsed_str = _format_duration(elapsed_ms)
            frame_char = SPINNER_FRAMES[self._frame]

            text = Text()
            text.append(f"  {frame_char} ", style="bold #cba6f7")
            text.append(self._text, style="#cba6f7")
            text.append(f"  {elapsed_str}", style="#6c7086")

            content.update(text)
        except Exception:
            pass
