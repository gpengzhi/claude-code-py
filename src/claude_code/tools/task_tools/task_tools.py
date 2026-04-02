"""Task tools -- in-memory task tracking for agentic workflows.

Consolidated into a single module.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from pydantic import BaseModel, Field

from claude_code.tool.base import Tool, ToolResult, ToolUseContext

logger = logging.getLogger(__name__)

VALID_STATUSES = {"pending", "in_progress", "completed", "deleted"}


# --- Inputs ---

class TaskCreateInput(BaseModel):
    subject: str = Field(description="A brief title for the task")
    description: str = Field(description="What needs to be done")
    activeForm: Optional[str] = Field(default=None, description="Spinner text when in_progress")


class TaskGetInput(BaseModel):
    taskId: str = Field(description="The ID of the task to retrieve")


class TaskUpdateInput(BaseModel):
    taskId: str = Field(description="The ID of the task to update")
    status: Optional[str] = Field(default=None, description="pending, in_progress, completed, or deleted")
    subject: Optional[str] = Field(default=None, description="New subject")
    description: Optional[str] = Field(default=None, description="New description")
    addBlocks: Optional[list[str]] = Field(default=None, description="Task IDs this task blocks")
    addBlockedBy: Optional[list[str]] = Field(default=None, description="Task IDs that block this task")


class TaskListInput(BaseModel):
    pass


# --- Helpers ---

def _get_tasks(context: ToolUseContext) -> dict:
    return context.get_app_state().tasks


def _save_tasks(context: ToolUseContext, tasks: dict) -> None:
    context.set_app_state(lambda state: setattr(state, "tasks", tasks) or state)


# --- Tools ---

class TaskCreateTool(Tool):
    name = "TaskCreate"
    input_model = TaskCreateInput

    def get_description(self) -> str:
        return "Creates a new task in the task list."

    def get_prompt(self) -> str:
        return "Creates a new task with subject and description."

    async def call(self, args: BaseModel, context: ToolUseContext) -> ToolResult:
        assert isinstance(args, TaskCreateInput)
        if not args.subject.strip():
            return ToolResult(data="Error: subject is required", is_error=True)

        tasks = _get_tasks(context)
        next_id = str(max((int(k) for k in tasks if k.isdigit()), default=0) + 1)
        tasks[next_id] = {
            "id": next_id, "subject": args.subject, "description": args.description,
            "status": "pending", "blocks": [], "blockedBy": [],
            **({"activeForm": args.activeForm} if args.activeForm else {}),
        }
        _save_tasks(context, tasks)
        return ToolResult(data=f"Created task #{next_id}: {args.subject} (status: pending)")


class TaskGetTool(Tool):
    name = "TaskGet"
    input_model = TaskGetInput

    def get_description(self) -> str:
        return "Retrieves a task by its ID."

    def get_prompt(self) -> str:
        return "Returns full task details including dependencies."

    def is_read_only(self, input_data: BaseModel) -> bool:
        return True

    def is_concurrency_safe(self, input_data: BaseModel) -> bool:
        return True

    async def call(self, args: BaseModel, context: ToolUseContext) -> ToolResult:
        assert isinstance(args, TaskGetInput)
        tasks = _get_tasks(context)
        task = tasks.get(args.taskId.strip())
        if not task:
            return ToolResult(data=f"Error: task #{args.taskId} not found", is_error=True)
        return ToolResult(data=json.dumps(task, indent=2))


class TaskUpdateTool(Tool):
    name = "TaskUpdate"
    input_model = TaskUpdateInput

    def get_description(self) -> str:
        return "Updates an existing task."

    def get_prompt(self) -> str:
        return "Updates task status, subject, description, or dependencies."

    async def call(self, args: BaseModel, context: ToolUseContext) -> ToolResult:
        assert isinstance(args, TaskUpdateInput)
        tasks = _get_tasks(context)
        task_id = args.taskId.strip()

        if task_id not in tasks:
            return ToolResult(data=f"Error: task #{task_id} not found", is_error=True)

        # Deletion
        if args.status == "deleted":
            del tasks[task_id]
            for other in tasks.values():
                for key in ("blocks", "blockedBy"):
                    if task_id in other.get(key, []):
                        other[key].remove(task_id)
            _save_tasks(context, tasks)
            return ToolResult(data=f"Deleted task #{task_id}")

        if args.status and args.status not in VALID_STATUSES:
            return ToolResult(data=f"Error: invalid status '{args.status}'", is_error=True)

        task = tasks[task_id]
        changes = []
        for field, label in [("status", "status"), ("subject", "subject"), ("description", "description")]:
            val = getattr(args, field, None)
            if val is not None:
                task[field] = val
                changes.append(f"{label}={val}" if field == "status" else f"{label} updated")

        for args_field, task_field, reverse_field in [
            ("addBlocks", "blocks", "blockedBy"),
            ("addBlockedBy", "blockedBy", "blocks"),
        ]:
            ids = getattr(args, args_field, None)
            if ids:
                lst = task.setdefault(task_field, [])
                for bid in ids:
                    if bid not in lst:
                        lst.append(bid)
                    if bid in tasks:
                        rev = tasks[bid].setdefault(reverse_field, [])
                        if task_id not in rev:
                            rev.append(task_id)
                changes.append(f"{task_field}: +{len(ids)}")

        if not changes:
            return ToolResult(data=f"No changes for task #{task_id}")

        _save_tasks(context, tasks)
        return ToolResult(data=f"Updated task #{task_id}: {', '.join(changes)}")


class TaskListTool(Tool):
    name = "TaskList"
    input_model = TaskListInput

    def get_description(self) -> str:
        return "Lists all tasks."

    def get_prompt(self) -> str:
        return "Returns summary of all tasks: id, subject, status, blockedBy."

    def is_read_only(self, input_data: BaseModel) -> bool:
        return True

    def is_concurrency_safe(self, input_data: BaseModel) -> bool:
        return True

    async def call(self, args: BaseModel, context: ToolUseContext) -> ToolResult:
        tasks = _get_tasks(context)
        if not tasks:
            return ToolResult(data="No tasks found.")
        summaries = [
            {"id": t.get("id", k), "subject": t.get("subject", ""), "status": t.get("status", "pending"),
             "blockedBy": [b for b in t.get("blockedBy", []) if b in tasks and tasks[b].get("status") != "completed"]}
            for k, t in sorted(tasks.items(), key=lambda x: int(x[0]) if x[0].isdigit() else 0)
        ]
        return ToolResult(data=json.dumps(summaries, indent=2))
