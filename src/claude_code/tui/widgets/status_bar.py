"""Status bar widget -- bottom bar showing model, cost, tokens.

Maps to src/components/StatusLine.tsx in the TypeScript codebase.
"""

from __future__ import annotations

from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from rich.text import Text


class StatusBar(Widget):
    """Bottom status bar displaying session info."""

    DEFAULT_CSS = """
    StatusBar {
        height: 1;
        dock: bottom;
        background: $primary-background-darken-1;
        padding: 0 1;
    }
    """

    model: reactive[str] = reactive("claude-sonnet-4-20250514")
    cost_usd: reactive[float] = reactive(0.0)
    turn_count: reactive[int] = reactive(0)
    mode: reactive[str] = reactive("code")

    def compose(self):
        yield Static("", id="status-content")

    def watch_model(self) -> None:
        self._update_display()

    def watch_cost_usd(self) -> None:
        self._update_display()

    def watch_turn_count(self) -> None:
        self._update_display()

    def watch_mode(self) -> None:
        self._update_display()

    def on_mount(self) -> None:
        self._update_display()

    def _update_display(self) -> None:
        try:
            content = self.query_one("#status-content", Static)
            text = Text()

            # Model name (shortened)
            model_short = self.model.split("/")[-1] if "/" in self.model else self.model
            if len(model_short) > 30:
                model_short = model_short[:27] + "..."
            text.append(f" {model_short}", style="bold")

            # Separator
            text.append("  |  ", style="dim")

            # Cost
            text.append(f"${self.cost_usd:.4f}", style="green" if self.cost_usd < 1.0 else "yellow")

            # Separator
            text.append("  |  ", style="dim")

            # Turn count
            text.append(f"{self.turn_count} turns", style="dim")

            # Mode
            if self.mode != "code":
                text.append("  |  ", style="dim")
                text.append(f"[{self.mode}]", style="bold yellow")

            content.update(text)
        except Exception:
            pass

    def update_stats(
        self,
        model: str | None = None,
        cost_usd: float | None = None,
        turn_count: int | None = None,
        mode: str | None = None,
    ) -> None:
        """Update status bar values."""
        if model is not None:
            self.model = model
        if cost_usd is not None:
            self.cost_usd = cost_usd
        if turn_count is not None:
            self.turn_count = turn_count
        if mode is not None:
            self.mode = mode
