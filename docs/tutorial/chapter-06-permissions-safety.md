# Chapter 6: Permissions and Safety

An AI agent with shell access is powerful and dangerous. This chapter covers the layered safety system that prevents the agent from doing harm -- permission modes, rule matching, hook-based interception, bash security checks, and OS-level sandboxing.

## What You'll Learn

- The read-before-edit pattern and why it prevents hallucinated edits
- Permission modes: default, acceptEdits, bypassPermissions, dontAsk, plan
- Rule matching with wildcard patterns: `Bash(git *)`, `Read(*)`
- The hook system: PreToolUse/PostToolUse shell hooks that can block or modify
- 15 bash security checks (control chars, injection, unicode whitespace, and more)
- OS-level sandboxing (macOS sandbox-exec, Linux bubblewrap)
- Why tools return errors instead of throwing exceptions

## The Read-Before-Edit Pattern

The Edit tool refuses to operate on a file you have not previously read in the same session. This is not a technicality -- it is a critical safety mechanism.

**Without this rule**, the model can hallucinate file contents and write edits based on what it *thinks* the file contains. The `old_string` in an edit might match a hallucinated line, not the real one, producing silent corruption.

**With this rule**, the model must first read the file, which loads the real contents into context. Now the model's edit is grounded in reality.

```
Without read-before-edit:          With read-before-edit:

Model imagines file has:           Model reads actual file:
  def foo():                         def foo():
    return 42                          logger.info("called")
                                       return calculate()
Model edits based on imagination:
  "change return 42 to return 0"   Model edits based on reality:
                                     "change calculate() to compute()"
  → old_string doesn't match
  → silent failure or wrong edit   → edit is grounded in actual contents
```

## Permission Modes

Every tool call passes through the permission system before execution. The system supports five modes:

| Mode | Behavior |
|---|---|
| `default` | Auto-allow reads, ask for writes and shell commands |
| `acceptEdits` | Auto-allow reads AND file edits, ask for shell commands |
| `bypassPermissions` | Allow everything without asking (dangerous) |
| `dontAsk` | Deny anything that would prompt (for non-interactive CI) |
| `plan` | Always ask, even for reads (review-first workflow) |

The decision flow is a simple priority chain:

```python
def has_permissions_to_use_tool(tool_name, tool_input, context) -> PermissionResult:
    # 1. Always-deny rules (highest priority)
    deny_rule = find_matching_rule(context.always_deny_rules, tool_name, tool_input)
    if deny_rule:
        return PermissionDenyDecision(message=f"Denied by rule")

    # 2. Always-allow rules
    allow_rule = find_matching_rule(context.always_allow_rules, tool_name, tool_input)
    if allow_rule:
        return PermissionAllowDecision(updated_input=tool_input)

    # 3. Mode-based decision
    mode = context.mode
    if mode == "bypassPermissions":
        return PermissionAllowDecision(updated_input=tool_input)
    if mode == "dontAsk":
        return PermissionDenyDecision(message="Permission mode is 'dontAsk'")
    # ... mode-specific logic
```

The three possible outcomes are:

```
┌─────────────┐
│  Tool Call   │
└──────┬──────┘
       │
       ▼
┌──────────────┐     ┌─────────┐
│  Deny Rules  │─yes─►  DENY   │
└──────┬───────┘     └─────────┘
       │ no
       ▼
┌──────────────┐     ┌─────────┐
│ Allow Rules  │─yes─►  ALLOW  │
└──────┬───────┘     └─────────┘
       │ no
       ▼
┌──────────────┐     ┌─────────┐
│  Mode Check  │────►│  ASK /  │
│              │     │ ALLOW / │
│              │     │  DENY   │
└──────────────┘     └─────────┘
```

## Rule Matching with Wildcards

Rules use fnmatch-style wildcards to match tool invocations. The format is `ToolName(pattern)` where the pattern is matched against the relevant input field.

```python
def match_rule_pattern(pattern: str, value: str) -> bool:
    return fnmatch.fnmatch(value, pattern)
```

Examples:

| Rule | Matches |
|---|---|
| `Read(*)` | Any Read call |
| `Bash(git *)` | Bash commands starting with "git " |
| `Edit(/home/user/*)` | Edit on files under /home/user/ |
| `Bash(npm test)` | Exactly `npm test` |
| `Bash(docker *)` | Any docker command |

Rules are matched against the tool's primary input field. For Bash, that is `command`. For Read/Edit/Write, that is `file_path`. For Grep, that is `pattern`.

You configure rules in settings.json:

```json
{
  "permissions": {
    "allow": [
      "Read(*)",
      "Bash(git status)",
      "Bash(git diff *)",
      "Bash(npm test)"
    ],
    "deny": [
      "Bash(rm -rf *)",
      "Bash(git push --force *)"
    ]
  }
}
```

Deny rules always win. If a command matches both an allow and a deny rule, it is denied.

## The Hook System

Hooks are shell commands that run in response to agent events. They can inspect, modify, or block tool calls. This is the primary extension point for corporate policies and custom workflows.

There are seven hook events:

| Event | When It Fires |
|---|---|
| `PreToolUse` | Before a tool executes |
| `PostToolUse` | After a tool executes successfully |
| `PostToolUseFailure` | After a tool execution fails |
| `UserPromptSubmit` | When the user submits a prompt |
| `SessionStart` | When a new session begins |
| `Notification` | When a notification is generated |
| `FileChanged` | When a file is modified |

Hooks are configured in settings.json with optional matchers:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash(git push *)",
        "hooks": [
          {
            "type": "command",
            "command": "python check_branch_protection.py"
          }
        ]
      }
    ]
  }
}
```

The hook command receives context through environment variables:

```python
env["CLAUDE_TOOL_NAME"] = context.get("tool_name", "")
env["CLAUDE_TOOL_INPUT"] = json.dumps(context.get("tool_input", {}))
env["CLAUDE_HOOK_EVENT"] = context.get("event", "")
```

**Blocking behavior**: If the hook command exits with a non-zero return code, the tool call is blocked. The stderr output becomes the error message shown to the model.

**Structured responses**: Hooks can also print JSON to stdout for richer control:

```json
{
  "outcome": "blocking",
  "blockingError": "Cannot push to protected branch",
  "permissionDecision": { "behavior": "deny" }
}
```

Hook types include `command` (shell), `http` (webhook), and `prompt` (LLM-based). HTTP hooks post the event context to a URL and interpret the response.

## Bash Security Checks

Before any shell command executes, it passes through 15 security checks. These detect patterns that could indicate prompt injection, command smuggling, or parsing ambiguities.

```python
def run_security_checks(command: str) -> SecurityCheckResult:
    checks = [
        _check_control_characters,
        _check_incomplete_commands,
        _check_unicode_whitespace,
        _check_command_substitution,
        _check_ifs_injection,
        _check_proc_environ,
        _check_dangerous_variables,
        _check_backslash_operators,
        _check_backslash_whitespace,
        _check_brace_expansion,
        _check_mid_word_hash,
        _check_ansi_c_quoting,
        _check_comment_quote_desync,
        _check_zsh_dangerous,
        _check_newlines,
    ]

    for check in checks:
        result = check(command)
        if result.blocked:
            return result
    return SecurityCheckResult()  # All clear
```

Each check targets a specific attack vector:

| Check | What It Catches |
|---|---|
| `CONTROL_CHARACTERS` | Non-printable chars (\x00-\x1F) that bypass visual inspection |
| `INCOMPLETE_COMMANDS` | Fragments starting with tab, dash, or operators (&&, \|\|) |
| `UNICODE_WHITESPACE` | Non-breaking spaces, zero-width chars that look like normal spaces |
| `COMMAND_SUBSTITUTION` | Backticks and $() that embed commands inside other commands |
| `IFS_INJECTION` | $IFS manipulation that changes how shells split words |
| `PROC_ENVIRON` | /proc/*/environ access that leaks environment variables |
| `DANGEROUS_VARIABLES` | Variables near redirections or pipes ($VAR > file) |
| `BACKSLASH_OPERATORS` | Escaped semicolons/pipes (\\;) that hide command structure |
| `BACKSLASH_WHITESPACE` | Backslash-space sequences that confuse argument parsing |
| `BRACE_EXPANSION` | {a,b,c} patterns that expand to multiple commands |
| `MID_WORD_HASH` | Hash characters inside words that may be interpreted as comments |
| `ANSI_C_QUOTING` | $'...' that can encode hidden characters |
| `COMMENT_QUOTE_DESYNC` | Quotes inside comments (#) that desync quote tracking |
| `ZSH_DANGEROUS` | Zsh-specific builtins (zmodload, sysopen) that bypass restrictions |
| `NEWLINES_CR/LF` | Carriage returns and newlines that split commands invisibly |

Each result includes an `is_misparsing` flag. When true, the check caught a parsing ambiguity (likely accidental) rather than malicious intent. This distinction helps decide whether to show a warning or hard-block.

## OS-Level Sandboxing

Even with permission checks and security scanning, defense in depth requires OS-level containment. The sandbox restricts what the subprocess can access on the filesystem.

```
┌────────────────────────────────────┐
│  macOS: sandbox-exec (seatbelt)    │
│                                    │
│  (deny file-write* (subpath "/"))  │
│  (allow file-write* (subpath CWD)) │
│  (allow file-write* (subpath TMP)) │
│  (allow network*)                  │
│  (allow process-exec*)             │
└────────────────────────────────────┘

┌────────────────────────────────────┐
│  Linux: bubblewrap (bwrap)         │
│                                    │
│  --ro-bind / /   (read-only root)  │
│  --bind CWD CWD  (writeable CWD)  │
│  --dev /dev                        │
│  --proc /proc                      │
│  --tmpfs /tmp                      │
└────────────────────────────────────┘
```

The sandbox is generated dynamically based on the current working directory:

```python
def build_macos_sandbox_profile(cwd, allow_write_paths=None, deny_write_paths=None):
    allow_write = allow_write_paths or [cwd]
    profile = f"""
(version 1)
(allow default)
(deny file-write* (subpath "/"))
(allow file-write* (subpath "{cwd}"))
(allow file-write* (subpath "{tempfile.gettempdir()}"))
(allow network*)
(allow process-exec*)
(allow process-fork)
"""
    return profile
```

The sandbox allows reads everywhere (so commands like `git` and `python` can access their own binaries) but restricts writes to the project directory and temp. This prevents a rogue command from modifying system files, other projects, or configuration directories.

**Fallback**: If neither sandbox-exec (macOS) nor bwrap (Linux) is available, commands run unsandboxed. The security checks still apply.

## Why Tools Return Errors Instead of Throwing

Every tool in the system returns a `ToolResult` with an `is_error` flag rather than raising exceptions:

```python
@dataclass
class ToolResult:
    data: Any = None
    is_error: bool = False
```

This is deliberate. When a tool returns an error, the error message is sent back to the model as a `tool_result` with `is_error: true`. The model can then recover:

```
Model: Bash(command="cat missing_file.txt")
Tool:  ToolResult(data="File not found: missing_file.txt", is_error=True)
Model: "Let me search for the correct filename..."
Model: Glob(pattern="**/missing*.txt")
```

If the tool raised an exception instead, the agentic loop would need to catch it, format it, and decide what to do. By returning errors as data, every tool failure is automatically self-healing -- the model sees the error and adjusts.

## The Full Safety Stack

Here is how all the layers compose:

```
User types a prompt
        │
        ▼
┌────────────────────┐
│ UserPromptSubmit   │  Hook can block prompts
│ hook               │
└────────┬───────────┘
         │
Model produces tool_use
         │
         ▼
┌────────────────────┐
│ Permission check   │  Mode + rules → allow/deny/ask
└────────┬───────────┘
         │ allowed
         ▼
┌────────────────────┐
│ PreToolUse hooks   │  Shell commands can block/modify
└────────┬───────────┘
         │ not blocked
         ▼
┌────────────────────┐
│ Security checks    │  15 pattern checks (Bash only)
│ (bash_security.py) │
└────────┬───────────┘
         │ passed
         ▼
┌────────────────────┐
│ OS sandbox         │  Filesystem write restrictions
│ (sandbox-exec/bwrap)│
└────────┬───────────┘
         │
         ▼
┌────────────────────┐
│ Tool executes      │  Returns ToolResult, never throws
└────────┬───────────┘
         │
         ▼
┌────────────────────┐
│ PostToolUse hooks  │  Audit, logging, validation
└────────────────────┘
```

Five layers, each catching different failure modes. Permission checks handle policy. Hooks handle custom workflows. Security checks handle injection attacks. The sandbox handles defense in depth. Error-as-data handles graceful recovery.

## Try It

Add a permission rule to block dangerous commands:

```json
{
  "permissions": {
    "deny": ["Bash(rm -rf *)"]
  }
}
```

Then ask the agent to clean up a directory. Watch it get denied and adapt.

Add a PreToolUse hook that logs all Bash commands:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "echo \"$(date): $CLAUDE_TOOL_NAME $CLAUDE_TOOL_INPUT\" >> /tmp/agent-audit.log"
          }
        ]
      }
    ]
  }
}
```

Now every Bash command the agent runs is logged to `/tmp/agent-audit.log`.

## Code Reference

The production version of this chapter lives in:
- [`src/claude_code/permissions/check.py`](../../src/claude_code/permissions/check.py) -- Permission pipeline and rule matching
- [`src/claude_code/permissions/modes.py`](../../src/claude_code/permissions/modes.py) -- Permission mode definitions
- [`src/claude_code/hooks/config.py`](../../src/claude_code/hooks/config.py) -- Hook configuration parsing
- [`src/claude_code/hooks/runner.py`](../../src/claude_code/hooks/runner.py) -- Hook execution engine
- [`src/claude_code/hooks/events.py`](../../src/claude_code/hooks/events.py) -- Hook event types
- [`src/claude_code/tools/bash_tool/security.py`](../../src/claude_code/tools/bash_tool/security.py) -- Bash security checks
- [`src/claude_code/tools/bash_tool/sandbox.py`](../../src/claude_code/tools/bash_tool/sandbox.py) -- OS-level sandboxing

---

**[← Chapter 5: Context Engineering](chapter-05-context-engineering.md) | [Chapter 7: Extension Points →](chapter-07-extension-points.md)**
