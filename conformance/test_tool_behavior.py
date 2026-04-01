"""Conformance: Tool behavior tests.

Verifies that tools produce equivalent results for the same inputs.
These tests run actual tool implementations against known inputs.
"""

import pytest
from pathlib import Path

from claude_code.tool.base import ToolUseContext
from claude_code.tool.registry import get_all_base_tools, find_tool_by_name


@pytest.fixture
def ctx(tmp_path: Path) -> ToolUseContext:
    return ToolUseContext(cwd=tmp_path)


def get_tool(name: str):
    tools = get_all_base_tools()
    return find_tool_by_name(tools, name)


class TestBashBehavior:
    """BashTool must execute commands and return stdout/stderr/exit code."""

    @pytest.mark.asyncio
    async def test_echo_returns_stdout(self, ctx: ToolUseContext) -> None:
        tool = get_tool("Bash")
        from claude_code.tools.bash_tool.bash_tool import BashInput
        result = await tool.call(BashInput(command="echo hello"), ctx)
        assert "hello" in result.data
        assert not result.is_error

    @pytest.mark.asyncio
    async def test_stderr_captured(self, ctx: ToolUseContext) -> None:
        tool = get_tool("Bash")
        from claude_code.tools.bash_tool.bash_tool import BashInput
        result = await tool.call(BashInput(command="echo err >&2"), ctx)
        assert "err" in result.data

    @pytest.mark.asyncio
    async def test_nonzero_exit_is_error(self, ctx: ToolUseContext) -> None:
        tool = get_tool("Bash")
        from claude_code.tools.bash_tool.bash_tool import BashInput
        result = await tool.call(BashInput(command="exit 42"), ctx)
        assert result.is_error
        assert "42" in result.data

    @pytest.mark.asyncio
    async def test_cwd_respected(self, ctx: ToolUseContext) -> None:
        tool = get_tool("Bash")
        from claude_code.tools.bash_tool.bash_tool import BashInput
        result = await tool.call(BashInput(command="pwd"), ctx)
        assert str(ctx.cwd) in result.data


class TestFileReadBehavior:
    """FileReadTool must read files with cat -n style line numbers."""

    @pytest.mark.asyncio
    async def test_line_numbers(self, ctx: ToolUseContext) -> None:
        """TS version outputs 'linenum\\tcontent' format."""
        f = ctx.cwd / "test.txt"
        f.write_text("alpha\nbeta\ngamma\n")
        tool = get_tool("Read")
        from claude_code.tools.file_read_tool.file_read_tool import FileReadInput
        result = await tool.call(FileReadInput(file_path=str(f)), ctx)
        # Must have line numbers
        assert "1\t" in result.data
        assert "2\t" in result.data
        assert "alpha" in result.data

    @pytest.mark.asyncio
    async def test_offset_1_based(self, ctx: ToolUseContext) -> None:
        """TS uses 0-based offset but displays 1-based line numbers."""
        f = ctx.cwd / "test.txt"
        f.write_text("line1\nline2\nline3\nline4\n")
        tool = get_tool("Read")
        from claude_code.tools.file_read_tool.file_read_tool import FileReadInput
        result = await tool.call(FileReadInput(file_path=str(f), offset=2, limit=1), ctx)
        assert "line3" in result.data
        assert "line1" not in result.data

    @pytest.mark.asyncio
    async def test_nonexistent_file_error(self, ctx: ToolUseContext) -> None:
        tool = get_tool("Read")
        from claude_code.tools.file_read_tool.file_read_tool import FileReadInput
        result = await tool.call(FileReadInput(file_path=str(ctx.cwd / "nope.txt")), ctx)
        assert result.is_error
        assert "does not exist" in result.data.lower() or "not found" in result.data.lower()

    @pytest.mark.asyncio
    async def test_tracks_read_state(self, ctx: ToolUseContext) -> None:
        """After reading, readFileState must have the file's mtime."""
        f = ctx.cwd / "test.txt"
        f.write_text("content")
        tool = get_tool("Read")
        from claude_code.tools.file_read_tool.file_read_tool import FileReadInput
        await tool.call(FileReadInput(file_path=str(f)), ctx)
        assert str(f) in ctx.read_file_state


class TestFileEditBehavior:
    """FileEditTool must require read-before-edit and enforce uniqueness."""

    @pytest.mark.asyncio
    async def test_must_read_first(self, ctx: ToolUseContext) -> None:
        """TS rejects edits to files not in readFileState."""
        f = ctx.cwd / "test.txt"
        f.write_text("hello world")
        tool = get_tool("Edit")
        from claude_code.tools.file_edit_tool.file_edit_tool import FileEditInput
        error = await tool.validate_input(
            FileEditInput(file_path=str(f), old_string="hello", new_string="bye"),
            ctx,
        )
        assert error is not None
        assert "read" in error.lower()

    @pytest.mark.asyncio
    async def test_rejects_same_strings(self, ctx: ToolUseContext) -> None:
        """TS rejects old_string == new_string."""
        tool = get_tool("Edit")
        from claude_code.tools.file_edit_tool.file_edit_tool import FileEditInput
        error = await tool.validate_input(
            FileEditInput(file_path="/tmp/x", old_string="same", new_string="same"),
            ctx,
        )
        assert error is not None

    @pytest.mark.asyncio
    async def test_rejects_non_unique_match(self, ctx: ToolUseContext) -> None:
        """TS rejects when old_string appears multiple times (without replace_all)."""
        f = ctx.cwd / "test.txt"
        f.write_text("foo bar foo baz foo")
        # Read first
        read_tool = get_tool("Read")
        from claude_code.tools.file_read_tool.file_read_tool import FileReadInput
        await read_tool.call(FileReadInput(file_path=str(f)), ctx)

        tool = get_tool("Edit")
        from claude_code.tools.file_edit_tool.file_edit_tool import FileEditInput
        result = await tool.call(
            FileEditInput(file_path=str(f), old_string="foo", new_string="qux"),
            ctx,
        )
        assert result.is_error
        assert "3" in result.data  # Should mention the count

    @pytest.mark.asyncio
    async def test_replace_all_works(self, ctx: ToolUseContext) -> None:
        f = ctx.cwd / "test.txt"
        f.write_text("foo bar foo baz foo")
        read_tool = get_tool("Read")
        from claude_code.tools.file_read_tool.file_read_tool import FileReadInput
        await read_tool.call(FileReadInput(file_path=str(f)), ctx)

        tool = get_tool("Edit")
        from claude_code.tools.file_edit_tool.file_edit_tool import FileEditInput
        result = await tool.call(
            FileEditInput(file_path=str(f), old_string="foo", new_string="qux", replace_all=True),
            ctx,
        )
        assert not result.is_error
        assert f.read_text() == "qux bar qux baz qux"


class TestFileWriteBehavior:
    """FileWriteTool must create files and parent directories."""

    @pytest.mark.asyncio
    async def test_creates_file(self, ctx: ToolUseContext) -> None:
        f = ctx.cwd / "new.txt"
        tool = get_tool("Write")
        from claude_code.tools.file_write_tool.file_write_tool import FileWriteInput
        result = await tool.call(FileWriteInput(file_path=str(f), content="hello"), ctx)
        assert not result.is_error
        assert f.read_text() == "hello"

    @pytest.mark.asyncio
    async def test_creates_parent_dirs(self, ctx: ToolUseContext) -> None:
        f = ctx.cwd / "a" / "b" / "c.txt"
        tool = get_tool("Write")
        from claude_code.tools.file_write_tool.file_write_tool import FileWriteInput
        result = await tool.call(FileWriteInput(file_path=str(f), content="deep"), ctx)
        assert not result.is_error
        assert f.read_text() == "deep"

    @pytest.mark.asyncio
    async def test_requires_read_for_overwrite(self, ctx: ToolUseContext) -> None:
        """TS requires reading existing files before overwriting."""
        f = ctx.cwd / "existing.txt"
        f.write_text("old content")
        tool = get_tool("Write")
        from claude_code.tools.file_write_tool.file_write_tool import FileWriteInput
        error = await tool.validate_input(
            FileWriteInput(file_path=str(f), content="new content"),
            ctx,
        )
        assert error is not None
        assert "read" in error.lower()


class TestGlobBehavior:
    """GlobTool must match patterns and return relative paths."""

    @pytest.mark.asyncio
    async def test_matches_pattern(self, ctx: ToolUseContext) -> None:
        (ctx.cwd / "a.py").write_text("")
        (ctx.cwd / "b.py").write_text("")
        (ctx.cwd / "c.js").write_text("")
        tool = get_tool("Glob")
        from claude_code.tools.glob_tool.glob_tool import GlobInput
        result = await tool.call(GlobInput(pattern="*.py", path=str(ctx.cwd)), ctx)
        assert "a.py" in result.data
        assert "b.py" in result.data
        assert "c.js" not in result.data

    @pytest.mark.asyncio
    async def test_no_matches_message(self, ctx: ToolUseContext) -> None:
        tool = get_tool("Glob")
        from claude_code.tools.glob_tool.glob_tool import GlobInput
        result = await tool.call(GlobInput(pattern="*.xyz", path=str(ctx.cwd)), ctx)
        assert "No files found" in result.data


class TestGrepBehavior:
    """GrepTool must search file contents with regex."""

    @pytest.mark.asyncio
    async def test_finds_matches(self, ctx: ToolUseContext) -> None:
        (ctx.cwd / "code.py").write_text("def hello():\n    pass\n")
        tool = get_tool("Grep")
        from claude_code.tools.grep_tool.grep_tool import GrepInput
        result = await tool.call(GrepInput(pattern="hello", path=str(ctx.cwd)), ctx)
        assert "code.py" in result.data

    @pytest.mark.asyncio
    async def test_no_matches_message(self, ctx: ToolUseContext) -> None:
        (ctx.cwd / "code.py").write_text("x = 1\n")
        tool = get_tool("Grep")
        from claude_code.tools.grep_tool.grep_tool import GrepInput
        result = await tool.call(GrepInput(pattern="zzz_nonexistent", path=str(ctx.cwd)), ctx)
        assert "No matches" in result.data


# --- Message Format Conformance ---

class TestMessageFormat:
    """Verify messages are formatted correctly for the Anthropic API."""

    def test_user_message_format(self) -> None:
        from claude_code.services.api.claude import build_api_messages
        messages = [{"role": "user", "content": "hello"}]
        api = build_api_messages(messages)
        assert api[0]["role"] == "user"
        assert api[0]["content"] == "hello"

    def test_assistant_message_format(self) -> None:
        from claude_code.services.api.claude import build_api_messages
        messages = [{"role": "assistant", "content": [{"type": "text", "text": "hi"}]}]
        api = build_api_messages(messages)
        assert api[0]["role"] == "assistant"

    def test_system_messages_filtered(self) -> None:
        """System and progress messages should not appear in API messages."""
        from claude_code.services.api.claude import build_api_messages
        messages = [
            {"role": "system", "content": "internal"},
            {"role": "user", "content": "hello"},
            {"role": "progress", "content": "working..."},
        ]
        api = build_api_messages(messages)
        assert len(api) == 1
        assert api[0]["role"] == "user"
