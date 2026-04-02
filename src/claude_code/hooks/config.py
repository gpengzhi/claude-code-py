"""Hook configuration parsing.

Parses hook definitions from settings.json.
"""

from __future__ import annotations

import logging
from typing import Any

from claude_code.hooks.events import HookEvent

logger = logging.getLogger(__name__)


class HookMatcher:
    """A hook with optional tool matcher pattern."""

    def __init__(
        self,
        matcher: str | None,
        hooks: list[dict[str, Any]],
    ) -> None:
        self.matcher = matcher  # e.g., "Bash(git *)" or None for all
        self.hooks = hooks

    def matches_tool(self, tool_name: str, tool_input: dict[str, Any]) -> bool:
        """Check if this matcher applies to a given tool use."""
        if self.matcher is None:
            return True

        # Parse matcher: "ToolName" or "ToolName(pattern)"
        if "(" in self.matcher:
            name_part = self.matcher[:self.matcher.index("(")]
            pattern_part = self.matcher[self.matcher.index("(") + 1:].rstrip(")")
        else:
            name_part = self.matcher
            pattern_part = None

        if name_part != tool_name:
            return False

        if pattern_part is None:
            return True

        # Match pattern against tool input (simplified: check command field)
        command = tool_input.get("command", "")
        if isinstance(command, str):
            return _wildcard_match(pattern_part, command)
        return True


def _wildcard_match(pattern: str, text: str) -> bool:
    """Simple wildcard matching (* matches any characters)."""
    import fnmatch
    return fnmatch.fnmatch(text, pattern)


def parse_hooks_config(settings: dict[str, Any]) -> dict[HookEvent, list[HookMatcher]]:
    """Parse hooks configuration from settings.

    Settings format:
    {
        "hooks": {
            "PreToolUse": [
                { "matcher": "Bash(git *)", "hooks": [{"type": "command", "command": "..."}] }
            ]
        }
    }
    """
    hooks_config: dict[HookEvent, list[HookMatcher]] = {}
    raw_hooks = settings.get("hooks", {})

    for event_name, matchers in raw_hooks.items():
        try:
            event = HookEvent(event_name)
        except ValueError:
            logger.warning("Unknown hook event: %s", event_name)
            continue

        hook_matchers: list[HookMatcher] = []
        if isinstance(matchers, list):
            for matcher_def in matchers:
                if isinstance(matcher_def, dict):
                    hook_matchers.append(
                        HookMatcher(
                            matcher=matcher_def.get("matcher"),
                            hooks=matcher_def.get("hooks", []),
                        )
                    )
        hooks_config[event] = hook_matchers

    return hooks_config
