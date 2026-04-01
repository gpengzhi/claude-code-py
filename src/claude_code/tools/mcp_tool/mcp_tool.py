"""MCP Tool wrapper -- wraps MCP server tools as native tools.

Maps to the MCP tool integration in the TypeScript codebase.
Allows tools discovered from MCP servers to be used like built-in tools.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, create_model

from claude_code.tool.base import Tool, ToolResult, ToolUseContext

logger = logging.getLogger(__name__)


class MCPTool(Tool):
    """A tool that delegates to an MCP server.

    Dynamically created from MCP server tool discovery.
    """

    def __init__(
        self,
        tool_name: str,
        server_name: str,
        description: str,
        input_schema: dict[str, Any],
        connection: Any,  # MCPConnection
        read_only: bool = False,
        destructive: bool = False,
    ) -> None:
        self.name = tool_name
        self._server_name = server_name
        self._description = description
        self._connection = connection
        self._read_only = read_only
        self._destructive = destructive
        self._raw_tool_name = tool_name.split("__")[-1] if "__" in tool_name else tool_name

        # Build a dynamic Pydantic model from the MCP input schema
        self.input_model = _build_model_from_schema(tool_name, input_schema)

    def get_description(self) -> str:
        return self._description

    def get_prompt(self) -> str:
        return f"MCP tool from server '{self._server_name}': {self._description}"

    def is_read_only(self, input_data: BaseModel) -> bool:
        return self._read_only

    def is_concurrency_safe(self, input_data: BaseModel) -> bool:
        return self._read_only

    def is_destructive(self, input_data: BaseModel) -> bool:
        return self._destructive

    async def call(
        self,
        args: BaseModel,
        context: ToolUseContext,
    ) -> ToolResult:
        try:
            arguments = args.model_dump(exclude_none=True)
            result = await self._connection.call_tool(self._raw_tool_name, arguments)

            # MCP results have a "content" field with text/image blocks
            content = result.get("content", [])
            if isinstance(content, list):
                text_parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                return ToolResult(data="\n".join(text_parts) if text_parts else str(result))

            return ToolResult(data=str(content))
        except Exception as e:
            logger.error("MCP tool %s error: %s", self.name, e)
            return ToolResult(data=f"MCP tool error: {e}", is_error=True)


def _build_model_from_schema(name: str, schema: dict[str, Any]) -> type[BaseModel]:
    """Build a Pydantic model from a JSON Schema."""
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))

    fields: dict[str, Any] = {}
    for prop_name, prop_schema in properties.items():
        python_type = _json_type_to_python(prop_schema.get("type", "string"))
        default = ... if prop_name in required else None
        fields[prop_name] = (python_type if prop_name in required else python_type | None, default)

    if not fields:
        # Empty schema -- accept any kwargs
        return BaseModel

    model_name = f"MCPInput_{name.replace('-', '_').replace('.', '_')}"
    return create_model(model_name, **fields)


def _json_type_to_python(json_type: str) -> type:
    """Map JSON Schema types to Python types."""
    mapping = {
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "object": dict,
        "array": list,
    }
    return mapping.get(json_type, str)
