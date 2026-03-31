"""Built-in plugins -- plugins that ship with the CLI.

Maps to src/plugins/builtinPlugins.ts in the TypeScript codebase.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_BUILTIN_PLUGINS: dict[str, dict[str, Any]] = {}


@dataclass
class BuiltinPluginDef:
    """Definition of a built-in plugin."""
    name: str
    description: str
    default_enabled: bool = True
    skills: list[dict[str, Any]] | None = None
    hooks: dict[str, Any] | None = None


def register_builtin_plugin(definition: BuiltinPluginDef) -> None:
    """Register a built-in plugin."""
    _BUILTIN_PLUGINS[definition.name] = {
        "name": definition.name,
        "description": definition.description,
        "default_enabled": definition.default_enabled,
        "skills": definition.skills,
        "hooks": definition.hooks,
    }


def get_builtin_plugins() -> list[dict[str, Any]]:
    """Get all registered built-in plugins."""
    return list(_BUILTIN_PLUGINS.values())


def is_builtin_plugin_enabled(name: str, user_settings: dict[str, Any] | None = None) -> bool:
    """Check if a built-in plugin is enabled."""
    plugin = _BUILTIN_PLUGINS.get(name)
    if plugin is None:
        return False

    # Check user settings override
    if user_settings:
        disabled = user_settings.get("disabledBuiltinPlugins", [])
        if name in disabled:
            return False

    return plugin.get("default_enabled", True)
