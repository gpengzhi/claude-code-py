"""Error handling and retry logic for API calls.

"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 3
BASE_DELAY_MS = 1000
MAX_DELAY_MS = 30000

# Error categories
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 529}


class APIError(Exception):
    """Base class for API errors."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        error_type: str = "unknown",
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_type = error_type
        self.retryable = retryable


class RateLimitError(APIError):
    """Rate limit exceeded."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message, status_code=429, error_type="rate_limit", retryable=True)
        self.retry_after = retry_after


class AuthenticationError(APIError):
    """Authentication failed."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=401, error_type="authentication_failed", retryable=False)


class BillingError(APIError):
    """Billing/quota error."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=403, error_type="billing_error", retryable=False)


class ServerError(APIError):
    """Server-side error."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(message, status_code=status_code, error_type="server_error", retryable=True)


def classify_error(error: Exception) -> APIError:
    """Classify an exception into an APIError category."""
    error_str = str(error)

    # Check for anthropic SDK error types
    if hasattr(error, "status_code"):
        code = getattr(error, "status_code", None)
        if code == 401:
            return AuthenticationError(error_str)
        elif code == 403:
            return BillingError(error_str)
        elif code == 429:
            retry_after = None
            if hasattr(error, "response"):
                resp = getattr(error, "response", None)
                if resp and hasattr(resp, "headers"):
                    retry_str = resp.headers.get("retry-after")
                    if retry_str:
                        try:
                            retry_after = float(retry_str)
                        except ValueError:
                            pass
            return RateLimitError(error_str, retry_after)
        elif code and code >= 500:
            return ServerError(error_str, code)

    if "rate" in error_str.lower() and "limit" in error_str.lower():
        return RateLimitError(error_str)

    return APIError(error_str)


async def with_retry(
    func: Any,
    max_retries: int = MAX_RETRIES,
    on_retry: Any | None = None,
) -> Any:
    """Execute a function with exponential backoff retry.

    Args:
        func: Async callable to execute
        max_retries: Maximum number of retry attempts
        on_retry: Optional callback(attempt, delay, error) called before each retry
    """
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            return await func()
        except Exception as e:
            last_error = e
            api_error = classify_error(e)

            if not api_error.retryable or attempt >= max_retries:
                raise api_error from e

            # Calculate delay with exponential backoff
            if isinstance(api_error, RateLimitError) and api_error.retry_after:
                delay_s = api_error.retry_after
            else:
                delay_ms = min(BASE_DELAY_MS * (2 ** attempt), MAX_DELAY_MS)
                delay_s = delay_ms / 1000.0

            logger.warning(
                "API call failed (attempt %d/%d), retrying in %.1fs: %s",
                attempt + 1,
                max_retries + 1,
                delay_s,
                e,
            )

            if on_retry:
                await on_retry(attempt, delay_s, api_error)

            await asyncio.sleep(delay_s)

    raise last_error or APIError("Max retries exceeded")


# Cost warning thresholds
COST_WARNING_THRESHOLD = 5.0   # $5 warning
COST_LIMIT_THRESHOLD = 25.0   # $25 hard limit (configurable)


def check_cost_threshold(
    cost_usd: float,
    warning_threshold: float = COST_WARNING_THRESHOLD,
    limit_threshold: float = COST_LIMIT_THRESHOLD,
) -> str | None:
    """Check if cost has exceeded thresholds.

    Returns a warning/error message, or None.
    """
    if cost_usd >= limit_threshold:
        return f"Cost limit exceeded: ${cost_usd:.2f} >= ${limit_threshold:.2f}. Stopping."
    if cost_usd >= warning_threshold:
        return f"Warning: Cost is ${cost_usd:.2f} (threshold: ${warning_threshold:.2f})"
    return None
