"""User context -- CLAUDE.md file loading.

Loads CLAUDE.md files from the hierarchy: home > project > cwd.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

CLAUDE_MD_FILENAMES = ["CLAUDE.md", "claude.md"]


def find_claude_md_files(cwd: Path) -> list[tuple[str, Path]]:
    """Find all CLAUDE.md files in the hierarchy.

    Returns list of (label, path) tuples, from outermost to innermost:
    1. ~/.claude/CLAUDE.md (user-level)
    2. <git-root>/.claude/CLAUDE.md (project-level)
    3. <cwd>/CLAUDE.md (local)
    """
    found: list[tuple[str, Path]] = []

    # 1. User-level: ~/.claude/CLAUDE.md
    for name in CLAUDE_MD_FILENAMES:
        user_claude = Path.home() / ".claude" / name
        if user_claude.exists():
            found.append(("user", user_claude))
            break

    # 2. Walk up from cwd to find project-level .claude/CLAUDE.md
    current = cwd.resolve()
    home = Path.home().resolve()
    checked: set[Path] = set()

    while current != current.parent and current != home:
        if current in checked:
            break
        checked.add(current)

        for name in CLAUDE_MD_FILENAMES:
            # Check .claude/CLAUDE.md
            project_claude = current / ".claude" / name
            if project_claude.exists() and ("project", project_claude) not in found:
                found.append(("project", project_claude))
                break

            # Check CLAUDE.md in the directory itself
            dir_claude = current / name
            if dir_claude.exists() and ("project", dir_claude) not in found:
                found.append(("project", dir_claude))
                break

        current = current.parent

    return found


def load_user_context(cwd: Path) -> str:
    """Load and combine all CLAUDE.md files into user context.

    Load user context from CLAUDE.md files..
    """
    files = find_claude_md_files(cwd)
    if not files:
        return ""

    parts: list[str] = []
    for label, path in files:
        try:
            content = path.read_text(encoding="utf-8").strip()
            if content:
                parts.append(f"# CLAUDE.md ({label}: {path})\n\n{content}")
        except (OSError, UnicodeDecodeError) as e:
            logger.warning("Failed to read %s: %s", path, e)

    return "\n\n---\n\n".join(parts)
