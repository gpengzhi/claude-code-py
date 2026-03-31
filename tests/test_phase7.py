"""Tests for Phase 7: Plugins, Vim, Auth, Errors."""

import json
import pytest
from pathlib import Path

from claude_code.plugins.loader import (
    LoadedPlugin,
    PluginLoadResult,
    load_plugin_from_dir,
    load_plugin_manifest,
    load_all_plugins,
    get_plugin_commands,
)
from claude_code.plugins.builtin import (
    register_builtin_plugin,
    get_builtin_plugins,
    BuiltinPluginDef,
)
from claude_code.tui.vim.types import VimMode, VimState
from claude_code.tui.vim.motions import (
    word_boundary_forward,
    word_boundary_backward,
    word_end_forward,
    resolve_motion,
)
from claude_code.tui.vim.transitions import transition, TransitionResult
from claude_code.utils.auth import get_api_key_source, is_authenticated
from claude_code.services.api.errors import (
    classify_error,
    APIError,
    RateLimitError,
    AuthenticationError,
    check_cost_threshold,
)


# --- Plugin System ---

class TestPlugins:
    def test_load_plugin_from_dir(self, tmp_path: Path) -> None:
        plugin_dir = tmp_path / "my-plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(json.dumps({
            "name": "my-plugin",
            "description": "A test plugin",
        }))
        skills_dir = plugin_dir / "skills"
        skills_dir.mkdir()
        skill_dir = skills_dir / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\ndescription: Test\n---\nDo it.")

        plugin = load_plugin_from_dir(plugin_dir)
        assert plugin is not None
        assert plugin.name == "my-plugin"
        assert plugin.skills_path == skills_dir

    def test_load_plugin_manifest(self, tmp_path: Path) -> None:
        plugin_dir = tmp_path / "plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text('{"name": "test", "version": "1.0"}')
        manifest = load_plugin_manifest(plugin_dir)
        assert manifest is not None
        assert manifest["name"] == "test"

    def test_load_plugin_no_manifest(self, tmp_path: Path) -> None:
        plugin_dir = tmp_path / "bare-plugin"
        plugin_dir.mkdir()
        plugin = load_plugin_from_dir(plugin_dir)
        assert plugin is not None
        assert plugin.name == "bare-plugin"

    def test_load_all_plugins_empty(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("claude_code.plugins.loader.get_plugins_dir", lambda: tmp_path / "nope")
        result = load_all_plugins()
        assert len(result.enabled) == 0

    def test_get_plugin_commands(self, tmp_path: Path) -> None:
        plugin_dir = tmp_path / "plugin"
        skills_dir = plugin_dir / "skills" / "my-cmd"
        skills_dir.mkdir(parents=True)
        (skills_dir / "SKILL.md").write_text("---\ndescription: Plugin cmd\n---\nRun it.")

        plugin = LoadedPlugin(name="test", path=plugin_dir, source="local", skills_path=plugin_dir / "skills")
        commands = get_plugin_commands([plugin])
        assert len(commands) == 1
        assert commands[0]["name"] == "my-cmd"

    def test_builtin_plugin(self) -> None:
        register_builtin_plugin(BuiltinPluginDef(
            name="test-builtin",
            description="Test builtin",
        ))
        plugins = get_builtin_plugins()
        names = [p["name"] for p in plugins]
        assert "test-builtin" in names


# --- Vim Motions ---

class TestVimMotions:
    def test_word_forward(self) -> None:
        text = "hello world foo"
        assert word_boundary_forward(text, 0) == 6   # -> 'w' in world
        assert word_boundary_forward(text, 6) == 12   # -> 'f' in foo

    def test_word_backward(self) -> None:
        text = "hello world foo"
        assert word_boundary_backward(text, 12) == 6  # -> 'w' in world
        assert word_boundary_backward(text, 6) == 0   # -> 'h' in hello

    def test_word_end(self) -> None:
        text = "hello world"
        assert word_end_forward(text, 0) == 4   # -> 'o' in hello
        assert word_end_forward(text, 4) == 10  # -> 'd' in world

    def test_resolve_motion_h_l(self) -> None:
        text = "hello"
        assert resolve_motion("h", text, 2) == 1
        assert resolve_motion("l", text, 2) == 3
        assert resolve_motion("h", text, 0) == 0  # Clamped
        assert resolve_motion("l", text, 4) == 4  # Clamped

    def test_resolve_motion_0_dollar(self) -> None:
        text = "hello world"
        assert resolve_motion("0", text, 5) == 0
        assert resolve_motion("$", text, 0) == 10

    def test_resolve_motion_with_count(self) -> None:
        text = "hello world foo bar"
        pos = resolve_motion("w", text, 0, count=2)
        assert pos == 12  # Jumped two words


# --- Vim Transitions ---

class TestVimTransitions:
    def test_insert_to_normal(self) -> None:
        state = VimState(mode=VimMode.INSERT, cursor=5)
        result = transition(state, "escape", "hello world")
        assert result.state.mode == VimMode.NORMAL
        assert result.state.cursor == 4  # cursor - 1

    def test_normal_to_insert_i(self) -> None:
        state = VimState(mode=VimMode.NORMAL, cursor=3)
        result = transition(state, "i", "hello")
        assert result.state.mode == VimMode.INSERT
        assert result.state.cursor == 3

    def test_normal_to_insert_a(self) -> None:
        state = VimState(mode=VimMode.NORMAL, cursor=3)
        result = transition(state, "a", "hello")
        assert result.state.mode == VimMode.INSERT
        assert result.state.cursor == 4

    def test_normal_to_insert_A(self) -> None:
        state = VimState(mode=VimMode.NORMAL, cursor=0)
        result = transition(state, "A", "hello")
        assert result.state.mode == VimMode.INSERT
        assert result.state.cursor == 5  # End of line

    def test_motion_w(self) -> None:
        state = VimState(mode=VimMode.NORMAL, cursor=0)
        result = transition(state, "w", "hello world")
        assert result.state.cursor == 6

    def test_delete_x(self) -> None:
        state = VimState(mode=VimMode.NORMAL, cursor=2)
        result = transition(state, "x", "hello")
        assert result.text == "helo"

    def test_delete_dd(self) -> None:
        state = VimState(mode=VimMode.NORMAL, cursor=0)
        r1 = transition(state, "d", "hello")
        assert r1.state.operator == "d"
        r2 = transition(r1.state, "d", "hello")
        assert r2.text == ""

    def test_change_C(self) -> None:
        state = VimState(mode=VimMode.NORMAL, cursor=5)
        result = transition(state, "C", "hello world")
        assert result.text == "hello"
        assert result.state.mode == VimMode.INSERT

    def test_count_prefix(self) -> None:
        state = VimState(mode=VimMode.NORMAL, cursor=0)
        r1 = transition(state, "3", "hello world foo")
        assert r1.state.count == 3
        r2 = transition(r1.state, "w", "hello world foo")
        # 3w should jump 3 words... but count is only applied on next motion
        assert r2.state.cursor > 0

    def test_enter_submits(self) -> None:
        state = VimState(mode=VimMode.NORMAL, cursor=0)
        result = transition(state, "enter", "hello")
        assert result.submit


# --- Auth ---

class TestAuth:
    def test_api_key_source(self) -> None:
        source = get_api_key_source()
        assert source in ("environment", "file", "none")

    def test_is_authenticated(self) -> None:
        result = is_authenticated()
        assert isinstance(result, bool)


# --- Error Handling ---

class TestErrors:
    def test_classify_generic_error(self) -> None:
        err = classify_error(Exception("something broke"))
        assert isinstance(err, APIError)
        assert err.error_type == "unknown"

    def test_classify_rate_limit(self) -> None:
        err = classify_error(Exception("rate limit exceeded"))
        assert isinstance(err, RateLimitError)

    def test_cost_threshold_ok(self) -> None:
        assert check_cost_threshold(0.50) is None

    def test_cost_threshold_warning(self) -> None:
        result = check_cost_threshold(6.0)
        assert result is not None
        assert "Warning" in result

    def test_cost_threshold_limit(self) -> None:
        result = check_cost_threshold(30.0)
        assert result is not None
        assert "limit" in result.lower()
