"""Tests for AppState."""

from claude_code.state.app_state import AppState, get_default_app_state, update_app_state


def test_default_app_state():
    state = get_default_app_state()
    assert state.verbose is False
    assert state.main_loop_model == "claude-sonnet-4-20250514"
    assert state.tool_permission_context.mode == "default"


def test_update_app_state():
    state = get_default_app_state()
    new_state = update_app_state(state, verbose=True)
    assert new_state.verbose is True
    assert state.verbose is False  # Original unchanged


def test_app_state_with_overrides():
    state = get_default_app_state(verbose=True, fast_mode=True)
    assert state.verbose is True
    assert state.fast_mode is True
