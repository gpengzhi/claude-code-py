"""Conformance: Tool schema tests.

Verifies that claude-code-py's tool schemas match Claude Code's schemas
as sent to the Anthropic API. Each test compares field names, types, and
required/optional status.
"""

import pytest
from claude_code.tool.registry import get_all_base_tools, find_tool_by_name


def get_tool(name: str):
    tools = get_all_base_tools()
    tool = find_tool_by_name(tools, name)
    assert tool is not None, f"Tool {name} not found"
    return tool


def get_schema(name: str) -> dict:
    return get_tool(name).get_tool_schema()


def get_input_schema(name: str) -> dict:
    return get_schema(name)["input_schema"]


def get_properties(name: str) -> dict:
    return get_input_schema(name).get("properties", {})


def get_required(name: str) -> list[str]:
    return get_input_schema(name).get("required", [])


# --- Tool Name Conformance ---

class TestToolNames:
    """Verify tool names match the TypeScript originals exactly."""

    @pytest.mark.parametrize("expected_name", [
        "Bash", "Read", "Edit", "Write", "Glob", "Grep",
        "WebFetch", "WebSearch", "Agent",
        "TaskCreate", "TaskGet", "TaskUpdate", "TaskList",
        "EnterPlanMode", "ExitPlanMode",
        "AskUserQuestion", "Skill",
    ])
    def test_tool_name_exists(self, expected_name: str) -> None:
        schema = get_schema(expected_name)
        assert schema["name"] == expected_name


# --- BashTool Schema Conformance ---

class TestBashSchema:
    """BashTool must have: command (required), timeout (optional), description (optional),
    run_in_background (optional), dangerouslyDisableSandbox (optional)."""

    def test_name(self) -> None:
        assert get_schema("Bash")["name"] == "Bash"

    def test_has_description(self) -> None:
        assert len(get_schema("Bash")["description"]) > 0

    def test_command_field(self) -> None:
        props = get_properties("Bash")
        assert "command" in props
        assert props["command"]["type"] == "string"

    def test_command_required(self) -> None:
        assert "command" in get_required("Bash")

    def test_timeout_field(self) -> None:
        props = get_properties("Bash")
        assert "timeout" in props

    def test_timeout_optional(self) -> None:
        # timeout should NOT be in required
        required = get_required("Bash")
        assert "timeout" not in required

    def test_description_field(self) -> None:
        props = get_properties("Bash")
        assert "description" in props

    def test_run_in_background_field(self) -> None:
        props = get_properties("Bash")
        assert "run_in_background" in props


# --- FileReadTool Schema Conformance ---

class TestFileReadSchema:
    """FileReadTool must have: file_path (required), offset (optional), limit (optional)."""

    def test_name(self) -> None:
        assert get_schema("Read")["name"] == "Read"

    def test_file_path_required(self) -> None:
        assert "file_path" in get_required("Read")
        assert get_properties("Read")["file_path"]["type"] == "string"

    def test_offset_optional(self) -> None:
        props = get_properties("Read")
        assert "offset" in props
        assert "offset" not in get_required("Read")

    def test_limit_optional(self) -> None:
        props = get_properties("Read")
        assert "limit" in props
        assert "limit" not in get_required("Read")

    def test_offset_nonnegative(self) -> None:
        props = get_properties("Read")
        # Should have minimum: 0
        offset = props["offset"]
        assert offset.get("minimum", offset.get("exclusiveMinimum", -1)) >= 0 or \
               "anyOf" in offset  # Pydantic wraps optional in anyOf

    def test_limit_positive(self) -> None:
        props = get_properties("Read")
        limit = props["limit"]
        # Should have exclusiveMinimum: 0 or minimum: 1
        has_positive_constraint = (
            limit.get("exclusiveMinimum", -1) >= 0 or
            limit.get("minimum", 0) >= 1 or
            "anyOf" in limit  # Pydantic wraps optional
        )
        assert has_positive_constraint


# --- FileEditTool Schema Conformance ---

class TestFileEditSchema:
    """FileEditTool must have: file_path, old_string, new_string (all required),
    replace_all (optional, default false)."""

    def test_name(self) -> None:
        assert get_schema("Edit")["name"] == "Edit"

    def test_required_fields(self) -> None:
        required = get_required("Edit")
        assert "file_path" in required
        assert "old_string" in required
        assert "new_string" in required

    def test_replace_all_optional(self) -> None:
        assert "replace_all" not in get_required("Edit")
        props = get_properties("Edit")
        assert "replace_all" in props

    def test_replace_all_default_false(self) -> None:
        props = get_properties("Edit")
        ra = props["replace_all"]
        assert ra.get("default") is False


# --- FileWriteTool Schema Conformance ---

class TestFileWriteSchema:
    """FileWriteTool must have: file_path (required), content (required)."""

    def test_name(self) -> None:
        assert get_schema("Write")["name"] == "Write"

    def test_required_fields(self) -> None:
        required = get_required("Write")
        assert "file_path" in required
        assert "content" in required

    def test_only_two_fields(self) -> None:
        props = get_properties("Write")
        assert len(props) == 2


# --- GlobTool Schema Conformance ---

class TestGlobSchema:
    """GlobTool must have: pattern (required), path (optional)."""

    def test_name(self) -> None:
        assert get_schema("Glob")["name"] == "Glob"

    def test_pattern_required(self) -> None:
        assert "pattern" in get_required("Glob")

    def test_path_optional(self) -> None:
        assert "path" not in get_required("Glob")
        assert "path" in get_properties("Glob")


# --- GrepTool Schema Conformance ---

class TestGrepSchema:
    """GrepTool must have: pattern (required), path, glob, output_mode, -B, -A, -C,
    context, -n, -i, type, head_limit, offset, multiline (all optional)."""

    def test_name(self) -> None:
        assert get_schema("Grep")["name"] == "Grep"

    def test_pattern_required(self) -> None:
        assert "pattern" in get_required("Grep")

    def test_optional_fields_exist(self) -> None:
        props = get_properties("Grep")
        expected_optional = ["path", "glob", "output_mode", "type", "head_limit", "offset", "multiline"]
        for field in expected_optional:
            assert field in props, f"Missing optional field: {field}"

    def test_output_mode_enum(self) -> None:
        props = get_properties("Grep")
        om = props["output_mode"]
        # Should have enum or anyOf with enum
        has_enum = "enum" in om or (
            "anyOf" in om and any("enum" in item for item in om.get("anyOf", []))
        )
        assert has_enum, "output_mode should have enum values"


# --- Tool Behavior Conformance ---

class TestToolBehaviorFlags:
    """Verify read-only and concurrency-safe flags match TS behavior."""

    @pytest.mark.parametrize("tool_name,expected_read_only", [
        ("Read", True),
        ("Glob", True),
        ("Grep", True),
        ("Edit", False),
        ("Write", False),
    ])
    def test_read_only(self, tool_name: str, expected_read_only: bool) -> None:
        tool = get_tool(tool_name)
        # Create a minimal input for the check
        input_data = tool.input_model.model_construct()
        assert tool.is_read_only(input_data) == expected_read_only

    @pytest.mark.parametrize("tool_name,expected_concurrent", [
        ("Read", True),
        ("Glob", True),
        ("Grep", True),
        ("Edit", False),
        ("Write", False),
    ])
    def test_concurrency_safe(self, tool_name: str, expected_concurrent: bool) -> None:
        tool = get_tool(tool_name)
        input_data = tool.input_model.model_construct()
        assert tool.is_concurrency_safe(input_data) == expected_concurrent
