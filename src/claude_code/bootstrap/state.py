"""Global session state singleton.

Maps to src/bootstrap/state.ts in the TypeScript codebase.
Holds all session-scoped state that persists across the application lifecycle.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


@dataclass
class SessionState:
    """Global mutable session state. Singleton instance accessed via module-level functions."""

    cwd: Path = field(default_factory=Path.cwd)
    original_cwd: Path = field(default_factory=Path.cwd)
    project_root: Path = field(default_factory=Path.cwd)
    session_id: str = ""
    is_interactive: bool = True
    client_type: str = "cli"
    entrypoint: str = "cli"
    model: str = ""
    verbose: bool = False

    # Trust
    session_trust_accepted: bool = False

    # Shell
    shell: str = field(default_factory=lambda: os.environ.get("SHELL", "/bin/bash"))


# Module-level singleton
_state = SessionState()


def get_state() -> SessionState:
    """Get the global session state."""
    return _state


def get_cwd() -> Path:
    return _state.cwd


def set_cwd(cwd: Path) -> None:
    _state.cwd = cwd.resolve()


def get_session_id() -> str:
    return _state.session_id


def set_session_id(session_id: str) -> None:
    _state.session_id = session_id


def is_interactive() -> bool:
    return _state.is_interactive


def set_is_interactive(interactive: bool) -> None:
    _state.is_interactive = interactive


def get_project_root() -> Path:
    return _state.project_root


def set_project_root(root: Path) -> None:
    _state.project_root = root.resolve()
