# Chapter 7: Extension Points

A coding agent that can only do what its authors anticipated is a dead end. This chapter covers the main extension mechanisms: slash commands, skills, MCP servers, auto-compact, and the streaming tool executor. Together, they let users and teams customize the agent without forking the codebase.

## What You'll Learn

- Slash commands: a simple registry pattern for built-in operations
- Skills: markdown files with YAML frontmatter in .claude/skills/
- MCP client: connecting to external tool servers via stdio
- Auto-compact: extending conversations beyond the context window
- The streaming tool executor: starting read-only tools during streaming

## Slash Commands

Slash commands are the simplest extension point. They are synchronous operations triggered by the user typing `/name` in the prompt. Each command is a function registered in a global dictionary.

```python
@dataclass
class Command:
    name: str
    description: str
    aliases: list[str] | None = None
    hidden: bool = False
    handler: Callable[..., Awaitable[CommandResult]] | None = None

@dataclass
class CommandResult:
    message: str = ""
    level: str = "info"       # info, warning, error
    should_query: bool = False # If True, send message to model
    query_text: str = ""

# Global registry
_commands: dict[str, Command] = {}

def register_command(cmd: Command) -> None:
    _commands[cmd.name] = cmd
    if cmd.aliases:
        for alias in cmd.aliases:
            _commands[alias] = cmd
```

A command handler receives keyword arguments (the engine, user args, etc.) and returns a `CommandResult`. Most commands produce a message for the user. Some, like `/compact`, set `should_query=True` to send a prompt to the model.

Here is the `/cost` command:

```python
async def cmd_cost(**kwargs) -> CommandResult:
    engine = kwargs.get("engine")
    if engine:
        usage = engine.total_usage
        return CommandResult(
            message=(
                f"Total cost: ${usage.cost_usd:.4f}\n"
                f"Input tokens: {usage.input_tokens:,}\n"
                f"Output tokens: {usage.output_tokens:,}"
            )
        )
    return CommandResult(message="No active session.")

register_command(Command("cost", "Show cost and token usage", handler=cmd_cost))
```

The built-in commands include:

| Command | What It Does |
|---|---|
| `/help` | List available commands |
| `/clear` | Clear conversation history |
| `/cost` | Show token usage and cost |
| `/model` | Show or change the model |
| `/compact` | Summarize and compress context |
| `/init` | Create a CLAUDE.md file |
| `/memory` | Show memory status |
| `/config` | Show current settings |
| `/doctor` | Run diagnostics |
| `/resume` | List recent sessions |

## Skills

Skills are a richer extension than slash commands. They are markdown files with YAML frontmatter that describe a task for the model to perform. Skills live in `.claude/skills/` directories and can be invoked by the user (`/skill-name`) or triggered automatically by the model.

A skill file looks like this:

```markdown
---
description: Create a git commit with a good message
when_to_use: When the user says /commit or asks to commit changes
allowed-tools: [Bash, Read, Glob]
user-invocable: true
context: inline
---
Look at the current git diff and staged changes, then create a commit
with a clear, concise message following conventional commit format.
Do not push unless explicitly asked.
```

The frontmatter fields control how the skill behaves:

| Field | Purpose |
|---|---|
| `description` | Shown in help listings |
| `when_to_use` | Tells the model when to auto-invoke this skill |
| `allowed-tools` | Restricts which tools the skill can access |
| `user-invocable` | Whether the user can type /skill-name |
| `model` | Override the model for this skill |
| `effort` | Effort level hint |
| `context` | `inline` (same context) or `fork` (new context) |
| `paths` | Glob patterns for conditional activation |

Skills are discovered by walking up the directory tree:

```python
def find_skill_dirs(cwd: Path) -> list[Path]:
    dirs: list[Path] = []
    current = cwd.resolve()

    while current != current.parent:
        skill_dir = current / ".claude" / "skills"
        if skill_dir.is_dir():
            dirs.append(skill_dir)
        current = current.parent

    # User-level
    user_skills = Path.home() / ".claude" / "skills"
    if user_skills.is_dir():
        dirs.append(user_skills)

    return dirs
```

Two file formats are supported:

```
.claude/skills/
    commit/SKILL.md        ← directory format (preferred)
    review-pr/SKILL.md
    simplify.md            ← flat file format (legacy)
```

Skills are deduplicated by name -- the first one found (closest to cwd) wins. This lets a project override a user-level skill of the same name.

**Bundled skills** ship with the CLI and are registered in code rather than loaded from files:

```python
register_bundled_skill({
    "name": "commit",
    "description": "Create a git commit with a good message",
    "user_invocable": True,
    "body": "Look at the current git diff and staged changes...",
    "source": "bundled",
})
```

## MCP Client

The Model Context Protocol (MCP) lets you connect external tool servers to the agent. An MCP server is a separate process (or HTTP endpoint) that exposes tools, resources, and prompts through a standardized JSON-RPC protocol.

```
Agent                         MCP Server (separate process)
  │                                │
  ├── initialize ────────────────► │
  │ ◄── capabilities ──────────────┤
  │                                │
  ├── tools/list ──────────────► │
  │ ◄── [{name, schema}, ...] ────┤
  │                                │
  ├── tools/call ──────────────► │
  │   {name: "query", args: {..}}  │
  │ ◄── {content: [{text: "..."}]} ┤
  │                                │
  disconnect                       │
```

MCP server configs come from three places (in precedence order):

1. `.claude/settings.local.json` -- local overrides
2. `.mcp.json` files walking up from cwd -- project configs
3. `~/.claude/settings.json` -- user-level defaults

A config looks like this:

```json
{
  "mcpServers": {
    "database": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-sqlite", "mydb.sqlite"]
    },
    "remote-api": {
      "type": "http",
      "url": "https://mcp.example.com/api",
      "headers": { "Authorization": "Bearer ${MCP_TOKEN}" }
    }
  }
}
```

The stdio transport is implemented (spawns a subprocess, communicates via stdin/stdout JSON-RPC). HTTP/SSE transports are parsed from config but not yet implemented.

MCP tools get namespaced to avoid conflicts with built-in tools:

```python
def build_mcp_tool_name(server_name: str, tool_name: str) -> str:
    return f"mcp__{normalize_mcp_name(server_name)}__{normalize_mcp_name(tool_name)}"

# Example: "database" server + "query" tool → "mcp__database__query"
```

All configured servers are connected concurrently at startup:

```python
async def connect_all_servers(configs):
    connections = {}

    async def connect_one(name, config):
        conn = MCPConnection(name, config)
        success = await asyncio.wait_for(conn.connect(), timeout=30.0)
        if success:
            await conn.list_tools()
            connections[name] = conn

    tasks = [connect_one(name, config) for name, config in configs.items()]
    await asyncio.gather(*tasks, return_exceptions=True)
    return connections
```

## Auto-Compact

Context windows are finite. When the conversation grows too long, the agent automatically compacts it: summarizing older messages while preserving the most recent context. The `/compact` command triggers this manually.

```
Before compact:                   After compact:
┌──────────────────────┐         ┌──────────────────────┐
│ System prompt        │         │ System prompt        │
│ Message 1            │         │ Summary of 1-8       │
│ Message 2            │         │ Message 9            │
│ Message 3            │         │ Message 10           │
│ ...                  │         │ Message 11           │
│ Message 8            │         │ (room for more)      │
│ Message 9            │         └──────────────────────┘
│ Message 10           │
│ Message 11           │
│ (approaching limit)  │
└──────────────────────┘
```

The system prompt tells the model: "The system will automatically compress prior messages in your conversation as it approaches context limits. This means your conversation with the user is not limited by the context window."

This is why the `SUMMARIZE_TOOL_RESULTS_SECTION` exists in the system prompt -- it tells the model to write down important information from tool results, because those results may be cleared during compaction.

## The Extension Architecture

Here is how all the extension points relate:

```
┌────────────────────────────────────────────────┐
│                   Agent                        │
│                                                │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐ │
│  │  Slash   │  │  Skills  │  │   Plugins    │ │
│  │  Cmds    │  │          │  │              │ │
│  │          │  │ .claude/  │  │  git repos   │ │
│  │ /help    │  │ skills/  │  │  containing: │ │
│  │ /cost    │  │          │  │  - skills    │ │
│  │ /compact │  │ YAML +   │  │  - hooks     │ │
│  │ /model   │  │ markdown │  │  - MCP cfgs  │ │
│  └──────────┘  └──────────┘  └──────┬───────┘ │
│                                      │         │
│                              ┌───────▼───────┐ │
│                              │  MCP Client   │ │
│                              │               │ │
│                              │ stdio / HTTP  │ │
│                              │ connections   │ │
│                              └───────────────┘ │
│                                                │
│  ┌───────────────────────────────────────────┐ │
│  │             Hook System                   │ │
│  │  PreToolUse / PostToolUse / SessionStart  │ │
│  │  (runs shell commands, webhooks)          │ │
│  └───────────────────────────────────────────┘ │
└────────────────────────────────────────────────┘
```

Slash commands are for simple, immediate operations. Skills are for model-driven workflows described in natural language. Plugins bundle multiple extensions for distribution. MCP connects to external systems. Hooks intercept and modify behavior at the tool level.

## Try It

Create a custom skill:

```bash
mkdir -p .claude/skills/explain
cat > .claude/skills/explain/SKILL.md << 'EOF'
---
description: Explain a file or function in detail
when_to_use: When the user asks to explain code
allowed-tools: [Read, Glob, Grep]
user-invocable: true
---
Read the specified file or function. Explain what it does, why it exists,
and how it fits into the larger codebase. Include:
1. Purpose and responsibility
2. Key design decisions
3. Dependencies and dependents
4. Potential gotchas
EOF
```

Now type `/explain src/main.py` to invoke it.

Connect an MCP server by creating `.mcp.json` in your project root:

```json
{
  "mcpServers": {
    "filesystem": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "."]
    }
  }
}
```

The agent will discover and connect to the server on next startup.

## What Would You Add Next?

The extension system is designed to grow. Here are some ideas for contributors:

- **Skill chaining**: Run one skill's output as input to another
- **Conditional skills**: Activate skills based on file patterns (the `paths` frontmatter field is parsed but not fully wired)
- **MCP resource integration**: Expose MCP resources as context, not just tools
- **MCP HTTP/SSE transport**: Implement the HTTP transport for remote MCP servers
- **Hook templates**: Pre-built hooks for common workflows (lint-on-save, test-on-edit)

## Code Reference

The production version of this chapter lives in:
- [`src/claude_code/commands/registry.py`](../../src/claude_code/commands/registry.py) -- Slash command registry
- [`src/claude_code/skills/loader.py`](../../src/claude_code/skills/loader.py) -- Skill discovery and loading
- [`src/claude_code/skills/bundled.py`](../../src/claude_code/skills/bundled.py) -- Built-in bundled skills
- [`src/claude_code/services/mcp/client.py`](../../src/claude_code/services/mcp/client.py) -- MCP client connections
- [`src/claude_code/services/mcp/types.py`](../../src/claude_code/services/mcp/types.py) -- MCP type definitions
- [`src/claude_code/tool/streaming_executor.py`](../../src/claude_code/tool/streaming_executor.py) -- Streaming tool execution

---

**[← Chapter 6: Permissions and Safety](chapter-06-permissions-safety.md)**
