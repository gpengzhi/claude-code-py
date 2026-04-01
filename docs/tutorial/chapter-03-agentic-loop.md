# Chapter 3: The Agentic Loop

Chapter 2 ended with a 20-line while-loop that called the model and executed tools. That loop was the skeleton. This chapter puts muscles on it -- error recovery, parallel execution, context management, and infinite-loop protection. By the end, you'll have a production-grade agentic loop.

## What You'll Learn

- The full while(true) loop that makes agents autonomous
- Why max_turns matters (infinite loop protection)
- Parallel execution for read-only tools with asyncio.gather
- How to handle tool errors gracefully (return to model, don't crash)
- Auto-compact when context gets too long
- max_output_tokens recovery (resume mid-thought)
- Tool result budget (truncating old results to save context space)

## The Skeleton vs. The Real Thing

In Chapter 2, the loop was simple:

```
while True:
    response = call_model()
    if no tool_use: break
    results = execute_tools()
    messages.append(results)
```

The production loop handles six more things:

```
while turn < max_turns:                    # 1. Infinite loop protection
    if abort_event.is_set(): return        # 2. User interruption
    messages = apply_budget(messages)       # 3. Tool result budget
    messages = maybe_compact(messages)      # 4. Auto-compact
    response = call_model(messages)
    if max_tokens_hit: inject_resume()     # 5. Output recovery
    if no tool_use: break
    results = execute_tools_smart()        # 6. Parallel execution
    messages.append(results)
```

Let's build each piece.

## Step 1: The Loop Shell

```python
# src/query/loop.py
async def query_loop(
    messages: list[dict],
    system_prompt: str,
    model: str,
    max_tokens: int = 16384,
    tools: list[Tool] | None = None,
    abort_event: asyncio.Event | None = None,
    max_turns: int = 100,
) -> AsyncGenerator[AssistantMessage | dict, None]:
    """Core agentic loop."""

    turn_count = 0
    working_messages = list(messages)
    max_output_recovery_count = 0

    while turn_count < max_turns:
        turn_count += 1

        # --- Check for user interruption ---
        if abort_event and abort_event.is_set():
            yield {"type": "system_event", "event": "aborted"}
            return

        # --- Apply tool result budget ---
        working_messages = apply_tool_result_budget(working_messages)

        # --- Auto-compact check ---
        working_messages, did_compact = await compact_tracker.maybe_compact(
            working_messages, model
        )
        if did_compact:
            yield {"type": "system_event", "event": "compacted"}

        # --- Call the model ---
        assistant_message = None
        tool_use_blocks = []

        async for event in query_model(
            messages=working_messages,
            system_prompt=system_prompt,
            model=model,
            max_tokens=max_tokens,
            tools=tools,
        ):
            if isinstance(event, AssistantMessage):
                assistant_message = event
                yield event
                for block in event.content:
                    if isinstance(block, ToolUseBlock):
                        tool_use_blocks.append(block)
            elif isinstance(event, dict):
                yield event  # Pass through stream events

        if assistant_message is None:
            return

        # --- max_output_tokens recovery ---
        if (
            assistant_message.stop_reason == "max_tokens"
            and not tool_use_blocks
            and max_output_recovery_count < 3
        ):
            max_output_recovery_count += 1
            working_messages.append(assistant_message.to_dict())
            working_messages.append({
                "role": "user",
                "content": "Output token limit hit. Resume directly -- no recap.",
            })
            continue  # Re-enter the loop

        # --- Append assistant message ---
        working_messages.append(assistant_message.to_dict())

        # --- If no tool use, we're done ---
        if not tool_use_blocks:
            return

        max_output_recovery_count = 0  # Reset on successful tool use

        # --- Execute tools ---
        tool_results = await run_tools(tool_use_blocks, tools, context)
        working_messages.append({
            "role": "user",
            "content": [r.to_dict() for r in tool_results],
        })

        yield {"type": "tool_results", "turn": turn_count, "count": len(tool_results)}
```

That's about 70 lines. Let's break down each piece.

## Step 2: Infinite Loop Protection (max_turns)

Without a limit, a confused model can loop forever -- calling tools, getting results, calling more tools, and never stopping. This is the most common agent failure mode.

```python
while turn_count < max_turns:    # Default: 100
    turn_count += 1
    ...
```

**Why 100?** It's enough for complex multi-file refactors (which typically take 10-30 turns) but catches runaway loops before they burn your API budget. The user can override it.

```
Turn 1:   Read file A          ─┐
Turn 2:   Read file B           │  Normal operation
Turn 3:   Edit file A           │
Turn 4:   Run tests            ─┘
Turn 5:   Fix test failure     ─┐
Turn 6:   Run tests again       │  Recovery
Turn 7:   All tests pass       ─┘  (stop_reason: "end_turn")
```

If the model reaches turn 100 without stopping, something is wrong. The loop exits and the UI shows a warning.

## Step 3: Parallel Tool Execution

When the model requests multiple read-only tools, there's no reason to run them one at a time. Reading 5 files sequentially takes 5x longer than reading them in parallel.

```python
# src/tool/executor.py
async def run_tools(tool_use_blocks, tools, context):
    """Execute tools -- read-only in parallel, writes serially."""
    tool_map = {t.name: t for t in tools}
    results = []
    parallel_batch = []

    for block in tool_use_blocks:
        tool = tool_map[block.name]
        parsed = tool.input_model.model_validate(block.input)

        if tool.is_concurrency_safe(parsed):
            parallel_batch.append((tool, block.input, block.id))
        else:
            # Flush parallel batch before running a write tool
            if parallel_batch:
                batch_results = await asyncio.gather(*[
                    execute_tool(t, inp, uid, context)
                    for t, inp, uid in parallel_batch
                ])
                results.extend(batch_results)
                parallel_batch = []
            # Run write tool serially
            results.append(await execute_tool(tool, block.input, block.id, context))

    # Flush remaining parallel batch
    if parallel_batch:
        batch_results = await asyncio.gather(*[
            execute_tool(t, inp, uid, context)
            for t, inp, uid in parallel_batch
        ])
        results.extend(batch_results)

    return results
```

The key is `is_concurrency_safe()`. Each tool declares whether it's safe to run in parallel:

```python
class ReadTool(Tool):
    def is_concurrency_safe(self, args) -> bool:
        return True   # Reading never conflicts

class BashTool(Tool):
    def is_concurrency_safe(self, args) -> bool:
        return False  # Commands can have side effects

class EditTool(Tool):
    def is_concurrency_safe(self, args) -> bool:
        return False  # File writes must be serialized
```

The pattern: read-only tools batch into `asyncio.gather()`. When a write tool appears, flush the batch, run the write, then start a new batch.

```
Model requests:  [Read A, Read B, Read C, Edit D, Read E]
                  └─── parallel ───┘  │serial│  │serial│
                                                (could batch
                                                 with next reads)
```

## Step 4: Graceful Error Handling

The golden rule: **never crash on a tool error. Return it to the model.**

```python
async def execute_tool(tool, tool_input, tool_use_id, context):
    """Execute a single tool with full error handling."""

    # 1. Validate input
    try:
        parsed = tool.input_model.model_validate(tool_input)
    except ValidationError as e:
        return ToolResultBlock(
            tool_use_id=tool_use_id,
            content=f"Input validation error: {e}",
            is_error=True,   # <-- Tell the model it failed
        )

    # 2. Execute
    try:
        result = await tool.call(parsed, context)
    except asyncio.CancelledError:
        return ToolResultBlock(
            tool_use_id=tool_use_id,
            content="Tool execution was cancelled.",
            is_error=True,
        )
    except Exception as e:
        return ToolResultBlock(
            tool_use_id=tool_use_id,
            content=f"Error executing {tool.name}: {e}",
            is_error=True,   # <-- Model sees the error and adapts
        )

    # 3. Format and return
    return ToolResultBlock(
        tool_use_id=tool_use_id,
        content=tool.format_result(result),
        is_error=result.is_error,
    )
```

**Why this matters**: The model is remarkably good at recovering from errors:

| Error | Model's Recovery |
|---|---|
| "File not found: main.py" | Searches for the correct path |
| "Permission denied" | Asks the user or tries a different approach |
| "Command timed out" | Breaks the command into smaller steps |
| "Invalid regex: unclosed (" | Fixes the regex and retries |
| "Input validation error" | Reformats the arguments |

If you crash instead, the user sees a traceback and has to restart. If you return the error, the model self-corrects in the next turn.

## Step 5: Auto-Compact

The API has a context window limit (typically 200K tokens). Long conversations eventually hit it. Auto-compact detects when you're approaching the limit and summarizes older messages:

```python
class AutoCompactTracker:
    """Monitors context size and triggers compaction when needed."""

    async def maybe_compact(self, messages, model):
        """Check if context is too large and compact if needed."""
        total_tokens = estimate_tokens(messages)

        if total_tokens < COMPACT_THRESHOLD:
            return messages, False  # No compaction needed

        # Ask the model to summarize the conversation so far
        summary = await summarize_conversation(messages, model)

        # Replace old messages with the summary
        compacted = [
            {"role": "user", "content": f"[Conversation summary: {summary}]"},
            messages[-1],  # Keep the most recent message
        ]
        return compacted, True
```

```
Before compact (approaching 200K tokens):
┌───────────────────────────────────┐
│ msg 1: "Read all test files"      │
│ msg 2: [Read result: 5000 lines]  │
│ msg 3: [Read result: 3000 lines]  │  <- These are huge
│ msg 4: [Read result: 4000 lines]  │
│ msg 5: "Now fix the bug in..."    │
│ msg 6: [Edit result]              │
│ msg 7: "Run the tests"            │
│ msg 8: [Bash result: all pass]    │
└───────────────────────────────────┘

After compact:
┌───────────────────────────────────┐
│ [Summary: Read 3 test files,      │
│  fixed a null-check bug in foo.py │
│  line 42, all tests now pass]     │
│ msg 8: [Bash result: all pass]    │  <- Keep recent context
└───────────────────────────────────┘
```

The model keeps working with full context of what it did, just without the raw file contents it no longer needs.

## Step 6: max_output_tokens Recovery

Sometimes the model's response gets cut off mid-sentence because it hits the output token limit. Instead of losing that work, we inject a "continue" message:

```python
if (
    assistant_message.stop_reason == "max_tokens"
    and not tool_use_blocks
    and max_output_recovery_count < MAX_RECOVERY_ATTEMPTS  # 3
):
    max_output_recovery_count += 1

    # Keep the partial response
    working_messages.append(assistant_message.to_dict())

    # Ask it to continue
    working_messages.append({
        "role": "user",
        "content": (
            "Output token limit hit. Resume directly -- "
            "no apology, no recap of what you were doing. "
            "Pick up mid-thought if that is where the cut happened. "
            "Break remaining work into smaller pieces."
        ),
    })
    continue  # Back to top of while loop
```

```
Turn N:   Model writes 16K tokens of code... [CUT OFF]
          stop_reason: "max_tokens"
          │
          ▼
Turn N+1: "Resume directly -- no recap..."
          Model continues exactly where it left off
          │
          ▼
Turn N+2: (if still cut off, retry again, up to 3 times)
```

**Why "no apology, no recap"?** Without this instruction, the model wastes tokens saying "I apologize for being cut off. Let me continue where I left off. I was working on..." -- which wastes the limited output budget on fluff.

**Why max 3 retries?** If the model can't finish in 3 continuations (~48K output tokens), it's probably generating something too large and needs to break the task into pieces.

## Step 7: Tool Result Budget

Old tool results accumulate in the message history. A single `Read` of a large file might be 50K characters. After 20 tool calls, you've used half your context window on stale data.

The budget system walks messages from newest to oldest, tracking total size. When the budget (800K chars, roughly 200K tokens) is exceeded, it replaces old results with stubs:

```python
TOOL_RESULT_BUDGET_CHARS = 800_000

def apply_tool_result_budget(messages):
    """Truncate oversized tool results in older messages."""
    total_chars = 0

    # Walk from newest to oldest (preserve recent results)
    for i in range(len(messages) - 1, -1, -1):
        content = messages[i].get("content", "")
        if isinstance(content, list):
            for j, block in enumerate(content):
                if block.get("type") == "tool_result":
                    block_size = len(str(block.get("content", "")))
                    total_chars += block_size
                    if total_chars > TOOL_RESULT_BUDGET_CHARS:
                        # Replace with stub
                        messages[i]["content"][j] = {
                            **block,
                            "content": "[Tool result truncated to save context space]",
                        }

    return messages
```

```
Message history (newest at bottom):
┌─────────────────────────────────────┐
│ tool_result: [50K chars] ──────► [truncated stub]   │  Over budget
│ tool_result: [30K chars] ──────► [truncated stub]   │  Over budget
│ tool_result: [40K chars] ──────► [kept as-is]       │  Under budget
│ tool_result: [10K chars] ──────► [kept as-is]       │  Under budget
└─────────────────────────────────────┘
                ▲                    ▲
           Oldest (truncate first)  Newest (preserve)
```

The model can always re-read a file if it needs the content again. But keeping stale results wastes context that could be used for new work.

## Try It

Here's a minimal version you can run to see the recovery paths:

```python
import asyncio
from src.query.loop import query_loop

async def main():
    messages = [{"role": "user", "content": "Read every .py file in src/ and summarize them"}]

    async for event in query_loop(
        messages=messages,
        system_prompt="You are a helpful coding assistant.",
        model="claude-sonnet-4-20250514",
        tools=[ReadTool(), BashTool()],
        max_turns=50,
    ):
        if isinstance(event, dict):
            if event.get("event") == "compacted":
                print("[auto-compact triggered]")
            elif event.get("event") == "max_tokens_recovery":
                print(f"[resuming, attempt {event['attempt']}]")
            elif event.get("type") == "tool_results":
                print(f"[turn {event['turn']}: {event['count']} tools executed]")

asyncio.run(main())
```

## What Just Happened

```
User: "Read every .py file and summarize"
 │
 ▼
┌─ Turn 1 ────────────────────────────────────────┐
│ Model: tool_use Read(src/main.py)               │
│        tool_use Read(src/utils.py)   ← parallel │
│        tool_use Read(src/config.py)  ← parallel │
│                                                  │
│ Executor: asyncio.gather(Read, Read, Read)       │
│ Results: 3 tool_result blocks                    │
└──────────────────────────────────────────────────┘
 │
 ▼
┌─ Turn 2 ────────────────────────────────────────┐
│ Model: tool_use Read(src/api.py)                │
│        tool_use Read(src/db.py)      ← parallel │
│                                                  │
│ Executor: asyncio.gather(Read, Read)             │
│ [Budget check: 200K chars used, under 800K]      │
└──────────────────────────────────────────────────┘
 │
 ▼
┌─ Turn 3 ────────────────────────────────────────┐
│ Model: "Here is a summary of all files..."      │
│ stop_reason: "max_tokens"  (cut off!)           │
│                                                  │
│ Recovery: inject "Resume directly..."            │
└──────────────────────────────────────────────────┘
 │
 ▼
┌─ Turn 4 ────────────────────────────────────────┐
│ Model: "...continuing the summary..."           │
│ stop_reason: "end_turn"                         │
│                                                  │
│ No tool_use → loop exits                         │
└──────────────────────────────────────────────────┘
```

## The Complete Picture

```
                    ┌───────────────────────────┐
                    │       query_loop()        │
                    │                           │
                    │  while turn < max_turns:  │
                    │    ┌─────────────────┐    │
                    │    │ Budget + Compact│    │
                    │    └────────┬────────┘    │
                    │             │             │
                    │    ┌────────▼────────┐    │
                    │    │  query_model()  │    │
                    │    │  (streaming)    │    │
                    │    └────────┬────────┘    │
                    │             │             │
                    │      ┌──────┴──────┐     │
                    │      │             │     │
                    │  max_tokens?   tool_use? │
                    │      │             │     │
                    │  inject       ┌────▼───┐ │
                    │  resume       │run_tools│ │
                    │  continue     │        │ │
                    │               │parallel│ │
                    │               │+ serial│ │
                    │               └────┬───┘ │
                    │                    │     │
                    │             no tool_use? │
                    │                 return   │
                    └───────────────────────────┘
```

## Code Reference

The production version of this chapter lives in:
- [`src/claude_code/query/loop.py`](../../src/claude_code/query/loop.py) -- The full agentic loop with all recovery paths
- [`src/claude_code/tool/executor.py`](../../src/claude_code/tool/executor.py) -- Tool execution pipeline (parallel + serial)
- [`src/claude_code/tool/streaming_executor.py`](../../src/claude_code/tool/streaming_executor.py) -- Start tool execution while model is still streaming
- [`src/claude_code/services/compact/`](../../src/claude_code/services/compact/) -- Auto-compact implementation

---

**[← Chapter 2: Adding Tools](chapter-02-adding-tools.md) | [Chapter 4: A Real Terminal UI →](chapter-04-terminal-ui.md)**
