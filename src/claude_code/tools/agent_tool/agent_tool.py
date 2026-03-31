"""AgentTool -- Spawn sub-agents for complex tasks.

Maps to src/tools/AgentTool/AgentTool.ts in the TypeScript codebase.
"""

from __future__ import annotations

import logging
from typing import Optional

from pydantic import BaseModel, Field

from claude_code.tool.base import Tool, ToolResult, ToolUseContext

logger = logging.getLogger(__name__)


class AgentInput(BaseModel):
    description: str = Field(description="Description of the task for the sub-agent")
    prompt: str = Field(description="The prompt to send to the sub-agent")
    subagent_type: Optional[str] = Field(
        default=None,
        description="Type of sub-agent to spawn",
    )
    model: Optional[str] = Field(
        default=None,
        description="Model to use for the sub-agent",
    )
    run_in_background: Optional[bool] = Field(
        default=None,
        description="Whether to run the sub-agent in the background",
    )


class AgentTool(Tool):
    name = "Agent"
    aliases = ["agent", "sub_agent", "SubAgent"]
    input_model = AgentInput
    max_result_size_chars = 100_000

    def get_description(self) -> str:
        return "Spawns a sub-agent to handle a complex task."

    def get_prompt(self) -> str:
        return (
            "Spawns a sub-agent to handle a complex task.\n"
            "- Provide a clear description and prompt for the sub-agent\n"
            "- The sub-agent has access to the same tools\n"
            "- Use for tasks that require extended exploration or analysis"
        )

    async def call(
        self,
        args: BaseModel,
        context: ToolUseContext,
    ) -> ToolResult:
        assert isinstance(args, AgentInput)

        if not args.prompt.strip():
            return ToolResult(data="Error: prompt is required", is_error=True)

        logger.info("AgentTool: spawning sub-agent for: %s", args.description)

        try:
            # Import here to avoid circular imports
            from claude_code.query_engine import QueryEngine

            app_state = context.get_app_state()
            model = args.model or app_state.main_loop_model

            engine = QueryEngine(
                model=model,
                tools=context.tools,
                cwd=context.cwd,
                app_state=app_state,
                agent_id=f"sub-{context.agent_id or 'main'}",
                agent_type=args.subagent_type or "sub",
            )

            result = await engine.run(args.prompt)
            return ToolResult(data=result)

        except ImportError:
            # QueryEngine not available - return a simplified response
            logger.warning("QueryEngine not available for AgentTool")
            return ToolResult(
                data=(
                    f"Sub-agent requested for: {args.description}\n"
                    f"Prompt: {args.prompt}\n\n"
                    "Note: Sub-agent execution is not yet fully integrated. "
                    "The QueryEngine module is required for sub-agent spawning."
                ),
                is_error=True,
            )
        except Exception as e:
            logger.error("AgentTool error: %s", e)
            return ToolResult(
                data=f"Error spawning sub-agent: {e}",
                is_error=True,
            )
