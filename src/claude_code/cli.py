"""CLI entry point.

Maps to src/main.tsx and src/entrypoints/cli.tsx in the TypeScript codebase.
Uses Click for argument parsing (replacing Commander.js).
"""

from __future__ import annotations

import asyncio
import sys

import click

from claude_code import __version__


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
    "--system-prompt",
    default=None,
    help="Custom system prompt.",
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
    system_prompt: str | None,
    verbose: bool,
    prompt: str | None,
) -> None:
    """claude-code-py -- A Python reimplementation of Claude Code."""
    import logging

    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)

    # Resolve model
    resolved_model = model or "claude-sonnet-4-20250514"

    if print_mode or not sys.stdin.isatty():
        # Non-interactive mode
        if prompt is None:
            # Read from stdin
            prompt = sys.stdin.read().strip()
        if not prompt:
            click.echo("Error: No prompt provided. Use -p with a prompt or pipe input.", err=True)
            sys.exit(1)

        asyncio.run(
            _run_print_mode(
                prompt=prompt,
                model=resolved_model,
                max_tokens=max_tokens,
                system_prompt=system_prompt or "",
            )
        )
    else:
        # Interactive TUI mode
        _run_interactive(
            model=resolved_model,
            max_tokens=max_tokens,
            system_prompt=system_prompt or "",
            initial_prompt=prompt,
        )


async def _run_print_mode(
    prompt: str,
    model: str,
    max_tokens: int,
    system_prompt: str,
) -> None:
    """Run in non-interactive print mode with tool support."""
    from pathlib import Path

    from claude_code.context.system_prompt import build_full_context
    from claude_code.memory.memdir import build_memory_prompt
    from claude_code.query.engine import QueryEngine
    from claude_code.tool.registry import get_tools
    from claude_code.types.message import AssistantMessage

    tools = get_tools()
    cwd = Path.cwd()

    # Build system prompt with full context (CLAUDE.md, tools, memory)
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
    )

    # Prepend git context to the first user message if available
    effective_prompt = prompt
    if git_context:
        effective_prompt = f"<system-context>\n{git_context}\n</system-context>\n\n{prompt}"

    try:
        async for event in engine.submit_message(effective_prompt):
            if isinstance(event, dict):
                event_type = event.get("type")
                if event_type == "stream_event" and event.get("event_type") == "text_delta":
                    # Stream text as it arrives
                    sys.stdout.write(event.get("text", ""))
                    sys.stdout.flush()
                elif event_type == "api_error":
                    click.echo(f"\nError: {event.get('error', 'Unknown error')}", err=True)
                    sys.exit(1)
            elif isinstance(event, AssistantMessage):
                # Print any remaining text blocks that weren't streamed
                pass

        # Final newline
        sys.stdout.write("\n")
        sys.stdout.flush()

    except KeyboardInterrupt:
        click.echo("\nInterrupted.", err=True)
        sys.exit(130)
    except Exception as e:
        click.echo(f"\nError: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()


def _run_interactive(
    model: str,
    max_tokens: int,
    system_prompt: str,
    initial_prompt: str | None = None,
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
    )

    try:
        app.run()
    except KeyboardInterrupt:
        pass
