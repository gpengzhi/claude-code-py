# Build Production-Level Claude Code in Python

> Production-quality open-source Claude Code in Python -- readable enough to learn from, robust enough to use.

[![Tests](https://img.shields.io/badge/tests-186%20passed-brightgreen)]()
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)]()
[![License](https://img.shields.io/badge/license-MIT-green)]()

## What Is This?

An open-source Python implementation of [Claude Code](https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/overview) -- Anthropic's agentic coding tool. It implements the same tools, the same agentic loop, and the same safety model as the real thing, in ~8,800 lines of readable Python.

**This is not a toy.** It has real sandboxed shell execution, real file editing with encoding detection, real MCP integration, real permission scoping, and a conformance test suite proving behavioral parity with the TypeScript original.

## Why Does This Exist?

Most "build your own agent" tutorials stop at the 5-line loop:

```python
while True:
    response = call_model(messages, tools)
    if no tool_use: break
    results = execute_tools(response)
    messages.append(results)
```

Real-world agents like Claude Code have 500,000+ lines on top of this loop. **What are all those lines doing?** This project answers that question -- with ~8,800 lines of working Python that you can read, run, and modify.

There's a gap in the ecosystem:

| | [learn-claude-code](https://github.com/shareAI-lab/learn-claude-code) | **claude-code-py** | Official Claude Code |
|---|---|---|---|
| Purpose | Tutorial | Learn & Use | Production tool |
| Lines of code | ~2K | ~8.8K | ~500K |
| Tools | 1 (bash blocklist) | 17 (conformance-tested) | 40+ |
| Security | String-match blocklist | 15 checks + sandbox | Full sandbox |
| MCP support | No | Yes (stdio + HTTP) | Yes |
| Permission system | No | 5 modes + rules | Full |
| Hooks | No | Pre/PostToolUse | Full |
| Tests | None | 186 (unit + conformance) | Internal |
| Can you use it? | No | **Yes** | Yes |
| Can you read it? | Yes | **Yes** | Not really |
| Can you modify it? | Yes | **Yes** | No |

## Quick Start

```bash
pip install -e ".[dev]"
export ANTHROPIC_API_KEY=sk-ant-...

# Non-interactive mode
claude-code-py -p "What files are in this directory?"

# Interactive TUI
claude-code-py

# With a specific model
claude-code-py -m claude-opus-4-20250514 -p "Review this codebase"

# Resume a previous session
claude-code-py --resume <session-id>

# Bypass permissions (for CI/scripts)
claude-code-py --dangerously-skip-permissions -p "Fix the failing test"
```

## Architecture

```
CLI (cli.py)
 |
 +-- Settings & Config (utils/config.py)
 |     Merges: ~/.claude/settings.json < .claude/settings.json < env vars < CLI flags
 |
 +-- Context Assembly (context/)
 |     System prompt (11 sections) + CLAUDE.md + git context + memory
 |
 +-- QueryEngine (query/engine.py)
 |     Owns message history, usage tracking, abort handling
 |
 +-- Query Loop (query/loop.py)  <-- THE CORE
 |     while turn < max_turns:
 |       1. Apply tool result budget (truncate old results)
 |       2. Auto-compact if approaching context limit
 |       3. Stream model response
 |       4. Start read-only tools during streaming
 |       5. Execute remaining tools (parallel if safe, serial if not)
 |       6. Recovery: max_tokens retry, compact, budget trim
 |
 +-- Tool Execution Pipeline (tool/executor.py)
 |     Parse input -> Validate -> PreToolUse hooks -> Permissions -> Execute -> PostToolUse hooks -> Truncate
 |
 +-- 17 Built-in Tools (tools/)
 |     Bash, Read, Edit, Write, Glob, Grep, WebFetch, WebSearch, Agent,
 |     TaskCreate/Get/Update/List, EnterPlanMode, ExitPlanMode,
 |     AskUserQuestion, Skill
 |
 +-- MCP Tools (services/mcp/ + tools/mcp_tool/)
 |     Discovers and wraps MCP server tools as native tools
 |
 +-- Permissions (permissions/check.py)
 |     5 modes: default, acceptEdits, plan, bypassPermissions, dontAsk
 |     Rule matching with fnmatch wildcards
 |
 +-- Hooks (hooks/)
 |     command hooks (shell), http hooks (webhook), loaded from settings.json
 |
 +-- TUI (tui/)
       Textual app: streaming markdown, spinner, status bar, permission dialogs, vim mode
```

## What Makes This Production-Quality

### Security (not a blocklist)

The Bash tool has **15 named security checks** ported from the TypeScript original:
- Control characters, unicode whitespace, IFS injection
- Command substitution via backticks, ANSI-C quoting
- `/proc/*/environ` access, dangerous variable contexts
- Brace expansion, comment-quote desync, newline injection
- macOS/Linux sandbox support

### Reliability

- **Prompt caching** -- `cache_control: ephemeral` on system prompt and last message
- **Auto-compact** -- summarizes oldest 2/3 of messages when hitting 80% of context window
- **max_output_tokens recovery** -- up to 3 retries with "resume mid-thought" messages
- **Tool result budget** -- truncates old tool results when total exceeds 800K chars
- **Streaming tool execution** -- starts read-only tools before the model finishes responding
- **Cost threshold** -- warns at $5, hard-stops at $25 to prevent runaway agents
- **Extended thinking** -- `--thinking` flag enables interleaved thinking blocks
- **API retry** with exponential backoff (3 attempts)

### Conformance-Tested

89 conformance tests verify behavioral parity with the TypeScript original:
- Tool schemas match field-by-field (names, types, required flags)
- Behavioral tests: read-before-edit, 1-based offset, replace_all, non-unique rejection
- Config paths, settings merge precedence, memory format, session JSONL format

```bash
pytest conformance/ -v
```

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
- [`services/mcp/client.py`](src/claude_code/services/mcp/client.py) -- MCP client (stdio + HTTP)

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
  -m, --model TEXT                Model (e.g., claude-sonnet-4-20250514)
  --max-tokens INTEGER            Max response tokens (default: 16384)
  --max-turns INTEGER             Max agentic turns (default: 100)
  --system-prompt TEXT            Custom system prompt
  --permission-mode               default|acceptEdits|plan|bypassPermissions|dontAsk
  --dangerously-skip-permissions  Bypass all permission checks
  --resume TEXT                   Resume a previous session by ID
  --thinking                      Enable extended thinking
  --verbose                       Debug logging
```

## Running Tests

```bash
# All tests
pytest tests/ conformance/ -v

# Just conformance (schema + behavioral parity)
pytest conformance/ -v

# Just unit tests
pytest tests/ -v
```

## Contributing

Contributions welcome. The conformance test suite is the quality bar:

```bash
pytest conformance/ -v  # Must pass
pytest tests/ -v        # Must pass
```

Areas of interest:
- Additional conformance tests for edge cases
- MCP HTTP transport completion
- Additional tool implementations
- Performance profiling and optimization

## License

MIT
