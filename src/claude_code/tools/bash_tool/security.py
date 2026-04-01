"""Bash security checks.

Maps to src/tools/BashTool/bashSecurity.ts in the TypeScript codebase.
Implements 15 named security checks that detect dangerous command patterns.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Unicode whitespace characters that could cause parsing inconsistencies
UNICODE_WHITESPACE = re.compile(
    r"[\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000\uFEFF]"
)

# Control characters (non-printable)
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")

# Command substitution patterns
COMMAND_SUBSTITUTION = re.compile(r"\$\(|\`|\$\{")

# IFS injection
IFS_PATTERN = re.compile(r"\$IFS|\$\{[^}]*IFS")

# /proc/*/environ access
PROC_ENVIRON = re.compile(r"/proc/.*/environ")

# Dangerous variable contexts (variable near redirection/pipe)
DANGEROUS_VARS = re.compile(r"[<>|]\s*\$[A-Za-z_]|\$[A-Za-z_]\w*\s*[|<>]")

# Incomplete command patterns
STARTS_WITH_TAB = re.compile(r"^\s*\t")
STARTS_WITH_DASH = re.compile(r"^\s*-")
STARTS_WITH_OPERATOR = re.compile(r"^\s*(&&|\|\||;|>>?|<)")

# Brace expansion
BRACE_EXPANSION = re.compile(r"\{[^}]*[,.].*\}")

# Mid-word hash
MID_WORD_HASH = re.compile(r"\S#")

# Backslash-escaped operators
BACKSLASH_OPERATORS = re.compile(r"\\[;|&<>]")

# Backslash-escaped whitespace
BACKSLASH_WHITESPACE = re.compile(r"\\ |\\\t")

# Comment-quote desync
COMMENT_QUOTE = re.compile(r"#.*['\"]")

# ANSI-C quoting
ANSI_C_QUOTING = re.compile(r"\$'")

# Zsh dangerous commands
ZSH_DANGEROUS = {
    "zmodload", "emulate", "sysopen", "sysread", "syswrite", "sysseek",
    "zpty", "ztcp", "zsocket", "mapfile", "zf_rm", "zf_mv", "zf_ln",
    "zf_chmod", "zf_chown", "zf_mkdir", "zf_rmdir", "zf_chgrp",
}


@dataclass
class SecurityCheckResult:
    """Result of a security check."""
    blocked: bool = False
    check_id: str = ""
    message: str = ""
    is_misparsing: bool = False  # If true, this is a parsing ambiguity (not malice)


def run_security_checks(command: str) -> SecurityCheckResult:
    """Run all security checks against a command.

    Returns the first failing check, or a non-blocked result if all pass.
    """
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
            logger.warning("Security check %s blocked: %s", result.check_id, result.message)
            return result

    return SecurityCheckResult()


def _check_control_characters(cmd: str) -> SecurityCheckResult:
    if CONTROL_CHARS.search(cmd):
        return SecurityCheckResult(
            blocked=True, check_id="CONTROL_CHARACTERS",
            message="Command contains non-printable control characters that could bypass security checks",
            is_misparsing=True,
        )
    return SecurityCheckResult()


def _check_incomplete_commands(cmd: str) -> SecurityCheckResult:
    stripped = cmd.strip()
    if STARTS_WITH_TAB.match(stripped):
        return SecurityCheckResult(
            blocked=True, check_id="INCOMPLETE_COMMANDS",
            message="Command appears to be an incomplete fragment (starts with tab)",
            is_misparsing=True,
        )
    if stripped.startswith("-") and not stripped.startswith("--"):
        # Allow common flag patterns like -e, but block bare dashes
        if len(stripped) == 1 or stripped[1] == " ":
            return SecurityCheckResult(
                blocked=True, check_id="INCOMPLETE_COMMANDS",
                message="Command appears to be an incomplete fragment (starts with -)",
                is_misparsing=True,
            )
    if STARTS_WITH_OPERATOR.match(stripped):
        return SecurityCheckResult(
            blocked=True, check_id="INCOMPLETE_COMMANDS",
            message="Command appears to be an incomplete fragment (starts with operator)",
            is_misparsing=True,
        )
    return SecurityCheckResult()


def _check_unicode_whitespace(cmd: str) -> SecurityCheckResult:
    if UNICODE_WHITESPACE.search(cmd):
        return SecurityCheckResult(
            blocked=True, check_id="UNICODE_WHITESPACE",
            message="Command contains Unicode whitespace characters that could cause parsing inconsistencies",
            is_misparsing=True,
        )
    return SecurityCheckResult()


def _check_command_substitution(cmd: str) -> SecurityCheckResult:
    # Skip if command is clearly a simple command
    # Only flag in contexts where substitution could be dangerous
    if "`" in cmd:
        # Check if backtick is outside of single quotes
        in_single = False
        for i, c in enumerate(cmd):
            if c == "'" and (i == 0 or cmd[i - 1] != "\\"):
                in_single = not in_single
            elif c == "`" and not in_single:
                return SecurityCheckResult(
                    blocked=True, check_id="COMMAND_SUBSTITUTION",
                    message="Command contains backticks (`) for command substitution",
                )
    return SecurityCheckResult()


def _check_ifs_injection(cmd: str) -> SecurityCheckResult:
    if IFS_PATTERN.search(cmd):
        return SecurityCheckResult(
            blocked=True, check_id="IFS_INJECTION",
            message="Command contains IFS variable usage which could bypass security validation",
        )
    return SecurityCheckResult()


def _check_proc_environ(cmd: str) -> SecurityCheckResult:
    if PROC_ENVIRON.search(cmd):
        return SecurityCheckResult(
            blocked=True, check_id="PROC_ENVIRON",
            message="Command accesses /proc/*/environ which could expose sensitive environment variables",
        )
    return SecurityCheckResult()


def _check_dangerous_variables(cmd: str) -> SecurityCheckResult:
    if DANGEROUS_VARS.search(cmd):
        return SecurityCheckResult(
            blocked=True, check_id="DANGEROUS_VARIABLES",
            message="Command contains variables in dangerous contexts (redirections or pipes)",
        )
    return SecurityCheckResult()


def _check_backslash_operators(cmd: str) -> SecurityCheckResult:
    if BACKSLASH_OPERATORS.search(cmd):
        return SecurityCheckResult(
            blocked=True, check_id="BACKSLASH_OPERATORS",
            message="Command contains a backslash before a shell operator which can hide command structure",
            is_misparsing=True,
        )
    return SecurityCheckResult()


def _check_backslash_whitespace(cmd: str) -> SecurityCheckResult:
    if BACKSLASH_WHITESPACE.search(cmd):
        return SecurityCheckResult(
            blocked=True, check_id="BACKSLASH_WHITESPACE",
            message="Command contains backslash-escaped whitespace that could alter command parsing",
            is_misparsing=True,
        )
    return SecurityCheckResult()


def _check_brace_expansion(cmd: str) -> SecurityCheckResult:
    if BRACE_EXPANSION.search(cmd):
        return SecurityCheckResult(
            blocked=True, check_id="BRACE_EXPANSION",
            message="Command contains brace expansion that could alter command parsing",
            is_misparsing=True,
        )
    return SecurityCheckResult()


def _check_mid_word_hash(cmd: str) -> SecurityCheckResult:
    # Check for # directly after non-whitespace (outside quotes)
    if MID_WORD_HASH.search(cmd):
        # Exclude common safe patterns like #! (shebang) and ${#...} (string length)
        if not cmd.strip().startswith("#") and "${#" not in cmd:
            return SecurityCheckResult(
                blocked=True, check_id="MID_WORD_HASH",
                message="Command contains mid-word # which is parsed differently by different shells",
                is_misparsing=True,
            )
    return SecurityCheckResult()


def _check_ansi_c_quoting(cmd: str) -> SecurityCheckResult:
    if ANSI_C_QUOTING.search(cmd):
        return SecurityCheckResult(
            blocked=True, check_id="ANSI_C_QUOTING",
            message="Command contains ANSI-C quoting ($'...') which can hide characters",
        )
    return SecurityCheckResult()


def _check_comment_quote_desync(cmd: str) -> SecurityCheckResult:
    # Only check unquoted portions
    if COMMENT_QUOTE.search(cmd):
        return SecurityCheckResult(
            blocked=True, check_id="COMMENT_QUOTE_DESYNC",
            message="Command contains quote characters inside a # comment which can desync quote tracking",
            is_misparsing=True,
        )
    return SecurityCheckResult()


def _check_zsh_dangerous(cmd: str) -> SecurityCheckResult:
    base_cmd = cmd.strip().split()[0] if cmd.strip() else ""
    if base_cmd in ZSH_DANGEROUS:
        return SecurityCheckResult(
            blocked=True, check_id="ZSH_DANGEROUS",
            message=f"Command uses Zsh-specific '{base_cmd}' which can bypass security checks",
        )
    return SecurityCheckResult()


def _check_newlines(cmd: str) -> SecurityCheckResult:
    if "\r" in cmd:
        return SecurityCheckResult(
            blocked=True, check_id="NEWLINES_CR",
            message="Command contains carriage return (\\r) which shells tokenize differently",
            is_misparsing=True,
        )
    # Check for newlines that aren't backslash-continued
    if "\n" in cmd:
        lines = cmd.split("\n")
        for i, line in enumerate(lines[:-1]):
            stripped_line = line.rstrip()
            next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
            # Allow backslash continuation
            if stripped_line.endswith("\\"):
                continue
            # Allow heredoc continuation
            if "<<" in stripped_line:
                continue
            # Newline followed by non-empty content is suspicious
            if next_line:
                return SecurityCheckResult(
                    blocked=True, check_id="NEWLINES_LF",
                    message="Command contains newlines that could separate multiple commands",
                    is_misparsing=True,
                )
    return SecurityCheckResult()
