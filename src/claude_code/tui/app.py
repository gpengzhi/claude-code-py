"""Main Textual application.

Maps to the App + REPL screen composition from the TypeScript codebase.
This is the root Textual App that manages the TUI lifecycle.
"""

from __future__ import annotations

from typing import Any

from textual.app import App
from textual.binding import Binding

from claude_code.tool.base import Tool


CSS = """\
Screen {
    background: $surface;
}

#message-container {
    height: 1fr;
    overflow-y: auto;
    padding: 0 1;
}

#input-area {
    dock: bottom;
    height: auto;
    max-height: 40%;
    padding: 0 1;
}

#prompt-text-input {
    width: 1fr;
    height: 1;
    background: #1e1e2e;
    color: #cdd6f4;
    border: none;
}

#prompt-text-input:focus {
    border: none;
    background: #1e1e2e;
    color: #cdd6f4;
}

.prompt-prefix {
    width: auto;
    height: 1;
    padding: 0;
}

#status-bar {
    dock: bottom;
    height: 1;
    background: $primary-background-darken-1;
    color: $text-muted;
    padding: 0 1;
}

#spinner-area {
    dock: bottom;
    height: auto;
    padding: 0 1;
    display: none;
}

#spinner-area.visible {
    display: block;
}

.message-row {
    margin: 0 0 1 0;
}

.user-message {
    color: $text;
}

.assistant-message {
    color: $accent;
}

.tool-use-message {
    color: $warning;
    margin: 0 0 0 2;
}

.tool-result-message {
    color: $text-muted;
    margin: 0 0 0 2;
}

.error-message {
    color: $error;
}

.thinking-message {
    color: $warning;
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
