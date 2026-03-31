"""NotebookEditTool -- Edit Jupyter notebook cells.

Maps to src/tools/NotebookEditTool/NotebookEditTool.ts in the TypeScript codebase.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from claude_code.tool.base import Tool, ToolResult, ToolUseContext

logger = logging.getLogger(__name__)

VALID_CELL_TYPES = {"code", "markdown"}
VALID_EDIT_MODES = {"replace", "insert", "delete"}


class NotebookEditInput(BaseModel):
    notebook_path: str = Field(description="The absolute path to the Jupyter notebook file")
    new_source: str = Field(description="The new source for the cell")
    cell_number: Optional[int] = Field(
        default=None,
        description="The 0-indexed cell number to edit",
    )
    cell_type: Optional[str] = Field(
        default=None,
        description="The type of the cell: code or markdown",
    )
    edit_mode: Optional[str] = Field(
        default=None,
        description="The edit mode: replace, insert, or delete",
    )


class NotebookEditTool(Tool):
    name = "NotebookEdit"
    aliases = ["notebook_edit"]
    input_model = NotebookEditInput
    max_result_size_chars = 100_000

    def get_description(self) -> str:
        return "Edits a cell in a Jupyter notebook (.ipynb file)."

    def get_prompt(self) -> str:
        return (
            "Edits a cell in a Jupyter notebook (.ipynb file).\n"
            "- notebook_path must be an absolute path\n"
            "- cell_number is 0-indexed\n"
            "- edit_mode: replace (default), insert, or delete\n"
            "- cell_type: code or markdown (required for insert)"
        )

    async def call(
        self,
        args: BaseModel,
        context: ToolUseContext,
    ) -> ToolResult:
        assert isinstance(args, NotebookEditInput)

        notebook_path = Path(args.notebook_path)
        if not notebook_path.is_absolute():
            notebook_path = context.cwd / notebook_path

        edit_mode = args.edit_mode or "replace"
        if edit_mode not in VALID_EDIT_MODES:
            return ToolResult(
                data=f"Error: invalid edit_mode '{edit_mode}'. Must be one of: {', '.join(sorted(VALID_EDIT_MODES))}",
                is_error=True,
            )

        if args.cell_type and args.cell_type not in VALID_CELL_TYPES:
            return ToolResult(
                data=f"Error: invalid cell_type '{args.cell_type}'. Must be one of: {', '.join(sorted(VALID_CELL_TYPES))}",
                is_error=True,
            )

        # Read the notebook
        if not notebook_path.exists():
            if edit_mode != "insert":
                return ToolResult(
                    data=f"Error: notebook does not exist: {args.notebook_path}",
                    is_error=True,
                )
            # Create a new notebook for insert mode
            notebook = {
                "nbformat": 4,
                "nbformat_minor": 5,
                "metadata": {
                    "kernelspec": {
                        "display_name": "Python 3",
                        "language": "python",
                        "name": "python3",
                    },
                    "language_info": {"name": "python", "version": "3.10.0"},
                },
                "cells": [],
            }
        else:
            try:
                raw = notebook_path.read_text(encoding="utf-8")
                notebook = json.loads(raw)
            except json.JSONDecodeError as e:
                return ToolResult(
                    data=f"Error: invalid JSON in notebook: {e}",
                    is_error=True,
                )
            except Exception as e:
                return ToolResult(
                    data=f"Error reading notebook: {e}",
                    is_error=True,
                )

        cells = notebook.get("cells", [])
        cell_number = args.cell_number
        source_lines = args.new_source.split("\n")
        # Ensure each line ends with \n except the last
        source_list = [line + "\n" for line in source_lines[:-1]]
        if source_lines:
            source_list.append(source_lines[-1])

        # Handle edit modes
        if edit_mode == "insert":
            cell_type = args.cell_type
            if not cell_type:
                return ToolResult(
                    data="Error: cell_type is required for insert mode",
                    is_error=True,
                )

            new_cell = {
                "cell_type": cell_type,
                "metadata": {},
                "source": source_list,
            }
            if cell_type == "code":
                new_cell["execution_count"] = None
                new_cell["outputs"] = []

            insert_at = cell_number if cell_number is not None else len(cells)
            if insert_at < 0 or insert_at > len(cells):
                return ToolResult(
                    data=f"Error: cell_number {insert_at} out of range (0-{len(cells)})",
                    is_error=True,
                )
            cells.insert(insert_at, new_cell)
            action = f"Inserted new {cell_type} cell at position {insert_at}"

        elif edit_mode == "delete":
            if cell_number is None:
                return ToolResult(
                    data="Error: cell_number is required for delete mode",
                    is_error=True,
                )
            if cell_number < 0 or cell_number >= len(cells):
                return ToolResult(
                    data=f"Error: cell_number {cell_number} out of range (0-{len(cells) - 1})",
                    is_error=True,
                )
            deleted = cells.pop(cell_number)
            action = f"Deleted cell {cell_number} (was {deleted.get('cell_type', 'unknown')})"

        else:  # replace
            if cell_number is None:
                return ToolResult(
                    data="Error: cell_number is required for replace mode",
                    is_error=True,
                )
            if cell_number < 0 or cell_number >= len(cells):
                return ToolResult(
                    data=f"Error: cell_number {cell_number} out of range (0-{len(cells) - 1})",
                    is_error=True,
                )
            cell = cells[cell_number]
            cell["source"] = source_list
            if args.cell_type:
                cell["cell_type"] = args.cell_type
            action = f"Replaced cell {cell_number}"

        notebook["cells"] = cells

        # Write back
        try:
            notebook_path.parent.mkdir(parents=True, exist_ok=True)
            notebook_path.write_text(
                json.dumps(notebook, indent=1, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except Exception as e:
            return ToolResult(
                data=f"Error writing notebook: {e}",
                is_error=True,
            )

        logger.info("NotebookEdit: %s in %s", action, args.notebook_path)
        return ToolResult(
            data=f"{action} in {args.notebook_path} (total cells: {len(cells)})"
        )
