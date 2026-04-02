"""Main Textual application.

This is the root Textual App that manages the TUI lifecycle.
"""

from __future__ import annotations

from typing import Any

from textual.app import App
from textual.binding import Binding

from claude_code.tool.base import Tool


CSS = """\
Screen {
    background: #1e1e2e;
    layout: vertical;
}

/* Messages fill all available space */
#message-container {
    height: 1fr;
    min-height: 3;
    overflow-y: auto;
    padding: 1 2;
    background: #1e1e2e;
}

/* Spinner sits above input when visible */
#spinner-area {
    height: auto;
    padding: 0 2;
    background: #1e1e2e;
    display: none;
}

#spinner-area.visible {
    display: block;
}

/* Input area pinned to bottom */
#input-area {
    height: auto;
    max-height: 3;
    padding: 0 2;
    background: #1e1e2e;
}

.prompt-prefix {
    width: 2;
    height: 1;
    color: #a6e3a1;
}

#prompt-text-input {
    width: 1fr;
    height: 1;
    background: #1e1e2e;
    color: #cdd6f4;
    border: none;
    padding: 0;
}

#prompt-text-input:focus {
    border: none;
    background: #1e1e2e;
    color: #cdd6f4;
}

/* Status bar at very bottom */
#status-bar {
    height: 1;
    background: #181825;
    color: #6c7086;
    padding: 0 2;
}

/* Message styles */
.message-row {
    margin: 0 0 1 0;
}

.user-message {
    color: #cdd6f4;
}

.assistant-message {
    color: #cdd6f4;
}

.tool-use-message {
    color: #89b4fa;
    margin: 0 0 0 2;
}

.tool-result-message {
    color: #6c7086;
    margin: 0 0 0 2;
}

.error-message {
    color: #f38ba8;
}

.thinking-message {
    color: #f9e2af;
    text-style: italic;
}
"""


class ClaudeCodeApp(App):
    """The main Claude Code Python TUI application."""

    CSS = CSS

    BINDINGS = [
        Binding("ctrl+c", "interrupt", "Interrupt", show=False),
        Binding("ctrl+d", "quit", "Quit", show=False),
        Binding("escape", "escape_key", "Escape", show=False),
    ]

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        system_prompt: str = "",
        max_tokens: int = 16384,
        tools: list[Tool] | None = None,
        initial_prompt: str | None = None,
        hooks_config: dict | None = None,
        permission_mode: str = "default",
        resume_session: str | None = None,
        thinking: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._model = model
        self._system_prompt = system_prompt
        self._max_tokens = max_tokens
        self._tools = tools or []
        self._initial_prompt = initial_prompt
        self._hooks_config = hooks_config
        self._permission_mode = permission_mode
        self._resume_session = resume_session
        self._thinking = thinking

    async def on_mount(self) -> None:
        """Push the REPL screen on mount."""
        from claude_code.tui.screens.repl import REPLScreen

        screen = REPLScreen(
            model=self._model,
            system_prompt=self._system_prompt,
            max_tokens=self._max_tokens,
            tools=self._tools,
            hooks_config=self._hooks_config,
            permission_mode=self._permission_mode,
            resume_session=self._resume_session,
            thinking=self._thinking,
        )
        await self.push_screen(screen)

        # Submit initial prompt if provided
        if self._initial_prompt:
            from claude_code.tui.widgets.prompt_input import PromptSubmitted
            self.set_timer(0.2, lambda: screen.post_message(
                PromptSubmitted(self._initial_prompt)  # type: ignore
            ))

    def action_interrupt(self) -> None:
        """Handle Ctrl+C."""
        screen = self.screen
        if hasattr(screen, "cancel_query"):
            screen.cancel_query()  # type: ignore
        else:
            self.exit()

    def action_escape_key(self) -> None:
        """Handle Escape -- same as interrupt."""
        self.action_interrupt()

    def action_quit(self) -> None:
        """Handle Ctrl+D."""
        self.exit()
