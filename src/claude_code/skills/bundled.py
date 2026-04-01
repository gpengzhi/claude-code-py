"""Bundled skills -- skills that ship with the CLI."""

from __future__ import annotations

from typing import Any

BUNDLED_SKILLS: list[dict[str, Any]] = [
    {
        "name": "commit",
        "description": "Create a git commit with a good message",
        "user_invocable": True,
        "body": "Look at the current git diff and staged changes, then create a commit with a clear, concise message following conventional commit format. Do not push unless explicitly asked.",
        "source": "bundled",
    },
    {
        "name": "review-pr",
        "description": "Review a pull request",
        "user_invocable": True,
        "body": "Review the current PR or the PR specified by the user. Look at the diff, check for bugs, style issues, and suggest improvements.",
        "source": "bundled",
    },
    {
        "name": "simplify",
        "description": "Review changed code for quality and simplify",
        "user_invocable": True,
        "body": "Review the recently changed code for reuse opportunities, quality issues, and efficiency improvements. Fix any issues found.",
        "source": "bundled",
    },
]


def get_bundled_skills() -> list[dict[str, Any]]:
    """Get all bundled skills."""
    return list(BUNDLED_SKILLS)
