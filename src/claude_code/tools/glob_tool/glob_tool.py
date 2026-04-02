"""GlobTool -- File pattern matching.

Maps to src/tools/GlobTool/GlobTool.ts in the TypeScript codebase.
"""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import BaseModel, Field

from claude_code.tool.base import Tool, ToolResult, ToolUseContext

logger = logging.getLogger(__name__)

DEFAULT_MAX_RESULTS = 100
IGNORE_DIRS = {".git", ".svn", ".hg", "node_modules", "__pycache__", ".venv", "venv"}


class GlobInput(BaseModel):
    pattern: str = Field(description="The glob pattern to match files against")
    path: str | None = Field(
        default=None,
        description="The directory to search in. Defaults to current working directory.",
    )


class GlobTool(Tool):
    name = "Glob"
    aliases = ["glob", "find_files"]
    input_model = GlobInput
    max_result_size_chars = 100_000

    def get_description(self) -> str:
        return "Fast file pattern matching tool that works with any codebase size."

    def get_prompt(self) -> str:
        return (
            "Fast file pattern matching tool.\n"
            "- Supports glob patterns like '**/*.py' or 'src/**/*.ts'\n"
            "- Returns matching file paths sorted by modification time\n"
            "- Use this when you need to find files by name patterns"
        )

    def is_read_only(self, input_data: BaseModel) -> bool:
        return True

    def is_concurrency_safe(self, input_data: BaseModel) -> bool:
        return True

    async def validate_input(
        self,
        input_data: BaseModel,
        context: ToolUseContext,
    ) -> str | None:
        assert isinstance(input_data, GlobInput)

        if input_data.path:
            search_path = Path(input_data.path)
            if not search_path.is_absolute():
                search_path = context.cwd / search_path
            if not search_path.exists():
                return f"Directory does not exist: {input_data.path}"
            if not search_path.is_dir():
                return f"Path is not a directory: {input_data.path}"

        return None

    async def call(
        self,
        args: BaseModel,
        context: ToolUseContext,
    ) -> ToolResult:
        assert isinstance(args, GlobInput)

        search_path = Path(args.path) if args.path else context.cwd
        if not search_path.is_absolute():
            search_path = context.cwd / search_path

        pattern = args.pattern

        try:
            # Use wcmatch for advanced glob support
            from wcmatch import glob as wcglob

            matches = wcglob.glob(
                pattern,
                root_dir=str(search_path),
                flags=wcglob.GLOBSTAR | wcglob.DOTGLOB,
            )

            # Filter out ignored directories, sort by mtime (newest first)
            results: list[tuple[float, str]] = []
            for match in matches:
                full_path = search_path / match
                # Skip ignored directories
                parts = Path(match).parts
                if any(part in IGNORE_DIRS for part in parts):
                    continue
                try:
                    mtime = full_path.stat().st_mtime
                    # Return relative paths
                    results.append((mtime, match))
                except OSError:
                    results.append((0, match))

            results.sort(key=lambda x: x[0], reverse=True)

            # Limit results
            truncated = len(results) > DEFAULT_MAX_RESULTS
            results = results[:DEFAULT_MAX_RESULTS]

            if not results:
                return ToolResult(data="No files found")

            filenames = [r[1] for r in results]
            output = "\n".join(filenames)
            if truncated:
                output += f"\n\n(Results truncated. Showing {DEFAULT_MAX_RESULTS} of {len(results)} matches.)"

            return ToolResult(data=output)

        except Exception as e:
            return ToolResult(
                data=f"Error running glob: {e}",
                is_error=True,
            )
