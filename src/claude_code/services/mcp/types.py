"""MCP types.

Maps to src/services/mcp/types.ts in the TypeScript codebase.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


TransportType = Literal["stdio", "sse", "http"]

ConfigScope = Literal["local", "user", "project", "dynamic", "enterprise", "plugin"]


class McpStdioConfig(BaseModel):
    """Configuration for a stdio-based MCP server."""
    type: Literal["stdio"] = "stdio"
    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)


class McpSseConfig(BaseModel):
    """Configuration for an SSE-based MCP server."""
    type: Literal["sse"] = "sse"
    url: str
    headers: dict[str, str] = Field(default_factory=dict)


class McpHttpConfig(BaseModel):
    """Configuration for a Streamable HTTP MCP server."""
    type: Literal["http"] = "http"
    url: str
    headers: dict[str, str] = Field(default_factory=dict)


McpServerConfig = McpStdioConfig | McpSseConfig | McpHttpConfig


class McpToolInfo(BaseModel):
    """Information about a tool provided by an MCP server."""
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=dict)
    server_name: str = ""
    read_only: bool = False
    destructive: bool = False


class McpResourceInfo(BaseModel):
    """Information about a resource provided by an MCP server."""
    uri: str
    name: str = ""
    description: str = ""
    mime_type: str = ""
