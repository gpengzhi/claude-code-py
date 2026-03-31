"""FileReadTool -- Read file contents.

Maps to src/tools/FileReadTool/FileReadTool.ts in the TypeScript codebase.
"""

from __future__ import annotations

import logging
import mimetypes
from pathlib import Path

from pydantic import BaseModel, Field

from claude_code.tool.base import Tool, ToolResult, ToolUseContext

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico"}
BINARY_EXTENSIONS = {
    ".exe", ".dll", ".so", ".dylib", ".o", ".a", ".lib", ".bin",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    ".pyc", ".pyo", ".class", ".wasm",
}


class FileReadInput(BaseModel):
    file_path: str = Field(description="The absolute path to the file to read")
    offset: int | None = Field(
        default=None,
        ge=0,
        description="Line number to start reading from (0-indexed)",
    )
    limit: int | None = Field(
        default=None,
        gt=0,
        description="Number of lines to read",
    )


class FileReadTool(Tool):
    name = "Read"
    aliases = ["FileRead", "file_read", "ReadFile"]
    input_model = FileReadInput
    max_result_size_chars = 1_000_000  # 1MB text limit

    def get_description(self) -> str:
        return "Reads a file from the local filesystem."

    def get_prompt(self) -> str:
        return (
            "Reads a file from the local filesystem.\n"
            "- The file_path parameter must be an absolute path\n"
            "- By default, reads up to 2000 lines from the beginning\n"
            "- Use offset and limit to read specific ranges"
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
        assert isinstance(input_data, FileReadInput)
        file_path = input_data.file_path

        if not file_path:
            return "file_path is required"

        # Block dangerous device paths
        dangerous = {"/dev/zero", "/dev/random", "/dev/urandom", "/dev/stdin"}
        if file_path in dangerous:
            return f"Cannot read device path: {file_path}"

        # Check for binary extensions (except images and PDFs)
        ext = Path(file_path).suffix.lower()
        if ext in BINARY_EXTENSIONS:
            return f"Cannot read binary file ({ext}). Use a specialized tool."

        return None

    async def call(
        self,
        args: BaseModel,
        context: ToolUseContext,
    ) -> ToolResult:
        assert isinstance(args, FileReadInput)

        file_path = Path(args.file_path)

        # Resolve relative paths against cwd
        if not file_path.is_absolute():
            file_path = context.cwd / file_path

        # Check if file exists
        if not file_path.exists():
            # Try to suggest similar files
            parent = file_path.parent
            if parent.exists():
                similar = [
                    f.name
                    for f in parent.iterdir()
                    if f.name.startswith(file_path.name[:3])
                ][:5]
                if similar:
                    return ToolResult(
                        data=f"File does not exist: {args.file_path}\nSimilar files: {', '.join(similar)}",
                        is_error=True,
                    )
            return ToolResult(
                data=f"File does not exist: {args.file_path}",
                is_error=True,
            )

        if file_path.is_dir():
            return ToolResult(
                data=f"Path is a directory, not a file: {args.file_path}. Use Bash with ls instead.",
                is_error=True,
            )

        # Check if it's an image
        ext = file_path.suffix.lower()
        if ext in IMAGE_EXTENSIONS:
            return ToolResult(
                data=f"[Image file: {args.file_path} ({ext})]",
            )

        # Read text file
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except PermissionError:
            return ToolResult(
                data=f"Permission denied: {args.file_path}",
                is_error=True,
            )
        except Exception as e:
            return ToolResult(
                data=f"Error reading file: {e}",
                is_error=True,
            )

        # Apply offset and limit
        lines = content.split("\n")
        offset = args.offset or 0
        limit = args.limit or 2000

        if offset > 0:
            lines = lines[offset:]
        if limit:
            lines = lines[:limit]

        # Format with line numbers (cat -n style)
        numbered_lines = []
        for i, line in enumerate(lines, start=offset + 1):
            numbered_lines.append(f"{i}\t{line}")

        result = "\n".join(numbered_lines)

        # Track in readFileState for edit validation
        context.read_file_state[str(file_path)] = {
            "mtime": file_path.stat().st_mtime,
            "partial": args.offset is not None or args.limit is not None,
        }

        return ToolResult(data=result)
