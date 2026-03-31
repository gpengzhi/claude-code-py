"""System prompt builder.

Maps to src/constants/prompts.ts and src/utils/queryContext.ts in the TypeScript codebase.
Assembles the full system prompt from sections: tool descriptions, environment info,
user context (CLAUDE.md), git context, memory, etc.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import platform
import os
from pathlib import Path
from typing import Any

from claude_code.context.git_context import load_git_context
from claude_code.context.user_context import load_user_context
from claude_code.tool.base import Tool

logger = logging.getLogger(__name__)


def get_environment_info(cwd: Path) -> str:
    """Get environment information for the system prompt."""
    parts = [
        f"Working directory: {cwd}",
        f"Platform: {platform.system().lower()}",
        f"Shell: {os.environ.get('SHELL', '/bin/bash')}",
        f"Python: {platform.python_version()}",
    ]
    return "\n".join(parts)


def get_date_info() -> str:
    """Get current date info."""
    now = datetime.datetime.now()
    return f"Today's date is {now.strftime('%Y-%m-%d')}."


def build_tool_descriptions(tools: list[Tool]) -> str:
    """Build the tool descriptions section of the system prompt."""
    if not tools:
        return ""

    parts = ["# Available Tools\n"]
    for tool in tools:
        desc = tool.get_description()
        prompt = tool.get_prompt()
        parts.append(f"## {tool.name}")
        if desc:
            parts.append(desc)
        if prompt:
            parts.append(prompt)
        parts.append("")

    return "\n".join(parts)


async def build_system_prompt(
    tools: list[Tool],
    cwd: Path,
    custom_system_prompt: str | None = None,
    include_tools: bool = True,
    include_context: bool = True,
    memory_prompt: str = "",
) -> str:
    """Build the complete system prompt.

    Maps to getSystemPrompt() + fetchSystemPromptParts() in the TS codebase.
    """
    sections: list[str] = []

    # 1. Core identity
    if custom_system_prompt:
        sections.append(custom_system_prompt)
    else:
        sections.append(
            "You are Claude Code, an interactive agent that helps users with software "
            "engineering tasks. Use the tools available to you to assist the user.\n\n"
            "Keep your responses concise and direct. Focus on what the user asked for."
        )

    # 2. Tool descriptions
    if include_tools and tools:
        sections.append(build_tool_descriptions(tools))

    # 3. Environment info
    sections.append(f"# Environment\n{get_environment_info(cwd)}")

    # 4. Date
    sections.append(get_date_info())

    # 5. User context (CLAUDE.md files) -- loaded synchronously
    if include_context:
        user_ctx = load_user_context(cwd)
        if user_ctx:
            sections.append(f"# User Context\n\n{user_ctx}")

    # 6. Memory
    if memory_prompt:
        sections.append(f"# Memory\n\n{memory_prompt}")

    return "\n\n".join(sections)


async def build_full_context(
    tools: list[Tool],
    cwd: Path,
    custom_system_prompt: str | None = None,
    memory_prompt: str = "",
) -> tuple[str, str]:
    """Build both the system prompt and the system context (git info).

    Returns (system_prompt, system_context).
    System context is prepended to the first user message.
    """
    # Build system prompt and git context in parallel
    system_prompt_task = build_system_prompt(
        tools=tools,
        cwd=cwd,
        custom_system_prompt=custom_system_prompt,
        memory_prompt=memory_prompt,
    )
    git_context_task = load_git_context(cwd)

    system_prompt, git_context = await asyncio.gather(
        system_prompt_task, git_context_task
    )

    return system_prompt, git_context
