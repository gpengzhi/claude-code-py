"""Hook runner -- executes hooks.

Supports command (shell), prompt (LLM), and http (webhook) hook types.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

import aiohttp

from claude_code.hooks.config import HookMatcher
from claude_code.hooks.events import HookEvent

logger = logging.getLogger(__name__)

DEFAULT_HOOK_TIMEOUT = 60.0  # seconds


class HookResult:
    """Result from running a hook."""

    def __init__(
        self,
        outcome: str = "success",  # success, blocking, non_blocking_error, cancelled
        message: str | None = None,
        blocking_error: str | None = None,
        updated_input: dict[str, Any] | None = None,
        permission_behavior: str | None = None,  # allow, deny, ask
    ) -> None:
        self.outcome = outcome
        self.message = message
        self.blocking_error = blocking_error
        self.updated_input = updated_input
        self.permission_behavior = permission_behavior

    @property
    def is_blocking(self) -> bool:
        return self.outcome == "blocking"


async def run_hook(
    hook_def: dict[str, Any],
    context: dict[str, Any],
) -> HookResult:
    """Run a single hook definition."""
    hook_type = hook_def.get("type", "command")
    timeout = hook_def.get("timeout", DEFAULT_HOOK_TIMEOUT)

    try:
        if hook_type == "command":
            return await _run_command_hook(hook_def, context, timeout)
        elif hook_type == "http":
            return await _run_http_hook(hook_def, context, timeout)
        elif hook_type == "prompt":
            logger.warning("Prompt hooks are not supported (requires LLM integration)")
            return HookResult(
                outcome="non_blocking_error",
                message="Prompt hooks are not implemented. Use 'command' or 'http' hook types.",
            )
        else:
            logger.warning("Unknown hook type: %s", hook_type)
            return HookResult(outcome="non_blocking_error", message=f"Unknown hook type: {hook_type}")
    except asyncio.TimeoutError:
        return HookResult(outcome="non_blocking_error", message=f"Hook timed out after {timeout}s")
    except Exception as e:
        logger.error("Hook execution failed: %s", e)
        return HookResult(outcome="non_blocking_error", message=str(e))


async def _run_command_hook(
    hook_def: dict[str, Any],
    context: dict[str, Any],
    timeout: float,
) -> HookResult:
    """Run a shell command hook."""
    command = hook_def.get("command", "")
    if not command:
        return HookResult(outcome="non_blocking_error", message="Empty command")

    # Build environment with hook context
    env = {**os.environ}
    env["CLAUDE_TOOL_NAME"] = context.get("tool_name", "")
    env["CLAUDE_TOOL_INPUT"] = json.dumps(context.get("tool_input", {}))
    env["CLAUDE_HOOK_EVENT"] = context.get("event", "")

    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
        cwd=context.get("cwd"),
    )

    stdout_bytes, stderr_bytes = await asyncio.wait_for(
        proc.communicate(), timeout=timeout
    )

    stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
    stderr = stderr_bytes.decode("utf-8", errors="replace").strip()

    if proc.returncode != 0:
        # Non-zero exit = blocking error (hook rejected the action)
        error_msg = stderr or stdout or f"Hook exited with code {proc.returncode}"
        return HookResult(outcome="blocking", blocking_error=error_msg)

    # Try to parse JSON output for structured response
    if stdout:
        try:
            response = json.loads(stdout)
            return HookResult(
                outcome=response.get("outcome", "success"),
                message=response.get("message"),
                blocking_error=response.get("blockingError"),
                updated_input=response.get("updatedInput"),
                permission_behavior=response.get("permissionDecision", {}).get("behavior"),
            )
        except json.JSONDecodeError:
            pass

    return HookResult(outcome="success", message=stdout if stdout else None)


async def _run_http_hook(
    hook_def: dict[str, Any],
    context: dict[str, Any],
    timeout: float,
) -> HookResult:
    """Run an HTTP webhook hook."""
    url = hook_def.get("url", "")
    if not url:
        return HookResult(outcome="non_blocking_error", message="Empty URL")

    headers = hook_def.get("headers", {})
    payload = {
        "event": context.get("event", ""),
        "tool_name": context.get("tool_name", ""),
        "tool_input": context.get("tool_input", {}),
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                if resp.status >= 400:
                    return HookResult(
                        outcome="blocking",
                        blocking_error=f"Webhook returned {resp.status}",
                    )
                try:
                    body = await resp.json()
                    return HookResult(
                        outcome=body.get("outcome", "success"),
                        message=body.get("message"),
                        blocking_error=body.get("blockingError"),
                    )
                except Exception:
                    return HookResult(outcome="success")
    except aiohttp.ClientError as e:
        return HookResult(outcome="non_blocking_error", message=str(e))


async def run_hooks_for_event(
    event: HookEvent,
    hooks_config: dict[HookEvent, list[HookMatcher]],
    tool_name: str = "",
    tool_input: dict[str, Any] | None = None,
    cwd: str | None = None,
) -> list[HookResult]:
    """Run all hooks that match a given event and tool."""
    matchers = hooks_config.get(event, [])
    if not matchers:
        return []

    context = {
        "event": event.value,
        "tool_name": tool_name,
        "tool_input": tool_input or {},
        "cwd": cwd,
    }

    results: list[HookResult] = []
    for matcher in matchers:
        if not matcher.matches_tool(tool_name, tool_input or {}):
            continue

        for hook_def in matcher.hooks:
            result = await run_hook(hook_def, context)
            results.append(result)

            # Stop on blocking result
            if result.is_blocking:
                return results

    return results
