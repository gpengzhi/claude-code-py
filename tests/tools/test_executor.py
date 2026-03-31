"""Tests for the tool executor."""

import pytest

from claude_code.tool.base import Tool, ToolResult, ToolUseContext
from claude_code.tool.executor import execute_tool, run_tools
from claude_code.tool.registry import get_all_base_tools, find_tool_by_name

from pydantic import BaseModel, Field
from pathlib import Path


class DummyInput(BaseModel):
    value: str = "test"


class DummyTool(Tool):
    name = "DummyTool"
    input_model = DummyInput

    def get_description(self) -> str:
        return "A test tool"

    async def call(self, args: BaseModel, context: ToolUseContext) -> ToolResult:
        assert isinstance(args, DummyInput)
        return ToolResult(data=f"got: {args.value}")


class FailingTool(Tool):
    name = "FailingTool"
    input_model = DummyInput

    def get_description(self) -> str:
        return "A tool that fails"

    async def call(self, args: BaseModel, context: ToolUseContext) -> ToolResult:
        raise RuntimeError("intentional failure")


class TestExecutor:
    @pytest.mark.asyncio
    async def test_execute_tool_success(self, tmp_path: Path) -> None:
        ctx = ToolUseContext(cwd=tmp_path)
        tool = DummyTool()
        result = await execute_tool(tool, {"value": "hello"}, "id1", ctx)
        assert not result.is_error
        assert "got: hello" in result.content

    @pytest.mark.asyncio
    async def test_execute_tool_invalid_input(self, tmp_path: Path) -> None:
        ctx = ToolUseContext(cwd=tmp_path)
        tool = DummyTool()
        # Pydantic rejects int for str field
        result = await execute_tool(tool, {"value": 123}, "id1", ctx)
        assert result.is_error
        assert "validation error" in result.content.lower()

    @pytest.mark.asyncio
    async def test_execute_tool_failure(self, tmp_path: Path) -> None:
        ctx = ToolUseContext(cwd=tmp_path)
        tool = FailingTool()
        result = await execute_tool(tool, {}, "id1", ctx)
        assert result.is_error
        assert "intentional failure" in result.content


class TestRegistry:
    def test_get_all_base_tools(self) -> None:
        tools = get_all_base_tools()
        names = [t.name for t in tools]
        assert "Bash" in names
        assert "Read" in names
        assert "Edit" in names
        assert "Write" in names
        assert "Glob" in names
        assert "Grep" in names

    def test_find_tool_by_name(self) -> None:
        tools = get_all_base_tools()
        assert find_tool_by_name(tools, "Bash") is not None
        assert find_tool_by_name(tools, "Read") is not None
        assert find_tool_by_name(tools, "Unknown") is None

    def test_find_tool_by_alias(self) -> None:
        tools = get_all_base_tools()
        assert find_tool_by_name(tools, "FileRead") is not None
        assert find_tool_by_name(tools, "FileEdit") is not None
