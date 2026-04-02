"""Permission types.

Maps to src/types/permissions.ts in the TypeScript codebase.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# Permission modes
ExternalPermissionMode = Literal[
    "acceptEdits", "bypassPermissions", "default", "dontAsk", "plan"
]
InternalPermissionMode = Literal[
    "acceptEdits", "bypassPermissions", "default", "dontAsk", "plan", "auto", "bubble"
]
PermissionMode = InternalPermissionMode

PermissionBehavior = Literal["allow", "deny", "ask"]
RiskLevel = Literal["LOW", "MEDIUM", "HIGH"]

PermissionRuleSource = Literal[
    "userSettings",
    "projectSettings",
    "localSettings",
    "flagSettings",
    "policySettings",
    "cliArg",
    "command",
    "session",
]

PermissionUpdateDestination = Literal[
    "userSettings", "projectSettings", "localSettings", "session", "cliArg"
]


class PermissionRuleValue(BaseModel):
    tool_name: str
    rule_content: str | None = None



# Permission decisions
class PermissionAllowDecision(BaseModel):
    behavior: Literal["allow"] = "allow"
    updated_input: Any | None = None
    user_modified: bool | None = None
    decision_reason: Any | None = None
    tool_use_id: str | None = None


class PermissionAskDecision(BaseModel):
    behavior: Literal["ask"] = "ask"
    message: str = ""
    updated_input: Any | None = None
    decision_reason: Any | None = None
    suggestions: list[Any] = Field(default_factory=list)


class PermissionDenyDecision(BaseModel):
    behavior: Literal["deny"] = "deny"
    message: str = ""
    decision_reason: Any | None = None
    tool_use_id: str | None = None


class PermissionPassthroughResult(BaseModel):
    behavior: Literal["passthrough"] = "passthrough"
    message: str = ""
    decision_reason: Any | None = None


PermissionDecision = PermissionAllowDecision | PermissionAskDecision | PermissionDenyDecision
PermissionResult = PermissionDecision | PermissionPassthroughResult

# Permission rules by source
ToolPermissionRulesBySource = dict[PermissionRuleSource, list[PermissionRuleValue]]


class AdditionalWorkingDirectory(BaseModel):
    path: str
    source: PermissionRuleSource


class ToolPermissionContext(BaseModel, frozen=True):
    """Central permission gate for tool execution."""

    mode: PermissionMode = "default"
    additional_working_directories: dict[str, AdditionalWorkingDirectory] = Field(
        default_factory=dict
    )
    always_allow_rules: ToolPermissionRulesBySource = Field(default_factory=dict)
    always_deny_rules: ToolPermissionRulesBySource = Field(default_factory=dict)
    always_ask_rules: ToolPermissionRulesBySource = Field(default_factory=dict)
    is_bypass_permissions_mode_available: bool = False
    should_avoid_permission_prompts: bool | None = None
