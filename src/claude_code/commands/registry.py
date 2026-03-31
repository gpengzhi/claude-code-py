"""Slash command registry.

Maps to src/commands.ts in the TypeScript codebase.
Each command is a simple async function registered by name.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


@dataclass
class Command:
    """A slash command definition."""
    name: str
    description: str
    aliases: list[str] | None = None
    hidden: bool = False
    handler: Callable[..., Awaitable[CommandResult]] | None = None


@dataclass
class CommandResult:
    """Result of running a slash command."""
    message: str = ""
    level: str = "info"  # info, warning, error
    should_query: bool = False  # If True, send message to model
    query_text: str = ""


# Global command registry
_commands: dict[str, Command] = {}


def register_command(cmd: Command) -> None:
    """Register a slash command."""
    _commands[cmd.name] = cmd
    if cmd.aliases:
        for alias in cmd.aliases:
            _commands[alias] = cmd


def get_command(name: str) -> Command | None:
    """Look up a command by name (without the /)."""
    return _commands.get(name)


def get_all_commands() -> list[Command]:
    """Get all unique registered commands (no alias duplicates)."""
    seen: set[str] = set()
    result: list[Command] = []
    for cmd in _commands.values():
        if cmd.name not in seen:
            seen.add(cmd.name)
            result.append(cmd)
    return sorted(result, key=lambda c: c.name)


def _register_builtin_commands() -> None:
    """Register all built-in slash commands."""
    # These are registered on first access
    pass


# --- Built-in command handlers ---

async def cmd_help(**kwargs: Any) -> CommandResult:
    """Show available commands."""
    commands = get_all_commands()
    lines = ["Available commands:"]
    for cmd in commands:
        if not cmd.hidden:
            lines.append(f"  /{cmd.name:<12} {cmd.description}")
    return CommandResult(message="\n".join(lines))


async def cmd_clear(**kwargs: Any) -> CommandResult:
    """Clear conversation history."""
    return CommandResult(message="Conversation cleared.", level="info")


async def cmd_cost(**kwargs: Any) -> CommandResult:
    """Show cost and usage."""
    engine = kwargs.get("engine")
    if engine:
        usage = engine.total_usage
        total_tokens = usage.input_tokens + usage.output_tokens
        return CommandResult(
            message=(
                f"Total cost: ${usage.cost_usd:.4f}\n"
                f"Input tokens: {usage.input_tokens:,}\n"
                f"Output tokens: {usage.output_tokens:,}\n"
                f"Cache read: {usage.cache_read_input_tokens:,}\n"
                f"Cache write: {usage.cache_creation_input_tokens:,}\n"
                f"Total tokens: {total_tokens:,}\n"
                f"Turns: {engine.turn_count}"
            )
        )
    return CommandResult(message="No active session.")


async def cmd_model(**kwargs: Any) -> CommandResult:
    """Show or change the model."""
    engine = kwargs.get("engine")
    args = kwargs.get("args", "").strip()
    if args and engine:
        engine.model = args
        return CommandResult(message=f"Model changed to: {args}")
    elif engine:
        return CommandResult(message=f"Current model: {engine.model}")
    return CommandResult(message="No active session.")


async def cmd_compact(**kwargs: Any) -> CommandResult:
    """Compact conversation history."""
    return CommandResult(
        message="Compacting conversation...",
        should_query=True,
        query_text="Please provide a brief summary of our conversation so far, focusing on key decisions and current state.",
    )


async def cmd_init(**kwargs: Any) -> CommandResult:
    """Initialize CLAUDE.md in the current directory."""
    from pathlib import Path
    cwd = Path.cwd()
    claude_md = cwd / "CLAUDE.md"
    if claude_md.exists():
        return CommandResult(
            message=f"CLAUDE.md already exists at {claude_md}",
            level="warning",
        )
    claude_md.write_text(
        "# CLAUDE.md\n\n"
        "## Project Overview\n\n"
        "<!-- Describe your project here -->\n\n"
        "## Coding Guidelines\n\n"
        "<!-- Add coding conventions, style preferences, etc. -->\n\n"
        "## Important Notes\n\n"
        "<!-- Any important context for Claude -->\n",
        encoding="utf-8",
    )
    return CommandResult(message=f"Created {claude_md}")


async def cmd_memory(**kwargs: Any) -> CommandResult:
    """Show memory status."""
    from claude_code.memory.memdir import list_memory_files, load_memory_index
    from claude_code.memory.paths import get_memory_dir

    mem_dir = get_memory_dir()
    index = load_memory_index()
    files = list_memory_files()

    lines = [f"Memory directory: {mem_dir}"]
    lines.append(f"Memory files: {len(files)}")
    if index:
        lines.append(f"\nMEMORY.md:\n{index[:500]}")
    else:
        lines.append("No MEMORY.md index found.")
    return CommandResult(message="\n".join(lines))


async def cmd_config(**kwargs: Any) -> CommandResult:
    """Show current configuration."""
    from claude_code.utils.config import get_merged_settings
    import json
    settings = get_merged_settings()
    if settings:
        return CommandResult(
            message=f"Current settings:\n{json.dumps(settings, indent=2)[:1000]}"
        )
    return CommandResult(message="No settings configured.")


async def cmd_doctor(**kwargs: Any) -> CommandResult:
    """Run diagnostics."""
    import shutil
    from pathlib import Path
    from claude_code.utils.config import get_claude_home

    lines = ["claude-code-py diagnostics:"]

    # Check Python version
    import sys
    lines.append(f"  Python: {sys.version}")

    # Check API key
    import os
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    lines.append(f"  API key: {'set' if has_key else 'NOT SET'}")

    base_url = os.environ.get("ANTHROPIC_BASE_URL")
    if base_url:
        lines.append(f"  Base URL: {base_url}")

    # Check tools
    rg = shutil.which("rg")
    lines.append(f"  ripgrep: {'found' if rg else 'not found (using fallback)'}")
    git = shutil.which("git")
    lines.append(f"  git: {'found' if git else 'not found'}")

    # Check config dirs
    claude_home = get_claude_home()
    lines.append(f"  Config dir: {claude_home} ({'exists' if claude_home.exists() else 'missing'})")

    return CommandResult(message="\n".join(lines))


async def cmd_resume(**kwargs: Any) -> CommandResult:
    """List recent sessions."""
    from claude_code.utils.session_storage import list_sessions
    import datetime

    sessions = list_sessions(limit=10)
    if not sessions:
        return CommandResult(message="No saved sessions found.")

    lines = ["Recent sessions:"]
    for s in sessions:
        dt = datetime.datetime.fromtimestamp(s["date"])
        prompt = s.get("first_prompt", "")[:50]
        lines.append(f"  {s['session_id'][:8]}  {dt:%Y-%m-%d %H:%M}  {prompt}")

    return CommandResult(message="\n".join(lines))


async def cmd_quit(**kwargs: Any) -> CommandResult:
    """Exit the application."""
    return CommandResult(message="__quit__")


# Register all built-in commands
register_command(Command("help", "Show available commands", aliases=["h", "?"], handler=cmd_help))
register_command(Command("clear", "Clear conversation", handler=cmd_clear))
register_command(Command("cost", "Show cost and token usage", handler=cmd_cost))
register_command(Command("model", "Show or change model (/model <name>)", handler=cmd_model))
register_command(Command("compact", "Compact conversation history", handler=cmd_compact))
register_command(Command("init", "Create CLAUDE.md in current directory", handler=cmd_init))
register_command(Command("memory", "Show memory status", aliases=["mem"], handler=cmd_memory))
register_command(Command("config", "Show configuration", handler=cmd_config))
register_command(Command("doctor", "Run diagnostics", handler=cmd_doctor))
register_command(Command("resume", "List recent sessions", handler=cmd_resume))
register_command(Command("quit", "Exit", aliases=["exit", "q"], handler=cmd_quit))
