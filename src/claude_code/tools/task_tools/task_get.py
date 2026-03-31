"""TaskGetTool -- Get a task by ID.

Maps to the task management system in the TypeScript codebase.
"""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel, Field

from claude_code.tool.base import Tool, ToolResult, ToolUseContext

logger = logging.getLogger(__name__)


class TaskGetInput(BaseModel):
    taskId: str = Field(description="The ID of the task to retrieve")


class TaskGetTool(Tool):
    name = "TaskGet"
    aliases = ["task_get"]
    input_model = TaskGetInput
    max_result_size_chars = 10_000

    def get_description(self) -> str:
        return "Retrieves a task by its ID from the task list."

    def get_prompt(self) -> str:
        return (
            "Retrieves a task by its ID from the task list.\n"
            "- Returns full task details including subject, description, status\n"
            "- Also shows dependency information (blocks, blockedBy)"
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
        assert isinstance(args, TaskGetInput)

        task_id = args.taskId.strip()
        if not task_id:
            return ToolResult(data="Error: taskId is required", is_error=True)

        app_state = context.get_app_state()
        tasks = app_state.tasks

        if task_id not in tasks:
            return ToolResult(
                data=f"Error: task #{task_id} not found",
                is_error=True,
            )

        task = tasks[task_id]
        return ToolResult(data=json.dumps(task, indent=2))
