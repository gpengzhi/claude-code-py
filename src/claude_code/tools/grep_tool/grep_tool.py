"""GrepTool -- Content search via ripgrep.

"""

from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from claude_code.tool.base import Tool, ToolResult, ToolUseContext

logger = logging.getLogger(__name__)

DEFAULT_HEAD_LIMIT = 250
VCS_DIRS = [".git", ".svn", ".hg", ".bzr", ".jj", ".sl"]


class GrepInput(BaseModel):
    pattern: str = Field(description="The regex pattern to search for")
    path: str | None = Field(
        default=None,
        description="File or directory to search in. Defaults to cwd.",
    )
    glob: str | None = Field(
        default=None,
        description="Glob pattern to filter files (e.g. '*.py')",
    )
    output_mode: Literal["content", "files_with_matches", "count"] | None = Field(
        default=None,
        description="Output mode. Defaults to 'files_with_matches'.",
    )
    context: int | None = Field(default=None, alias="-C", description="Context lines")
    before: int | None = Field(default=None, alias="-B", description="Lines before match")
    after: int | None = Field(default=None, alias="-A", description="Lines after match")
    case_insensitive: bool | None = Field(default=None, alias="-i")
    line_numbers: bool | None = Field(default=None, alias="-n")
    type: str | None = Field(default=None, description="File type filter (e.g. 'py', 'js')")
    head_limit: int | None = Field(default=None, description="Max output entries")
    offset: int | None = Field(default=None, description="Skip first N entries")
    multiline: bool | None = Field(default=None, description="Enable multiline mode")

    model_config = {"populate_by_name": True}


class GrepTool(Tool):
    name = "Grep"
    aliases = ["grep", "search", "rg"]
    input_model = GrepInput
    max_result_size_chars = 20_000

    def get_description(self) -> str:
        return "A powerful search tool built on ripgrep."

    def get_prompt(self) -> str:
        return (
            "A powerful search tool built on ripgrep.\n"
            "- Supports full regex syntax\n"
            "- Filter files with glob or type parameter\n"
            "- Output modes: 'content', 'files_with_matches' (default), 'count'"
        )

    def is_read_only(self, input_data: BaseModel) -> bool:
        return True

    def is_concurrency_safe(self, input_data: BaseModel) -> bool:
        return True

    async def call(
        self,
        args: BaseModel,
        context: ToolUseContext,
    ) -> ToolResult:
        assert isinstance(args, GrepInput)

        search_path = args.path or str(context.cwd)
        output_mode = args.output_mode or "files_with_matches"
        head_limit = args.head_limit if args.head_limit is not None else DEFAULT_HEAD_LIMIT
        offset = args.offset or 0

        # Check if ripgrep is available
        rg_path = shutil.which("rg")
        if rg_path is None:
            return await self._fallback_grep(args, context)

        # Build ripgrep command
        cmd = [rg_path]

        # Output mode
        if output_mode == "files_with_matches":
            cmd.append("--files-with-matches")
        elif output_mode == "count":
            cmd.append("--count")
        # content mode is default (no flag)

        # Search hidden files (matches TS --hidden flag)
        cmd.append("--hidden")

        # Limit line length to prevent base64/minified lines flooding output
        cmd.extend(["--max-columns", "500"])

        # VCS exclusions
        for vcs_dir in VCS_DIRS:
            cmd.extend(["--glob", f"!{vcs_dir}/"])

        # Options
        if args.case_insensitive:
            cmd.append("-i")
        if output_mode == "content" and (args.line_numbers is not False):
            cmd.append("-n")
        if args.before:
            cmd.extend(["-B", str(args.before)])
        if args.after:
            cmd.extend(["-A", str(args.after)])
        if args.context:
            cmd.extend(["-C", str(args.context)])
        if args.glob:
            cmd.extend(["--glob", args.glob])
        if args.type:
            cmd.extend(["--type", args.type])
        if args.multiline:
            cmd.extend(["-U", "--multiline-dotall"])

        # Pattern -- use -e when pattern starts with - to avoid flag confusion
        if args.pattern.startswith("-"):
            cmd.extend(["-e", args.pattern])
        else:
            cmd.append(args.pattern)
        cmd.append(search_path)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=30.0,
            )

            stdout = stdout_bytes.decode("utf-8", errors="replace")

            # ripgrep returns exit code 1 for "no matches" (not an error)
            if proc.returncode and proc.returncode > 1:
                stderr = stderr_bytes.decode("utf-8", errors="replace")
                return ToolResult(
                    data=f"Grep error: {stderr}",
                    is_error=True,
                )

            if not stdout.strip():
                return ToolResult(data="No matches found")

            # Apply offset and head_limit
            lines = stdout.rstrip("\n").split("\n")
            if offset > 0:
                lines = lines[offset:]
            if head_limit > 0:
                lines = lines[:head_limit]

            # Relativize paths
            cwd_str = str(context.cwd)
            result_lines = []
            for line in lines:
                if line.startswith(cwd_str + "/"):
                    line = line[len(cwd_str) + 1 :]
                result_lines.append(line)

            return ToolResult(data="\n".join(result_lines))

        except asyncio.TimeoutError:
            return ToolResult(
                data="Grep timed out after 30 seconds",
                is_error=True,
            )
        except Exception as e:
            return ToolResult(
                data=f"Grep error: {e}",
                is_error=True,
            )

    async def _fallback_grep(
        self,
        args: GrepInput,
        context: ToolUseContext,
    ) -> ToolResult:
        """Fallback to Python re module when ripgrep is not available."""
        import re

        search_path = Path(args.path) if args.path else context.cwd
        if not search_path.is_absolute():
            search_path = context.cwd / search_path

        try:
            flags = re.MULTILINE
            if args.case_insensitive:
                flags |= re.IGNORECASE
            if args.multiline:
                flags |= re.DOTALL
            regex = re.compile(args.pattern, flags)
        except re.error as e:
            return ToolResult(data=f"Invalid regex: {e}", is_error=True)

        matches: list[str] = []
        glob_pattern = args.glob or "**/*"

        try:
            for file_path in search_path.glob(glob_pattern):
                if not file_path.is_file():
                    continue
                if any(part.startswith(".") for part in file_path.parts):
                    continue
                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                    if regex.search(content):
                        rel = str(file_path.relative_to(context.cwd))
                        matches.append(rel)
                except (PermissionError, OSError):
                    continue

                if len(matches) >= DEFAULT_HEAD_LIMIT:
                    break

        except Exception as e:
            return ToolResult(data=f"Search error: {e}", is_error=True)

        if not matches:
            return ToolResult(data="No matches found")

        return ToolResult(data="\n".join(matches))
