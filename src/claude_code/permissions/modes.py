"""Permission modes.

Maps to permission mode behavior in the TypeScript codebase.
"""

from __future__ import annotations

from claude_code.types.permissions import PermissionMode

# Mode descriptions for user display
MODE_DESCRIPTIONS: dict[str, str] = {
    "default": "Ask before running write operations",
    "acceptEdits": "Auto-accept file edits, ask for shell commands",
    "bypassPermissions": "Allow all operations without asking (dangerous)",
    "dontAsk": "Deny anything that would prompt (non-interactive)",
    "plan": "Require plan approval before execution",
    "auto": "Use classifier for automated allow/deny",
}


def is_mode_interactive(mode: PermissionMode) -> bool:
    """Check if a mode requires user interaction for some operations."""
    return mode in ("default", "acceptEdits", "plan")


def is_mode_permissive(mode: PermissionMode) -> bool:
    """Check if a mode auto-allows most operations."""
    return mode in ("bypassPermissions", "auto")
