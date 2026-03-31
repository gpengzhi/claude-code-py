"""Bundled skills -- skills that ship with the CLI.

Maps to src/skills/bundledSkills.ts in the TypeScript codebase.
"""

from __future__ import annotations

from typing import Any

# Registry of bundled skills
_bundled_skills: list[dict[str, Any]] = []


def register_bundled_skill(skill: dict[str, Any]) -> None:
    """Register a bundled skill."""
    _bundled_skills.append(skill)


def get_bundled_skills() -> list[dict[str, Any]]:
    """Get all registered bundled skills."""
    return list(_bundled_skills)


def init_bundled_skills() -> None:
    """Initialize built-in bundled skills."""
    # These are simplified versions of Claude Code's bundled skills

    register_bundled_skill({
        "name": "commit",
        "description": "Create a git commit with a good message",
        "user_invocable": True,
        "body": (
            "Look at the current git diff and staged changes, then create a commit "
            "with a clear, concise message following conventional commit format. "
            "Do not push unless explicitly asked."
        ),
        "source": "bundled",
    })

    register_bundled_skill({
        "name": "review-pr",
        "description": "Review a pull request",
        "user_invocable": True,
        "body": (
            "Review the current PR or the PR specified by the user. "
            "Look at the diff, check for bugs, style issues, and suggest improvements."
        ),
        "source": "bundled",
    })

    register_bundled_skill({
        "name": "simplify",
        "description": "Review changed code for quality and simplify",
        "user_invocable": True,
        "body": (
            "Review the recently changed code for reuse opportunities, quality issues, "
            "and efficiency improvements. Fix any issues found."
        ),
        "source": "bundled",
    })


# Initialize on import
init_bundled_skills()
