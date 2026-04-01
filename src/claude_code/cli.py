"""CLI entry point.

Maps to src/main.tsx and src/entrypoints/cli.tsx in the TypeScript codebase.
Uses Click for argument parsing (replacing Commander.js).
"""

from __future__ import annotations

import asyncio
import sys

import click

from claude_code import __version__


def _resolve_model(settings: dict) -> str:
    """Resolve the model ID from settings and environment.

    Maps aliases like 'opus[1m]', 'sonnet', 'haiku' to actual model IDs
    using ANTHROPIC_DEFAULT_*_MODEL env vars (matching TS behavior).
    """
    import os

    model_str = settings.get("model", "")

    # Map aliases to env-var-based model IDs (matching TS getDefaultModel)
    alias_map = {
        "opus": os.environ.get("ANTHROPIC_DEFAULT_OPUS_MODEL", "claude-opus-4-20250514"),
        "sonnet": os.environ.get("ANTHROPIC_DEFAULT_SONNET_MODEL", "claude-sonnet-4-20250514"),
        "haiku": os.environ.get("ANTHROPIC_DEFAULT_HAIKU_MODEL", "claude-haiku-4-5-20251001"),
    }

    if model_str:
        # Check for alias match (e.g., "opus[1m]" contains "opus")
        model_lower = model_str.lower()
        for alias, resolved in alias_map.items():
            if alias in model_lower:
                return resolved
        # Not an alias -- use as-is (could be a full model ID)
        return model_str

    # No model in settings -- use sonnet default
    return alias_map["sonnet"]


@click.command()
@click.version_option(version=__version__, prog_name="claude-code-py")
@click.option(
    "-p",
    "--print",
    "print_mode",
    is_flag=True,
    help="Non-interactive print mode. Sends prompt and prints response.",
)
@click.option(
    "-m",
    "--model",
    default=None,
    help="Model to use (e.g., claude-sonnet-4-20250514, claude-opus-4-20250514).",
)
@click.option(
    "--max-tokens",
    default=16384,
    type=int,
    help="Maximum tokens for model response.",
)
@click.option(
    "--max-turns",
    default=100,
    type=int,
    help="Maximum agentic turns per query.",
)
@click.option(
    "--system-prompt",
    default=None,
    help="Custom system prompt.",
)
@click.option(
    "--permission-mode",
    type=click.Choice(["default", "acceptEdits", "plan", "bypassPermissions", "dontAsk"]),
    default=None,
    help="Permission mode for tool execution.",
)
@click.option(
    "--dangerously-skip-permissions",
    is_flag=True,
    help="Bypass all permission checks (use with caution).",
)
@click.option(
    "--resume",
    "resume_session",
    default=None,
    help="Resume a previous session by ID.",
)
@click.option(
    "--thinking",
    is_flag=True,
    help="Enable extended thinking (interleaved thinking blocks).",
)
@click.option(
    "--verbose",
    is_flag=True,
    help="Enable verbose logging.",
)
@click.argument("prompt", required=False, default=None)
def main(
    print_mode: bool,
    model: str | None,
    max_tokens: int,
    max_turns: int,
    system_prompt: str | None,
    permission_mode: str | None,
    dangerously_skip_permissions: bool,
    resume_session: str | None,
    thinking: bool,
    verbose: bool,
    prompt: str | None,
) -> None:
    """claude-code-py -- Production-quality open-source Claude Code in Python."""
    import logging
    import os

    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)

    # Check for API key early
    if not os.environ.get("ANTHROPIC_API_KEY"):
        click.echo(
            "Error: ANTHROPIC_API_KEY environment variable is not set.\n"
            "  export ANTHROPIC_API_KEY=sk-ant-...\n"
            "See https://console.anthropic.com/ to get an API key.",
            err=True,
        )
        sys.exit(1)

    # Load settings from config files
    from claude_code.utils.config import get_merged_settings, get_hooks_config, get_permission_rules
    settings = get_merged_settings()

    # Apply env overrides from settings (matching TS settings.env behavior)
    env_overrides = settings.get("env", {})
    if isinstance(env_overrides, dict):
        for key, value in env_overrides.items():
            if key not in os.environ:  # Don't override existing env vars
                os.environ[key] = str(value)

    # Resolve model: CLI flag > CLAUDE_MODEL env var > sonnet default
    # We don't read "model" from ~/.claude/settings.json because that's
    # the official Claude Code's config, not ours.
    resolved_model = model or os.environ.get("CLAUDE_MODEL") or _resolve_model({"model": "sonnet"})

    # Resolve permission mode
    resolved_perm_mode = "default"
    if dangerously_skip_permissions:
        resolved_perm_mode = "bypassPermissions"
    elif permission_mode:
        resolved_perm_mode = permission_mode
    elif settings.get("permissionMode"):
        resolved_perm_mode = settings["permissionMode"]

    # Load hooks config from settings
    hooks_config = get_hooks_config(settings) or None

    # Load permission rules from settings
    perm_rules = get_permission_rules(settings)

    # Decide mode: only use print mode if -p flag is explicitly set,
    # or if a prompt argument is given (one-shot). Otherwise launch TUI.
    use_print_mode = print_mode or prompt is not None

    if use_print_mode:
        # Non-interactive mode -- default to accepting all tools since user can't approve
        if resolved_perm_mode == "default":
            resolved_perm_mode = "bypassPermissions"

        if prompt is None:
            prompt = sys.stdin.read().strip()
        if not prompt:
            click.echo("Error: No prompt provided. Use -p with a prompt or pipe input.", err=True)
            sys.exit(1)

        asyncio.run(
            _run_print_mode(
                prompt=prompt,
                model=resolved_model,
                max_tokens=max_tokens,
                max_turns=max_turns,
                system_prompt=system_prompt or "",
                hooks_config=hooks_config,
                permission_mode=resolved_perm_mode,
                perm_rules=perm_rules,
                resume_session=resume_session,
                thinking=thinking,
            )
        )
    else:
        _run_interactive(
            model=resolved_model,
            max_tokens=max_tokens,
            max_turns=max_turns,
            system_prompt=system_prompt or "",
            hooks_config=hooks_config,
            permission_mode=resolved_perm_mode,
            perm_rules=perm_rules,
            initial_prompt=prompt,
            resume_session=resume_session,
            thinking=thinking,
        )


async def _run_print_mode(
    prompt: str,
    model: str,
    max_tokens: int,
    max_turns: int,
    system_prompt: str,
    hooks_config: dict | None,
    permission_mode: str,
    perm_rules: dict,
    resume_session: str | None,
    thinking: bool = False,
) -> None:
    """Run in non-interactive print mode with tool support."""
    from pathlib import Path

    from claude_code.context.system_prompt import build_full_context
    from claude_code.memory.memdir import build_memory_prompt
    from claude_code.query.engine import QueryEngine
    from claude_code.tool.registry import get_tools
    from claude_code.types.message import AssistantMessage, TextBlock

    tools = get_tools()
    cwd = Path.cwd()

    # Build system prompt with full context
    memory_prompt = build_memory_prompt()
    full_system_prompt, git_context = await build_full_context(
        tools=tools,
        cwd=cwd,
        custom_system_prompt=system_prompt if system_prompt else None,
        memory_prompt=memory_prompt,
    )

    engine = QueryEngine(
        model=model,
        system_prompt=full_system_prompt,
        max_tokens=max_tokens,
        tools=tools,
        hooks_config=hooks_config,
        thinking=thinking,
        permission_mode=permission_mode,
    )

    # Resume session if requested
    if resume_session:
        from claude_code.utils.session_storage import load_session
        prev_messages = load_session(resume_session)
        for msg in prev_messages:
            # Strip session metadata before injecting
            msg.pop("sessionId", None)
            msg.pop("timestamp", None)
            engine.messages.append(msg)

    # Prepend git context to the first user message if available
    effective_prompt = prompt
    if git_context:
        effective_prompt = f"<system-context>\n{git_context}\n</system-context>\n\n{prompt}"

    streamed_text = False
    try:
        async for event in engine.submit_message(effective_prompt, max_turns=max_turns):
            if isinstance(event, dict):
                event_type = event.get("type")
                if event_type == "stream_event" and event.get("event_type") == "text_delta":
                    sys.stdout.write(event.get("text", ""))
                    sys.stdout.flush()
                    streamed_text = True
                elif event_type == "api_error":
                    click.echo(f"\nError: {event.get('error', 'Unknown error')}", err=True)
                    sys.exit(1)
            elif isinstance(event, AssistantMessage):
                # Only print text blocks if we didn't already stream them
                if not streamed_text:
                    for block in event.content:
                        if isinstance(block, TextBlock) and block.text:
                            sys.stdout.write(block.text)
                            sys.stdout.flush()
                streamed_text = False  # Reset for next turn

        sys.stdout.write("\n")
        sys.stdout.flush()

        # Print cost summary to stderr
        if engine.total_usage.cost_usd > 0:
            click.echo(
                f"\n[cost: ${engine.total_usage.cost_usd:.4f} | "
                f"in: {engine.total_usage.input_tokens} | "
                f"out: {engine.total_usage.output_tokens} | "
                f"turns: {engine.turn_count}]",
                err=True,
            )

    except KeyboardInterrupt:
        click.echo("\nInterrupted.", err=True)
        sys.exit(130)
    except Exception as e:
        click.echo(f"\nError: {e}", err=True)
        sys.exit(1)


def _run_interactive(
    model: str,
    max_tokens: int,
    max_turns: int,
    system_prompt: str,
    hooks_config: dict | None,
    permission_mode: str,
    perm_rules: dict,
    initial_prompt: str | None = None,
    resume_session: str | None = None,
    thinking: bool = False,
) -> None:
    """Run in interactive TUI mode."""
    import asyncio
    from pathlib import Path

    from claude_code.context.system_prompt import build_full_context
    from claude_code.memory.memdir import build_memory_prompt
    from claude_code.tool.registry import get_tools
    from claude_code.tui.app import ClaudeCodeApp

    tools = get_tools()
    cwd = Path.cwd()

    # Build system prompt synchronously (blocking is fine before TUI starts)
    memory_prompt = build_memory_prompt()
    full_system_prompt, _git_context = asyncio.run(
        build_full_context(
            tools=tools,
            cwd=cwd,
            custom_system_prompt=system_prompt if system_prompt else None,
            memory_prompt=memory_prompt,
        )
    )

    app = ClaudeCodeApp(
        model=model,
        system_prompt=full_system_prompt,
        max_tokens=max_tokens,
        tools=tools,
        initial_prompt=initial_prompt,
        hooks_config=hooks_config,
        permission_mode=permission_mode,
        resume_session=resume_session,
        thinking=thinking,
    )

    try:
        app.run()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
