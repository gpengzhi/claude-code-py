"""REPL screen -- main interactive conversation screen.

Maps to src/screens/REPL.tsx in the TypeScript codebase.
This is the central hub that connects the query engine to the TUI widgets.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from textual.app import ComposeResult
from textual.screen import Screen
from textual.css.query import NoMatches

from claude_code.query.engine import QueryEngine
from claude_code.tool.base import Tool
from claude_code.tool.registry import get_tools
from claude_code.tui.widgets.message_list import MessageList
from claude_code.tui.widgets.prompt_input import PromptInput, PromptSubmitted
from claude_code.tui.widgets.spinner import Spinner
from claude_code.tui.widgets.status_bar import StatusBar
from claude_code.types.message import AssistantMessage, TextBlock, ThinkingBlock, ToolUseBlock
from claude_code.utils.session_storage import generate_session_id, save_message, load_session

logger = logging.getLogger(__name__)


class REPLScreen(Screen):
    """The main interactive REPL screen."""

    AUTO_FOCUS = "#prompt-text-input"

    def __init__(
        self,
        model: str,
        system_prompt: str = "",
        max_tokens: int = 16384,
        tools: list[Tool] | None = None,
        hooks_config: dict | None = None,
        permission_mode: str = "default",
        resume_session: str | None = None,
        thinking: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._tools = tools or get_tools()
        self._permission_mode = permission_mode
        self._session_id = resume_session or generate_session_id()

        # Permission callback that routes through the TUI dialog
        async def _permission_callback(
            tool_name: str, tool_input: dict[str, Any], message: str,
        ) -> bool:
            return await self._ask_permission(tool_name, tool_input, message)

        self._engine = QueryEngine(
            model=model,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            tools=self._tools,
            hooks_config=hooks_config,
            permission_callback=_permission_callback,
            thinking=thinking,
        )
        self._is_querying = False
        self._streaming_text = ""
        self._current_task: asyncio.Task | None = None

        # Resume previous session if requested
        if resume_session:
            prev_messages = load_session(resume_session)
            for msg in prev_messages:
                msg.pop("sessionId", None)
                msg.pop("timestamp", None)
                self._engine.messages.append(msg)

    def compose(self) -> ComposeResult:
        yield MessageList(id="message-container")
        yield Spinner(id="spinner-area")
        yield PromptInput(id="input-area")
        yield StatusBar(id="status-bar")

    def on_mount(self) -> None:
        try:
            status = self.query_one("#status-bar", StatusBar)
            status.update_stats(model=self._engine.model)
            logger.info("Session ID: %s", self._session_id)
        except NoMatches:
            pass

    async def _ask_permission(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        message: str,
    ) -> bool:
        """Show permission dialog and wait for user response."""
        from claude_code.tui.widgets.permission_dialog import PermissionDialog

        dialog = PermissionDialog(
            tool_name=tool_name,
            tool_input=tool_input,
            message=message,
        )
        result = await self.app.push_screen_wait(dialog)
        return bool(result)

    async def on_prompt_submitted(self, event: PromptSubmitted) -> None:
        """Handle user prompt submission."""
        text = event.text

        # Handle slash commands
        if text.startswith("/"):
            await self._handle_slash_command(text)
            return

        if self._is_querying:
            return

        # Show user message and persist
        messages = self.query_one("#message-container", MessageList)
        messages.add_user_message(text)
        save_message(self._session_id, {"role": "user", "content": text})

        self._set_querying(True)
        self._current_task = asyncio.create_task(self._run_query(text))

    async def _run_query(self, prompt: str) -> None:
        """Run the query engine and update the UI with results."""
        messages = self.query_one("#message-container", MessageList)
        spinner = self.query_one("#spinner-area", Spinner)

        spinner.show("Thinking...")
        self._streaming_text = ""

        try:
            async for event in self._engine.submit_message(prompt):
                if isinstance(event, AssistantMessage):
                    if self._streaming_text:
                        messages.finish_streaming()
                        self._streaming_text = ""

                    # Persist assistant message
                    save_message(self._session_id, event.model_dump(exclude_none=True))

                    for block in event.content:
                        if isinstance(block, ToolUseBlock):
                            messages.add_tool_use(block.name, block.input)
                        elif isinstance(block, ThinkingBlock):
                            messages.add_thinking(block.thinking)

                elif isinstance(event, dict):
                    event_type = event.get("type")

                    if event_type == "stream_event" and event.get("event_type") == "text_delta":
                        delta = event.get("text", "")
                        if not self._streaming_text:
                            messages.start_streaming()
                        self._streaming_text += delta
                        messages.update_streaming(self._streaming_text)

                    elif event_type == "tool_result_display":
                        spinner.update_text(f"Running {event.get('tool_name', 'tool')}...")
                        messages.add_tool_result(
                            event.get("tool_use_id", ""),
                            str(event.get("content", "")),
                            event.get("is_error", False),
                        )

                    elif event_type == "tool_results":
                        turn = event.get("turn", 0)
                        count = event.get("count", 0)
                        spinner.update_text(f"Turn {turn} ({count} tool results)...")

                    elif event_type == "api_error":
                        messages.add_system_message(
                            f"API Error: {event.get('error', 'Unknown')}",
                            level="error",
                        )

        except asyncio.CancelledError:
            messages.add_system_message("Query cancelled.", level="warning")
        except Exception as e:
            logger.error("Query failed: %s", e, exc_info=True)
            messages.add_system_message(f"Error: {e}", level="error")
        finally:
            if self._streaming_text:
                messages.finish_streaming()
                self._streaming_text = ""

            spinner.hide()
            self._set_querying(False)

            try:
                status = self.query_one("#status-bar", StatusBar)
                status.update_stats(
                    cost_usd=self._engine.total_usage.cost_usd,
                    turn_count=self._engine.turn_count,
                )
            except NoMatches:
                pass

    def _set_querying(self, querying: bool) -> None:
        """Update the querying state and enable/disable input."""
        self._is_querying = querying
        try:
            prompt = self.query_one("#input-area", PromptInput)
            prompt.set_disabled(querying)
            if not querying:
                prompt.set_focus()
        except NoMatches:
            pass

    async def _handle_slash_command(self, text: str) -> None:
        """Handle slash commands via the command registry."""
        from claude_code.commands.registry import get_command

        messages = self.query_one("#message-container", MessageList)

        parts = text.strip().split(None, 1)
        cmd_name = parts[0].lstrip("/").lower()
        cmd_args = parts[1] if len(parts) > 1 else ""

        cmd = get_command(cmd_name)
        if cmd is None:
            messages.add_system_message(
                f"Unknown command: /{cmd_name}. Type /help for available commands.",
                level="warning",
            )
            return

        if cmd.handler is None:
            messages.add_system_message(f"Command /{cmd_name} has no handler.", level="error")
            return

        result = await cmd.handler(engine=self._engine, args=cmd_args)

        if result.message == "__quit__":
            self.app.exit()
            return

        if cmd_name == "clear":
            for child in list(messages.children):
                child.remove()

        if result.message:
            messages.add_system_message(result.message, level=result.level)

        if result.should_query and result.query_text:
            self._set_querying(True)
            self._current_task = asyncio.create_task(
                self._run_query(result.query_text)
            )

    def cancel_query(self) -> None:
        """Cancel the current query."""
        if self._current_task and not self._current_task.done():
            self._engine.abort()
            self._current_task.cancel()
