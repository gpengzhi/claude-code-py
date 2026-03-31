"""AskUserQuestionTool -- Ask the user a question.

Maps to src/tools/AskUserQuestionTool/AskUserQuestionTool.ts in the TypeScript codebase.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from pydantic import BaseModel, Field

from claude_code.tool.base import Tool, ToolResult, ToolUseContext

logger = logging.getLogger(__name__)


class QuestionOption(BaseModel):
    label: str = Field(description="The option label")
    description: Optional[str] = Field(default=None, description="Option description")


class Question(BaseModel):
    question: str = Field(description="The question to ask")
    header: Optional[str] = Field(default=None, description="Header text for the question")
    options: Optional[list[QuestionOption]] = Field(
        default=None,
        description="Options for the user to choose from",
    )
    multiSelect: Optional[bool] = Field(
        default=None,
        description="Whether the user can select multiple options",
    )


class AskUserQuestionInput(BaseModel):
    questions: list[Question] = Field(
        description="List of questions to ask the user",
    )


class AskUserQuestionTool(Tool):
    name = "AskUserQuestion"
    aliases = ["ask_user", "ask_question"]
    input_model = AskUserQuestionInput
    max_result_size_chars = 10_000

    def get_description(self) -> str:
        return "Asks the user a question and returns their response."

    def get_prompt(self) -> str:
        return (
            "Asks the user a question and returns their response.\n"
            "- Each question can have a header, options, and multiSelect flag\n"
            "- Options provide a list of choices for the user\n"
            "- In non-interactive mode, returns a notice that user interaction is unavailable"
        )

    def is_read_only(self, input_data: BaseModel) -> bool:
        return True

    async def call(
        self,
        args: BaseModel,
        context: ToolUseContext,
    ) -> ToolResult:
        assert isinstance(args, AskUserQuestionInput)

        if not args.questions:
            return ToolResult(data="Error: at least one question is required", is_error=True)

        # In a CLI context, we format the questions for display.
        # In non-interactive / agent mode, we cannot prompt the user.
        app_state = context.get_app_state()

        # If running as a sub-agent, user interaction is not available
        if not app_state.is_main_agent:
            return ToolResult(
                data="User interaction not available in sub-agent mode.",
                is_error=True,
            )

        # Format questions for output
        parts = []
        for i, q in enumerate(args.questions, 1):
            section = []
            if q.header:
                section.append(f"## {q.header}")
            section.append(q.question)

            if q.options:
                select_type = "multi-select" if q.multiSelect else "single-select"
                section.append(f"({select_type})")
                for j, opt in enumerate(q.options, 1):
                    desc = f" - {opt.description}" if opt.description else ""
                    section.append(f"  {j}. {opt.label}{desc}")

            parts.append("\n".join(section))

        formatted = "\n\n".join(parts)

        # In a real interactive implementation, this would render a dialog
        # and wait for user input. For now, return the formatted questions
        # as a signal that user input is needed.
        return ToolResult(
            data=(
                "User interaction not available in the current execution context. "
                f"Questions that would be asked:\n\n{formatted}"
            ),
        )
