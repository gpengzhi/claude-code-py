"""Vim motions.

Maps to src/vim/motions.ts in the TypeScript codebase.
Resolves motion commands (h, l, w, b, e, 0, $, etc.) to cursor positions.
"""

from __future__ import annotations

import re


def word_boundary_forward(text: str, cursor: int) -> int:
    """Move cursor to the start of the next word (w motion)."""
    if cursor >= len(text):
        return cursor
    # Skip current word
    i = cursor
    if text[i].isalnum() or text[i] == '_':
        while i < len(text) and (text[i].isalnum() or text[i] == '_'):
            i += 1
    elif not text[i].isspace():
        while i < len(text) and not text[i].isspace() and not (text[i].isalnum() or text[i] == '_'):
            i += 1
    # Skip whitespace
    while i < len(text) and text[i].isspace():
        i += 1
    return min(i, len(text))


def word_boundary_backward(text: str, cursor: int) -> int:
    """Move cursor to the start of the previous word (b motion)."""
    if cursor <= 0:
        return 0
    i = cursor - 1
    # Skip whitespace
    while i > 0 and text[i].isspace():
        i -= 1
    # Skip word
    if i >= 0 and (text[i].isalnum() or text[i] == '_'):
        while i > 0 and (text[i - 1].isalnum() or text[i - 1] == '_'):
            i -= 1
    elif i >= 0 and not text[i].isspace():
        while i > 0 and not text[i - 1].isspace() and not (text[i - 1].isalnum() or text[i - 1] == '_'):
            i -= 1
    return max(i, 0)


def word_end_forward(text: str, cursor: int) -> int:
    """Move cursor to the end of the current/next word (e motion)."""
    if cursor >= len(text) - 1:
        return max(len(text) - 1, 0)
    i = cursor + 1
    # Skip whitespace
    while i < len(text) and text[i].isspace():
        i += 1
    # Move to end of word
    if i < len(text) and (text[i].isalnum() or text[i] == '_'):
        while i < len(text) - 1 and (text[i + 1].isalnum() or text[i + 1] == '_'):
            i += 1
    elif i < len(text):
        while i < len(text) - 1 and not text[i + 1].isspace() and not (text[i + 1].isalnum() or text[i + 1] == '_'):
            i += 1
    return min(i, max(len(text) - 1, 0))


def find_char_forward(text: str, cursor: int, char: str) -> int | None:
    """Find character forward (f motion). Returns position or None."""
    idx = text.find(char, cursor + 1)
    return idx if idx >= 0 else None


def find_char_backward(text: str, cursor: int, char: str) -> int | None:
    """Find character backward (F motion). Returns position or None."""
    idx = text.rfind(char, 0, cursor)
    return idx if idx >= 0 else None


def resolve_motion(motion: str, text: str, cursor: int, count: int = 1) -> int:
    """Resolve a vim motion to a new cursor position."""
    for _ in range(count):
        if motion == "h":
            cursor = max(cursor - 1, 0)
        elif motion == "l":
            cursor = min(cursor + 1, max(len(text) - 1, 0))
        elif motion == "w":
            cursor = word_boundary_forward(text, cursor)
        elif motion == "b":
            cursor = word_boundary_backward(text, cursor)
        elif motion == "e":
            cursor = word_end_forward(text, cursor)
        elif motion == "0":
            cursor = 0
        elif motion == "^":
            # First non-whitespace character
            match = re.match(r'\s*', text)
            cursor = match.end() if match else 0
        elif motion == "$":
            cursor = max(len(text) - 1, 0)
        else:
            break
    return cursor
