"""TaskUpdateTool -- Update an existing task.

Maps to the task management system in the TypeScript codebase.
"""

from __future__ import annotations

import logging
from typing import Optional

from pydantic import BaseModel, Field

from claude_code.tool.base import Tool, ToolResult, ToolUseContext

logger = logging.getLogger(__name__)

VALID_STATUSES = {"pending", "in_progress", "completed", "deleted"}


class TaskUpdateInput(BaseModel):
    taskId: str = Field(description="The ID of the task to update")
    status: Optional[str] = Field(
        default=None,
        description="New status: pending, in_progress, completed, or deleted",
    )
    subject: Optional[str] = Field(
        default=None,
        description="New subject for the task",
    )
    description: Optional[str] = Field(
        default=None,
        description="New description for the task",
    )
    activeForm: Optional[str] = Field(
        default=None,
        description="Present continuous form shown in spinner when in_progress",
    )
    owner: Optional[str] = Field(
        default=None,
        description="New owner for the task",
    )
    addBlocks: Optional[list[str]] = Field(
        default=None,
        description="Task IDs that this task blocks",
    )
    addBlockedBy: Optional[list[str]] = Field(
        default=None,
        description="Task IDs that block this task",
    )


class TaskUpdateTool(Tool):
    name = "TaskUpdate"
    aliases = ["task_update"]
    input_model = TaskUpdateInput
    max_result_size_chars = 10_000

    def get_description(self) -> str:
        return "Updates an existing task in the task list."

    def get_prompt(self) -> str:
        return (
            "Updates an existing task in the task list.\n"
            "- taskId: The ID of the task to update\n"
            "- status: pending -> in_progress -> completed, or deleted\n"
            "- Can also update subject, description, owner, and dependencies"
        )

    async def call(
        self,
        args: BaseModel,
        context: ToolUseContext,
    ) -> ToolResult:
        assert isinstance(args, TaskUpdateInput)

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

        # Handle deletion
        if args.status == "deleted":
            del tasks[task_id]
            # Remove from other tasks' blocks/blockedBy
            for other in tasks.values():
                if task_id in other.get("blocks", []):
                    other["blocks"].remove(task_id)
                if task_id in other.get("blockedBy", []):
                    other["blockedBy"].remove(task_id)

            def updater(state):
                state.tasks = tasks
                return state

            context.set_app_state(updater)
            logger.info("TaskUpdate: deleted task #%s", task_id)
            return ToolResult(data=f"Deleted task #{task_id}")

        # Validate status
        if args.status is not None and args.status not in VALID_STATUSES:
            return ToolResult(
                data=f"Error: invalid status '{args.status}'. Must be one of: {', '.join(sorted(VALID_STATUSES))}",
                is_error=True,
            )

        # Apply updates
        changes = []
        if args.status is not None:
            task["status"] = args.status
            changes.append(f"status={args.status}")
        if args.subject is not None:
            task["subject"] = args.subject
            changes.append(f"subject updated")
        if args.description is not None:
            task["description"] = args.description
            changes.append("description updated")
        if args.activeForm is not None:
            task["activeForm"] = args.activeForm
            changes.append("activeForm updated")
        if args.owner is not None:
            task["owner"] = args.owner
            changes.append(f"owner={args.owner}")

        # Handle dependency updates
        if args.addBlocks:
            blocks = task.get("blocks", [])
            for bid in args.addBlocks:
                if bid not in blocks:
                    blocks.append(bid)
                # Also add reverse reference
                if bid in tasks:
                    blocked_by = tasks[bid].get("blockedBy", [])
                    if task_id not in blocked_by:
                        blocked_by.append(task_id)
                    tasks[bid]["blockedBy"] = blocked_by
            task["blocks"] = blocks
            changes.append(f"blocks: +{len(args.addBlocks)}")

        if args.addBlockedBy:
            blocked_by = task.get("blockedBy", [])
            for bid in args.addBlockedBy:
                if bid not in blocked_by:
                    blocked_by.append(bid)
                # Also add reverse reference
                if bid in tasks:
                    blocks = tasks[bid].get("blocks", [])
                    if task_id not in blocks:
                        blocks.append(task_id)
                    tasks[bid]["blocks"] = blocks
            task["blockedBy"] = blocked_by
            changes.append(f"blockedBy: +{len(args.addBlockedBy)}")

        if not changes:
            return ToolResult(data=f"No changes specified for task #{task_id}")

        tasks[task_id] = task

        def updater(state):
            state.tasks = tasks
            return state

        context.set_app_state(updater)

        logger.info("TaskUpdate: updated task #%s: %s", task_id, ", ".join(changes))
        return ToolResult(
            data=f"Updated task #{task_id}: {', '.join(changes)}"
        )
