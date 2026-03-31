"""Tests for hooks, commands, and auto-compact."""

import pytest
from pathlib import Path
from typing import Any

from claude_code.hooks.events import HookEvent
from claude_code.hooks.config import HookMatcher, parse_hooks_config
from claude_code.hooks.runner import HookResult, run_hooks_for_event
from claude_code.commands.registry import (
    get_command,
    get_all_commands,
    cmd_help,
    cmd_doctor,
    cmd_init,
    cmd_clear,
    CommandResult,
)
from claude_code.services.compact.compact import (
    estimate_tokens,
    should_auto_compact,
    AutoCompactTracker,
)


# --- Hook Config ---

class TestHookConfig:
    def test_parse_empty_config(self) -> None:
        result = parse_hooks_config({})
        assert result == {}

    def test_parse_hooks_config(self) -> None:
        settings = {
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash(git *)",
                        "hooks": [{"type": "command", "command": "echo allowed"}],
                    }
                ]
            }
        }
        result = parse_hooks_config(settings)
        assert HookEvent.PRE_TOOL_USE in result
        assert len(result[HookEvent.PRE_TOOL_USE]) == 1

    def test_hook_matcher_matches(self) -> None:
        matcher = HookMatcher(matcher="Bash(git *)", hooks=[])
        assert matcher.matches_tool("Bash", {"command": "git status"})
        assert not matcher.matches_tool("Bash", {"command": "rm -rf /"})
        assert not matcher.matches_tool("Read", {"file_path": "/tmp/x"})

    def test_hook_matcher_no_pattern(self) -> None:
        matcher = HookMatcher(matcher=None, hooks=[])
        assert matcher.matches_tool("Bash", {})
        assert matcher.matches_tool("Read", {})

    def test_hook_matcher_tool_only(self) -> None:
        matcher = HookMatcher(matcher="Bash", hooks=[])
        assert matcher.matches_tool("Bash", {"command": "anything"})
        assert not matcher.matches_tool("Read", {})


# --- Hook Runner ---

class TestHookRunner:
    @pytest.mark.asyncio
    async def test_run_hooks_empty(self) -> None:
        results = await run_hooks_for_event(
            HookEvent.PRE_TOOL_USE, {}, "Bash", {"command": "ls"}
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_run_command_hook(self) -> None:
        config = {
            HookEvent.PRE_TOOL_USE: [
                HookMatcher(
                    matcher=None,
                    hooks=[{"type": "command", "command": "echo ok"}],
                )
            ]
        }
        results = await run_hooks_for_event(
            HookEvent.PRE_TOOL_USE, config, "Bash", {"command": "ls"}
        )
        assert len(results) == 1
        assert results[0].outcome == "success"

    @pytest.mark.asyncio
    async def test_run_blocking_hook(self) -> None:
        config = {
            HookEvent.PRE_TOOL_USE: [
                HookMatcher(
                    matcher=None,
                    hooks=[{"type": "command", "command": "exit 1"}],
                )
            ]
        }
        results = await run_hooks_for_event(
            HookEvent.PRE_TOOL_USE, config, "Bash", {"command": "rm -rf /"}
        )
        assert len(results) == 1
        assert results[0].is_blocking


# --- Commands ---

class TestCommands:
    def test_get_all_commands(self) -> None:
        cmds = get_all_commands()
        names = [c.name for c in cmds]
        assert "help" in names
        assert "clear" in names
        assert "cost" in names
        assert "model" in names
        assert "compact" in names
        assert "doctor" in names
        assert "quit" in names

    def test_get_command(self) -> None:
        assert get_command("help") is not None
        assert get_command("h") is not None  # alias
        assert get_command("nonexistent") is None

    @pytest.mark.asyncio
    async def test_cmd_help(self) -> None:
        result = await cmd_help()
        assert "Available commands" in result.message
        assert "/help" in result.message

    @pytest.mark.asyncio
    async def test_cmd_doctor(self) -> None:
        result = await cmd_doctor()
        assert "diagnostics" in result.message
        assert "Python" in result.message

    @pytest.mark.asyncio
    async def test_cmd_clear(self) -> None:
        result = await cmd_clear()
        assert "cleared" in result.message.lower()

    @pytest.mark.asyncio
    async def test_cmd_init_already_exists(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "CLAUDE.md").write_text("existing")
        result = await cmd_init()
        assert "already exists" in result.message


# --- Auto-Compact ---

class TestAutoCompact:
    def test_estimate_tokens(self) -> None:
        messages = [
            {"role": "user", "content": "hello " * 100},  # ~600 chars = ~150 tokens
        ]
        tokens = estimate_tokens(messages)
        assert tokens > 100
        assert tokens < 200

    def test_should_not_compact_small(self) -> None:
        messages = [{"role": "user", "content": "hi"}]
        assert not should_auto_compact(messages)

    def test_should_compact_large(self) -> None:
        # Create a large conversation
        messages = [
            {"role": "user", "content": "x" * 100_000}
            for _ in range(10)
        ]
        assert should_auto_compact(messages, context_window=200_000)

    def test_auto_compact_tracker(self) -> None:
        tracker = AutoCompactTracker(context_window=1000)
        small = [{"role": "user", "content": "hi"}]
        assert not tracker.should_compact(small)

        large = [{"role": "user", "content": "x" * 5000}]
        assert tracker.should_compact(large)
