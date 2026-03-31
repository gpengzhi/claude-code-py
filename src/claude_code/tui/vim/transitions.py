"""Vim transitions -- the main state machine.

Maps to src/vim/transitions.ts in the TypeScript codebase.
Handles key input and transitions between vim states.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from claude_code.tui.vim.types import VimMode, VimState, CommandType
from claude_code.tui.vim.motions import resolve_motion


@dataclass
class TransitionResult:
    """Result of processing a key in vim mode."""
    state: VimState
    text: str
    handled: bool = True
    submit: bool = False  # True if Enter was pressed in insert mode


def transition(state: VimState, key: str, text: str) -> TransitionResult:
    """Process a key press and return the new state.

    This is the main vim state machine dispatch.
    """
    if state.mode == VimMode.INSERT:
        return _handle_insert(state, key, text)
    elif state.mode == VimMode.NORMAL:
        return _handle_normal(state, key, text)
    return TransitionResult(state=state, text=text, handled=False)


def _handle_insert(state: VimState, key: str, text: str) -> TransitionResult:
    """Handle keys in insert mode."""
    if key == "escape":
        # Switch to normal mode
        new_state = VimState(mode=VimMode.NORMAL, cursor=max(state.cursor - 1, 0))
        return TransitionResult(state=new_state, text=text)

    # In insert mode, most keys are handled by the text input widget
    return TransitionResult(state=state, text=text, handled=False)


def _handle_normal(state: VimState, key: str, text: str) -> TransitionResult:
    """Handle keys in normal mode."""
    new_state = VimState(
        mode=state.mode,
        cursor=state.cursor,
        register=state.register,
        last_find=state.last_find,
        last_find_direction=state.last_find_direction,
    )

    # Count prefix
    if state.command_type == CommandType.IDLE and key.isdigit() and key != "0":
        new_state.command_type = CommandType.COUNT
        new_state.count = int(key)
        return TransitionResult(state=new_state, text=text)

    if state.command_type == CommandType.COUNT and key.isdigit():
        new_state.command_type = CommandType.COUNT
        new_state.count = state.count * 10 + int(key)
        return TransitionResult(state=new_state, text=text)

    count = state.count if state.count > 0 else 1

    # Mode switches
    if key == "i":
        new_state.mode = VimMode.INSERT
        new_state.reset_command()
        return TransitionResult(state=new_state, text=text)

    if key == "a":
        new_state.mode = VimMode.INSERT
        new_state.cursor = min(state.cursor + 1, len(text))
        new_state.reset_command()
        return TransitionResult(state=new_state, text=text)

    if key == "I":
        new_state.mode = VimMode.INSERT
        new_state.cursor = 0
        new_state.reset_command()
        return TransitionResult(state=new_state, text=text)

    if key == "A":
        new_state.mode = VimMode.INSERT
        new_state.cursor = len(text)
        new_state.reset_command()
        return TransitionResult(state=new_state, text=text)

    if key == "o" or key == "O":
        new_state.mode = VimMode.INSERT
        new_state.cursor = len(text)
        new_state.reset_command()
        return TransitionResult(state=new_state, text=text)

    # Motions
    if key in ("h", "l", "w", "b", "e", "0", "^", "$"):
        new_state.cursor = resolve_motion(key, text, state.cursor, count)
        new_state.reset_command()
        return TransitionResult(state=new_state, text=text)

    # Delete
    if key == "x":
        if text and state.cursor < len(text):
            new_text = text[:state.cursor] + text[state.cursor + 1:]
            new_state.cursor = min(state.cursor, max(len(new_text) - 1, 0))
            new_state.reset_command()
            return TransitionResult(state=new_state, text=new_text)
        new_state.reset_command()
        return TransitionResult(state=new_state, text=text)

    # Delete line (dd)
    if key == "d" and state.operator == "d":
        new_state.reset_command()
        return TransitionResult(state=new_state, text="")

    if key == "d":
        new_state.command_type = CommandType.OPERATOR
        new_state.operator = "d"
        return TransitionResult(state=new_state, text=text)

    # Change (cc)
    if key == "c" and state.operator == "c":
        new_state.mode = VimMode.INSERT
        new_state.cursor = 0
        new_state.reset_command()
        return TransitionResult(state=new_state, text="")

    if key == "c":
        new_state.command_type = CommandType.OPERATOR
        new_state.operator = "c"
        return TransitionResult(state=new_state, text=text)

    # Change to end of line (C)
    if key == "C":
        new_text = text[:state.cursor]
        new_state.mode = VimMode.INSERT
        new_state.cursor = len(new_text)
        new_state.reset_command()
        return TransitionResult(state=new_state, text=new_text)

    # Delete to end of line (D)
    if key == "D":
        new_text = text[:state.cursor]
        new_state.cursor = max(len(new_text) - 1, 0)
        new_state.reset_command()
        return TransitionResult(state=new_state, text=new_text)

    # Paste
    if key == "p":
        new_state.reset_command()
        return TransitionResult(state=new_state, text=text)

    # Undo (not implemented in single-line -- just reset)
    if key == "u":
        new_state.reset_command()
        return TransitionResult(state=new_state, text=text)

    # Enter in normal mode submits
    if key == "enter":
        new_state.reset_command()
        return TransitionResult(state=new_state, text=text, submit=True)

    # Unknown key -- reset command state
    new_state.reset_command()
    return TransitionResult(state=new_state, text=text, handled=False)
