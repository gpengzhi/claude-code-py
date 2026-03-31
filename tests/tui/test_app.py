"""Tests for the TUI application."""

import pytest

from claude_code.tui.app import ClaudeCodeApp
from claude_code.tui.widgets.message_list import MessageList
from claude_code.tui.widgets.status_bar import StatusBar


class TestClaudeCodeApp:
    @pytest.mark.asyncio
    async def test_app_creates(self) -> None:
        """Test that the app can be created."""
        app = ClaudeCodeApp(model="test-model")
        assert app._model == "test-model"

    @pytest.mark.asyncio
    async def test_app_composes(self) -> None:
        """Test that the app composes correctly via Textual pilot."""
        app = ClaudeCodeApp(model="test-model")

        async with app.run_test() as pilot:
            # The REPL screen should be pushed and have key widgets
            screen = app.screen
            assert screen is not None

            # Check key widgets exist on the screen
            message_list = screen.query("MessageList")
            assert len(message_list) > 0

            status_bar = screen.query("StatusBar")
            assert len(status_bar) > 0


class TestMessageList:
    @pytest.mark.asyncio
    async def test_add_user_message(self) -> None:
        """Test adding a user message."""
        app = ClaudeCodeApp(model="test-model")

        async with app.run_test() as pilot:
            ml = app.screen.query_one(MessageList)
            ml.add_user_message("Hello world")
            # Should have at least 2 children (welcome + user message)
            assert len(ml.children) >= 2

    @pytest.mark.asyncio
    async def test_add_assistant_text(self) -> None:
        """Test adding an assistant message."""
        app = ClaudeCodeApp(model="test-model")

        async with app.run_test() as pilot:
            ml = app.screen.query_one(MessageList)
            ml.add_assistant_text("Hello from Claude")
            assert len(ml.children) >= 2

    @pytest.mark.asyncio
    async def test_add_tool_use(self) -> None:
        """Test adding a tool use indicator."""
        app = ClaudeCodeApp(model="test-model")

        async with app.run_test() as pilot:
            ml = app.screen.query_one(MessageList)
            ml.add_tool_use("Bash", {"command": "echo hello"})
            assert len(ml.children) >= 2


class TestStatusBar:
    @pytest.mark.asyncio
    async def test_update_stats(self) -> None:
        """Test updating status bar."""
        app = ClaudeCodeApp(model="test-model")

        async with app.run_test() as pilot:
            sb = app.screen.query_one(StatusBar)
            sb.update_stats(model="claude-opus", cost_usd=0.05, turn_count=3)
            assert sb.model == "claude-opus"
            assert sb.cost_usd == 0.05
            assert sb.turn_count == 3
