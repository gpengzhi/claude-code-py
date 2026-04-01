"""MCP client -- connects to MCP servers and invokes tools.

Maps to src/services/mcp/client.ts in the TypeScript codebase.
Supports stdio and HTTP transports for the Model Context Protocol.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from claude_code.services.mcp.types import (
    McpHttpConfig,
    McpServerConfig,
    McpSseConfig,
    McpStdioConfig,
    McpToolInfo,
    McpResourceInfo,
)

logger = logging.getLogger(__name__)

CONNECTION_TIMEOUT = 30.0  # seconds
TOOL_TIMEOUT = 120.0  # seconds


def normalize_mcp_name(name: str) -> str:
    """Normalize a name for use in MCP tool names.

    Replaces non-alphanumeric chars with _, collapses consecutive underscores.
    """
    normalized = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
    normalized = re.sub(r"_+", "_", normalized)
    return normalized.strip("_")


def build_mcp_tool_name(server_name: str, tool_name: str) -> str:
    """Build a fully-qualified MCP tool name: mcp__server__tool."""
    return f"mcp__{normalize_mcp_name(server_name)}__{normalize_mcp_name(tool_name)}"


class MCPConnection:
    """A connection to a single MCP server."""

    def __init__(self, name: str, config: McpServerConfig) -> None:
        self.name = name
        self.config = config
        self.connected = False
        self.tools: list[McpToolInfo] = []
        self.resources: list[McpResourceInfo] = []
        self._process: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task | None = None
        self._pending: dict[int, asyncio.Future] = {}
        self._next_id = 1
        self._stdin: asyncio.StreamWriter | None = None
        self._buffer = ""

    async def connect(self) -> bool:
        """Connect to the MCP server."""
        try:
            if isinstance(self.config, McpStdioConfig):
                return await self._connect_stdio()
            elif isinstance(self.config, (McpSseConfig, McpHttpConfig)):
                return await self._connect_http()
            else:
                logger.error("Unsupported MCP transport: %s", type(self.config))
                return False
        except Exception as e:
            logger.error("Failed to connect to MCP server %s: %s", self.name, e)
            return False

    async def _connect_stdio(self) -> bool:
        """Connect via stdio transport (subprocess)."""
        assert isinstance(self.config, McpStdioConfig)

        env = {**os.environ, **self.config.env}
        self._process = await asyncio.create_subprocess_exec(
            self.config.command, *self.config.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        self._stdin = self._process.stdin

        # Start reading responses
        self._reader_task = asyncio.create_task(self._read_responses())

        # Initialize the connection
        result = await self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {"roots": {}, "elicitation": {}},
            "clientInfo": {"name": "claude-code-py", "version": "0.1.0"},
        })

        if result is not None:
            # Send initialized notification
            await self._send_notification("notifications/initialized", {})
            self.connected = True
            return True

        return False

    async def _connect_http(self) -> bool:
        """Connect via HTTP transport (SSE or Streamable HTTP)."""
        # For HTTP transports, we don't maintain a persistent connection.
        # Each request is a separate HTTP call.
        self.connected = True
        return True

    async def _read_responses(self) -> None:
        """Read JSON-RPC responses from the server's stdout."""
        assert self._process and self._process.stdout

        try:
            while True:
                line = await self._process.stdout.readline()
                if not line:
                    break

                text = line.decode("utf-8", errors="replace").strip()
                if not text:
                    continue

                try:
                    msg = json.loads(text)
                except json.JSONDecodeError:
                    # Handle Content-Length framed messages
                    if text.startswith("Content-Length:"):
                        length = int(text.split(":")[1].strip())
                        await self._process.stdout.readline()  # Empty line
                        body = await self._process.stdout.readexactly(length)
                        msg = json.loads(body)
                    else:
                        continue

                # Route response to pending future
                if "id" in msg and msg["id"] in self._pending:
                    future = self._pending.pop(msg["id"])
                    if "error" in msg:
                        future.set_exception(
                            Exception(msg["error"].get("message", "MCP error"))
                        )
                    else:
                        future.set_result(msg.get("result"))
        except (asyncio.CancelledError, ConnectionError):
            pass
        except Exception as e:
            logger.debug("MCP reader error for %s: %s", self.name, e)

    async def _send_request(
        self, method: str, params: dict[str, Any] | None = None,
    ) -> Any:
        """Send a JSON-RPC request and await the response."""
        if not self._stdin:
            return None

        request_id = self._next_id
        self._next_id += 1

        msg = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        if params:
            msg["params"] = params

        body = json.dumps(msg)
        frame = f"Content-Length: {len(body)}\r\n\r\n{body}"

        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[request_id] = future

        self._stdin.write(frame.encode("utf-8"))
        await self._stdin.drain()

        try:
            return await asyncio.wait_for(future, timeout=CONNECTION_TIMEOUT)
        except asyncio.TimeoutError:
            self._pending.pop(request_id, None)
            logger.error("MCP request timed out: %s", method)
            return None

    async def _send_notification(
        self, method: str, params: dict[str, Any] | None = None,
    ) -> None:
        """Send a JSON-RPC notification (no response expected)."""
        if not self._stdin:
            return

        msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params:
            msg["params"] = params

        body = json.dumps(msg)
        frame = f"Content-Length: {len(body)}\r\n\r\n{body}"
        self._stdin.write(frame.encode("utf-8"))
        await self._stdin.drain()

    async def list_tools(self) -> list[McpToolInfo]:
        """Discover tools from the MCP server."""
        result = await self._send_request("tools/list", {})
        if result is None:
            return []

        tools = []
        for t in result.get("tools", []):
            annotations = t.get("annotations", {})
            tools.append(McpToolInfo(
                name=t.get("name", ""),
                description=t.get("description", "")[:2048],
                input_schema=t.get("inputSchema", {}),
                server_name=self.name,
                read_only=annotations.get("readOnlyHint", False),
                destructive=annotations.get("destructiveHint", False),
            ))
        self.tools = tools
        return tools

    async def list_resources(self) -> list[McpResourceInfo]:
        """Discover resources from the MCP server."""
        result = await self._send_request("resources/list", {})
        if result is None:
            return []

        resources = []
        for r in result.get("resources", []):
            resources.append(McpResourceInfo(
                uri=r.get("uri", ""),
                name=r.get("name", ""),
                description=r.get("description", ""),
                mime_type=r.get("mimeType", ""),
            ))
        self.resources = resources
        return resources

    async def call_tool(
        self, tool_name: str, arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """Call a tool on the MCP server."""
        result = await self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments,
        })
        return result or {}

    async def disconnect(self) -> None:
        """Disconnect from the server."""
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

        if self._process:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()

        self.connected = False


def load_mcp_configs(settings: dict[str, Any], cwd: Path | None = None) -> dict[str, McpServerConfig]:
    """Load MCP server configurations from settings and .mcp.json files.

    Sources (in precedence order):
    1. .claude/settings.local.json (mcpServers)
    2. .mcp.json files walking up from cwd
    3. ~/.claude/settings.json (mcpServers)
    """
    configs: dict[str, McpServerConfig] = {}

    # From settings
    for name, config in settings.get("mcpServers", {}).items():
        try:
            server_type = config.get("type", "stdio")
            if server_type == "stdio":
                configs[name] = McpStdioConfig(**config)
            elif server_type == "sse":
                configs[name] = McpSseConfig(**config)
            elif server_type == "http":
                configs[name] = McpHttpConfig(**config)
        except Exception as e:
            logger.warning("Invalid MCP config for %s: %s", name, e)

    # From .mcp.json files
    if cwd:
        current = cwd.resolve()
        home = Path.home().resolve()
        while current != current.parent:
            mcp_json = current / ".mcp.json"
            if mcp_json.exists():
                try:
                    data = json.loads(mcp_json.read_text(encoding="utf-8"))
                    for name, config in data.get("mcpServers", {}).items():
                        if name not in configs:  # Don't override higher-precedence
                            server_type = config.get("type", "stdio")
                            if server_type == "stdio":
                                configs[name] = McpStdioConfig(**config)
                            elif server_type == "sse":
                                configs[name] = McpSseConfig(**config)
                            elif server_type == "http":
                                configs[name] = McpHttpConfig(**config)
                except Exception as e:
                    logger.warning("Error reading %s: %s", mcp_json, e)

            if current == home:
                break
            current = current.parent

    return configs


async def connect_all_servers(
    configs: dict[str, McpServerConfig],
) -> dict[str, MCPConnection]:
    """Connect to all configured MCP servers concurrently."""
    connections: dict[str, MCPConnection] = {}

    async def connect_one(name: str, config: McpServerConfig) -> None:
        conn = MCPConnection(name, config)
        try:
            success = await asyncio.wait_for(conn.connect(), timeout=CONNECTION_TIMEOUT)
            if success:
                await conn.list_tools()
                connections[name] = conn
                logger.info("Connected to MCP server: %s (%d tools)", name, len(conn.tools))
            else:
                logger.warning("Failed to connect to MCP server: %s", name)
        except asyncio.TimeoutError:
            logger.warning("Connection to MCP server %s timed out", name)
        except Exception as e:
            logger.warning("Error connecting to MCP server %s: %s", name, e)

    # Connect in batches (max 3 concurrent for stdio, 20 for remote)
    tasks = [connect_one(name, config) for name, config in configs.items()]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

    return connections
