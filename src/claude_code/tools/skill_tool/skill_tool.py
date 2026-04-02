"""SkillTool -- invokes skills via a sub-agent.

Loads the skill body and executes it as a system prompt on a sub-agent,
matching a sub-agent pattern.
"""

from __future__ import annotations

import logging

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
                data=f"Unknown skill: {args.skill}. Available: {', '.join(s['name'] for s in all_skills)}",
                is_error=True,
            )

        skill_body = skill.get("body", "")
        user_prompt = args.args or skill_body

        # Determine which tools the skill is allowed to use
        allowed_tools = skill.get("allowed_tools")
        if allowed_tools and isinstance(allowed_tools, list):
            skill_tools = [t for t in context.tools if t.name in allowed_tools]
        else:
            skill_tools = context.tools

        # Fork a sub-agent with the skill body as system prompt
        try:
            from claude_code.query.engine import QueryEngine

            parent_perm_mode = "bypassPermissions"
            if context._app_state is not None:
                parent_perm_mode = context.get_app_state().tool_permission_context.mode

            engine = QueryEngine(
                model=skill.get("model") or context.model or "claude-sonnet-4-20250514",
                system_prompt=f"You are executing the skill '{args.skill}'.\n\n{skill_body}",
                tools=skill_tools,
                cwd=context.cwd,
                permission_mode=parent_perm_mode,
            )

            progress = context.progress_callback
            if progress:
                progress(f"Skill '{args.skill}': thinking...")

            result_parts: list[str] = []
            async for event in engine.submit_message(user_prompt, max_turns=10):
                if isinstance(event, dict):
                    if event.get("type") == "stream_event" and event.get("event_type") == "text_delta":
                        result_parts.append(event.get("text", ""))
                elif hasattr(event, "content"):
                    for block in event.content:
                        if hasattr(block, "name") and progress:
                            progress(f"Skill '{args.skill}': running {block.name}...")

            return ToolResult(data="".join(result_parts) or f"(skill '{args.skill}' produced no output)")

        except Exception as e:
            logger.error("SkillTool error: %s", e)
            return ToolResult(data=f"Error executing skill '{args.skill}': {e}", is_error=True)
