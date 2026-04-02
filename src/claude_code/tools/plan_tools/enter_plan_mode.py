"""EnterPlanModeTool -- Transition to plan mode.

"""

from __future__ import annotations

import logging

from pydantic import BaseModel

from claude_code.tool.base import Tool, ToolResult, ToolUseContext

logger = logging.getLogger(__name__)


class EnterPlanModeInput(BaseModel):
    pass


class EnterPlanModeTool(Tool):
    name = "EnterPlanMode"
    aliases = ["enter_plan_mode"]
    input_model = EnterPlanModeInput
    max_result_size_chars = 1_000

    def get_description(self) -> str:
        return "Transitions the session to plan mode."

    def get_prompt(self) -> str:
        return (
            "Transitions the session to plan mode.\n"
            "- In plan mode, the assistant focuses on planning and analysis\n"
            "- No code modifications are made in plan mode\n"
            "- Use ExitPlanMode to return to code mode"
        )

    async def call(
        self,
        args: BaseModel,
        context: ToolUseContext,
    ) -> ToolResult:
        app_state = context.get_app_state()

        if app_state.mode == "plan":
            return ToolResult(data="Already in plan mode.")

        def updater(state):
            state.mode = "plan"
            return state

        context.set_app_state(updater)

        logger.info("EnterPlanMode: switched to plan mode")
        return ToolResult(data="Entered plan mode. Focus on planning and analysis.")
