# claude-code-py

**Learn how AI coding agents work -- by reading one.**

This is an educational Python reimplementation of the architecture behind AI coding agents like [Claude Code](https://claude.ai/code). Every module is documented to explain *why* it exists, not just *what* it does.

If you've ever wondered how tools like Claude Code, Cursor, or aider actually work under the hood -- how they call models, execute tools, manage permissions, stream responses, and maintain context -- this codebase is for you.

## Who This Is For

- **Developers** who use AI coding agents and want to understand the internals
- **Engineers** building their own agentic systems
- **Students** studying LLM application architecture
- **Researchers** exploring tool-use patterns, agentic loops, and human-AI interaction

## Architecture Overview

An AI coding agent is simpler than you think. At its core, it's a loop:

```
while True:
    response = call_model(messages, tools)
    if response has no tool_use:
        break                          # Model is done
    for tool_call in response:
        result = execute_tool(tool_call)
        messages.append(result)        # Feed result back
```

Everything else -- streaming, permissions, context management, TUI -- is infrastructure around this loop. This repo implements each layer:

```
┌─────────────────────────────────────────────┐
│                   CLI (cli.py)              │  ← Entry point
├─────────────────────────────────────────────┤
│              TUI (tui/)                     │  ← Terminal interface
│  ┌──────────┐ ┌────────┐ ┌──────────────┐  │
│  │ Messages │ │Spinner │ │ Status Bar   │  │
│  │ List     │ │        │ │              │  │
│  └──────────┘ └────────┘ └──────────────┘  │
├─────────────────────────────────────────────┤
│           Query Engine (query/)             │  ← Agentic loop
│  ┌──────────────────────────────────────┐   │
│  │ call_model → run_tools → repeat     │   │
│  └──────────────────────────────────────┘   │
├─────────────────────────────────────────────┤
│          Tool System (tool/, tools/)        │  ← Tool execution
│  ┌─────┐ ┌──────┐ ┌──────┐ ┌──────┐       │
│  │Bash │ │ Read │ │ Edit │ │ Grep │ ...   │
│  └─────┘ └──────┘ └──────┘ └──────┘       │
├─────────────────────────────────────────────┤
│        Context (context/, memory/)          │  ← What the model knows
│  ┌───────────┐ ┌─────────┐ ┌────────────┐  │
│  │ CLAUDE.md │ │Git Info │ │ Memory     │  │
│  └───────────┘ └─────────┘ └────────────┘  │
├─────────────────────────────────────────────┤
│    Infrastructure (hooks/, commands/, etc.)  │  ← Extension points
│  ┌───────┐ ┌──────────┐ ┌─────────┐        │
│  │ Hooks │ │ Commands │ │ Skills  │        │
│  └───────┘ └──────────┘ └─────────┘        │
└─────────────────────────────────────────────┘
```

## Reading Guide

Start here, in this order:

### Chapter 1: The Agentic Loop
**The core of every AI coding agent.**
- [`query/loop.py`](src/claude_code/query/loop.py) -- The while-loop that calls the model and executes tools
- [`query/engine.py`](src/claude_code/query/engine.py) -- Session state management across turns
- [`services/api/claude.py`](src/claude_code/services/api/claude.py) -- How streaming API calls work (SSE events → messages)

### Chapter 2: The Tool System
**How agents interact with the real world.**
- [`tool/base.py`](src/claude_code/tool/base.py) -- The Tool protocol: what every tool must implement
- [`tool/executor.py`](src/claude_code/tool/executor.py) -- The execution pipeline: parse → validate → permission check → call
- [`tool/registry.py`](src/claude_code/tool/registry.py) -- How tools are discovered and registered
- [`tools/bash_tool/`](src/claude_code/tools/bash_tool/) -- A real tool implementation (shell execution)
- [`tools/file_edit_tool/`](src/claude_code/tools/file_edit_tool/) -- The read-before-edit pattern

### Chapter 3: Context Engineering
**What makes the model useful -- what you put in the prompt.**
- [`context/system_prompt.py`](src/claude_code/context/system_prompt.py) -- How the system prompt is assembled from sections
- [`context/user_context.py`](src/claude_code/context/user_context.py) -- CLAUDE.md: user-defined instructions
- [`context/git_context.py`](src/claude_code/context/git_context.py) -- Injecting git status so the model knows the repo state
- [`memory/`](src/claude_code/memory/) -- Persistent memory across sessions

### Chapter 4: Terminal UI
**How to build a streaming chat interface.**
- [`tui/app.py`](src/claude_code/tui/app.py) -- The Textual application shell
- [`tui/screens/repl.py`](src/claude_code/tui/screens/repl.py) -- Wiring the query engine to the UI
- [`tui/widgets/`](src/claude_code/tui/widgets/) -- Message list, spinner, status bar, permission dialog

### Chapter 5: Extension Points
**How agents become customizable.**
- [`hooks/`](src/claude_code/hooks/) -- Pre/post tool-use hooks (run shell commands before tools execute)
- [`commands/registry.py`](src/claude_code/commands/registry.py) -- Slash command system
- [`skills/`](src/claude_code/skills/) -- Markdown-defined skills with YAML frontmatter
- [`plugins/`](src/claude_code/plugins/) -- Git-based plugin loading

### Chapter 6: Infrastructure
**The plumbing that makes it production-ready.**
- [`services/compact/`](src/claude_code/services/compact/) -- Auto-compaction when context gets too long
- [`services/api/errors.py`](src/claude_code/services/api/errors.py) -- Error classification and retry logic
- [`utils/config.py`](src/claude_code/utils/config.py) -- Multi-source settings with precedence
- [`utils/session_storage.py`](src/claude_code/utils/session_storage.py) -- Conversation persistence (JSONL)

## Key Concepts Explained

### Why a "tool loop" instead of a single API call?
LLMs can't execute code or read files. Instead, you give the model a list of *tools* (functions it can call), and when it wants to use one, it returns a `tool_use` block instead of text. Your code executes the tool and sends the result back. The model then decides what to do next. This loop is what makes agents *agentic*.

### Why parallel tool execution?
Read-only tools (Read, Glob, Grep) can't interfere with each other, so they run concurrently via `asyncio.gather()`. Write tools (Edit, Write, Bash) run serially. This is a simple but effective optimization -- see `tool/executor.py`.

### Why "read before edit"?
The Edit tool requires you to Read the file first. This prevents the model from making edits based on stale knowledge (hallucinated file contents). The `readFileState` dict tracks what's been read and when, and rejects edits if the file changed since the last read.

### Why CLAUDE.md?
Users need a way to give persistent instructions ("always use type hints", "this project uses pytest"). CLAUDE.md files are loaded from a hierarchy (user → project → directory) and injected into the system prompt. It's the simplest possible customization mechanism.

### Why hooks?
Sometimes you want to run a script before or after a tool executes -- linting after file edits, blocking dangerous commands, notifying a webhook. Hooks are configured in `settings.json` and run as shell commands with the tool's input as environment variables.

## Running It

This is a working agent, not just documentation:

```bash
pip install -e ".[dev]"

# Non-interactive mode
export ANTHROPIC_API_KEY=your-key
claude-code-py -p "What is 2+2?"

# With tools
claude-code-py -p "Read the file pyproject.toml and tell me the version"

# Interactive TUI
claude-code-py

# Run tests
pytest tests/ conformance/ -v
```

## Stats

| Metric | Value |
|---|---|
| Source files | 65 |
| Lines of Python | ~7,300 |
| Tools | 18 |
| Tests | 215 |
| Dependencies | 9 (anthropic, click, pydantic, textual, rich, pyyaml, aiohttp, aiofiles, wcmatch) |

## Tech Stack

| Purpose | Library | Replaces (in Claude Code) |
|---|---|---|
| CLI | [Click](https://click.palletsprojects.com/) | Commander.js |
| Terminal UI | [Textual](https://textual.textualize.io/) | Ink (React for terminal) |
| Schemas | [Pydantic](https://docs.pydantic.dev/) | Zod |
| API | [anthropic](https://github.com/anthropics/anthropic-sdk-python) | @anthropic-ai/sdk |
| Async | asyncio | Node.js event loop |

## Contributing

This is an educational project. Contributions that improve clarity, documentation, or test coverage are especially welcome. See the [conformance tests](conformance/) for the verification approach.

## License

MIT
