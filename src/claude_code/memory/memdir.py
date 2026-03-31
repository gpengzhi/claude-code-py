"""Memory directory management.

Maps to src/memdir/memdir.ts in the TypeScript codebase.
Manages the persistent file-based memory system.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml

from claude_code.memory.paths import (
    ensure_memory_dir,
    get_memory_dir,
    get_memory_index_path,
    is_auto_memory_enabled,
)

logger = logging.getLogger(__name__)

MAX_INDEX_LINES = 200
MAX_INDEX_BYTES = 25_000


def load_memory_index(project_root: Path | None = None) -> str:
    """Load the MEMORY.md index file content.

    Returns the content truncated to MAX_INDEX_LINES / MAX_INDEX_BYTES.
    """
    index_path = get_memory_index_path(project_root)
    if not index_path.exists():
        return ""

    try:
        content = index_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        logger.warning("Failed to read MEMORY.md: %s", e)
        return ""

    # Truncate
    lines = content.split("\n")
    if len(lines) > MAX_INDEX_LINES:
        lines = lines[:MAX_INDEX_LINES]
        lines.append(f"\n... (truncated at {MAX_INDEX_LINES} lines)")
    content = "\n".join(lines)

    if len(content.encode("utf-8")) > MAX_INDEX_BYTES:
        content = content[:MAX_INDEX_BYTES]
        content += f"\n... (truncated at {MAX_INDEX_BYTES} bytes)"

    return content


def load_memory_file(file_path: Path) -> dict[str, Any] | None:
    """Load a memory file and parse its YAML frontmatter.

    Memory files have the format:
    ---
    name: memory name
    description: one-line description
    type: user|feedback|project|reference
    ---
    Memory content here
    """
    if not file_path.exists():
        return None

    try:
        content = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    # Parse frontmatter
    match = re.match(r'^---\n(.*?)\n---\n(.*)', content, re.DOTALL)
    if not match:
        return {"content": content, "name": file_path.stem, "type": "user"}

    try:
        frontmatter = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        frontmatter = {}

    return {
        "name": frontmatter.get("name", file_path.stem),
        "description": frontmatter.get("description", ""),
        "type": frontmatter.get("type", "user"),
        "content": match.group(2).strip(),
    }


def list_memory_files(project_root: Path | None = None) -> list[Path]:
    """List all memory files (excluding MEMORY.md index)."""
    mem_dir = get_memory_dir(project_root)
    if not mem_dir.exists():
        return []

    files = []
    for path in mem_dir.glob("*.md"):
        if path.name != "MEMORY.md":
            files.append(path)
    return sorted(files)


def build_memory_prompt(project_root: Path | None = None) -> str:
    """Build the memory section of the system prompt.

    Loads MEMORY.md index and injects it into context.
    """
    if not is_auto_memory_enabled():
        return ""

    index_content = load_memory_index(project_root)
    if not index_content:
        return ""

    mem_dir = get_memory_dir(project_root)
    return (
        f"You have a persistent memory system at `{mem_dir}/`.\n"
        f"Current MEMORY.md index:\n\n{index_content}"
    )
