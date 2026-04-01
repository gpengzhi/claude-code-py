"""Streaming tool executor -- starts tools while model is still streaming.

Maps to src/services/tools/StreamingToolExecutor.ts in the TypeScript codebase.
When a tool_use block completes during streaming, we can start executing it
immediately instead of waiting for the full response.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from claude_code.tool.base import Tool, ToolUseContext
from claude_code.tool.executor import execute_tool
from claude_code.types.message import ToolResultBlock, ToolUseBlock

logger = logging.getLogger(__name__)


class StreamingToolExecutor:
    """Executes tools as they arrive during streaming.

    Usage:
        executor = StreamingToolExecutor(tools, context)
        # During streaming, when a tool_use block completes:
        executor.submit(tool_use_block)
        # After streaming finishes:
        results = await executor.get_remaining_results()
    """

    def __init__(
        self,
        tools: list[Tool],
        context: ToolUseContext,
        hooks_config: dict | None = None,
    ) -> None:
        self._tool_map = {t.name: t for t in tools}
        for t in tools:
            for alias in t.aliases:
                self._tool_map[alias] = t
        self._context = context
        self._hooks_config = hooks_config
        self._pending: dict[str, asyncio.Task[ToolResultBlock]] = {}
        self._completed: dict[str, ToolResultBlock] = {}

    def submit(self, block: ToolUseBlock) -> None:
        """Submit a tool_use block for immediate execution.

        Only read-only/concurrency-safe tools are started during streaming.
        Write tools are queued and executed after streaming completes.
        """
        tool = self._tool_map.get(block.name)
        if tool is None:
            self._completed[block.id] = ToolResultBlock(
                tool_use_id=block.id,
                content=f"Unknown tool: {block.name}",
                is_error=True,
            )
            return

        # Check if safe to execute during streaming
        try:
            parsed = tool.input_model.model_validate(block.input)
            is_safe = tool.is_concurrency_safe(parsed)
        except Exception:
            is_safe = False

        if is_safe:
            # Start execution immediately
            task = asyncio.create_task(
                execute_tool(
                    tool, block.input, block.id,
                    self._context, self._hooks_config,
                )
            )
            self._pending[block.id] = task
            logger.debug("Started streaming execution of %s (id=%s)", block.name, block.id)

    async def get_results(self, tool_use_blocks: list[ToolUseBlock]) -> list[ToolResultBlock]:
        """Get results for all tool_use blocks.

        For tools already started during streaming, await their completion.
        For remaining tools, execute them now (respecting concurrency rules).
        """
        results: list[ToolResultBlock] = []

        for block in tool_use_blocks:
            # Already completed (e.g., unknown tool error)
            if block.id in self._completed:
                results.append(self._completed[block.id])
                continue

            # Started during streaming -- await it
            if block.id in self._pending:
                try:
                    result = await self._pending[block.id]
                    results.append(result)
                except Exception as e:
                    results.append(ToolResultBlock(
                        tool_use_id=block.id,
                        content=f"Error: {e}",
                        is_error=True,
                    ))
                continue

            # Not started yet -- execute now
            tool = self._tool_map.get(block.name)
            if tool is None:
                results.append(ToolResultBlock(
                    tool_use_id=block.id,
                    content=f"Unknown tool: {block.name}",
                    is_error=True,
                ))
            else:
                result = await execute_tool(
                    tool, block.input, block.id,
                    self._context, self._hooks_config,
                )
                results.append(result)

        return results

    def cancel_all(self) -> None:
        """Cancel all pending tool executions."""
        for task in self._pending.values():
            if not task.done():
                task.cancel()
