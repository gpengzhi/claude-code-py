"""Anthropic API client wrapper.

Maps to src/services/api/client.ts in the TypeScript codebase.
Handles client creation for different providers (direct API, Bedrock, Vertex).
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from anthropic import AsyncAnthropic


def get_api_key() -> str | None:
    """Get the Anthropic API key from environment."""
    return os.environ.get("ANTHROPIC_API_KEY")


def get_api_provider() -> str:
    """Determine the API provider from environment."""
    if os.environ.get("ANTHROPIC_BEDROCK_BASE_URL") or os.environ.get(
        "AWS_REGION"
    ):
        return "bedrock"
    if os.environ.get("ANTHROPIC_VERTEX_PROJECT_ID") or os.environ.get(
        "CLOUD_ML_PROJECT_ID"
    ):
        return "vertex"
    return "anthropic"


@lru_cache(maxsize=1)
def get_anthropic_client() -> AsyncAnthropic:
    """Get or create the Anthropic async client (singleton)."""
    from anthropic import AsyncAnthropic

    provider = get_api_provider()

    if provider == "bedrock":
        from anthropic import AsyncAnthropicBedrock

        return AsyncAnthropicBedrock()  # type: ignore[return-value]

    if provider == "vertex":
        from anthropic import AsyncAnthropicVertex

        project_id = os.environ.get(
            "ANTHROPIC_VERTEX_PROJECT_ID",
            os.environ.get("CLOUD_ML_PROJECT_ID", ""),
        )
        region = os.environ.get("CLOUD_ML_REGION", "us-east5")
        return AsyncAnthropicVertex(project_id=project_id, region=region)  # type: ignore[return-value]

    # Direct Anthropic API
    api_key = get_api_key()
    base_url = os.environ.get("ANTHROPIC_BASE_URL")

    return AsyncAnthropic(
        api_key=api_key or "",
        base_url=base_url,
    )
