# Chapter 1: Hello Agent

In this chapter, you'll build a CLI that sends a prompt to Claude and streams the response in real-time. By the end, you'll have a working `agent.py` that you can run from your terminal.

## What You'll Learn

- How the Anthropic Messages API works
- What Server-Sent Events (SSE) streaming looks like
- How to build a CLI entry point with Click

## The Shortest Possible Agent

Before we build anything production-quality, let's see the absolute minimum code for an AI agent. It's 15 lines:

```python
import anthropic

client = anthropic.Anthropic()

messages = [{"role": "user", "content": "What is 2+2?"}]

with client.messages.stream(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    messages=messages,
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
print()
```

That's a complete agent (minus tools). The API returns text in chunks, and we print each chunk as it arrives. This is streaming.

But this isn't useful yet. Let's build it properly.

## Step 1: Project Setup

```bash
mkdir my-agent && cd my-agent
python -m venv .venv && source .venv/bin/activate
pip install anthropic click
```

## Step 2: The API Client

The Anthropic SDK handles authentication, retries, and HTTP connections. We wrap it in a function so we can swap providers later:

```python
# src/api_client.py
import os
from anthropic import AsyncAnthropic

def get_client() -> AsyncAnthropic:
    """Create the Anthropic async client."""
    return AsyncAnthropic(
        api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        base_url=os.environ.get("ANTHROPIC_BASE_URL"),  # Optional proxy
    )
```

**Why async?** Tool execution will involve file I/O and subprocess calls. Async lets us run multiple tools concurrently in Chapter 3.

## Step 3: Streaming

The API uses Server-Sent Events (SSE) -- a standard for streaming HTTP responses. Each event has a type:

| Event | Meaning |
|---|---|
| `message_start` | Response is beginning |
| `content_block_start` | A new text/tool_use block is starting |
| `content_block_delta` | Incremental text for the current block |
| `content_block_stop` | The block is complete |
| `message_delta` | Final stats (token usage, stop reason) |
| `message_stop` | Response is done |

Here's how we process them:

```python
# src/streaming.py
import asyncio
import json
from dataclasses import dataclass, field

@dataclass
class AssistantMessage:
    """A complete response from the model."""
    text: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str | None = None
    cost_usd: float = 0.0

async def stream_response(client, messages, system_prompt="", model="claude-sonnet-4-20250514"):
    """Stream a response from the API, yielding text chunks as they arrive."""
    accumulated_text = ""

    async with client.messages.stream(
        model=model,
        max_tokens=16384,
        system=system_prompt,
        messages=messages,
    ) as stream:
        async for event in stream:
            if event.type == "content_block_delta":
                if event.delta.type == "text_delta":
                    chunk = event.delta.text
                    accumulated_text += chunk
                    yield {"type": "text", "text": chunk}

        # Get final message for usage stats
        final = await stream.get_final_message()

    yield {
        "type": "done",
        "message": AssistantMessage(
            text=accumulated_text,
            model=model,
            input_tokens=final.usage.input_tokens,
            output_tokens=final.usage.output_tokens,
            stop_reason=final.stop_reason,
        ),
    }
```

**Key insight**: We yield each text chunk immediately for real-time display, AND accumulate the full text for the final message. The caller decides what to do with each.

## Step 4: The CLI

```python
# agent.py
import asyncio
import sys
import click

from src.api_client import get_client
from src.streaming import stream_response

@click.command()
@click.option("-p", "--print", "print_mode", is_flag=True, help="Print mode")
@click.option("-m", "--model", default="claude-sonnet-4-20250514")
@click.argument("prompt", required=False)
def main(print_mode, model, prompt):
    """A minimal AI coding agent."""
    if not prompt:
        if not sys.stdin.isatty():
            prompt = sys.stdin.read().strip()
        else:
            click.echo("Usage: python agent.py -p 'your prompt'")
            return

    asyncio.run(run(prompt, model))

async def run(prompt, model):
    client = get_client()
    messages = [{"role": "user", "content": prompt}]

    async for event in stream_response(client, messages, model=model):
        if event["type"] == "text":
            sys.stdout.write(event["text"])
            sys.stdout.flush()
        elif event["type"] == "done":
            msg = event["message"]
            sys.stdout.write("\n")
            # Print usage to stderr
            sys.stderr.write(
                f"\n[{msg.input_tokens} in, {msg.output_tokens} out, "
                f"stop: {msg.stop_reason}]\n"
            )

if __name__ == "__main__":
    main()
```

## Try It

```bash
export ANTHROPIC_API_KEY=your-key-here
python agent.py -p "Explain what an agentic loop is in 3 sentences."
```

You should see the response stream in real-time, followed by token usage stats.

## What Just Happened

```
Your terminal                    Anthropic API
    │                                │
    ├─ POST /v1/messages ──────────► │
    │   {messages, model, stream}    │
    │                                │
    │ ◄── SSE: content_block_delta ──┤  "An"
    │ ◄── SSE: content_block_delta ──┤  " agentic"
    │ ◄── SSE: content_block_delta ──┤  " loop"
    │ ◄── SSE: content_block_delta ──┤  " is..."
    │           ...                  │
    │ ◄── SSE: message_stop ─────────┤
    │                                │
    done                             done
```

One HTTP request, many SSE events. That's all streaming is.

## What's Missing

This agent can only talk. It can't *do* anything -- it can't read files, edit code, or run commands. In Chapter 2, we'll give it tools.

## Code Reference

The production version of this chapter lives in:
- [`src/claude_code/services/api/client.py`](../../src/claude_code/services/api/client.py) -- API client
- [`src/claude_code/services/api/claude.py`](../../src/claude_code/services/api/claude.py) -- Streaming implementation
- [`src/claude_code/cli.py`](../../src/claude_code/cli.py) -- CLI entry point

---

**Next: [Chapter 2: Adding Tools →](chapter-02-adding-tools.md)**
