"""Tests for extended tools and skills."""

import json
import pytest
from pathlib import Path
from typing import Any

from claude_code.tool.base import ToolUseContext
from claude_code.tool.registry import get_all_base_tools, find_tool_by_name
from claude_code.state.app_state import AppState


# --- Registry ---

class TestExtendedRegistry:
    def test_all_tools_load(self) -> None:
        tools = get_all_base_tools()
        assert len(tools) == 17  # 6 core + 11 extended
        names = [t.name for t in tools]
        assert "WebFetch" in names
        assert "WebSearch" in names
        assert "Agent" in names
        assert "TaskCreate" in names
        assert "TaskUpdate" in names
        assert "TaskGet" in names
        assert "TaskList" in names
        assert "EnterPlanMode" in names
        assert "ExitPlanMode" in names
        assert "AskUserQuestion" in names
        assert "Skill" in names

    def test_all_tools_have_schemas(self) -> None:
        for tool in get_all_base_tools():
            schema = tool.get_tool_schema()
            assert "name" in schema
            assert "description" in schema
            assert "input_schema" in schema
            assert schema["name"] == tool.name


# --- Task Tools ---

class TestTaskTools:
    @pytest.fixture
    def ctx(self, tmp_path: Path) -> ToolUseContext:
        state = AppState(tasks={})
        ctx = ToolUseContext(cwd=tmp_path)
        ctx._app_state = state
        return ctx

    @pytest.mark.asyncio
    async def test_task_create(self, ctx: ToolUseContext) -> None:
        from claude_code.tools.task_tools.task_tools import TaskCreateTool, TaskCreateInput
        tool = TaskCreateTool()
        result = await tool.call(
            TaskCreateInput(subject="Test task", description="Do something"),
            ctx,
        )
        assert not result.is_error
        assert "1" in str(result.data)  # First task ID

    @pytest.mark.asyncio
    async def test_task_list_empty(self, ctx: ToolUseContext) -> None:
        from claude_code.tools.task_tools.task_tools import TaskListTool, TaskListInput
        tool = TaskListTool()
        result = await tool.call(TaskListInput(), ctx)
        assert not result.is_error


# --- Plan Tools ---

class TestPlanTools:
    @pytest.fixture
    def ctx(self, tmp_path: Path) -> ToolUseContext:
        ctx = ToolUseContext(cwd=tmp_path)
        ctx._app_state = AppState()
        return ctx

    @pytest.mark.asyncio
    async def test_enter_plan_mode(self, ctx: ToolUseContext) -> None:
        from claude_code.tools.plan_tools.enter_plan_mode import EnterPlanModeTool, EnterPlanModeInput
        tool = EnterPlanModeTool()
        result = await tool.call(EnterPlanModeInput(), ctx)
        assert not result.is_error
        assert ctx.get_app_state().mode == "plan"

    @pytest.mark.asyncio
    async def test_exit_plan_mode(self, ctx: ToolUseContext) -> None:
        from claude_code.tools.plan_tools.exit_plan_mode import ExitPlanModeTool, ExitPlanModeInput
        tool = ExitPlanModeTool()
        result = await tool.call(ExitPlanModeInput(), ctx)
        assert not result.is_error


# --- WebFetch ---

class TestWebFetch:
    @pytest.mark.asyncio
    async def test_web_fetch_invalid_url(self, tmp_path: Path) -> None:
        from claude_code.tools.web_fetch_tool.web_fetch_tool import WebFetchTool, WebFetchInput
        ctx = ToolUseContext(cwd=tmp_path)
        tool = WebFetchTool()
        result = await tool.call(
            WebFetchInput(url="not-a-url", prompt="test"),
            ctx,
        )
        assert result.is_error


# --- Skills ---

class TestSkills:
    def test_find_skill_dirs(self, tmp_path: Path) -> None:
        from claude_code.skills.loader import find_skill_dirs
        skill_dir = tmp_path / ".claude" / "skills"
        skill_dir.mkdir(parents=True)
        dirs = find_skill_dirs(tmp_path)
        assert skill_dir in dirs

    def test_load_skill_file(self, tmp_path: Path) -> None:
        from claude_code.skills.loader import load_skill_file
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        skill_file = skill_dir / "SKILL.md"
        skill_file.write_text(
            "---\ndescription: Test skill\nuser-invocable: true\n---\nDo the thing."
        )
        skill = load_skill_file(skill_file)
        assert skill is not None
        assert skill["name"] == "my-skill"
        assert skill["description"] == "Test skill"
        assert skill["body"] == "Do the thing."

    def test_load_all_skills(self, tmp_path: Path) -> None:
        from claude_code.skills.loader import load_all_skills
        skill_dir = tmp_path / ".claude" / "skills" / "test-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\ndescription: Test\n---\nBody")
        skills = load_all_skills(tmp_path)
        assert len(skills) >= 1
        assert skills[0]["name"] == "test-skill"

    def test_bundled_skills(self) -> None:
        from claude_code.skills.bundled import get_bundled_skills
        skills = get_bundled_skills()
        names = [s["name"] for s in skills]
        assert "commit" in names
        assert "review-pr" in names
        assert "simplify" in names
