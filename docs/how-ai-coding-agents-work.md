# How AI Coding Agents Work

A deep-dive into the architecture of AI coding agents, explained through the claude-code-py codebase.

## The Big Picture

Every AI coding agent -- Claude Code, Cursor, aider, Copilot Workspace -- follows the same fundamental pattern. Understanding this pattern lets you build your own, evaluate existing tools, and debug when things go wrong.

The core insight: **an AI coding agent is just a loop that alternates between thinking (LLM) and acting (tools).**

```
User: "Fix the bug in auth.py"
  │
  ▼
┌─────────────────────────────┐
│  System Prompt              │  "You are a coding agent. You have these tools: ..."
│  + User Context (CLAUDE.md) │  "This project uses Django 4.2, pytest..."
│  + Git Context              │  "Branch: fix/auth-bug, 3 files changed..."
│  + User Message             │  "Fix the bug in auth.py"
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────┐
│  LLM (Claude API)           │
│                             │
│  "I need to read auth.py    │
│   first to understand the   │
│   bug."                     │
│                             │
│  → tool_use: Read(auth.py)  │
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────┐
│  Tool Executor              │
│                             │
│  Read auth.py → returns     │
│  file contents with line    │
│  numbers                    │
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────┐
│  LLM (Claude API)           │
│                             │
│  "I see the bug on line 42. │
│   The comparison should be  │
│   != not ==."               │
│                             │
│  → tool_use: Edit(auth.py,  │
│     old="==", new="!=")     │
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────┐
│  Tool Executor              │
│                             │
│  Edit auth.py → success     │
└─────────────┬───────────────┘
              │
              ▼
┌─────────────────────────────┐
│  LLM (Claude API)           │
│                             │
│  "I've fixed the bug.       │
│   The issue was..."         │
│                             │
│  → (no tool_use = done)     │
└─────────────────────────────┘
```

That's it. Everything else is optimization and UX.

---

## Layer 1: The API Call

**File: `services/api/claude.py`**

At the lowest level, we're making an HTTP request to the Anthropic API with streaming enabled:

```python
async with client.messages.stream(
    model="claude-sonnet-4-20250514",
    max_tokens=16384,
    system="You are a coding agent...",
    messages=[{"role": "user", "content": "Fix the bug"}],
    tools=[{"name": "Read", "input_schema": {...}}, ...],
) as stream:
    async for event in stream:
        # Process SSE events as they arrive
```

The API returns Server-Sent Events (SSE). Each event is one of:
- `message_start` -- the response is beginning
- `content_block_start` -- a new block (text, tool_use, thinking) is starting
- `content_block_delta` -- incremental content for the current block
- `content_block_stop` -- the block is complete
- `message_delta` -- final usage stats and stop reason
- `message_stop` -- the response is done

We accumulate these into complete `AssistantMessage` objects. Text deltas are also yielded immediately for real-time streaming display.

**Key insight**: The model doesn't "call" tools. It returns a `tool_use` content block that says "I want to call this tool with these arguments." It's our code that actually executes the tool and sends the result back.

---

## Layer 2: The Agentic Loop

**File: `query/loop.py`**

```python
while turn_count < max_turns:
    # 1. Auto-compact if context is too long
    messages, did_compact = await compact_tracker.maybe_compact(messages, model)

    # 2. Call the model
    async for event in query_model(messages, system_prompt, model, tools=tools):
        if isinstance(event, AssistantMessage):
            # Extract any tool_use blocks
            for block in event.content:
                if isinstance(block, ToolUseBlock):
                    tool_use_blocks.append(block)

    # 3. If no tool use, we're done
    if not tool_use_blocks:
        return

    # 4. Execute tools (parallel for read-only, serial for writes)
    tool_results = await run_tools(tool_use_blocks, tools, context)

    # 5. Append results and loop
    messages.append({"role": "user", "content": tool_results})
```

**Why `max_turns`?** Without a limit, a confused model could loop forever (read file → edit file → read file → edit file...). The limit is a safety valve.

**Why auto-compact?** Each turn adds tokens. Eventually you hit the context window limit. Auto-compact summarizes older messages to free up space. It's the difference between a 5-turn agent and a 50-turn one.

---

## Layer 3: The Tool System

**Files: `tool/base.py`, `tool/executor.py`, `tools/*/`**

Every tool implements the same interface:

```python
class Tool(ABC):
    name: str                           # "Bash", "Read", "Edit", etc.
    input_model: type[BaseModel]        # Pydantic model for input validation

    async def call(self, args, context) -> ToolResult:
        ...                             # Actually do the thing

    def is_concurrency_safe(self, input) -> bool:
        ...                             # Can this run in parallel?

    def get_tool_schema(self) -> dict:
        ...                             # JSON schema for the API
```

The execution pipeline for each tool call (see `tool/executor.py`):

```
tool_use block from API
    │
    ├─ 1. Parse input (Pydantic validation)
    │     Bad input? → return error to model
    │
    ├─ 2. Validate (tool-specific checks)
    │     File not read yet? → return "read first" error
    │
    ├─ 3. Run PreToolUse hooks
    │     Hook blocked? → return error to model
    │
    ├─ 4. Check permissions
    │     User denied? → return "permission denied"
    │
    ├─ 5. Execute (tool.call())
    │     Exception? → return error to model
    │
    ├─ 6. Run PostToolUse hooks
    │
    └─ 7. Format and truncate result
          Truncate if too large (100KB default)
```

**Why return errors to the model instead of crashing?** The model can learn from errors and try again. "File not found" leads the model to search for the correct path. "Permission denied" leads it to ask the user.

**Why parallel execution?** Multiple `Read` or `Glob` calls can't interfere with each other, so we run them concurrently:

```python
# Read-only tools → asyncio.gather()
# Write tools → sequential await
```

---

## Layer 4: Context Engineering

**Files: `context/`**

What's in the system prompt matters more than the model you choose. The system prompt is assembled from sections:

```
1. Identity       → "You are Claude Code, a coding agent..."
2. Tool docs      → Description + usage instructions for each tool
3. Environment    → Working directory, platform, shell
4. Date           → "Today's date is YYYY-MM-DD"
5. CLAUDE.md      → User's custom instructions (loaded from file hierarchy)
6. Memory         → Persistent facts from previous sessions
```

**CLAUDE.md hierarchy** (from outermost to innermost):
```
~/.claude/CLAUDE.md           ← User-wide (applies everywhere)
<project>/.claude/CLAUDE.md   ← Project-specific
<cwd>/CLAUDE.md               ← Directory-specific
```

**Git context** is injected into the first user message, not the system prompt:
```xml
<system-context>
Current branch: fix/auth-bug
Status: M src/auth.py
Recent commits: abc1234 refactor login flow
</system-context>
```

**Why not put everything in the system prompt?** The system prompt is cached (Anthropic's prompt caching). Git status changes every turn, so it goes in the user message to avoid busting the cache.

---

## Layer 5: The TUI

**Files: `tui/`**

The terminal UI needs to:
1. Show a text input for the user
2. Stream the model's response in real-time
3. Display tool use/result blocks inline
4. Show a spinner during model calls
5. Handle Ctrl+C to interrupt

We use [Textual](https://textual.textualize.io/) (Python's equivalent of React for the terminal). The component tree:

```
App
 └─ REPLScreen
     ├─ MessageList     ← Scrollable message history
     ├─ Spinner          ← "Thinking..." with elapsed time
     ├─ PromptInput      ← Text input with history
     └─ StatusBar        ← Model name, cost, turns
```

The REPL screen orchestrates the query engine:

```python
async def _run_query(self, prompt):
    spinner.show("Thinking...")
    async for event in engine.submit_message(prompt):
        if text_delta:
            message_list.update_streaming(text)    # Real-time display
        elif tool_use:
            message_list.add_tool_use(name, input)  # Show what tool is running
        elif tool_result:
            message_list.add_tool_result(content)   # Show the result
    spinner.hide()
```

---

## Layer 6: Extension Points

**Files: `hooks/`, `skills/`, `commands/`**

Two ways to extend the agent:

### Hooks (runtime guards)
```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "Bash(rm *)",
      "hooks": [{"type": "command", "command": "echo 'BLOCKED' && exit 1"}]
    }]
  }
}
```
Shell commands that run before/after tool execution. Non-zero exit = block the tool.

### Skills (prompt templates)
```markdown
---
description: Create a git commit
user-invocable: true
---
Look at the git diff, then create a commit with a clear message.
```
Markdown files in `.claude/skills/` that become `/skill-name` commands.

---

## Design Decisions Worth Studying

| Decision | Why |
|---|---|
| Tools return errors, not exceptions | Lets the model self-correct |
| Read-before-edit requirement | Prevents edits based on hallucinated file content |
| Parallel read-only tools | Simple concurrency with zero coordination |
| JSONL session storage | Append-only, crash-safe, streamable |
| YAML frontmatter for skills | Human-readable, git-friendly, no build step |
| Settings hierarchy (global < project < local) | Same pattern as .gitconfig |
| Auto-compact via summarization | Extends effective context window transparently |

---

## What's NOT Here (and why)

Intentionally omitted to keep the codebase focused:

- **Security classifiers**: Claude Code's auto-mode uses a classifier to approve/deny tools. We use rule-based permission modes instead.
- **Telemetry**: No analytics or event logging.
- **OAuth flow**: No browser-based authentication. API key auth only.
- **MCP HTTP transport**: Only stdio transport is implemented. HTTP/SSE transport is not yet supported.
