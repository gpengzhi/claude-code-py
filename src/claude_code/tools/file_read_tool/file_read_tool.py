"""FileReadTool -- Read file contents.

Maps to src/tools/FileReadTool/FileReadTool.ts in the TypeScript codebase.
Supports text files, PDFs, images, and Jupyter notebooks.
"""

from __future__ import annotations

import base64
import json
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
DANGEROUS_PATHS = {
    "/dev/zero", "/dev/random", "/dev/urandom", "/dev/stdin",
    "/dev/null", "/dev/tty", "/dev/console",
    "/proc/self/fd/0", "/proc/self/fd/1", "/proc/self/fd/2",
}

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10MB
MAX_TOKEN_ESTIMATE = 200_000  # ~800KB of text


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
    pages: str | None = Field(
        default=None,
        description="Page range for PDF files (e.g., '1-5')",
    )


class FileReadTool(Tool):
    name = "Read"
    aliases = ["FileRead", "file_read", "ReadFile"]
    input_model = FileReadInput
    max_result_size_chars = 1_000_000

    def get_description(self) -> str:
        return "Reads a file from the local filesystem."

    def get_prompt(self) -> str:
        return (
            "Reads a file from the local filesystem.\n"
            "- The file_path parameter must be an absolute path\n"
            "- By default, reads up to 2000 lines from the beginning\n"
            "- Use offset and limit to read specific ranges\n"
            "- Can read images (returns base64), PDFs, and Jupyter notebooks"
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

        if file_path in DANGEROUS_PATHS:
            return f"Cannot read device path: {file_path}"

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
        if not file_path.is_absolute():
            file_path = context.cwd / file_path

        # Dedup cache: same file+range+mtime returns stub
        state = context.read_file_state.get(str(file_path))
        if state and file_path.exists():
            try:
                current_mtime = file_path.stat().st_mtime
                if current_mtime == state.get("mtime"):
                    same_range = (
                        state.get("offset") == (args.offset or 0)
                        and state.get("limit") == (args.limit or 2000)
                    )
                    if same_range:
                        return ToolResult(
                            data=f"<file_unchanged path=\"{args.file_path}\" />"
                        )
            except OSError:
                pass

        # Check existence
        if not file_path.exists():
            parent = file_path.parent
            if parent.exists():
                similar = [
                    f.name for f in parent.iterdir()
                    if f.name.startswith(file_path.name[:3])
                ][:5]
                if similar:
                    return ToolResult(
                        data=f"File does not exist: {args.file_path}\n"
                             f"Similar files: {', '.join(similar)}",
                        is_error=True,
                    )
            return ToolResult(
                data=f"File does not exist: {args.file_path}",
                is_error=True,
            )

        if file_path.is_dir():
            return ToolResult(
                data=f"Path is a directory: {args.file_path}. Use Bash with ls instead.",
                is_error=True,
            )

        ext = file_path.suffix.lower()

        # --- Image files ---
        if ext in IMAGE_EXTENSIONS:
            return self._read_image(file_path, args)

        # --- PDF files ---
        if ext == ".pdf":
            return self._read_pdf(file_path, args)

        # --- Jupyter notebooks ---
        if ext == ".ipynb":
            return self._read_notebook(file_path, args, context)

        # --- Text files ---
        return self._read_text(file_path, args, context)

    def _read_image(self, file_path: Path, args: FileReadInput) -> ToolResult:
        """Read an image file as base64."""
        try:
            size = file_path.stat().st_size
            if size > 5 * 1024 * 1024:  # 5MB limit for images
                return ToolResult(
                    data=f"Image too large: {size:,} bytes (max 5MB)",
                    is_error=True,
                )
            data = file_path.read_bytes()
            b64 = base64.b64encode(data).decode("ascii")
            media_type = mimetypes.guess_type(str(file_path))[0] or "image/png"
            return ToolResult(data={
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": b64,
                },
            })
        except Exception as e:
            return ToolResult(data=f"Error reading image: {e}", is_error=True)

    def _read_pdf(self, file_path: Path, args: FileReadInput) -> ToolResult:
        """Read a PDF file."""
        try:
            import pypdf
        except ImportError:
            # Fallback: tell the user to install pypdf
            return ToolResult(
                data=f"[PDF file: {args.file_path}] Install 'pypdf' package to read PDFs: pip install pypdf",
            )

        try:
            reader = pypdf.PdfReader(str(file_path))
            total_pages = len(reader.pages)

            # Parse page range
            if args.pages:
                pages = self._parse_page_range(args.pages, total_pages)
            elif total_pages > 20:
                return ToolResult(
                    data=f"PDF has {total_pages} pages. Use the 'pages' parameter to read specific pages (max 20).",
                    is_error=True,
                )
            else:
                pages = list(range(total_pages))

            if len(pages) > 20:
                return ToolResult(
                    data="Maximum 20 pages per request.",
                    is_error=True,
                )

            parts = []
            for page_num in pages:
                if 0 <= page_num < total_pages:
                    text = reader.pages[page_num].extract_text()
                    parts.append(f"--- Page {page_num + 1} ---\n{text}")

            return ToolResult(data="\n\n".join(parts))
        except Exception as e:
            return ToolResult(data=f"Error reading PDF: {e}", is_error=True)

    def _parse_page_range(self, pages_str: str, total: int) -> list[int]:
        """Parse '1-5' or '3' or '1,3,5' into 0-indexed page numbers."""
        result: list[int] = []
        for part in pages_str.split(","):
            part = part.strip()
            if "-" in part:
                start, end = part.split("-", 1)
                for i in range(int(start) - 1, min(int(end), total)):
                    result.append(i)
            else:
                result.append(int(part) - 1)
        return result

    def _read_notebook(
        self, file_path: Path, args: FileReadInput, context: ToolUseContext,
    ) -> ToolResult:
        """Read a Jupyter notebook with structured cell output."""
        try:
            nb = json.loads(file_path.read_text(encoding="utf-8"))
        except Exception as e:
            return ToolResult(data=f"Error reading notebook: {e}", is_error=True)

        cells = nb.get("cells", [])
        parts: list[str] = []

        for i, cell in enumerate(cells):
            cell_type = cell.get("cell_type", "unknown")
            source = "".join(cell.get("source", []))

            parts.append(f"--- Cell {i + 1} [{cell_type}] ---")
            parts.append(source)

            # Show outputs for code cells
            outputs = cell.get("outputs", [])
            if outputs:
                for out in outputs:
                    out_type = out.get("output_type", "")
                    if out_type == "stream":
                        text = "".join(out.get("text", []))
                        parts.append(f"[output]: {text}")
                    elif out_type in ("execute_result", "display_data"):
                        data = out.get("data", {})
                        if "text/plain" in data:
                            text = "".join(data["text/plain"])
                            parts.append(f"[output]: {text}")
                    elif out_type == "error":
                        ename = out.get("ename", "")
                        evalue = out.get("evalue", "")
                        parts.append(f"[error]: {ename}: {evalue}")

            parts.append("")

        result = "\n".join(parts)

        context.read_file_state[str(file_path)] = {
            "mtime": file_path.stat().st_mtime,
            "partial": False,
            "offset": 0,
            "limit": len(cells),
        }
        return ToolResult(data=result)

    def _read_text(
        self, file_path: Path, args: FileReadInput, context: ToolUseContext,
    ) -> ToolResult:
        """Read a text file with line numbers."""
        # File size guard
        try:
            size = file_path.stat().st_size
            if size > MAX_FILE_SIZE_BYTES:
                return ToolResult(
                    data=f"File too large: {size:,} bytes (max {MAX_FILE_SIZE_BYTES:,}). "
                         f"Use offset and limit to read a portion.",
                    is_error=True,
                )
        except OSError:
            pass

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except PermissionError:
            return ToolResult(data=f"Permission denied: {args.file_path}", is_error=True)
        except Exception as e:
            return ToolResult(data=f"Error reading file: {e}", is_error=True)

        # Token estimate guard
        estimated_tokens = len(content) // 4
        if estimated_tokens > MAX_TOKEN_ESTIMATE and args.limit is None:
            line_count = content.count("\n")
            return ToolResult(
                data=f"File is very large (~{estimated_tokens:,} tokens, {line_count:,} lines). "
                     f"Use offset and limit to read a portion.",
                is_error=True,
            )

        lines = content.split("\n")
        offset = args.offset or 0
        limit = args.limit or 2000
        lines = lines[offset:offset + limit]

        # Format with line numbers (cat -n style)
        numbered = [f"{i + offset + 1}\t{line}" for i, line in enumerate(lines)]
        result = "\n".join(numbered)

        context.read_file_state[str(file_path)] = {
            "mtime": file_path.stat().st_mtime,
            "partial": args.offset is not None or args.limit is not None,
            "offset": args.offset or 0,
            "limit": args.limit or 2000,
        }

        return ToolResult(data=result)
