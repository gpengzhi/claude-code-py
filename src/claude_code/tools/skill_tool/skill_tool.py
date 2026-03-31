"""SkillTool -- invokes skills as sub-agent prompts.

Maps to src/tools/SkillTool/SkillTool.ts in the TypeScript codebase.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from claude_code.tool.base import Tool, ToolResult, ToolUseContext

logger = logging.getLogger(__name__)


class SkillInput(BaseModel):
    skill: str = Field(description="The skill name to invoke")
    args: str | None = Field(default=None, description="Optional arguments for the skill")


class SkillTool(Tool):
    name = "Skill"
    aliases = ["skill"]
    input_model = SkillInput
    max_result_size_chars = 100_000

    def get_description(self) -> str:
        return "Execute a skill within the main conversation."

    def get_prompt(self) -> str:
        return (
            "Execute a skill within the main conversation.\n"
            "When users reference a slash command or /<something>, use this tool."
        )

    async def call(
        self,
        args: BaseModel,
        context: ToolUseContext,
    ) -> ToolResult:
        assert isinstance(args, SkillInput)

        from claude_code.skills.loader import load_all_skills
        from claude_code.skills.bundled import get_bundled_skills

        # Search for the skill
        all_skills = load_all_skills(context.cwd) + get_bundled_skills()
        skill = None
        for s in all_skills:
            if s["name"] == args.skill:
                skill = s
                break

        if skill is None:
            return ToolResult(
                data=f"Unknown skill: {args.skill}. Available skills: {', '.join(s['name'] for s in all_skills)}",
                is_error=True,
            )

        # Build the prompt from skill body
        prompt = skill.get("body", "")
        if args.args:
            prompt = f"{prompt}\n\nArguments: {args.args}"

        return ToolResult(data=f"[Skill '{args.skill}' loaded]\n\n{prompt}")
