# Chapter 2: Adding Tools

This is the most important chapter. Tools are what separate a chatbot from an agent. After this chapter, your agent will be able to read files, run commands, and interact with the real world.

## What You'll Learn

- How LLM tool use actually works (it's simpler than you think)
- The tool_use → tool_result protocol
- How to design a clean Tool interface
- How to implement your first tools: Read and Bash

## The Key Insight

**The model doesn't execute tools. It asks you to.**

When you give the API a list of tools, the model can choose to emit a `tool_use` content block instead of (or alongside) text. That block says: "I want to call tool X with arguments Y." Your code then:

1. Executes the tool
2. Sends the result back as a `tool_result` message
3. The model continues with the result

```
                    ┌──────────────┐
                    │  Your Code   │
                    └──────┬───────┘
                           │
    "Read the file"        │  tool schemas
    ─────────────────────► API ◄────────────
                           │
    ◄── tool_use: Read     │  "I need to read it"
        file_path: main.py │
                           │
    execute Read(main.py)  │
    ─────────────────────► │
    tool_result: "def..."  │
                           │
    ◄── text: "The file    │  "Here's what I found"
        contains..."       │
```

## Step 1: Defining Tool Schemas

The API needs to know what tools are available. Each tool has a name, description, and a JSON Schema for its input:

```python
TOOLS = [
    {
        "name": "Read",
        "description": "Read a file from disk. Returns contents with line numbers.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the file"
                }
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "Bash",
        "description": "Execute a shell command.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The command to run"
                }
            },
            "required": ["command"]
        }
    }
]
```

**Pro tip**: Use Pydantic to generate these schemas automatically:

```python
from pydantic import BaseModel, Field

class ReadInput(BaseModel):
    file_path: str = Field(description="Absolute path to the file")

# Generate JSON Schema:
ReadInput.model_json_schema()
# → {"type": "object", "properties": {"file_path": {"type": "string", ...}}, "required": ["file_path"]}
```

## Step 2: The Tool Protocol

Every tool we'll ever build follows the same pattern. Let's define it:

```python
# src/tool.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pydantic import BaseModel
from typing import Any

@dataclass
class ToolResult:
    """What a tool returns."""
    data: Any = None       # The output (string, dict, etc.)
    is_error: bool = False  # Was this an error?

class Tool(ABC):
    """Base class for all tools."""
    name: str = ""
    input_model: type[BaseModel] = BaseModel  # Pydantic model for input

    @abstractmethod
    async def call(self, args: BaseModel) -> ToolResult:
        """Execute the tool. Override this."""
        ...

    def get_schema(self) -> dict:
        """Generate the JSON schema for the API."""
        schema = self.input_model.model_json_schema()
        schema.pop("title", None)
        return {
            "name": self.name,
            "description": self.get_description(),
            "input_schema": schema,
        }

    def get_description(self) -> str:
        return ""
```

**Why a Protocol/ABC?** Because we'll have 18+ tools eventually. A consistent interface means the executor doesn't need to know which specific tool it's running.

## Step 3: Implementing Read

```python
# src/tools/read.py
from pathlib import Path
from pydantic import BaseModel, Field
from src.tool import Tool, ToolResult

class ReadInput(BaseModel):
    file_path: str = Field(description="Absolute path to the file")
    offset: int | None = Field(default=None, ge=0, description="Start line (0-indexed)")
    limit: int | None = Field(default=None, gt=0, description="Max lines to read")

class ReadTool(Tool):
    name = "Read"
    input_model = ReadInput

    def get_description(self) -> str:
        return "Read a file and return contents with line numbers."

    async def call(self, args: BaseModel) -> ToolResult:
        assert isinstance(args, ReadInput)
        path = Path(args.file_path)

        if not path.exists():
            return ToolResult(data=f"File not found: {args.file_path}", is_error=True)

        content = path.read_text()
        lines = content.split("\n")

        # Apply offset/limit
        offset = args.offset or 0
        limit = args.limit or 2000
        lines = lines[offset:offset + limit]

        # Format with line numbers (cat -n style)
        numbered = [f"{i + offset + 1}\t{line}" for i, line in enumerate(lines)]
        return ToolResult(data="\n".join(numbered))
```

**Why line numbers?** The model needs them to reference specific lines when suggesting edits. "Change line 42" is precise; "change the line that says..." is ambiguous.

**Why cat -n format (`number\tline`)?** It's the same format Claude Code uses. The model is trained to understand it.

## Step 4: Implementing Bash

```python
# src/tools/bash.py
import asyncio
import os
from pydantic import BaseModel, Field
from src.tool import Tool, ToolResult

class BashInput(BaseModel):
    command: str = Field(description="The command to execute")
    timeout: int | None = Field(default=None, description="Timeout in ms")

class BashTool(Tool):
    name = "Bash"
    input_model = BashInput

    def get_description(self) -> str:
        return "Execute a shell command and return stdout/stderr."

    async def call(self, args: BaseModel) -> ToolResult:
        assert isinstance(args, BashInput)

        timeout_s = (args.timeout or 120_000) / 1000

        proc = await asyncio.create_subprocess_shell(
            args.command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=os.getcwd(),
        )

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout_s)
        except asyncio.TimeoutError:
            proc.kill()
            return ToolResult(data="Command timed out", is_error=True)

        output = stdout.decode()
        if stderr:
            output += f"\n(stderr): {stderr.decode()}"
        if proc.returncode != 0:
            output += f"\n(exit code: {proc.returncode})"

        return ToolResult(
            data=output or "(no output)",
            is_error=proc.returncode != 0,
        )
```

## Step 5: The Tool Executor

Now we need to connect tool_use blocks from the API to our tool implementations:

```python
# src/executor.py
from pydantic import ValidationError
from src.tool import Tool, ToolResult

async def execute_tool(
    tool: Tool,
    tool_input: dict,
    tool_use_id: str,
) -> dict:
    """Execute a tool and return a tool_result block for the API."""

    # 1. Validate input with Pydantic
    try:
        parsed = tool.input_model.model_validate(tool_input)
    except ValidationError as e:
        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": f"Invalid input: {e}",
            "is_error": True,
        }

    # 2. Execute
    try:
        result = await tool.call(parsed)
    except Exception as e:
        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": f"Error: {e}",
            "is_error": True,
        }

    # 3. Return result for the API
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": str(result.data) if result.data else "",
        "is_error": result.is_error,
    }
```

**Critical design decision**: errors are returned to the model as `tool_result` with `is_error: true`. We never crash. Why? Because the model can often recover:

- "File not found" → model searches for the correct filename
- "Permission denied" → model asks the user
- "Invalid regex" → model fixes the pattern

## Step 6: Wiring It Together

Update the streaming code to handle tool_use blocks:

```python
# Updated stream_response (additions marked with ###)
async def stream_response(client, messages, system_prompt="", model="...", tools=None):
    params = {
        "model": model,
        "max_tokens": 16384,
        "system": system_prompt,
        "messages": messages,
    }
    if tools:
        params["tools"] = [t.get_schema() for t in tools]  ### Add tool schemas

    async with client.messages.stream(**params) as stream:
        # ... same streaming code as Chapter 1 ...
        # But now content blocks can be tool_use, not just text
        pass

    # After streaming, check for tool_use blocks
    if tool_use_blocks:  ### New
        yield {"type": "tool_use", "blocks": tool_use_blocks}
```

And the main loop becomes:

```python
async def run(prompt, model):
    client = get_client()
    tools = [ReadTool(), BashTool()]
    tool_map = {t.name: t for t in tools}
    messages = [{"role": "user", "content": prompt}]

    while True:
        # Call the model
        tool_uses = []
        async for event in stream_response(client, messages, tools=tools):
            if event["type"] == "text":
                print(event["text"], end="", flush=True)
            elif event["type"] == "tool_use":
                tool_uses = event["blocks"]
            elif event["type"] == "done":
                messages.append(event["message"].to_api_format())

        if not tool_uses:
            break  # Model is done

        # Execute tools and add results
        results = []
        for tu in tool_uses:
            tool = tool_map.get(tu["name"])
            result = await execute_tool(tool, tu["input"], tu["id"])
            results.append(result)
            print(f"\n  [{tu['name']}] → {'error' if result['is_error'] else 'ok'}")

        messages.append({"role": "user", "content": results})
```

**That's the agentic loop.** It's 20 lines of code. Everything else is details.

## Try It

```bash
python agent.py -p "Read the file agent.py and count how many functions it has"
```

The agent will:
1. Call Read(file_path="agent.py")
2. Receive the file contents
3. Count the functions
4. Respond with the answer

## What You've Built

```
User input
    │
    ▼
┌──────────┐     ┌─────────────┐     ┌──────────┐
│  CLI     │ ──► │ API + Stream│ ──► │ Display  │
└──────────┘     └──────┬──────┘     └──────────┘
                        │
                   tool_use?
                        │
                   ┌────▼────┐
                   │Executor │
                   │ ┌─────┐ │
                   │ │Read │ │
                   │ │Bash │ │
                   │ └─────┘ │
                   └─────────┘
```

## Code Reference

The production version lives in:
- [`src/claude_code/tool/base.py`](../../src/claude_code/tool/base.py) -- Tool protocol
- [`src/claude_code/tool/executor.py`](../../src/claude_code/tool/executor.py) -- Execution pipeline
- [`src/claude_code/tools/file_read_tool/`](../../src/claude_code/tools/file_read_tool/) -- Read implementation
- [`src/claude_code/tools/bash_tool/`](../../src/claude_code/tools/bash_tool/) -- Bash implementation

---

**[← Chapter 1: Hello Agent](chapter-01-hello-agent.md) | [Chapter 3: The Agentic Loop →](chapter-03-agentic-loop.md)**
