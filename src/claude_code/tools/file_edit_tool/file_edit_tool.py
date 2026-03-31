"""FileEditTool -- Edit existing files via old_string/new_string replacement.

Maps to src/tools/FileEditTool/FileEditTool.ts in the TypeScript codebase.
"""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import BaseModel, Field

from claude_code.tool.base import Tool, ToolResult, ToolUseContext

logger = logging.getLogger(__name__)


class FileEditInput(BaseModel):
    file_path: str = Field(description="The absolute path to the file to modify")
    old_string: str = Field(description="The text to replace")
    new_string: str = Field(description="The replacement text (must differ from old_string)")
    replace_all: bool = Field(default=False, description="Replace all occurrences")


class FileEditTool(Tool):
    name = "Edit"
    aliases = ["FileEdit", "file_edit"]
    input_model = FileEditInput
    max_result_size_chars = 100_000

    def get_description(self) -> str:
        return "Performs exact string replacements in files."

    def get_prompt(self) -> str:
        return (
            "Performs exact string replacements in files.\n"
            "- The file must have been read first using the Read tool\n"
            "- old_string must be unique in the file (or use replace_all)\n"
            "- old_string and new_string must be different"
        )

    async def validate_input(
        self,
        input_data: BaseModel,
        context: ToolUseContext,
    ) -> str | None:
        assert isinstance(input_data, FileEditInput)

        if input_data.old_string == input_data.new_string:
            return "old_string and new_string must be different"

        file_path = Path(input_data.file_path)
        if not file_path.is_absolute():
            file_path = context.cwd / file_path

        if not file_path.exists():
            return f"File does not exist: {input_data.file_path}"

        # Check if file was read first
        state = context.read_file_state.get(str(file_path))
        if state is None:
            return (
                f"You must read the file before editing it. "
                f"Use the Read tool to read {input_data.file_path} first."
            )

        # Check for stale file (modified since last read)
        try:
            current_mtime = file_path.stat().st_mtime
            if current_mtime != state.get("mtime"):
                return (
                    f"File has been modified since last read. "
                    f"Please re-read {input_data.file_path} before editing."
                )
        except OSError:
            pass

        return None

    async def call(
        self,
        args: BaseModel,
        context: ToolUseContext,
    ) -> ToolResult:
        assert isinstance(args, FileEditInput)

        file_path = Path(args.file_path)
        if not file_path.is_absolute():
            file_path = context.cwd / file_path

        # Read current content
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return ToolResult(data=f"Error reading file: {e}", is_error=True)

        old_string = args.old_string
        new_string = args.new_string

        # Check if old_string exists in file
        if old_string not in content:
            # Try to find a close match for better error message
            return ToolResult(
                data=f"The old_string was not found in {args.file_path}. "
                f"Make sure the string matches exactly, including whitespace and indentation.",
                is_error=True,
            )

        # Check uniqueness (unless replace_all)
        if not args.replace_all:
            count = content.count(old_string)
            if count > 1:
                return ToolResult(
                    data=f"The old_string appears {count} times in {args.file_path}. "
                    f"Provide more context to make it unique, or set replace_all=true.",
                    is_error=True,
                )

        # Apply replacement
        if args.replace_all:
            new_content = content.replace(old_string, new_string)
        else:
            new_content = content.replace(old_string, new_string, 1)

        # Write back
        try:
            file_path.write_text(new_content, encoding="utf-8")
        except Exception as e:
            return ToolResult(data=f"Error writing file: {e}", is_error=True)

        # Update read state
        context.read_file_state[str(file_path)] = {
            "mtime": file_path.stat().st_mtime,
            "partial": False,
        }

        # Generate a simple diff summary
        if args.replace_all:
            count = content.count(old_string)
            return ToolResult(
                data=f"Replaced {count} occurrence(s) in {args.file_path}"
            )
        else:
            return ToolResult(
                data=f"Successfully edited {args.file_path}"
            )
