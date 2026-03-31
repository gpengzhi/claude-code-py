"""Memory directory paths.

Maps to src/memdir/paths.ts in the TypeScript codebase.
Resolves memory directory locations based on project root.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)


def sanitize_path_for_dir_name(path: str) -> str:
    """Sanitize a path to be used as a directory name."""
    # Replace path separators and special chars
    sanitized = re.sub(r'[/\\:*?"<>|]', '-', path)
    # Remove leading/trailing dashes
    sanitized = sanitized.strip('-')
    # Collapse multiple dashes
    sanitized = re.sub(r'-+', '-', sanitized)
    return sanitized


def get_memory_base() -> Path:
    """Get the base directory for memory storage (~/.claude)."""
    return Path.home() / ".claude"


def get_memory_dir(project_root: Path | None = None) -> Path:
    """Get the memory directory for a project.

    Memory is stored at: ~/.claude/projects/<sanitized-project-path>/memory/
    All worktrees of the same git repo share one memory directory.
    """
    # Check environment override
    override = os.environ.get("CLAUDE_COWORK_MEMORY_PATH_OVERRIDE")
    if override:
        return Path(override)

    base = get_memory_base()
    if project_root is None:
        project_root = Path.cwd()

    sanitized = sanitize_path_for_dir_name(str(project_root))
    return base / "projects" / sanitized / "memory"


def get_memory_index_path(project_root: Path | None = None) -> Path:
    """Get the MEMORY.md index file path."""
    return get_memory_dir(project_root) / "MEMORY.md"


def ensure_memory_dir(project_root: Path | None = None) -> Path:
    """Ensure the memory directory exists and return its path."""
    mem_dir = get_memory_dir(project_root)
    mem_dir.mkdir(parents=True, exist_ok=True)
    return mem_dir


def is_auto_memory_enabled() -> bool:
    """Check if auto memory is enabled."""
    if os.environ.get("CLAUDE_CODE_DISABLE_AUTO_MEMORY"):
        return False
    if os.environ.get("CLAUDE_CODE_SIMPLE"):
        return False
    return True
