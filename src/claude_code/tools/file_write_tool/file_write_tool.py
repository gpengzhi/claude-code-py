"""FileWriteTool -- Write/create files.

Maps to src/tools/FileWriteTool/FileWriteTool.ts in the TypeScript codebase.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from pydantic import BaseModel, Field

from claude_code.tool.base import Tool, ToolResult, ToolUseContext

logger = logging.getLogger(__name__)


class FileWriteInput(BaseModel):
    file_path: str = Field(description="The absolute path to the file to write")
    content: str = Field(description="The content to write to the file")


class FileWriteTool(Tool):
    name = "Write"
    aliases = ["FileWrite", "file_write"]
    input_model = FileWriteInput
    max_result_size_chars = 100_000

    def get_description(self) -> str:
        return "Writes a file to the local filesystem."

    def get_prompt(self) -> str:
        return (
            "Writes a file to the local filesystem.\n"
            "- This tool will overwrite existing files\n"
            "- If the file exists, you MUST read it first\n"
            "- Prefer the Edit tool for modifying existing files"
        )

    async def validate_input(
        self,
        input_data: BaseModel,
        context: ToolUseContext,
    ) -> str | None:
        assert isinstance(input_data, FileWriteInput)

        file_path = Path(input_data.file_path)
        if not file_path.is_absolute():
            file_path = context.cwd / file_path

        # If file exists, it should have been read first
        if file_path.exists():
            state = context.read_file_state.get(str(file_path))
            if state is None:
                return (
                    f"File already exists: {input_data.file_path}. "
                    f"You must read it first with the Read tool before overwriting."
                )

        return None

    async def call(
        self,
        args: BaseModel,
        context: ToolUseContext,
    ) -> ToolResult:
        assert isinstance(args, FileWriteInput)

        file_path = Path(args.file_path)
        if not file_path.is_absolute():
            file_path = context.cwd / file_path

        is_new = not file_path.exists()

        # Create parent directories if needed
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return ToolResult(
                data=f"Error creating directory {file_path.parent}: {e}",
                is_error=True,
            )

        # Write the file
        try:
            file_path.write_text(args.content, encoding="utf-8")
        except PermissionError:
            return ToolResult(
                data=f"Permission denied: {args.file_path}",
                is_error=True,
            )
        except Exception as e:
            return ToolResult(
                data=f"Error writing file: {e}",
                is_error=True,
            )

        # Update read state
        context.read_file_state[str(file_path)] = {
            "mtime": file_path.stat().st_mtime,
            "partial": False,
        }

        action = "Created" if is_new else "Updated"
        line_count = args.content.count("\n") + 1
        return ToolResult(
            data=f"{action} {args.file_path} ({line_count} lines)"
        )
