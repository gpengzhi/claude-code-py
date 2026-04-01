"""FileEditTool -- Edit existing files via old_string/new_string replacement.

Maps to src/tools/FileEditTool/FileEditTool.ts in the TypeScript codebase.
Supports encoding detection, line-ending preservation, and quote normalization.
"""

from __future__ import annotations

import difflib
import logging
from pathlib import Path

from pydantic import BaseModel, Field

from claude_code.tool.base import Tool, ToolResult, ToolUseContext

logger = logging.getLogger(__name__)

MAX_EDIT_FILE_SIZE = 1024 * 1024 * 1024  # 1 GiB guard

# Quote normalization: maps curly quotes to straight quotes
QUOTE_MAP = str.maketrans({
    "\u2018": "'",  # left single
    "\u2019": "'",  # right single
    "\u201c": '"',  # left double
    "\u201d": '"',  # right double
})


class FileEditInput(BaseModel):
    file_path: str = Field(description="The absolute path to the file to modify")
    old_string: str = Field(description="The text to replace")
    new_string: str = Field(description="The replacement text (must differ from old_string)")
    replace_all: bool = Field(default=False, description="Replace all occurrences")


def detect_encoding(raw: bytes) -> str:
    """Detect file encoding. Matches TS UTF-16 LE BOM detection."""
    if raw[:2] == b"\xff\xfe":
        return "utf-16-le"
    if raw[:2] == b"\xfe\xff":
        return "utf-16-be"
    if raw[:3] == b"\xef\xbb\xbf":
        return "utf-8-sig"
    return "utf-8"


def detect_line_endings(content: str) -> str:
    """Detect the predominant line ending style."""
    crlf_count = content.count("\r\n")
    lf_count = content.count("\n") - crlf_count
    return "\r\n" if crlf_count > lf_count else "\n"


def normalize_quotes(text: str) -> str:
    """Normalize curly quotes to straight quotes for matching."""
    return text.translate(QUOTE_MAP)


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

        # Reject .ipynb files (use NotebookEditTool)
        if file_path.suffix.lower() == ".ipynb":
            return "Cannot edit .ipynb files with Edit. Use the NotebookEdit tool instead."

        # File size guard
        try:
            size = file_path.stat().st_size
            if size > MAX_EDIT_FILE_SIZE:
                return f"File too large ({size:,} bytes). Maximum is {MAX_EDIT_FILE_SIZE:,} bytes."
        except OSError:
            pass

        # Must read first
        state = context.read_file_state.get(str(file_path))
        if state is None:
            return (
                f"You must read the file before editing it. "
                f"Use the Read tool to read {input_data.file_path} first."
            )

        # Stale file check
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

        # Read raw bytes for encoding detection
        try:
            raw = file_path.read_bytes()
        except Exception as e:
            return ToolResult(data=f"Error reading file: {e}", is_error=True)

        encoding = detect_encoding(raw)
        content = raw.decode(encoding, errors="replace")
        line_ending = detect_line_endings(content)

        # Normalize to LF for matching
        normalized = content.replace("\r\n", "\n")
        old_string = args.old_string
        new_string = args.new_string

        # Try exact match first
        if old_string not in normalized:
            # Try quote-normalized match (curly quotes → straight)
            normalized_content_q = normalize_quotes(normalized)
            normalized_old_q = normalize_quotes(old_string)
            if normalized_old_q in normalized_content_q:
                # Find the actual string in original content that matches
                idx = normalized_content_q.find(normalized_old_q)
                old_string = normalized[idx:idx + len(normalized_old_q)]
            else:
                return ToolResult(
                    data=f"The old_string was not found in {args.file_path}. "
                    f"Make sure the string matches exactly, including whitespace and indentation.",
                    is_error=True,
                )

        # Check uniqueness
        if not args.replace_all:
            count = normalized.count(old_string)
            if count > 1:
                return ToolResult(
                    data=f"The old_string appears {count} times in {args.file_path}. "
                    f"Provide more context to make it unique, or set replace_all=true.",
                    is_error=True,
                )

        # Apply replacement
        if args.replace_all:
            new_content = normalized.replace(old_string, new_string)
        else:
            new_content = normalized.replace(old_string, new_string, 1)

        # Restore original line endings
        if line_ending == "\r\n":
            new_content = new_content.replace("\n", "\r\n")

        # Write back with original encoding
        try:
            file_path.write_bytes(new_content.encode(encoding))
        except Exception as e:
            return ToolResult(data=f"Error writing file: {e}", is_error=True)

        # Update read state
        context.read_file_state[str(file_path)] = {
            "mtime": file_path.stat().st_mtime,
            "partial": False,
            "offset": 0,
            "limit": 2000,
        }

        # Generate unified diff
        old_lines = normalized.splitlines(keepends=True)
        new_normalized = new_content.replace("\r\n", "\n")
        new_lines = new_normalized.splitlines(keepends=True)
        diff = difflib.unified_diff(
            old_lines, new_lines,
            fromfile=f"a/{args.file_path}",
            tofile=f"b/{args.file_path}",
            n=3,
        )
        diff_str = "".join(diff)

        if diff_str:
            return ToolResult(data=diff_str)
        elif args.replace_all:
            count = normalized.count(old_string)
            return ToolResult(data=f"Replaced {count} occurrence(s) in {args.file_path}")
        else:
            return ToolResult(data=f"Successfully edited {args.file_path}")
