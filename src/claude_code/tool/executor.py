"""Tool executor -- the execution pipeline.

Handles: input parsing -> validation -> PreToolUse hooks -> permission check -> call -> PostToolUse hooks -> result.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from pydantic import ValidationError

from claude_code.tool.base import Tool, ToolUseContext
from claude_code.types.message import ToolResultBlock

logger = logging.getLogger(__name__)


async def execute_tool(
    tool: Tool,
    tool_input: dict[str, Any],
    tool_use_id: str,
    context: ToolUseContext,
    hooks_config: dict | None = None,
) -> ToolResultBlock:
    """Execute a single tool with full pipeline.

    Pipeline:
    1. Parse input (Pydantic validation)
    2. Custom validation (tool.validate_input)
    3. Run PreToolUse hooks
    4. Check permissions
    5. Execute (tool.call)
    6. Run PostToolUse hooks
    7. Format and truncate result
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

    # 3. Run PreToolUse hooks
    if hooks_config:
        from claude_code.hooks.events import HookEvent
        from claude_code.hooks.runner import run_hooks_for_event

        hook_results = await run_hooks_for_event(
            event=HookEvent.PRE_TOOL_USE,
            hooks_config=hooks_config,
            tool_name=tool.name,
            tool_input=tool_input,
            cwd=str(context.cwd),
        )

        for hr in hook_results:
            if hr.is_blocking:
                return ToolResultBlock(
                    tool_use_id=tool_use_id,
                    content=f"Blocked by hook: {hr.blocking_error or hr.message}",
                    is_error=True,
                )
            # Apply updated input from hooks
            if hr.updated_input:
                try:
                    parsed_input = tool.input_model.model_validate(hr.updated_input)
                    tool_input = hr.updated_input
                except ValidationError:
                    pass  # Keep original input if hook's update is invalid

    # 4. Permission check -- global permission system (matches Claude Code behavior)
    from claude_code.permissions.check import has_permissions_to_use_tool
    if context._app_state is not None:
        perm_result = has_permissions_to_use_tool(
            tool.name, tool_input, context.get_app_state().tool_permission_context,
        )
    else:
        perm_result = await tool.check_permissions(parsed_input, context)
    if hasattr(perm_result, 'behavior'):
        if perm_result.behavior == "deny":
            return ToolResultBlock(
                tool_use_id=tool_use_id,
                content=f"Permission denied: {getattr(perm_result, 'message', 'Tool not allowed')}",
                is_error=True,
            )
        elif perm_result.behavior == "ask":
            # Route through permission callback if available
            message = getattr(perm_result, 'message', f'Allow {tool.name}?')
            if context.permission_callback:
                allowed = await context.permission_callback(tool.name, tool_input, message)
                if not allowed:
                    return ToolResultBlock(
                        tool_use_id=tool_use_id,
                        content=f"Permission denied by user: {tool.name}",
                        is_error=True,
                    )
            else:
                # No callback available -- deny by default for safety
                return ToolResultBlock(
                    tool_use_id=tool_use_id,
                    content=f"Permission required but no interactive session: {tool.name}",
                    is_error=True,
                )

    # 5. Execute tool
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

    # 6. Run PostToolUse hooks
    if hooks_config:
        from claude_code.hooks.events import HookEvent
        from claude_code.hooks.runner import run_hooks_for_event

        await run_hooks_for_event(
            event=HookEvent.POST_TOOL_USE,
            hooks_config=hooks_config,
            tool_name=tool.name,
            tool_input=tool_input,
            cwd=str(context.cwd),
        )

    # 7. Format result
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
    hooks_config: dict | None = None,
) -> list[ToolResultBlock]:
    """Execute multiple read-only tools in parallel."""
    tasks = [
        execute_tool(tool, input_data, tool_use_id, context, hooks_config)
        for tool, input_data, tool_use_id in tool_calls
    ]
    return await asyncio.gather(*tasks)


async def run_tools(
    tool_use_blocks: list[Any],
    tools: list[Tool],
    context: ToolUseContext,
    hooks_config: dict | None = None,
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

        # Check concurrency safety
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
                batch_results = await execute_tools_parallel(
                    parallel_batch, context, hooks_config
                )
                results.extend(batch_results)
                parallel_batch = []
            # Run serial tool
            result = await execute_tool(
                tool, tool_input, tool_use_id, context, hooks_config
            )
            results.append(result)

    # Flush remaining parallel batch
    if parallel_batch:
        batch_results = await execute_tools_parallel(
            parallel_batch, context, hooks_config
        )
        results.extend(batch_results)

    return results
