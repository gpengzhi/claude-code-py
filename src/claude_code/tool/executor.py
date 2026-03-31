"""Tool executor -- the execution pipeline.

Maps to src/services/tools/toolExecution.ts in the TypeScript codebase.
Handles: input parsing -> validation -> permission check -> tool.call() -> result.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from pydantic import ValidationError

from claude_code.tool.base import Tool, ToolResult, ToolUseContext
from claude_code.types.message import ToolResultBlock

logger = logging.getLogger(__name__)


async def execute_tool(
    tool: Tool,
    tool_input: dict[str, Any],
    tool_use_id: str,
    context: ToolUseContext,
) -> ToolResultBlock:
    """Execute a single tool with full pipeline.

    Pipeline: parse input -> validate -> check permissions -> call -> format result.
    """
    # 1. Parse and validate input via Pydantic
    try:
        parsed_input = tool.input_model.model_validate(tool_input)
    except ValidationError as e:
        error_msg = f"Input validation error for {tool.name}: {e}"
        logger.warning(error_msg)
        return ToolResultBlock(
            tool_use_id=tool_use_id,
            content=error_msg,
            is_error=True,
        )

    # 2. Custom validation
    validation_error = await tool.validate_input(parsed_input, context)
    if validation_error:
        return ToolResultBlock(
            tool_use_id=tool_use_id,
            content=validation_error,
            is_error=True,
        )

    # 3. Permission check (basic for now -- full system in Phase 4)
    # In print mode / bypass mode, we allow everything

    # 4. Execute tool
    try:
        result = await tool.call(parsed_input, context)
    except asyncio.CancelledError:
        return ToolResultBlock(
            tool_use_id=tool_use_id,
            content="Tool execution was cancelled.",
            is_error=True,
        )
    except Exception as e:
        logger.error("Tool %s execution failed: %s", tool.name, e, exc_info=True)
        return ToolResultBlock(
            tool_use_id=tool_use_id,
            content=f"Error executing {tool.name}: {e}",
            is_error=True,
        )

    # 5. Format result
    formatted = tool.format_result(result)
    is_error = result.is_error

    if isinstance(formatted, str):
        content = formatted
    else:
        content = str(formatted)

    # Truncate if needed
    if len(content) > tool.max_result_size_chars:
        content = content[: tool.max_result_size_chars] + "\n... (truncated)"

    return ToolResultBlock(
        tool_use_id=tool_use_id,
        content=content,
        is_error=is_error,
    )


async def execute_tools_parallel(
    tool_calls: list[tuple[Tool, dict[str, Any], str]],
    context: ToolUseContext,
) -> list[ToolResultBlock]:
    """Execute multiple read-only tools in parallel."""
    tasks = [
        execute_tool(tool, input_data, tool_use_id, context)
        for tool, input_data, tool_use_id in tool_calls
    ]
    return await asyncio.gather(*tasks)


async def run_tools(
    tool_use_blocks: list[Any],
    tools: list[Tool],
    context: ToolUseContext,
) -> list[ToolResultBlock]:
    """Execute a batch of tool_use blocks, respecting concurrency rules.

    Read-only/concurrency-safe tools run in parallel.
    Other tools run serially.
    """
    tool_map = {t.name: t for t in tools}
    for t in tools:
        for alias in t.aliases:
            tool_map[alias] = t

    results: list[ToolResultBlock] = []
    parallel_batch: list[tuple[Tool, dict[str, Any], str]] = []

    for block in tool_use_blocks:
        tool_name = block.name if hasattr(block, "name") else block.get("name", "")
        tool_input = block.input if hasattr(block, "input") else block.get("input", {})
        tool_use_id = block.id if hasattr(block, "id") else block.get("id", "")

        tool = tool_map.get(tool_name)
        if tool is None:
            results.append(
                ToolResultBlock(
                    tool_use_id=tool_use_id,
                    content=f"Unknown tool: {tool_name}",
                    is_error=True,
                )
            )
            continue

        # Try to parse input for concurrency check
        try:
            parsed = tool.input_model.model_validate(tool_input)
            is_safe = tool.is_concurrency_safe(parsed)
        except Exception:
            is_safe = False

        if is_safe:
            parallel_batch.append((tool, tool_input, tool_use_id))
        else:
            # Flush any pending parallel batch first
            if parallel_batch:
                batch_results = await execute_tools_parallel(parallel_batch, context)
                results.extend(batch_results)
                parallel_batch = []
            # Run serial tool
            result = await execute_tool(tool, tool_input, tool_use_id, context)
            results.append(result)

    # Flush remaining parallel batch
    if parallel_batch:
        batch_results = await execute_tools_parallel(parallel_batch, context)
        results.extend(batch_results)

    return results
