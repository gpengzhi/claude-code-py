"""Tests for Auth and Error handling."""

import pytest
from pathlib import Path

from claude_code.utils.auth import get_api_key_source, is_authenticated
from claude_code.services.api.errors import (
    classify_error,
    APIError,
    RateLimitError,
    AuthenticationError,
    check_cost_threshold,
)


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
