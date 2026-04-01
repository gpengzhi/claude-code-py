"""Diff utilities.

Maps to src/utils/diff.ts in the TypeScript codebase.
Provides structured diff generation for file edits.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Any


@dataclass
class DiffHunk:
    """A single diff hunk."""
    old_start: int = 0
    old_lines: int = 0
    new_start: int = 0
    new_lines: int = 0
    lines: list[str] = field(default_factory=list)


def get_patch_from_contents(
    file_path: str,
    old_content: str,
    new_content: str,
    context_lines: int = 3,
) -> str:
    """Generate a unified diff between two content strings.

    Returns the diff as a string (unified format).
    """
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)

    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
        n=context_lines,
    )

    return "".join(diff)


def get_patch_for_edits(
    file_path: str,
    file_contents: str,
    edits: list[dict[str, Any]],
    context_lines: int = 3,
) -> str:
    """Apply edits and generate a diff.

    edits: list of {old_string, new_string, replace_all?}
    """
    modified = file_contents
    for edit in edits:
        old_str = edit.get("old_string", "")
        new_str = edit.get("new_string", "")
        replace_all = edit.get("replace_all", False)

        if replace_all:
            modified = modified.replace(old_str, new_str)
        else:
            modified = modified.replace(old_str, new_str, 1)

    return get_patch_from_contents(file_path, file_contents, modified, context_lines)


def count_lines_changed(diff_str: str) -> tuple[int, int]:
    """Count added and removed lines in a unified diff.

    Returns (additions, deletions).
    """
    additions = 0
    deletions = 0
    for line in diff_str.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            additions += 1
        elif line.startswith("-") and not line.startswith("---"):
            deletions += 1
    return additions, deletions
