# claude-code-py

**Learn how to build production-level Claude Code in Python.**

This is a faithful Python reimplementation of [Claude Code](https://claude.ai/code) -- Anthropic's CLI coding agent. We studied the architecture of Claude Code and rebuilt it from scratch so you can understand every system, every edge case, and every design decision that makes a production AI coding agent work.

## Why This Exists

Most "build your own agent" tutorials stop at the 5-line loop:

```python
while True:
    response = call_model(messages, tools)
    if no tool_use: break
    results = execute_tools(response)
    messages.append(results)
```

Real-world agents like Claude Code have 200,000+ lines of code on top of this loop. **What are all those lines doing?**

This repo answers that question -- with 9,600 lines of working Python that you can read, run, and modify. Every module maps to the original Claude Code architecture. Every design decision is explained.

## Quick Start

```bash
pip install -e ".[dev]"
export ANTHROPIC_API_KEY=your-key

# Non-interactive
claude-code-py -p "Read pyproject.toml and tell me the version"

# Interactive TUI
claude-code-py

# Run tests
pytest tests/ conformance/ -v
```

## Tutorial: Build It From Scratch

A 7-chapter guide that builds this entire codebase step by step. Each chapter adds one layer, with working code you can run at every stage.

| | Chapter | What You Build |
|---|---|---|
| 1 | [Hello Agent](docs/tutorial/chapter-01-hello-agent.md) | A CLI that streams responses from Claude |
| 2 | [Adding Tools](docs/tutorial/chapter-02-adding-tools.md) | The tool protocol -- teach your agent to read files and run commands |
| 3 | [The Agentic Loop](docs/tutorial/chapter-03-agentic-loop.md) | Autonomous tool chaining, parallel execution, error recovery |
| 4 | [A Real Terminal UI](docs/tutorial/chapter-04-terminal-ui.md) | Interactive REPL with streaming, spinners, and permission dialogs |
| 5 | [Context Engineering](docs/tutorial/chapter-05-context-engineering.md) | System prompt assembly, CLAUDE.md, git context, persistent memory |
| 6 | [Permissions and Safety](docs/tutorial/chapter-06-permissions-safety.md) | Security checks, sandboxing, permission modes, hooks |
| 7 | [Extension Points](docs/tutorial/chapter-07-extension-points.md) | Skills, plugins, MCP client, slash commands |

## Reading the Code

If you prefer to dive straight into the source:

**Start here** -- the core loop that powers the entire agent:
- [`query/loop.py`](src/claude_code/query/loop.py) -- Call model, run tools, repeat. Plus recovery paths for token limits, auto-compact, and abort handling.

**Then understand the tool system** -- how the agent interacts with the world:
- [`tool/base.py`](src/claude_code/tool/base.py) -- The Tool protocol every tool implements
- [`tool/executor.py`](src/claude_code/tool/executor.py) -- Execution pipeline: parse, validate, hooks, permissions, call
- [`tools/bash_tool/`](src/claude_code/tools/bash_tool/) -- Shell execution with 15 security checks and sandboxing
- [`tools/file_edit_tool/`](src/claude_code/tools/file_edit_tool/) -- Read-before-edit pattern with encoding detection

**Then understand context engineering** -- what makes the agent actually useful:
- [`context/system_prompt.py`](src/claude_code/context/system_prompt.py) -- 11-section system prompt ported from Claude Code
- [`context/user_context.py`](src/claude_code/context/user_context.py) -- CLAUDE.md file loading
- [`memory/`](src/claude_code/memory/) -- Persistent memory across sessions

**Then understand safety and extensibility:**
- [`permissions/check.py`](src/claude_code/permissions/check.py) -- 5 permission modes with wildcard rule matching
- [`hooks/`](src/claude_code/hooks/) -- PreToolUse/PostToolUse hooks
- [`skills/`](src/claude_code/skills/) -- Markdown skill files with YAML frontmatter
- [`services/mcp/`](src/claude_code/services/mcp/) -- Model Context Protocol client

## What's Inside

**18 tools** matching Claude Code's tool names and input schemas: Bash, Read, Edit, Write, Glob, Grep, WebFetch, WebSearch, Agent, TaskCreate, TaskGet, TaskUpdate, TaskList, EnterPlanMode, ExitPlanMode, AskUserQuestion, NotebookEdit, Skill.

**Full interactive TUI** built with [Textual](https://textual.textualize.io/) -- message list, streaming markdown, spinner, status bar, permission dialogs, slash commands.

**Production reliability** -- API retry with backoff, prompt caching, auto-compact, max_output_tokens recovery, tool result budget, streaming tool execution.

**Security** -- 15 bash security checks (control chars, injection, unicode), macOS/Linux sandboxing, file encoding preservation, read-before-edit enforcement.

**305 tests** -- 215 unit tests + 90 conformance tests verifying behavioral parity with the original TypeScript Claude Code.

## Contributing

Contributions that improve fidelity to the original Claude Code behavior are especially welcome. The conformance test suite verifies behavioral parity:

```bash
pytest conformance/ -v
```

## License

MIT
