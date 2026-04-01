"""Permission checking -- the full permission pipeline.

Maps to src/utils/permissions/permissions.ts in the TypeScript codebase.
Implements rule matching, mode-based behavior, and permission resolution.
"""

from __future__ import annotations

import fnmatch
import logging
from typing import Any

from claude_code.types.permissions import (
    PermissionAllowDecision,
    PermissionAskDecision,
    PermissionDenyDecision,
    PermissionMode,
    PermissionResult,
    PermissionRuleValue,
    ToolPermissionContext,
    ToolPermissionRulesBySource,
)

logger = logging.getLogger(__name__)


def match_rule_pattern(pattern: str, value: str) -> bool:
    """Match a permission rule pattern against a value.

    Patterns use fnmatch-style wildcards:
    - "Read(*)" matches Read with any argument
    - "Bash(git *)" matches Bash with commands starting with "git "
    - "Edit(/home/user/*)" matches Edit on files under /home/user/
    """
    return fnmatch.fnmatch(value, pattern)


def match_tool_rule(
    rule: PermissionRuleValue,
    tool_name: str,
    tool_input: dict[str, Any],
) -> bool:
    """Check if a permission rule matches a tool invocation."""
    # Rule must match tool name
    if rule.tool_name != tool_name:
        return False

    # If no rule_content, it's a blanket match for this tool
    if not rule.rule_content:
        return True

    # Match rule_content against relevant tool input
    # Format: "ToolName(pattern)" -- the pattern part
    pattern = rule.rule_content

    # Check against common tool input fields
    if "command" in tool_input:
        return match_rule_pattern(pattern, str(tool_input["command"]))
    elif "file_path" in tool_input:
        return match_rule_pattern(pattern, str(tool_input["file_path"]))
    elif "pattern" in tool_input:
        return match_rule_pattern(pattern, str(tool_input["pattern"]))
    elif "url" in tool_input:
        return match_rule_pattern(pattern, str(tool_input["url"]))

    return False


def find_matching_rule(
    rules: ToolPermissionRulesBySource,
    tool_name: str,
    tool_input: dict[str, Any],
) -> PermissionRuleValue | None:
    """Find the first matching rule across all sources."""
    for source_rules in rules.values():
        for rule in source_rules:
            if match_tool_rule(rule, tool_name, tool_input):
                return rule
    return None


def has_permissions_to_use_tool(
    tool_name: str,
    tool_input: dict[str, Any],
    context: ToolPermissionContext,
) -> PermissionResult:
    """Check if a tool use is allowed by the permission system.

    Maps to hasPermissionsToUseTool() in the TS codebase.
    Decision flow:
    1. Check always-deny rules → deny
    2. Check always-allow rules → allow
    3. Check permission mode → mode-specific behavior
    """

    # 1. Always-deny rules (highest priority)
    deny_rule = find_matching_rule(context.always_deny_rules, tool_name, tool_input)
    if deny_rule:
        return PermissionDenyDecision(
            message=f"Denied by rule: {deny_rule.tool_name}({deny_rule.rule_content or '*'})",
        )

    # 2. Always-allow rules
    allow_rule = find_matching_rule(context.always_allow_rules, tool_name, tool_input)
    if allow_rule:
        return PermissionAllowDecision(updated_input=tool_input)

    # 3. Mode-based decision
    mode = context.mode

    if mode == "bypassPermissions":
        return PermissionAllowDecision(updated_input=tool_input)

    if mode == "dontAsk":
        return PermissionDenyDecision(message="Permission mode is 'dontAsk'")

    if mode == "acceptEdits":
        # Auto-accept file edits and reads, ask for everything else
        if tool_name in ("Read", "Edit", "Write", "Glob", "Grep", "NotebookEdit"):
            return PermissionAllowDecision(updated_input=tool_input)
        return PermissionAskDecision(
            message=f"Allow {tool_name}?",
        )

    if mode == "plan":
        # Always ask in plan mode
        return PermissionAskDecision(
            message=f"Allow {tool_name}? (plan mode)",
        )

    # Default mode: auto-allow reads and meta-tools, ask for writes and shell
    AUTO_ALLOW_TOOLS = {
        # Read-only tools
        "Read", "Glob", "Grep",
        # Task management (in-memory, no side effects)
        "TaskCreate", "TaskGet", "TaskUpdate", "TaskList",
        # Mode switching and interaction (no side effects)
        "EnterPlanMode", "ExitPlanMode", "AskUserQuestion",
        # Sub-agent and skill execution (delegates to the same permission system)
        "Agent", "Skill",
    }
    if tool_name in AUTO_ALLOW_TOOLS:
        return PermissionAllowDecision(updated_input=tool_input)

    return PermissionAskDecision(
        message=f"Allow {tool_name}?",
    )


def parse_permission_rule_string(rule_str: str) -> PermissionRuleValue:
    """Parse a rule string like 'Bash(git *)' into a PermissionRuleValue.

    Formats:
    - "ToolName" → matches all uses of ToolName
    - "ToolName(*)" → same as above
    - "ToolName(pattern)" → matches ToolName when input matches pattern
    """
    if "(" in rule_str and rule_str.endswith(")"):
        paren_idx = rule_str.index("(")
        tool_name = rule_str[:paren_idx]
        rule_content = rule_str[paren_idx + 1:-1]
        if rule_content == "*":
            rule_content = None  # Blanket match
        return PermissionRuleValue(tool_name=tool_name, rule_content=rule_content)
    else:
        return PermissionRuleValue(tool_name=rule_str, rule_content=None)
