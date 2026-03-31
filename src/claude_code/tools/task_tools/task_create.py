"""TaskCreateTool -- Create a new task.

Maps to the task management system in the TypeScript codebase.
"""

from __future__ import annotations

import logging
import uuid

from typing import Optional

from pydantic import BaseModel, Field

from claude_code.tool.base import Tool, ToolResult, ToolUseContext

logger = logging.getLogger(__name__)


class TaskCreateInput(BaseModel):
    subject: str = Field(description="A brief title for the task")
    description: str = Field(description="What needs to be done")
    activeForm: Optional[str] = Field(
        default=None,
        description="Present continuous form shown in spinner when in_progress",
    )


class TaskCreateTool(Tool):
    name = "TaskCreate"
    aliases = ["task_create"]
    input_model = TaskCreateInput
    max_result_size_chars = 10_000

    def get_description(self) -> str:
        return "Creates a new task in the task list."

    def get_prompt(self) -> str:
        return (
            "Creates a new task in the task list.\n"
            "- subject: A brief, actionable title\n"
            "- description: What needs to be done\n"
            "- activeForm: Present continuous form for spinner display"
        )

    async def call(
        self,
        args: BaseModel,
        context: ToolUseContext,
    ) -> ToolResult:
        assert isinstance(args, TaskCreateInput)

        if not args.subject.strip():
            return ToolResult(data="Error: subject is required", is_error=True)
        if not args.description.strip():
            return ToolResult(data="Error: description is required", is_error=True)

        app_state = context.get_app_state()
        tasks = app_state.tasks

        # Generate a sequential task ID
        existing_ids = [int(tid) for tid in tasks if tid.isdigit()]
        next_id = str(max(existing_ids, default=0) + 1)

        task = {
            "id": next_id,
            "subject": args.subject,
            "description": args.description,
            "status": "pending",
            "blocks": [],
            "blockedBy": [],
            "owner": None,
        }
        if args.activeForm:
            task["activeForm"] = args.activeForm

        tasks[next_id] = task

        # Update state
        def updater(state):
            state.tasks = tasks
            return state

        context.set_app_state(updater)

        logger.info("TaskCreate: created task #%s: %s", next_id, args.subject)

        return ToolResult(
            data=f"Created task #{next_id}: {args.subject} (status: pending)"
        )
