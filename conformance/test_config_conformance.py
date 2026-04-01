"""Conformance: Configuration and file format tests.

Verifies that claude-code-py uses the same file paths, formats, and
precedence as Claude Code.
"""

import json
import pytest
from pathlib import Path

from claude_code.utils.config import (
    get_claude_home,
    get_merged_settings,
    _read_json_file,
    _write_json_file,
)
from claude_code.memory.paths import get_memory_dir, get_memory_index_path
from claude_code.memory.memdir import load_memory_file
from claude_code.context.user_context import find_claude_md_files
from claude_code.utils.session_storage import save_message, load_session


class TestConfigPaths:
    """Verify config file paths match TS conventions."""

    def test_claude_home(self) -> None:
        """TS uses ~/.claude as the config home."""
        home = get_claude_home()
        assert home == Path.home() / ".claude"

    def test_settings_json_format(self, tmp_path: Path) -> None:
        """Settings should be valid JSON with consistent structure."""
        path = tmp_path / "settings.json"
        _write_json_file(path, {
            "model": "claude-sonnet-4-20250514",
            "permissions": {
                "allow": ["Read(*)", "Glob(*)"],
                "deny": [],
            },
            "hooks": {
                "PreToolUse": [],
            },
        })
        data = _read_json_file(path)
        assert data["model"] == "claude-sonnet-4-20250514"
        assert "permissions" in data
        assert "hooks" in data


class TestSettingsPrecedence:
    """Verify settings merge order: global < project < local."""

    def test_project_overrides_global(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # Setup global
        global_dir = tmp_path / "global" / ".claude"
        global_dir.mkdir(parents=True)
        _write_json_file(global_dir / "settings.json", {"model": "global-model", "verbose": False})

        # Setup project
        project_dir = tmp_path / "project" / ".claude"
        project_dir.mkdir(parents=True)
        _write_json_file(project_dir / "settings.json", {"model": "project-model"})

        monkeypatch.setattr("claude_code.utils.config.get_claude_home", lambda: global_dir.parent / ".claude")
        settings = get_merged_settings(tmp_path / "project")
        assert settings["model"] == "project-model"
        assert settings["verbose"] is False  # Inherited from global

    def test_env_overrides_all(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CLAUDE_MODEL", "env-model")
        monkeypatch.setattr("claude_code.utils.config.get_claude_home", lambda: tmp_path / ".claude")
        settings = get_merged_settings(tmp_path)
        assert settings["model"] == "env-model"


class TestMemoryFormat:
    """Verify memory file format matches TS conventions."""

    def test_memory_dir_path(self, tmp_path: Path) -> None:
        """Memory should be under ~/.claude/projects/<sanitized>/memory/."""
        mem_dir = get_memory_dir(tmp_path)
        assert "projects" in str(mem_dir)
        assert str(mem_dir).endswith("/memory")

    def test_memory_index_path(self, tmp_path: Path) -> None:
        """Index file must be MEMORY.md."""
        idx = get_memory_index_path(tmp_path)
        assert idx.name == "MEMORY.md"

    def test_memory_file_frontmatter(self, tmp_path: Path) -> None:
        """Memory files use YAML frontmatter with name, description, type."""
        mem_file = tmp_path / "user_role.md"
        mem_file.write_text(
            "---\n"
            "name: user role\n"
            "description: User is a senior engineer\n"
            "type: user\n"
            "---\n\n"
            "The user is a senior backend engineer with Go expertise."
        )
        data = load_memory_file(mem_file)
        assert data is not None
        assert data["name"] == "user role"
        assert data["type"] == "user"
        assert "senior backend" in data["content"]


class TestClaudeMdConformance:
    """Verify CLAUDE.md file discovery matches TS behavior."""

    def test_finds_claude_md_in_cwd(self, tmp_path: Path) -> None:
        (tmp_path / "CLAUDE.md").write_text("# Rules")
        files = find_claude_md_files(tmp_path)
        assert len(files) >= 1

    def test_finds_claude_md_in_dot_claude(self, tmp_path: Path) -> None:
        dot_claude = tmp_path / ".claude"
        dot_claude.mkdir()
        (dot_claude / "CLAUDE.md").write_text("# Config")
        files = find_claude_md_files(tmp_path)
        assert any(str(p).endswith(".claude/CLAUDE.md") for _, p in files)

    def test_case_insensitive_name(self, tmp_path: Path) -> None:
        """TS checks both CLAUDE.md and claude.md."""
        (tmp_path / "claude.md").write_text("# lowercase")
        files = find_claude_md_files(tmp_path)
        assert len(files) >= 1


class TestSessionFormat:
    """Verify session storage format matches TS conventions."""

    def test_jsonl_format(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Sessions must be stored as JSONL (one JSON object per line)."""
        monkeypatch.setattr(
            "claude_code.utils.session_storage.get_sessions_dir",
            lambda: tmp_path,
        )
        save_message("test-session", {"role": "user", "content": "hello"})
        save_message("test-session", {"role": "assistant", "content": [{"type": "text", "text": "hi"}]})

        # Read raw file -- must be valid JSONL
        session_file = tmp_path / "test-session.jsonl"
        lines = session_file.read_text().strip().split("\n")
        assert len(lines) == 2
        for line in lines:
            data = json.loads(line)
            assert "role" in data
            assert "sessionId" in data
            assert "timestamp" in data

    def test_session_has_metadata(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Each message must include sessionId and timestamp."""
        monkeypatch.setattr(
            "claude_code.utils.session_storage.get_sessions_dir",
            lambda: tmp_path,
        )
        save_message("sid-123", {"role": "user", "content": "test"})
        messages = load_session("sid-123")
        assert messages[0]["sessionId"] == "sid-123"
        assert "timestamp" in messages[0]
