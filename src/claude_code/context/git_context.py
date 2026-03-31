"""Git context -- git status for system prompt.

Maps to src/context.ts getSystemContext() in the TypeScript codebase.
Provides git information (branch, status, recent commits) for the system prompt.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from claude_code.utils.git import (
    get_default_branch,
    get_git_branch,
    get_git_recent_commits,
    get_git_status,
    get_git_user,
    is_git_repo,
)

logger = logging.getLogger(__name__)


async def load_git_context(cwd: Path) -> str:
    """Load git context for the system prompt.

    Returns a formatted string with git info, or empty string if not in a git repo.
    """
    if not await is_git_repo(cwd):
        return ""

    # Fetch git info in parallel
    branch, status, commits, default_branch, user = await asyncio.gather(
        get_git_branch(cwd),
        get_git_status(cwd),
        get_git_recent_commits(cwd),
        get_default_branch(cwd),
        get_git_user(cwd),
        return_exceptions=True,
    )

    parts: list[str] = []
    parts.append("gitStatus: This is the git status at the start of the conversation.")

    if isinstance(branch, str) and branch:
        parts.append(f"\nCurrent branch: {branch}")

    if isinstance(default_branch, str) and default_branch:
        parts.append(f"\nMain branch: {default_branch}")

    if isinstance(user, str) and user:
        parts.append(f"\nGit user: {user}")

    if isinstance(status, str) and status:
        parts.append(f"\nStatus:\n{status}")
    else:
        parts.append("\nStatus:\n(clean)")

    if isinstance(commits, str) and commits:
        parts.append(f"\nRecent commits:\n{commits}")

    return "\n".join(parts)
