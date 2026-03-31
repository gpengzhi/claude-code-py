"""Tests for core tools."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from claude_code.tool.base import ToolUseContext
from claude_code.tools.bash_tool.bash_tool import BashInput, BashTool
from claude_code.tools.file_edit_tool.file_edit_tool import FileEditInput, FileEditTool
from claude_code.tools.file_read_tool.file_read_tool import FileReadInput, FileReadTool
from claude_code.tools.file_write_tool.file_write_tool import FileWriteInput, FileWriteTool
from claude_code.tools.glob_tool.glob_tool import GlobInput, GlobTool
from claude_code.tools.grep_tool.grep_tool import GrepInput, GrepTool


@pytest.fixture
def ctx(tmp_path: Path) -> ToolUseContext:
    return ToolUseContext(cwd=tmp_path)


# --- BashTool ---

class TestBashTool:
    @pytest.mark.asyncio
    async def test_echo(self, ctx: ToolUseContext) -> None:
        tool = BashTool()
        result = await tool.call(BashInput(command="echo hello"), ctx)
        assert "hello" in result.data
        assert not result.is_error

    @pytest.mark.asyncio
    async def test_empty_command(self, ctx: ToolUseContext) -> None:
        tool = BashTool()
        result = await tool.call(BashInput(command=""), ctx)
        assert result.is_error

    @pytest.mark.asyncio
    async def test_failing_command(self, ctx: ToolUseContext) -> None:
        tool = BashTool()
        result = await tool.call(BashInput(command="false"), ctx)
        assert result.is_error

    @pytest.mark.asyncio
    async def test_timeout(self, ctx: ToolUseContext) -> None:
        tool = BashTool()
        result = await tool.call(
            BashInput(command="sleep 10", timeout=500), ctx
        )
        assert result.is_error
        assert "timed out" in result.data.lower()


# --- FileReadTool ---

class TestFileReadTool:
    @pytest.mark.asyncio
    async def test_read_file(self, ctx: ToolUseContext) -> None:
        test_file = ctx.cwd / "test.txt"
        test_file.write_text("line1\nline2\nline3\n")

        tool = FileReadTool()
        result = await tool.call(
            FileReadInput(file_path=str(test_file)), ctx
        )
        assert "line1" in result.data
        assert "line2" in result.data
        assert not result.is_error

    @pytest.mark.asyncio
    async def test_read_nonexistent(self, ctx: ToolUseContext) -> None:
        tool = FileReadTool()
        result = await tool.call(
            FileReadInput(file_path=str(ctx.cwd / "nope.txt")), ctx
        )
        assert result.is_error
        assert "does not exist" in result.data

    @pytest.mark.asyncio
    async def test_read_with_offset(self, ctx: ToolUseContext) -> None:
        test_file = ctx.cwd / "test.txt"
        test_file.write_text("line1\nline2\nline3\n")

        tool = FileReadTool()
        result = await tool.call(
            FileReadInput(file_path=str(test_file), offset=1, limit=1), ctx
        )
        assert "line2" in result.data
        assert "line1" not in result.data

    def test_is_read_only(self) -> None:
        tool = FileReadTool()
        assert tool.is_read_only(FileReadInput(file_path="/tmp/x"))
        assert tool.is_concurrency_safe(FileReadInput(file_path="/tmp/x"))


# --- FileEditTool ---

class TestFileEditTool:
    @pytest.mark.asyncio
    async def test_edit_file(self, ctx: ToolUseContext) -> None:
        test_file = ctx.cwd / "test.txt"
        test_file.write_text("hello world")

        # Must read first
        read_tool = FileReadTool()
        await read_tool.call(FileReadInput(file_path=str(test_file)), ctx)

        tool = FileEditTool()
        result = await tool.call(
            FileEditInput(
                file_path=str(test_file),
                old_string="hello",
                new_string="goodbye",
            ),
            ctx,
        )
        assert not result.is_error
        assert test_file.read_text() == "goodbye world"

    @pytest.mark.asyncio
    async def test_edit_requires_read(self, ctx: ToolUseContext) -> None:
        test_file = ctx.cwd / "test.txt"
        test_file.write_text("hello world")

        tool = FileEditTool()
        error = await tool.validate_input(
            FileEditInput(
                file_path=str(test_file),
                old_string="hello",
                new_string="goodbye",
            ),
            ctx,
        )
        assert error is not None
        assert "read" in error.lower()

    @pytest.mark.asyncio
    async def test_edit_same_string_rejected(self, ctx: ToolUseContext) -> None:
        tool = FileEditTool()
        error = await tool.validate_input(
            FileEditInput(
                file_path="/tmp/x",
                old_string="same",
                new_string="same",
            ),
            ctx,
        )
        assert error is not None


# --- FileWriteTool ---

class TestFileWriteTool:
    @pytest.mark.asyncio
    async def test_write_new_file(self, ctx: ToolUseContext) -> None:
        test_file = ctx.cwd / "new.txt"

        tool = FileWriteTool()
        result = await tool.call(
            FileWriteInput(file_path=str(test_file), content="hello\nworld"),
            ctx,
        )
        assert not result.is_error
        assert test_file.read_text() == "hello\nworld"
        assert "Created" in result.data

    @pytest.mark.asyncio
    async def test_write_creates_dirs(self, ctx: ToolUseContext) -> None:
        test_file = ctx.cwd / "deep" / "nested" / "file.txt"

        tool = FileWriteTool()
        result = await tool.call(
            FileWriteInput(file_path=str(test_file), content="content"),
            ctx,
        )
        assert not result.is_error
        assert test_file.exists()


# --- GlobTool ---

class TestGlobTool:
    @pytest.mark.asyncio
    async def test_glob_matches(self, ctx: ToolUseContext) -> None:
        (ctx.cwd / "a.py").write_text("")
        (ctx.cwd / "b.py").write_text("")
        (ctx.cwd / "c.txt").write_text("")

        tool = GlobTool()
        result = await tool.call(
            GlobInput(pattern="*.py", path=str(ctx.cwd)), ctx
        )
        assert "a.py" in result.data
        assert "b.py" in result.data
        assert "c.txt" not in result.data

    @pytest.mark.asyncio
    async def test_glob_no_matches(self, ctx: ToolUseContext) -> None:
        tool = GlobTool()
        result = await tool.call(
            GlobInput(pattern="*.xyz", path=str(ctx.cwd)), ctx
        )
        assert "No files found" in result.data

    def test_is_read_only(self) -> None:
        tool = GlobTool()
        assert tool.is_read_only(GlobInput(pattern="*"))
        assert tool.is_concurrency_safe(GlobInput(pattern="*"))


# --- GrepTool ---

class TestGrepTool:
    @pytest.mark.asyncio
    async def test_grep_matches(self, ctx: ToolUseContext) -> None:
        (ctx.cwd / "test.py").write_text("def hello():\n    pass\n")
        (ctx.cwd / "other.py").write_text("x = 1\n")

        tool = GrepTool()
        result = await tool.call(
            GrepInput(pattern="hello", path=str(ctx.cwd)), ctx
        )
        assert "test.py" in result.data
        assert not result.is_error

    @pytest.mark.asyncio
    async def test_grep_no_matches(self, ctx: ToolUseContext) -> None:
        (ctx.cwd / "test.py").write_text("x = 1\n")

        tool = GrepTool()
        result = await tool.call(
            GrepInput(pattern="nonexistent_pattern_xyz", path=str(ctx.cwd)), ctx
        )
        assert "No matches" in result.data

    def test_is_read_only(self) -> None:
        tool = GrepTool()
        assert tool.is_read_only(GrepInput(pattern="x"))
        assert tool.is_concurrency_safe(GrepInput(pattern="x"))
