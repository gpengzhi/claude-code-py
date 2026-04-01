"""Shell utilities.

Maps to src/utils/shell/ in the TypeScript codebase.
Provides shell quoting, parsing, and command analysis.
"""

from __future__ import annotations

import os
import platform
import re
import shlex
import shutil
from typing import Any


def get_default_shell() -> str:
    """Get the user's default shell."""
    return os.environ.get("SHELL", "/bin/bash")


def is_powershell_available() -> bool:
    """Check if PowerShell is available."""
    return shutil.which("pwsh") is not None or shutil.which("powershell") is not None


def quote_args(args: list[str]) -> str:
    """Safely quote shell arguments."""
    return " ".join(shlex.quote(arg) for arg in args)


def try_parse_command(command: str) -> list[str] | None:
    """Try to parse a command into tokens using shlex.

    Returns None if parsing fails (unbalanced quotes, etc.)
    """
    try:
        return shlex.split(command)
    except ValueError:
        return None


def get_base_command(command: str) -> str:
    """Extract the base command from a full command string.

    Handles pipes, redirections, and compound commands.
    Returns the first command token.
    """
    # Strip leading env vars (VAR=val cmd ...)
    cmd = command.strip()
    while re.match(r'^[A-Za-z_]\w*=\S+\s', cmd):
        cmd = re.sub(r'^[A-Za-z_]\w*=\S+\s+', '', cmd)

    # Take first token
    tokens = try_parse_command(cmd)
    if tokens:
        return tokens[0]

    # Fallback: split on whitespace
    return cmd.split()[0] if cmd.split() else ""


def has_pipe(command: str) -> bool:
    """Check if command contains a pipe (outside quotes)."""
    try:
        # shlex doesn't handle pipes, so we check manually
        in_single = False
        in_double = False
        for i, c in enumerate(command):
            if c == "'" and not in_double:
                in_single = not in_single
            elif c == '"' and not in_single:
                in_double = not in_double
            elif c == "|" and not in_single and not in_double:
                return True
    except Exception:
        pass
    return False


def has_redirection(command: str) -> bool:
    """Check if command contains redirection (outside quotes)."""
    in_single = False
    in_double = False
    for c in command:
        if c == "'" and not in_double:
            in_single = not in_single
        elif c == '"' and not in_single:
            in_double = not in_double
        elif c in "><" and not in_single and not in_double:
            return True
    return False


def has_command_substitution(command: str) -> bool:
    """Check if command contains command substitution ($() or ``)."""
    in_single = False
    for i, c in enumerate(command):
        if c == "'" and (i == 0 or command[i - 1] != "\\"):
            in_single = not in_single
        if not in_single:
            if c == "`":
                return True
            if c == "$" and i + 1 < len(command) and command[i + 1] == "(":
                return True
    return False


def split_pipe_commands(command: str) -> list[str]:
    """Split a piped command into individual commands."""
    commands: list[str] = []
    current = []
    in_single = False
    in_double = False

    for c in command:
        if c == "'" and not in_double:
            in_single = not in_single
            current.append(c)
        elif c == '"' and not in_single:
            in_double = not in_double
            current.append(c)
        elif c == "|" and not in_single and not in_double:
            commands.append("".join(current).strip())
            current = []
        else:
            current.append(c)

    if current:
        commands.append("".join(current).strip())

    return commands
