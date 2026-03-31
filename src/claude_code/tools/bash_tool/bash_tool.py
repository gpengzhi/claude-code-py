"""BashTool -- Execute shell commands.

Maps to src/tools/BashTool/BashTool.tsx in the TypeScript codebase.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from pydantic import BaseModel, Field

from claude_code.tool.base import Tool, ToolResult, ToolUseContext

logger = logging.getLogger(__name__)

MAX_TIMEOUT_MS = 600_000  # 10 minutes
DEFAULT_TIMEOUT_MS = 120_000  # 2 minutes
MAX_RESULT_SIZE = 30_000


class BashInput(BaseModel):
    command: str
    timeout: int | None = Field(
        default=None,
        description="Optional timeout in milliseconds (max 600000)",
    )
    description: str | None = Field(
        default=None,
        description="Clear, concise description of what this command does",
    )
    run_in_background: bool | None = Field(
        default=None,
        description="Set to true to run in background",
    )


class BashTool(Tool):
    name = "Bash"
    aliases = ["bash", "shell"]
    input_model = BashInput
    max_result_size_chars = MAX_RESULT_SIZE

    def get_description(self) -> str:
        return "Executes a given bash command and returns its output."

    def get_prompt(self) -> str:
        return (
            "Executes a given bash command and returns its output.\n"
            "The working directory persists between commands.\n"
            "Use this tool for system commands and terminal operations."
        )

    def is_read_only(self, input_data: BaseModel) -> bool:
        # Conservative: assume all bash commands are not read-only
        return False

    def is_concurrency_safe(self, input_data: BaseModel) -> bool:
        return self.is_read_only(input_data)

    async def call(
        self,
        args: BaseModel,
        context: ToolUseContext,
    ) -> ToolResult:
        assert isinstance(args, BashInput)

        command = args.command
        timeout_ms = min(args.timeout or DEFAULT_TIMEOUT_MS, MAX_TIMEOUT_MS)
        timeout_s = timeout_ms / 1000.0

        if not command.strip():
            return ToolResult(data="Error: empty command", is_error=True)

        cwd = str(context.cwd)
        shell = os.environ.get("SHELL", "/bin/bash")

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env={**os.environ, "TERM": "dumb"},
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout_s,
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return ToolResult(
                    data=f"Command timed out after {timeout_s:.0f}s",
                    is_error=True,
                )

            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")

            # Build output
            parts: list[str] = []
            if stdout:
                parts.append(stdout)
            if stderr:
                parts.append(f"(stderr): {stderr}")
            if proc.returncode and proc.returncode != 0:
                parts.append(f"(exit code: {proc.returncode})")

            output = "\n".join(parts) if parts else "(no output)"

            return ToolResult(
                data=output,
                is_error=proc.returncode != 0 and proc.returncode is not None,
            )

        except FileNotFoundError:
            return ToolResult(
                data=f"Shell not found: {shell}",
                is_error=True,
            )
        except PermissionError as e:
            return ToolResult(
                data=f"Permission denied: {e}",
                is_error=True,
            )
        except Exception as e:
            logger.error("BashTool execution error: %s", e)
            return ToolResult(
                data=f"Error executing command: {e}",
                is_error=True,
            )
