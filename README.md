# Build Production-Level Claude Code in Python

> We studied the architecture of Claude Code and rebuilt it in ~8,800 lines of Python so you can understand every system, every edge case, and every design decision that makes a production AI coding agent work.

[![Python](https://img.shields.io/badge/python-3.11%2B-blue)]()
[![License](https://img.shields.io/badge/license-MIT-green)]()

## Why This Exists

Most "build your own agent" tutorials stop at the 5-line loop:

```python
while True:
    response = call_model(messages, tools)
    if no tool_use: break
    results = execute_tools(response)
    messages.append(results)
```

Real-world agents like [Claude Code](https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/overview) have 500,000+ lines on top of this loop. **What are all those lines doing?**

This project answers that question -- with ~8,800 lines of working Python that you can read, run, and modify. Every module maps to the original Claude Code architecture. Every design decision is explained in the [7-chapter tutorial](docs/tutorial/).

## Quick Start

```bash
git clone https://github.com/gpengzhi/claude-code-py.git
cd claude-code-py
pip install -e .
export ANTHROPIC_API_KEY=sk-ant-...

# Non-interactive mode
claude-code-py -p "What files are in this directory?"

# Interactive TUI
claude-code-py
```

## What's Inside

**16 tools** matching Claude Code's tool names and schemas -- Bash (with 15 security checks + sandbox), Read, Edit, Write, Glob, Grep, WebFetch, Agent, TaskCreate/Get/Update/List, EnterPlanMode, ExitPlanMode, AskUserQuestion, Skill.

**Streaming API layer** -- prompt caching, extended thinking, cost tracking, retry with backoff, multi-provider support (Anthropic, Bedrock, Vertex).

**Context engineering** -- 11-section system prompt matching the TypeScript original, CLAUDE.md loading, git context injection, persistent memory across sessions.

**Safety** -- 5 permission modes with wildcard rules, Pre/PostToolUse hooks, cost threshold ($5 warn, $25 stop), auto-compact when approaching context limits.

**MCP client** -- stdio transport for Model Context Protocol servers, with tool discovery and execution.

## Reading the Code

**Start here** -- the agentic loop:
- [`query/loop.py`](src/claude_code/query/loop.py) -- The while loop, recovery paths, streaming executor

**The tool system:**
- [`tool/base.py`](src/claude_code/tool/base.py) -- Tool protocol
- [`tool/executor.py`](src/claude_code/tool/executor.py) -- 7-step execution pipeline
- [`tool/streaming_executor.py`](src/claude_code/tool/streaming_executor.py) -- Start tools during streaming
- [`tools/bash_tool/security.py`](src/claude_code/tools/bash_tool/security.py) -- 15 security checks

**Context engineering:**
- [`context/system_prompt.py`](src/claude_code/context/system_prompt.py) -- 11-section system prompt
- [`services/api/claude.py`](src/claude_code/services/api/claude.py) -- Streaming API with prompt caching
- [`services/compact/compact.py`](src/claude_code/services/compact/compact.py) -- Auto-compact

**Safety & extensibility:**
- [`permissions/check.py`](src/claude_code/permissions/check.py) -- Permission modes and rules
- [`hooks/runner.py`](src/claude_code/hooks/runner.py) -- Hook execution
- [`services/mcp/client.py`](src/claude_code/services/mcp/client.py) -- MCP client

## Learn: Build It From Scratch

A [7-chapter tutorial](docs/tutorial/) that builds this entire codebase step by step. Each chapter adds one layer, with working code at every stage.

| | Chapter | What You Build |
|---|---|---|
| 1 | [Hello Agent](docs/tutorial/chapter-01-hello-agent.md) | A CLI that streams responses from Claude |
| 2 | [Adding Tools](docs/tutorial/chapter-02-adding-tools.md) | The tool protocol -- teach your agent to read files and run commands |
| 3 | [The Agentic Loop](docs/tutorial/chapter-03-agentic-loop.md) | Autonomous tool chaining, parallel execution, error recovery |
| 4 | [A Real Terminal UI](docs/tutorial/chapter-04-terminal-ui.md) | Interactive REPL with streaming, spinners, and permission dialogs |
| 5 | [Context Engineering](docs/tutorial/chapter-05-context-engineering.md) | System prompt assembly, CLAUDE.md, git context, persistent memory |
| 6 | [Permissions and Safety](docs/tutorial/chapter-06-permissions-safety.md) | Security checks, sandboxing, permission modes, hooks |
| 7 | [Extension Points](docs/tutorial/chapter-07-extension-points.md) | Skills, MCP client, slash commands |

Also see: [How AI Coding Agents Work](docs/how-ai-coding-agents-work.md) -- a conceptual overview of the architecture.

## CLI Options

```
Usage: claude-code-py [OPTIONS] [PROMPT]

Options:
  --version                       Show version
  -p, --print                     Non-interactive print mode
  -m, --model TEXT                Model to use
  --max-tokens INTEGER            Max response tokens (default: 16384)
  --max-turns INTEGER             Max agentic turns (default: 100)
  --system-prompt TEXT            Custom system prompt
  --permission-mode               default|acceptEdits|plan|bypassPermissions|dontAsk
  --dangerously-skip-permissions  Bypass all permission checks
  --resume TEXT                   Resume a previous session by ID
  --thinking                      Enable extended thinking
  --verbose                       Debug logging
```
