"""Configuration system -- multi-source settings.

Maps to src/utils/settings/ in the TypeScript codebase.
Settings are merged from multiple sources in precedence order:
  defaults < global (~/.claude/settings.json) < project (.claude/settings.json) < CLI flags
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Config directory
CLAUDE_DIR_NAME = ".claude"
SETTINGS_FILE = "settings.json"
LOCAL_SETTINGS_FILE = "settings.local.json"


def get_claude_home() -> Path:
    """Get the global Claude config directory (~/.claude)."""
    return Path.home() / CLAUDE_DIR_NAME


def get_project_claude_dir(project_root: Path | None = None) -> Path:
    """Get the project-level .claude directory."""
    root = project_root or Path.cwd()
    return root / CLAUDE_DIR_NAME


def ensure_claude_home() -> Path:
    """Ensure ~/.claude exists and return its path."""
    claude_home = get_claude_home()
    claude_home.mkdir(parents=True, exist_ok=True)
    return claude_home


def _read_json_file(path: Path) -> dict[str, Any]:
    """Read a JSON file, returning empty dict on any error."""
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to read %s: %s", path, e)
    return {}


def _write_json_file(path: Path, data: dict[str, Any]) -> None:
    """Write a JSON file, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def get_global_settings() -> dict[str, Any]:
    """Read global settings from ~/.claude/settings.json."""
    return _read_json_file(get_claude_home() / SETTINGS_FILE)


def get_project_settings(project_root: Path | None = None) -> dict[str, Any]:
    """Read project settings from .claude/settings.json."""
    return _read_json_file(get_project_claude_dir(project_root) / SETTINGS_FILE)


def get_local_settings(project_root: Path | None = None) -> dict[str, Any]:
    """Read local settings from .claude/settings.local.json (gitignored)."""
    return _read_json_file(get_project_claude_dir(project_root) / LOCAL_SETTINGS_FILE)


def get_merged_settings(project_root: Path | None = None) -> dict[str, Any]:
    """Get settings merged from all sources (lowest to highest precedence)."""
    settings: dict[str, Any] = {}

    # 1. Global settings (lowest precedence)
    settings.update(get_global_settings())

    # 2. Project settings
    settings.update(get_project_settings(project_root))

    # 3. Local settings (gitignored, overrides project)
    settings.update(get_local_settings(project_root))

    # 4. Environment variable overrides
    if os.environ.get("CLAUDE_MODEL"):
        settings["model"] = os.environ["CLAUDE_MODEL"]

    return settings


def update_global_settings(updates: dict[str, Any]) -> None:
    """Update global settings (~/.claude/settings.json)."""
    settings = get_global_settings()
    settings.update(updates)
    _write_json_file(get_claude_home() / SETTINGS_FILE, settings)


def update_project_settings(
    updates: dict[str, Any],
    project_root: Path | None = None,
) -> None:
    """Update project settings (.claude/settings.json)."""
    settings = get_project_settings(project_root)
    settings.update(updates)
    _write_json_file(get_project_claude_dir(project_root) / SETTINGS_FILE, settings)


# Permission rules from settings
def get_permission_rules(
    settings: dict[str, Any],
) -> dict[str, list[dict[str, str]]]:
    """Extract permission rules from settings."""
    return {
        "allow": settings.get("permissions", {}).get("allow", []),
        "deny": settings.get("permissions", {}).get("deny", []),
        "ask": settings.get("permissions", {}).get("ask", []),
    }


# Hook configuration from settings
def get_hooks_config(settings: dict[str, Any]) -> dict[str, Any]:
    """Extract hooks configuration from settings."""
    return settings.get("hooks", {})
