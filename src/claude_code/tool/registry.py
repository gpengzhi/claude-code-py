"""Tool registry.

Maps to src/tools.ts in the TypeScript codebase.
Registers all built-in tools and provides lookup functions.
"""

from __future__ import annotations

from typing import Any

from claude_code.tool.base import Tool


def get_all_base_tools() -> list[Tool]:
    """Get all built-in tools.

    Maps to getAllBaseTools() in the TypeScript codebase.
    """
    from claude_code.tools.bash_tool.bash_tool import BashTool
    from claude_code.tools.file_edit_tool.file_edit_tool import FileEditTool
    from claude_code.tools.file_read_tool.file_read_tool import FileReadTool
    from claude_code.tools.file_write_tool.file_write_tool import FileWriteTool
    from claude_code.tools.glob_tool.glob_tool import GlobTool
    from claude_code.tools.grep_tool.grep_tool import GrepTool

    # Extended tools
    from claude_code.tools.web_fetch_tool.web_fetch_tool import WebFetchTool
    from claude_code.tools.agent_tool.agent_tool import AgentTool
    from claude_code.tools.task_tools.task_tools import TaskCreateTool, TaskGetTool, TaskUpdateTool, TaskListTool
    from claude_code.tools.plan_tools.enter_plan_mode import EnterPlanModeTool
    from claude_code.tools.plan_tools.exit_plan_mode import ExitPlanModeTool
    from claude_code.tools.ask_user_question_tool.ask_user_question_tool import AskUserQuestionTool
    from claude_code.tools.skill_tool.skill_tool import SkillTool

    return [
        # Core tools
        BashTool(),
        FileReadTool(),
        FileEditTool(),
        FileWriteTool(),
        GlobTool(),
        GrepTool(),
        # Extended tools
        WebFetchTool(),
        AgentTool(),
        TaskCreateTool(),
        TaskGetTool(),
        TaskUpdateTool(),
        TaskListTool(),
        EnterPlanModeTool(),
        ExitPlanModeTool(),
        AskUserQuestionTool(),
        SkillTool(),
    ]


def get_tools() -> list[Tool]:
    """Get the filtered list of enabled tools."""
    return [t for t in get_all_base_tools() if t.is_enabled()]


def get_tools_with_mcp(
    mcp_connections: dict[str, Any] | None = None,
) -> list[Tool]:
    """Get enabled tools plus MCP-discovered tools."""
    tools = get_tools()

    if mcp_connections:
        from claude_code.services.mcp.client import build_mcp_tool_name
        from claude_code.tools.mcp_tool.mcp_tool import MCPTool

        for conn_name, conn in mcp_connections.items():
            for mcp_tool in conn.tools:
                fq_name = build_mcp_tool_name(conn_name, mcp_tool.name)
                tools.append(MCPTool(
                    tool_name=fq_name,
                    server_name=conn_name,
                    description=mcp_tool.description,
                    input_schema=mcp_tool.input_schema,
                    connection=conn,
                    read_only=mcp_tool.read_only,
                    destructive=mcp_tool.destructive,
                ))

    return tools


def find_tool_by_name(tools: list[Tool], name: str) -> Tool | None:
    """Find a tool by name or alias."""
    for tool in tools:
        if tool.name == name or name in tool.aliases:
            return tool
    return None
