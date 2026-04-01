# Build Your Own AI Coding Agent in Python

A step-by-step guide to building a production-quality AI coding agent from scratch. Each chapter adds one layer, with working code you can run at every step.

By the end, you'll have built a fully functional coding agent that can read files, edit code, run commands, stream responses, and maintain context across sessions -- the same architecture used by Claude Code, Cursor, and other professional tools.

## Prerequisites

- Python 3.11+
- An Anthropic API key ([get one here](https://console.anthropic.com/))
- Basic familiarity with `asyncio`

## Chapters

### [Chapter 1: Hello Agent](chapter-01-hello-agent.md)
**Build a CLI that talks to Claude and streams the response.**

You'll learn:
- How the Anthropic Messages API works
- Server-Sent Events (SSE) streaming
- How to build a minimal CLI with Click

Result: `python agent.py -p "What is 2+2?"` streams a response.

---

### [Chapter 2: Adding Tools](chapter-02-adding-tools.md)
**Give your agent the ability to read files and run commands.**

You'll learn:
- How LLM tool use works (the model doesn't "call" tools -- it *requests* them)
- The tool_use → tool_result protocol
- How to define tools with Pydantic schemas
- The Tool Protocol pattern: a clean interface every tool implements

Result: `python agent.py -p "Read setup.py and tell me the version"` actually reads the file.

---

### [Chapter 3: The Agentic Loop](chapter-03-agentic-loop.md)
**Make your agent autonomous -- it calls tools, gets results, and decides what to do next.**

You'll learn:
- The while-loop that makes agents *agentic*
- Why max_turns matters (infinite loop protection)
- Parallel execution for read-only tools
- How to handle tool errors gracefully (return to model, don't crash)

Result: The agent can chain multiple tool calls to accomplish complex tasks.

---

### [Chapter 4: A Real Terminal UI](chapter-04-terminal-ui.md)
**Build an interactive chat interface with streaming, spinners, and tool output.**

You'll learn:
- Textual framework basics (Python's React-for-terminal)
- Real-time streaming display with incremental markdown rendering
- Component architecture: MessageList, PromptInput, Spinner, StatusBar
- How to wire an async query engine to a reactive UI

Result: A polished interactive REPL you can actually use for coding.

---

### [Chapter 5: Context Engineering](chapter-05-context-engineering.md)
**Make your agent actually useful by teaching it about the project.**

You'll learn:
- System prompt assembly (identity + tools + environment + custom instructions)
- CLAUDE.md: the simplest possible customization mechanism
- Git context injection (branch, status, recent commits)
- The memory system: persistent facts across sessions
- Why context engineering matters more than model choice

Result: The agent knows your project, remembers past conversations, and follows your coding style.

---

### [Chapter 6: Permissions and Safety](chapter-06-permissions-safety.md)
**Add guardrails so the agent doesn't rm -rf your repo.**

You'll learn:
- The read-before-edit pattern (why it prevents hallucination-based edits)
- Permission modes: ask, allow, deny
- Hook system: run shell commands before/after tool execution
- Why tools return errors instead of throwing exceptions
- Cost tracking and budget limits

Result: The agent asks before running dangerous commands and respects your rules.

---

### [Chapter 7: Extension Points](chapter-07-extension-points.md)
**Make your agent extensible with skills, commands, and plugins.**

You'll learn:
- Slash commands: a simple command registry pattern
- Skills: markdown files that become agent capabilities
- Plugins: git repos that bundle skills + hooks + tools
- Auto-compact: how to extend effective context beyond the window limit

Result: A fully extensible agent that others can customize.

---

## Architecture at a Glance

```
Chapter 1    CLI + API streaming
Chapter 2    + Tool system (Bash, Read, Edit, Write, Glob, Grep)
Chapter 3    + Agentic loop (call → tools → repeat)
Chapter 4    + Terminal UI (Textual)
Chapter 5    + Context (CLAUDE.md, git, memory)
Chapter 6    + Permissions and safety
Chapter 7    + Skills, commands, plugins
```

Each chapter's code builds on the previous one. The final result is the complete `claude-code-py` codebase.

## Design Principles

These principles guided both the original Claude Code and this reimplementation:

1. **Tools return errors, never crash.** A "file not found" error lets the model try a different path. An exception kills the session.

2. **Read before write.** The model must read a file before editing it. This one rule prevents an entire class of hallucination bugs.

3. **Parallel reads, serial writes.** `asyncio.gather()` for Glob/Grep/Read. Sequential execution for Edit/Write/Bash. Zero coordination overhead.

4. **Context > model.** A mediocre model with great context (CLAUDE.md, git status, memory) outperforms a frontier model with no context.

5. **Append-only persistence.** Sessions are JSONL files. Append a line, never rewrite. Crash-safe by design.

6. **Hierarchy for customization.** Settings, CLAUDE.md, and skills all follow the same pattern: user-level < project-level < directory-level.

## FAQ

**Q: Is this actually how Claude Code works?**
A: The architecture is based on studying Claude Code's structure. The patterns (agentic loop, tool protocol, context assembly) are the same. Implementation details differ -- Claude Code has ~200K lines of TypeScript, extensive security hardening, prompt caching, and proprietary optimizations we don't replicate.

**Q: Can I use this in production?**
A: You can, but it lacks sandboxing, security classifiers, and the full permission system. It's designed to teach, not to replace Claude Code.

**Q: Does this work with other LLMs?**
A: The architecture is model-agnostic. The API client (`services/api/`) is the only Anthropic-specific layer. Swapping in OpenAI or a local model requires changing ~100 lines.

**Q: How is this different from aider/OpenHands/etc?**
A: Those are products. This is a textbook. The goal is understanding, not features.
