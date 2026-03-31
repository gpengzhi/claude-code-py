"""Authentication helpers.

Maps to OAuth and API key management in the TypeScript codebase.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from claude_code.utils.config import get_claude_home

logger = logging.getLogger(__name__)


def get_api_key_source() -> str:
    """Determine where the API key comes from."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "environment"
    # Check keychain/credential store (platform-specific)
    key_file = get_claude_home() / "api_key"
    if key_file.exists():
        return "file"
    return "none"


def get_api_key() -> str | None:
    """Get the API key from available sources."""
    # 1. Environment variable (highest priority)
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key

    # 2. File-based storage
    key_file = get_claude_home() / "api_key"
    if key_file.exists():
        try:
            return key_file.read_text(encoding="utf-8").strip()
        except OSError:
            pass

    return None


def save_api_key(key: str) -> None:
    """Save API key to file storage."""
    key_file = get_claude_home() / "api_key"
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key_file.write_text(key, encoding="utf-8")
    # Restrict permissions
    key_file.chmod(0o600)


def clear_api_key() -> None:
    """Remove saved API key."""
    key_file = get_claude_home() / "api_key"
    if key_file.exists():
        key_file.unlink()


def is_authenticated() -> bool:
    """Check if we have a valid API key."""
    return get_api_key() is not None
