"""Bash sandbox -- restrict command execution.

Maps to src/utils/sandbox/ in the TypeScript codebase.
Supports macOS sandbox-exec (seatbelt) and Linux bubblewrap.
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import shutil
import tempfile

logger = logging.getLogger(__name__)


def is_sandbox_available() -> bool:
    """Check if sandboxing is available on the current platform."""
    system = platform.system()
    if system == "Darwin":
        return shutil.which("sandbox-exec") is not None
    elif system == "Linux":
        return shutil.which("bwrap") is not None
    return False


def build_macos_sandbox_profile(
    cwd: str,
    allow_write_paths: list[str] | None = None,
    deny_write_paths: list[str] | None = None,
    allow_network: bool = True,
) -> str:
    """Build a macOS sandbox-exec (seatbelt) profile.

    This is a simplified version of the TS sandbox profile.
    """
    allow_write = allow_write_paths or [cwd]
    deny_write = deny_write_paths or []

    # Build deny-write rules for settings files
    deny_rules = []
    for path in deny_write:
        deny_rules.append(f'  (deny file-write* (subpath "{path}"))')

    # Build allow-write rules
    allow_rules = []
    for path in allow_write:
        allow_rules.append(f'  (allow file-write* (subpath "{path}"))')

    # Allow temp directory
    tmp = tempfile.gettempdir()
    allow_rules.append(f'  (allow file-write* (subpath "{tmp}"))')

    network_rule = "  (allow network*)" if allow_network else "  (deny network*)"

    profile = f"""\
(version 1)
(allow default)
; Deny writes outside allowed paths
(deny file-write* (subpath "/"))
; Allow writes to specific paths
{chr(10).join(allow_rules)}
; Deny writes to protected paths
{chr(10).join(deny_rules)}
; Network
{network_rule}
; Allow process execution
(allow process-exec*)
(allow process-fork)
"""
    return profile


def build_linux_sandbox_args(
    command: str,
    cwd: str,
    allow_write_paths: list[str] | None = None,
) -> list[str]:
    """Build bubblewrap (bwrap) arguments for Linux sandboxing."""
    allow_write = allow_write_paths or [cwd]
    tmp = tempfile.gettempdir()

    args = [
        "bwrap",
        "--ro-bind", "/", "/",  # Read-only root
        "--dev", "/dev",
        "--proc", "/proc",
        "--tmpfs", "/tmp",
    ]

    # Allow write to specific paths
    for path in allow_write + [tmp]:
        if os.path.exists(path):
            args.extend(["--bind", path, path])

    # Set working directory
    args.extend(["--chdir", cwd])

    # The command
    args.extend(["--", "sh", "-c", command])

    return args


async def run_sandboxed(
    command: str,
    cwd: str,
    timeout: float = 120.0,
    allow_write_paths: list[str] | None = None,
    deny_write_paths: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> tuple[str, str, int]:
    """Run a command in a sandbox.

    Returns (stdout, stderr, returncode).
    Falls back to unsandboxed execution if sandbox is unavailable.
    """
    system = platform.system()
    run_env = {**(env or os.environ), "TERM": "dumb"}

    if system == "Darwin" and shutil.which("sandbox-exec"):
        return await _run_macos_sandbox(
            command, cwd, timeout, allow_write_paths, deny_write_paths, run_env
        )
    elif system == "Linux" and shutil.which("bwrap"):
        return await _run_linux_sandbox(
            command, cwd, timeout, allow_write_paths, run_env
        )
    else:
        # Fallback: run unsandboxed
        logger.debug("Sandbox unavailable, running unsandboxed")
        return await _run_unsandboxed(command, cwd, timeout, run_env)


async def _run_macos_sandbox(
    command: str,
    cwd: str,
    timeout: float,
    allow_write_paths: list[str] | None,
    deny_write_paths: list[str] | None,
    env: dict[str, str],
) -> tuple[str, str, int]:
    """Run with macOS sandbox-exec."""
    profile = build_macos_sandbox_profile(
        cwd, allow_write_paths, deny_write_paths
    )

    # Write profile to temp file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sb", delete=False) as f:
        f.write(profile)
        profile_path = f.name

    try:
        proc = await asyncio.create_subprocess_exec(
            "sandbox-exec", "-f", profile_path, "sh", "-c", command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout)
        return (
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
            proc.returncode or 0,
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return "", "Command timed out", -1
    finally:
        os.unlink(profile_path)


async def _run_linux_sandbox(
    command: str,
    cwd: str,
    timeout: float,
    allow_write_paths: list[str] | None,
    env: dict[str, str],
) -> tuple[str, str, int]:
    """Run with Linux bubblewrap."""
    args = build_linux_sandbox_args(command, cwd, allow_write_paths)

    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout)
        return (
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
            proc.returncode or 0,
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return "", "Command timed out", -1


async def _run_unsandboxed(
    command: str,
    cwd: str,
    timeout: float,
    env: dict[str, str],
) -> tuple[str, str, int]:
    """Fallback: run without sandbox."""
    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        env=env,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout)
        return (
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
            proc.returncode or 0,
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return "", "Command timed out", -1
