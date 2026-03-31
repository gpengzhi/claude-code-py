"""Tests for config, context, memory, and session storage."""

import json
import pytest
from pathlib import Path

from claude_code.utils.config import (
    get_merged_settings,
    _read_json_file,
    _write_json_file,
)
from claude_code.context.user_context import find_claude_md_files, load_user_context
from claude_code.context.system_prompt import (
    build_tool_descriptions,
    get_environment_info,
    get_date_info,
)
from claude_code.memory.memdir import (
    build_memory_prompt,
    load_memory_file,
    load_memory_index,
)
from claude_code.memory.paths import (
    get_memory_dir,
    sanitize_path_for_dir_name,
)
from claude_code.utils.session_storage import (
    generate_session_id,
    save_message,
    load_session,
    list_sessions,
)
from claude_code.utils.git import is_git_repo


# --- Config ---

class TestConfig:
    def test_read_json_file_nonexistent(self, tmp_path: Path) -> None:
        result = _read_json_file(tmp_path / "nope.json")
        assert result == {}

    def test_read_write_json_file(self, tmp_path: Path) -> None:
        path = tmp_path / "test.json"
        _write_json_file(path, {"key": "value"})
        result = _read_json_file(path)
        assert result == {"key": "value"}

    def test_read_invalid_json(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.json"
        path.write_text("not json {{{")
        result = _read_json_file(path)
        assert result == {}


# --- User Context ---

class TestUserContext:
    def test_find_claude_md_in_cwd(self, tmp_path: Path) -> None:
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text("# Project rules\nBe helpful.")
        files = find_claude_md_files(tmp_path)
        assert any(p == claude_md for _, p in files)

    def test_find_claude_md_in_dot_claude(self, tmp_path: Path) -> None:
        dot_claude = tmp_path / ".claude"
        dot_claude.mkdir()
        claude_md = dot_claude / "CLAUDE.md"
        claude_md.write_text("# Project config")
        files = find_claude_md_files(tmp_path)
        assert any(p == claude_md for _, p in files)

    def test_load_user_context(self, tmp_path: Path) -> None:
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text("Always use type hints.")
        ctx = load_user_context(tmp_path)
        assert "Always use type hints" in ctx

    def test_load_user_context_empty(self, tmp_path: Path) -> None:
        ctx = load_user_context(tmp_path)
        assert ctx == ""


# --- System Prompt ---

class TestSystemPrompt:
    def test_get_environment_info(self, tmp_path: Path) -> None:
        info = get_environment_info(tmp_path)
        assert str(tmp_path) in info
        assert "Platform" in info

    def test_get_date_info(self) -> None:
        info = get_date_info()
        assert "Today's date" in info
        assert "202" in info  # Year

    def test_build_tool_descriptions_empty(self) -> None:
        result = build_tool_descriptions([])
        assert result == ""


# --- Memory ---

class TestMemory:
    def test_sanitize_path(self) -> None:
        result = sanitize_path_for_dir_name("/Users/test/project")
        assert "/" not in result
        assert result  # Not empty

    def test_memory_dir(self, tmp_path: Path) -> None:
        mem_dir = get_memory_dir(tmp_path)
        assert "memory" in str(mem_dir)

    def test_load_memory_index_missing(self, tmp_path: Path) -> None:
        result = load_memory_index(tmp_path)
        assert result == ""

    def test_load_memory_index(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        mem_dir = get_memory_dir(tmp_path)
        mem_dir.mkdir(parents=True, exist_ok=True)
        index = mem_dir / "MEMORY.md"
        index.write_text("- [User role](user_role.md) -- senior engineer\n")

        result = load_memory_index(tmp_path)
        assert "senior engineer" in result

    def test_load_memory_file_with_frontmatter(self, tmp_path: Path) -> None:
        mem_file = tmp_path / "test_memory.md"
        mem_file.write_text(
            "---\nname: test\ndescription: test memory\ntype: user\n---\nContent here"
        )
        result = load_memory_file(mem_file)
        assert result is not None
        assert result["name"] == "test"
        assert result["type"] == "user"
        assert result["content"] == "Content here"

    def test_build_memory_prompt_empty(self, tmp_path: Path) -> None:
        result = build_memory_prompt(tmp_path)
        assert result == ""


# --- Session Storage ---

class TestSessionStorage:
    def test_generate_session_id(self) -> None:
        id1 = generate_session_id()
        id2 = generate_session_id()
        assert id1 != id2
        assert len(id1) == 36

    def test_save_and_load(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "claude_code.utils.session_storage.get_sessions_dir",
            lambda: tmp_path,
        )
        sid = "test-session-123"
        save_message(sid, {"role": "user", "content": "hello"})
        save_message(sid, {"role": "assistant", "content": [{"type": "text", "text": "hi"}]})

        messages = load_session(sid)
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"

    def test_list_sessions(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "claude_code.utils.session_storage.get_sessions_dir",
            lambda: tmp_path,
        )
        save_message("sess1", {"role": "user", "content": "first"})
        save_message("sess2", {"role": "user", "content": "second"})

        sessions = list_sessions()
        assert len(sessions) == 2


# --- Git ---

class TestGit:
    @pytest.mark.asyncio
    async def test_is_git_repo(self) -> None:
        # Current directory (claude-code-py) should be a git repo
        result = await is_git_repo(Path.cwd())
        # May or may not be depending on test context
        assert isinstance(result, bool)
