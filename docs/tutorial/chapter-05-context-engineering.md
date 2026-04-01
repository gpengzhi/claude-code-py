# Chapter 5: Context Engineering

The system prompt is the single most important input to the model. It determines how the agent behaves, what rules it follows, and what it knows about the user's environment. In this chapter, you'll learn how the system prompt is assembled from 13 distinct sections, how project-specific context flows in through CLAUDE.md files, and how the memory system gives the agent persistence across sessions.

## What You'll Learn

- How the system prompt is assembled from 11+ sections and why each exists
- CLAUDE.md: the three-level hierarchy (user > project > directory)
- Git context injection (branch, status, recent commits)
- The persistent memory system (files with YAML frontmatter, MEMORY.md index)
- Prompt caching (cache_control breakpoints on system blocks)
- Why context engineering matters more than model choice

## The System Prompt Assembly

The system prompt is not a single string. It is assembled from sections, each controlling a specific behavior. Here is the assembly order, matching the production code:

```
Section                         What It Controls
─────────────────────────────   ────────────────────────────────────
 1. Intro                       Identity, safety boundaries
 2. System                      Markdown output, permission modes, hooks
 3. Doing Tasks                 Software engineering behaviors
 4. Executing Actions           Reversibility, blast radius awareness
 5. Using Your Tools            Tool selection rules (Read not cat)
 6. Tone and Style              Conciseness, no emojis, link format
 7. Output Efficiency           Lead with the answer, skip filler
  ─── dynamic boundary ───
 8. Session Guidance            Agent tools, skill commands, search hints
 9. Summarize Tool Results      Preserve info from cleared results
10. Environment                 CWD, platform, shell, model identity
11. Date                        Today's date
12. User Context (CLAUDE.md)    Project-specific instructions
13. Memory                      Persistent facts from prior sessions
```

The first 7 sections are static -- they never change between sessions. Everything from section 8 onward is dynamic and depends on the current session, tools, and project.

**Why this order matters**: The model pays more attention to text at the beginning and end of context. Safety and behavioral rules come first. Project-specific context comes last so it is closest to the conversation.

## Building It In Code

The assembly happens in one function:

```python
async def build_system_prompt(
    tools: list[Tool],
    cwd: Path,
    custom_system_prompt: str | None = None,
    memory_prompt: str = "",
    model: str = "",
) -> str:
    sections: list[str] = []

    # Static behavioral sections (always the same)
    sections.append(get_intro_section())
    sections.append(get_system_section())
    sections.append(get_doing_tasks_section())
    sections.append(get_actions_section())
    sections.append(get_using_tools_section(tools))
    sections.append(get_tone_and_style_section())
    sections.append(get_output_efficiency_section())

    # Dynamic sections (session-scoped)
    sections.append(get_session_guidance_section(tools))
    sections.append(SUMMARIZE_TOOL_RESULTS_SECTION)
    sections.append(get_environment_info(cwd, model=model))
    sections.append(get_date_info())

    # Project context
    user_ctx = load_user_context(cwd)
    if user_ctx:
        sections.append(f"# User Context\n\n{user_ctx}")

    # Memory
    if memory_prompt:
        sections.append(f"# Memory\n\n{memory_prompt}")

    return "\n\n".join(sections)
```

Each `get_*_section()` function returns a self-contained block of text. The tool-dependent sections (5, 8) take the tool list as input so they can adapt -- for example, if the `Agent` tool is registered, session guidance adds a hint about using subagents for parallelization.

## What Each Section Does

**Intro**: Sets identity ("You are an interactive agent that helps users with software engineering tasks") and safety boundaries (no URL guessing, no destructive exploits).

**System**: Tells the model about the display layer (markdown in monospace), permission modes, hook feedback, and auto-compression.

**Doing Tasks**: The core software engineering behavior -- read before editing, don't gold-plate, don't add error handling for impossible scenarios, don't create unnecessary files.

**Actions**: Teaches reversibility awareness. "Carefully consider the reversibility and blast radius of actions." Destructive operations need confirmation; local file edits are freely allowed.

**Using Your Tools**: The "don't use Bash when a dedicated tool exists" rule. This is critical -- without it, the model uses `cat` instead of Read, `grep` instead of Grep, and the user loses visibility into what the agent is doing.

**Tone and Style**: No emojis. Short responses. Use `file_path:line_number` when referencing code.

**Output Efficiency**: "Lead with the answer or action, not the reasoning." This prevents the model from producing paragraphs of preamble before actually doing anything.

## CLAUDE.md: The Three-Level Hierarchy

CLAUDE.md files inject project-specific instructions into the system prompt. They are loaded from three levels:

```
~/.claude/CLAUDE.md              (user-level: your personal preferences)
    |
    v
<git-root>/.claude/CLAUDE.md    (project-level: team conventions)
    |
    v
<cwd>/CLAUDE.md                  (directory-level: local overrides)
```

The loader walks up from the current working directory, collecting files at each level:

```python
def find_claude_md_files(cwd: Path) -> list[tuple[str, Path]]:
    found: list[tuple[str, Path]] = []

    # 1. User-level: ~/.claude/CLAUDE.md
    user_claude = Path.home() / ".claude" / "CLAUDE.md"
    if user_claude.exists():
        found.append(("user", user_claude))

    # 2. Walk up from cwd to find project-level .claude/CLAUDE.md
    current = cwd.resolve()
    while current != current.parent:
        project_claude = current / ".claude" / "CLAUDE.md"
        if project_claude.exists():
            found.append(("project", project_claude))
            break
        current = current.parent

    return found
```

All found files are concatenated with separators and injected as the "User Context" section. This means a monorepo can have different CLAUDE.md files per package, and a user can have global preferences that apply everywhere.

**Practical example**: Your user-level CLAUDE.md might say "Always use single quotes in Python." Your project CLAUDE.md might say "This project uses pytest. Run `make test` to test."

## Git Context Injection

Git context is loaded in parallel with the system prompt and injected into the first user message (not the system prompt). It provides a snapshot of the repository state:

```python
async def load_git_context(cwd: Path) -> str:
    # Fetch all git info in parallel
    branch, status, commits, default_branch, user = await asyncio.gather(
        get_git_branch(cwd),
        get_git_status(cwd),
        get_git_recent_commits(cwd),
        get_default_branch(cwd),
        get_git_user(cwd),
    )

    parts = ["gitStatus: This is the git status at the start of the conversation."]
    parts.append(f"\nCurrent branch: {branch}")
    parts.append(f"\nMain branch: {default_branch}")
    parts.append(f"\nGit user: {user}")
    parts.append(f"\nStatus:\n{status}")
    parts.append(f"\nRecent commits:\n{commits}")
    return "\n".join(parts)
```

This gives the model immediate awareness of:
- Which branch it is on (to know whether to create a new one)
- What files are modified (to focus on relevant changes)
- Recent commit style (to match the project's conventions)
- Who the git user is (for commit authorship)

## The Memory System

Memory gives the agent persistence across sessions. Without it, every conversation starts from zero. The memory system uses files with YAML frontmatter stored in `~/.claude/projects/<project>/memory/`.

A memory file looks like this:

```markdown
---
name: project-architecture
description: Key architecture decisions for the API
type: project
---
The API uses a layered architecture:
- Router layer (FastAPI) handles HTTP
- Service layer contains business logic
- Repository layer talks to PostgreSQL via SQLAlchemy
```

There are four memory types, each for a different kind of information:

| Type | Purpose | Example |
|---|---|---|
| `user` | User's role, goals, preferences | "I prefer functional style" |
| `feedback` | Corrections from the user | "Don't use print, use logging" |
| `project` | Non-derivable project context | "Deploy deadline is March 15" |
| `reference` | Pointers to external resources | "API docs at internal.wiki/api" |

The `MEMORY.md` file is an index that gets loaded into the system prompt:

```python
def build_memory_prompt(project_root: Path | None = None) -> str:
    if not is_auto_memory_enabled():
        return ""
    index_content = load_memory_index(project_root)
    if not index_content:
        return ""
    mem_dir = get_memory_dir(project_root)
    return (
        f"You have a persistent memory system at `{mem_dir}/`.\n"
        f"Current MEMORY.md index:\n\n{index_content}"
    )
```

The index is truncated to 200 lines / 25KB to prevent memory from dominating the context window. Individual memory files are loaded on demand when the model needs them.

## Prompt Caching

Prompt caching saves money and latency. The API lets you mark breakpoints in the system prompt with `cache_control`. Everything before the breakpoint is cached on the server and reused across requests.

```
System prompt layout with cache breakpoints:

┌────────────────────────────────────┐
│  Sections 1-7 (static)            │  ← cache_control: ephemeral
│  ~3000 tokens, never changes      │
├────────────────────────────────────┤
│  Sections 8-13 (dynamic)          │  ← changes per session
│  Environment, CLAUDE.md, Memory   │
└────────────────────────────────────┘
│                                    │
│  Conversation messages             │
│  ...                               │
│  Last user message                 │  ← cache_control: ephemeral
└────────────────────────────────────┘
```

The static sections (1-7) are identical across all users and sessions. By placing a cache breakpoint after them, the API can reuse the cached KV computations for those ~3000 tokens on every request. The last user message also gets a breakpoint so that when the model makes multiple tool calls in sequence, the growing conversation prefix is cached.

**Impact**: On a typical 10-turn conversation, caching reduces input token costs by 60-80%.

## Putting It All Together

```
┌─────────────────────────────────────────┐
│           build_full_context()          │
│                                         │
│  ┌──────────┐    ┌──────────────────┐   │
│  │  System   │    │   Git Context    │   │
│  │  Prompt   │    │   (parallel)     │   │
│  │           │    │                  │   │
│  │ Sections  │    │ branch, status,  │   │
│  │  1-13     │    │ commits, user    │   │
│  └─────┬─────┘    └────────┬─────────┘   │
│        │                   │             │
│        ▼                   ▼             │
│  system param        first user msg      │
│  in API call         (prepended)         │
└─────────────────────────────────────────┘
```

System prompt and git context are fetched in parallel using `asyncio.gather()`, then delivered through different channels: the system prompt goes in the `system` parameter, and git context is prepended to the first user message.

## Try It

Create a CLAUDE.md file in your project:

```bash
mkdir -p .claude
cat > .claude/CLAUDE.md << 'EOF'
# Project Context

This is a Python project using FastAPI and pytest.
Always use type hints. Prefer f-strings over .format().
EOF
```

Then run the agent. The CLAUDE.md content will appear in the system prompt's User Context section. You can verify by adding a debug print in `build_system_prompt()`.

Try creating a memory file:

```bash
mkdir -p ~/.claude/projects/my-project/memory
cat > ~/.claude/projects/my-project/memory/MEMORY.md << 'EOF'
# Memory Index
- architecture.md: Key architecture decisions
EOF
```

## Context Engineering Matters More Than Model Choice

A well-constructed system prompt with the right CLAUDE.md, memory files, and git context will outperform a stronger model with a bare prompt. The 13-section system prompt is not bureaucracy -- each section was added because without it, the model exhibits a specific failure mode:

- Without "Doing Tasks": the model creates new files instead of editing existing ones
- Without "Using Your Tools": the model uses `cat` and `grep` instead of Read and Grep
- Without "Output Efficiency": the model writes three paragraphs before doing anything
- Without "Actions": the model force-pushes without asking
- Without CLAUDE.md: the model guesses at project conventions instead of following them

**Context engineering is the highest-leverage skill for working with AI agents.**

## Code Reference

The production version of this chapter lives in:
- [`src/claude_code/context/system_prompt.py`](../../src/claude_code/context/system_prompt.py) -- System prompt assembly
- [`src/claude_code/context/git_context.py`](../../src/claude_code/context/git_context.py) -- Git context loading
- [`src/claude_code/context/user_context.py`](../../src/claude_code/context/user_context.py) -- CLAUDE.md loading
- [`src/claude_code/memory/memdir.py`](../../src/claude_code/memory/memdir.py) -- Memory file management
- [`src/claude_code/memory/paths.py`](../../src/claude_code/memory/paths.py) -- Memory directory resolution
- [`src/claude_code/memory/types.py`](../../src/claude_code/memory/types.py) -- Memory type definitions

---

**[← Chapter 4: A Real Terminal UI](chapter-04-terminal-ui.md) | [Chapter 6: Permissions and Safety →](chapter-06-permissions-safety.md)**
