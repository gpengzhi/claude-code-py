# claude-code-py

**Learn how to build production-level Claude Code in Python.**

This is a faithful Python reimplementation of [Claude Code](https://claude.ai/code) -- Anthropic's CLI coding agent. We studied the architecture of Claude Code and rebuilt it from scratch so you can understand every system, every edge case, and every design decision that makes a production AI agent work.

If tutorials like [learn-claude-code](https://github.com/shareAI-lab/learn-claude-code) taught you what a harness is in 20 lines -- this repo shows you what the other **9,600 lines** are for.

## Why This Exists

Most "build your own agent" tutorials show you the loop:

```python
while True:
    response = call_model(messages, tools)
    if no tool_use: break
    results = execute_tools(response)
    messages.append(results)
```

That's 5 lines. Claude Code is 200,000 lines. **What are the other 199,995 lines doing?**

This repo answers that question with working code:

- Why does the model need 8 behavioral instruction sections in the system prompt?
- Why does `Read` track file mtimes and reject edits on stale files?
- Why does the query loop need 3 different recovery paths for token limits?
- Why are there 15 security checks on every shell command?
- Why does prompt caching need cache_control breakpoints on both system blocks and messages?
- Why does `grep exit 1` need special handling (it's not an error)?

Every answer is in the code, with the same architecture as the real Claude Code.

## Who This Is For

- Developers who finished intro tutorials and want the **full picture**
- Engineers building **production** agentic systems (not demos)
- Anyone who wants to understand **why Claude Code works so well** -- not just what it does

## What Makes This Different

|  | Intro tutorials | **This repo** |
|---|---|---|
| Core loop | 20-line example | 9,630 lines of production code |
| Tools | Simplified stubs | 18 tools matching Claude Code's schemas field-by-field |
| System prompt | "You are a helpful assistant" | 8 static + 3 dynamic sections ported verbatim from Claude Code |
| Security | None | 15 bash security checks (control chars, injection, unicode) |
| Error handling | try/except | Retry with backoff, max_tokens recovery, auto-compact, tool result budget |
| Permissions | None | 5 modes, wildcard rule matching, hook integration |
| Testing | Maybe a few | 215 unit tests + 90 conformance tests against the original |
| Usable? | Example code | **pip install and use as a real coding agent** |

## Quick Start

```bash
# Install
pip install -e ".[dev]"

# Use it (non-interactive)
export ANTHROPIC_API_KEY=your-key
claude-code-py -p "Read pyproject.toml and tell me the version"

# Use it (interactive TUI)
claude-code-py

# Run tests
pytest tests/ conformance/ -v
```

## Architecture

```
┌─────────────────────────────────────────────────┐
│                CLI (cli.py)                      │
├─────────────────────────────────────────────────┤
│         Interactive TUI (tui/)                   │
│   MessageList · Spinner · StatusBar · Prompts    │
├─────────────────────────────────────────────────┤
│        Query Engine (query/)                     │
│   call_model → run_tools → repeat               │
│   + auto-compact + max_tokens recovery           │
│   + tool result budget + abort handling          │
├─────────────────────────────────────────────────┤
│          Tool System (tool/, tools/)             │
│   18 tools · Pydantic schemas · parallel exec    │
│   + streaming executor + security checks         │
├─────────────────────────────────────────────────┤
│        Permissions (permissions/)                │
│   5 modes · rule matching · PreToolUse hooks     │
├─────────────────────────────────────────────────┤
│      Context Engine (context/, memory/)          │
│   System prompt (11 sections) · CLAUDE.md        │
│   Git context · Memory · Prompt caching          │
├─────────────────────────────────────────────────┤
│     Extensions (hooks/, skills/, plugins/)        │
│   Hook system · 11 slash commands · Skills       │
│   Plugin loader · MCP client · OAuth             │
└─────────────────────────────────────────────────┘
```

## Reading Guide: From Loop to Production

### Level 1: The Core Loop
*"I want to understand how AI coding agents work."*

- [`query/loop.py`](src/claude_code/query/loop.py) -- The agentic while-loop
- [`services/api/claude.py`](src/claude_code/services/api/claude.py) -- API streaming with SSE events
- [`tool/base.py`](src/claude_code/tool/base.py) -- What every tool must implement
- [`tool/executor.py`](src/claude_code/tool/executor.py) -- Parse → validate → hooks → call → format

### Level 2: Making It Reliable
*"My demo works. How do I make it production-quality?"*

- [`query/loop.py` recovery paths](src/claude_code/query/loop.py) -- max_tokens recovery, auto-compact, tool result budget
- [`services/api/errors.py`](src/claude_code/services/api/errors.py) -- Error classification, retry with backoff
- [`services/api/claude.py` caching](src/claude_code/services/api/claude.py) -- Prompt caching (saves ~50% on API costs)
- [`services/compact/compact.py`](src/claude_code/services/compact/compact.py) -- Auto-compaction when context gets too long

### Level 3: Making It Safe
*"How do I let an AI run shell commands without destroying everything?"*

- [`tools/bash_tool/security.py`](src/claude_code/tools/bash_tool/security.py) -- 15 security checks on every command
- [`tools/bash_tool/sandbox.py`](src/claude_code/tools/bash_tool/sandbox.py) -- macOS/Linux command sandboxing
- [`permissions/check.py`](src/claude_code/permissions/check.py) -- Rule matching, permission modes
- [`tools/file_edit_tool/`](src/claude_code/tools/file_edit_tool/) -- Read-before-edit, stale file detection, encoding preservation

### Level 4: Making It Smart
*"How does the model know about my project?"*

- [`context/system_prompt.py`](src/claude_code/context/system_prompt.py) -- 11-section system prompt assembly
- [`context/user_context.py`](src/claude_code/context/user_context.py) -- CLAUDE.md file hierarchy
- [`context/git_context.py`](src/claude_code/context/git_context.py) -- Git status/branch injection
- [`memory/`](src/claude_code/memory/) -- Persistent cross-session memory

### Level 5: Making It Extensible
*"How do I let users customize the agent?"*

- [`hooks/`](src/claude_code/hooks/) -- PreToolUse/PostToolUse shell hooks
- [`skills/`](src/claude_code/skills/) -- Markdown skill files with YAML frontmatter
- [`plugins/`](src/claude_code/plugins/) -- Git-based plugin loading
- [`commands/registry.py`](src/claude_code/commands/registry.py) -- Slash command system
- [`services/mcp/`](src/claude_code/services/mcp/) -- Model Context Protocol client

## The Deep Dive Tutorial

A 7-chapter guide that builds this entire codebase from scratch:

1. **[Hello Agent](docs/tutorial/chapter-01-hello-agent.md)** -- CLI + streaming API
2. **[Adding Tools](docs/tutorial/chapter-02-adding-tools.md)** -- Tool protocol + Read/Bash
3. **The Agentic Loop** -- Autonomous tool chaining *(coming soon)*
4. **Terminal UI** -- Textual REPL with streaming *(coming soon)*
5. **Context Engineering** -- System prompt + CLAUDE.md + memory *(coming soon)*
6. **Permissions and Safety** -- Security checks + sandbox *(coming soon)*
7. **Extension Points** -- Hooks + skills + plugins *(coming soon)*

## Stats

| Metric | Value |
|---|---|
| Source files | 73 |
| Lines of Python | 9,630 |
| Tools | 18 (matching Claude Code's tool names and schemas) |
| Unit tests | 215 |
| Conformance tests | 90 (verifying behavior against original) |
| Slash commands | 11 |
| Security checks | 15 |

## Tech Stack

| Purpose | Library | Replaces (in Claude Code) |
|---|---|---|
| CLI | [Click](https://click.palletsprojects.com/) | Commander.js |
| Terminal UI | [Textual](https://textual.textualize.io/) | Ink (React for terminal) |
| Schemas | [Pydantic](https://docs.pydantic.dev/) | Zod |
| API | [anthropic](https://github.com/anthropics/anthropic-sdk-python) | @anthropic-ai/sdk |
| Async | asyncio | Node.js event loop |

## Contributing

Contributions that improve fidelity to the original Claude Code behavior are especially welcome. Run the conformance tests to verify:

```bash
pytest conformance/ -v  # 90 tests verifying behavioral parity
```

## License

MIT
