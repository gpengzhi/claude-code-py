"""Plugin loader -- loads plugins from git repos and local directories.

Maps to src/utils/plugins/pluginLoader.ts in the TypeScript codebase.
Plugins are git repositories containing commands, skills, hooks, and MCP server configs.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from claude_code.utils.config import get_claude_home

logger = logging.getLogger(__name__)

PLUGINS_DIR = "plugins"
PLUGIN_MANIFEST = "plugin.json"


@dataclass
class LoadedPlugin:
    """A loaded plugin with its components."""
    name: str
    path: Path
    source: str  # "marketplace", "local", "builtin"
    enabled: bool = True
    manifest: dict[str, Any] = field(default_factory=dict)
    commands_path: Path | None = None
    skills_path: Path | None = None
    hooks_config: dict[str, Any] | None = None
    mcp_servers: dict[str, Any] | None = None

    @property
    def id(self) -> str:
        return f"{self.name}@{self.source}"


@dataclass
class PluginLoadResult:
    """Result of loading all plugins."""
    enabled: list[LoadedPlugin] = field(default_factory=list)
    disabled: list[LoadedPlugin] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)


def get_plugins_dir() -> Path:
    """Get the plugins installation directory."""
    return get_claude_home() / PLUGINS_DIR


def ensure_plugins_dir() -> Path:
    """Ensure the plugins directory exists."""
    plugins_dir = get_plugins_dir()
    plugins_dir.mkdir(parents=True, exist_ok=True)
    return plugins_dir


def load_plugin_manifest(plugin_dir: Path) -> dict[str, Any] | None:
    """Load a plugin's manifest file (plugin.json)."""
    manifest_path = plugin_dir / PLUGIN_MANIFEST
    if not manifest_path.exists():
        return None
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Failed to read plugin manifest %s: %s", manifest_path, e)
        return None


def load_plugin_from_dir(plugin_dir: Path, source: str = "local") -> LoadedPlugin | None:
    """Load a single plugin from a directory."""
    if not plugin_dir.is_dir():
        return None

    manifest = load_plugin_manifest(plugin_dir) or {}
    name = manifest.get("name", plugin_dir.name)

    plugin = LoadedPlugin(
        name=name,
        path=plugin_dir,
        source=source,
        manifest=manifest,
    )

    # Discover components
    commands_dir = plugin_dir / "commands"
    if commands_dir.is_dir():
        plugin.commands_path = commands_dir

    skills_dir = plugin_dir / "skills"
    if skills_dir.is_dir():
        plugin.skills_path = skills_dir

    hooks_file = plugin_dir / "hooks" / "hooks.json"
    if hooks_file.exists():
        try:
            plugin.hooks_config = json.loads(hooks_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    # MCP servers from manifest
    if "mcpServers" in manifest:
        plugin.mcp_servers = manifest["mcpServers"]

    return plugin


async def install_plugin_from_git(url: str, branch: str | None = None) -> LoadedPlugin | None:
    """Install a plugin from a git repository."""
    plugins_dir = ensure_plugins_dir()

    # Derive name from URL
    name = url.rstrip("/").split("/")[-1]
    if name.endswith(".git"):
        name = name[:-4]

    plugin_dir = plugins_dir / name

    if plugin_dir.exists():
        # Update existing
        logger.info("Updating plugin %s...", name)
        proc = await asyncio.create_subprocess_exec(
            "git", "pull", "--ff-only",
            cwd=str(plugin_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
    else:
        # Clone
        logger.info("Installing plugin %s from %s...", name, url)
        cmd = ["git", "clone", "--depth", "1"]
        if branch:
            cmd.extend(["--branch", branch])
        cmd.extend([url, str(plugin_dir)])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.error("Failed to clone plugin: %s", stderr.decode())
            return None

    return load_plugin_from_dir(plugin_dir, source="marketplace")


def load_all_plugins(settings: dict[str, Any] | None = None) -> PluginLoadResult:
    """Load all installed plugins.

    Reads plugin list from settings and loads each one.
    """
    result = PluginLoadResult()
    plugins_dir = get_plugins_dir()

    if not plugins_dir.exists():
        return result

    # Load from settings
    plugin_configs = (settings or {}).get("plugins", [])
    enabled_names: set[str] = set()

    for config in plugin_configs:
        if isinstance(config, str):
            enabled_names.add(config)
        elif isinstance(config, dict):
            name = config.get("name", "")
            if config.get("enabled", True):
                enabled_names.add(name)

    # Load all plugin directories
    for item in sorted(plugins_dir.iterdir()):
        if not item.is_dir():
            continue
        try:
            plugin = load_plugin_from_dir(item, source="marketplace")
            if plugin:
                if not enabled_names or plugin.name in enabled_names:
                    plugin.enabled = True
                    result.enabled.append(plugin)
                else:
                    plugin.enabled = False
                    result.disabled.append(plugin)
        except Exception as e:
            result.errors.append({
                "type": "generic-error",
                "plugin": item.name,
                "error": str(e),
            })

    return result


def get_plugin_commands(plugins: list[LoadedPlugin]) -> list[dict[str, Any]]:
    """Get all commands from loaded plugins."""
    from claude_code.skills.loader import load_skills_from_dir

    commands: list[dict[str, Any]] = []
    for plugin in plugins:
        if plugin.commands_path:
            skills = load_skills_from_dir(plugin.commands_path)
            for skill in skills:
                skill["source"] = f"plugin:{plugin.name}"
            commands.extend(skills)
        if plugin.skills_path:
            skills = load_skills_from_dir(plugin.skills_path)
            for skill in skills:
                skill["source"] = f"plugin:{plugin.name}"
            commands.extend(skills)
    return commands
