"""Git utilities.

Provides git status, branch info, and other git operations.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


async def run_git(args: list[str], cwd: Path | None = None) -> str | None:
    """Run a git command and return stdout, or None on error."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd) if cwd else None,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
        if proc.returncode == 0:
            return stdout.decode("utf-8", errors="replace").strip()
    except (asyncio.TimeoutError, FileNotFoundError, OSError) as e:
        logger.debug("git command failed: %s", e)
    return None


async def get_git_branch(cwd: Path | None = None) -> str | None:
    """Get the current git branch name."""
    return await run_git(["branch", "--show-current"], cwd)


async def get_git_status(cwd: Path | None = None) -> str | None:
    """Get a brief git status."""
    return await run_git(["status", "--short", "--branch"], cwd)


async def get_git_recent_commits(cwd: Path | None = None, count: int = 5) -> str | None:
    """Get recent commit log (one-line format)."""
    return await run_git(
        ["log", f"-{count}", "--oneline", "--no-decorate"],
        cwd,
    )


async def get_default_branch(cwd: Path | None = None) -> str:
    """Get the default branch (main or master)."""
    # Try to get from remote HEAD
    result = await run_git(["symbolic-ref", "refs/remotes/origin/HEAD", "--short"], cwd)
    if result:
        return result.replace("origin/", "")

    # Fallback: check if main or master exists
    for branch in ("main", "master"):
        check = await run_git(["rev-parse", "--verify", branch], cwd)
        if check:
            return branch

    return "main"


async def get_git_user(cwd: Path | None = None) -> str | None:
    """Get the git user name."""
    return await run_git(["config", "user.name"], cwd)


async def is_git_repo(cwd: Path | None = None) -> bool:
    """Check if the current directory is a git repository."""
    result = await run_git(["rev-parse", "--git-dir"], cwd)
    return result is not None


async def get_git_root(cwd: Path | None = None) -> Path | None:
    """Get the root of the git repository."""
    result = await run_git(["rev-parse", "--show-toplevel"], cwd)
    if result:
        return Path(result)
    return None
