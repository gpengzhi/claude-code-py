"""ExitPlanModeTool -- Exit plan mode and return to code mode.

Maps to the plan mode system in the TypeScript codebase.
"""

from __future__ import annotations

import logging
from typing import Optional

from pydantic import BaseModel, Field

from claude_code.tool.base import Tool, ToolResult, ToolUseContext

logger = logging.getLogger(__name__)


class ExitPlanModeInput(BaseModel):
    allowedPrompts: Optional[list[str]] = Field(
        default=None,
        description="Optional list of allowed prompts after exiting plan mode",
    )


class ExitPlanModeTool(Tool):
    name = "ExitPlanMode"
    aliases = ["exit_plan_mode"]
    input_model = ExitPlanModeInput
    max_result_size_chars = 1_000

    def get_description(self) -> str:
        return "Exits plan mode and returns to code mode."

    def get_prompt(self) -> str:
        return (
            "Exits plan mode and returns to code mode.\n"
            "- Returns the session to normal code execution mode\n"
            "- Optionally specify allowedPrompts to restrict next actions"
        )

    async def call(
        self,
        args: BaseModel,
        context: ToolUseContext,
    ) -> ToolResult:
        assert isinstance(args, ExitPlanModeInput)

        app_state = context.get_app_state()

        if app_state.mode != "plan":
            return ToolResult(data="Not currently in plan mode.")

        def updater(state):
            state.mode = "code"
            return state

        context.set_app_state(updater)

        logger.info("ExitPlanMode: switched back to code mode")

        msg = "Exited plan mode. Back to code mode."
        if args.allowedPrompts:
            msg += f" Allowed prompts: {', '.join(args.allowedPrompts)}"

        return ToolResult(data=msg)
