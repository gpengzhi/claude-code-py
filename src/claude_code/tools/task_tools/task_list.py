"""TaskListTool -- List all tasks.

Maps to the task management system in the TypeScript codebase.
"""

from __future__ import annotations

import json
import logging

from pydantic import BaseModel

from claude_code.tool.base import Tool, ToolResult, ToolUseContext

logger = logging.getLogger(__name__)


class TaskListInput(BaseModel):
    pass


class TaskListTool(Tool):
    name = "TaskList"
    aliases = ["task_list"]
    input_model = TaskListInput
    max_result_size_chars = 50_000

    def get_description(self) -> str:
        return "Lists all tasks in the task list."

    def get_prompt(self) -> str:
        return (
            "Lists all tasks in the task list.\n"
            "- Returns a summary of each task: id, subject, status, owner, blockedBy\n"
            "- Use TaskGet with a specific task ID to view full details"
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
        app_state = context.get_app_state()
        tasks = app_state.tasks

        if not tasks:
            return ToolResult(data="No tasks found.")

        # Build summary list
        summaries = []
        for task_id in sorted(tasks.keys(), key=lambda x: int(x) if x.isdigit() else 0):
            task = tasks[task_id]
            summary = {
                "id": task.get("id", task_id),
                "subject": task.get("subject", ""),
                "status": task.get("status", "pending"),
                "owner": task.get("owner", ""),
                "blockedBy": [
                    bid for bid in task.get("blockedBy", [])
                    if bid in tasks and tasks[bid].get("status") != "completed"
                ],
            }
            summaries.append(summary)

        return ToolResult(data=json.dumps(summaries, indent=2))
