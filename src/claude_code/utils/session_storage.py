"""Session storage -- conversation persistence.

Maps to src/utils/sessionStorage.ts in the TypeScript codebase.
Saves/loads conversations as JSONL files for resume support.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any

from claude_code.utils.config import get_claude_home

logger = logging.getLogger(__name__)

SESSIONS_DIR = "sessions"


def get_sessions_dir() -> Path:
    """Get the sessions directory (~/.claude/sessions/)."""
    sessions = get_claude_home() / SESSIONS_DIR
    sessions.mkdir(parents=True, exist_ok=True)
    return sessions


def get_session_file(session_id: str) -> Path:
    """Get the file path for a session."""
    return get_sessions_dir() / f"{session_id}.jsonl"


def generate_session_id() -> str:
    """Generate a new unique session ID."""
    return str(uuid.uuid4())


def save_message(session_id: str, message: dict[str, Any]) -> None:
    """Append a message to the session's JSONL file."""
    session_file = get_session_file(session_id)
    entry = {
        **message,
        "sessionId": session_id,
        "timestamp": time.time(),
    }
    try:
        with open(session_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except OSError as e:
        logger.warning("Failed to save message: %s", e)


def load_session(session_id: str) -> list[dict[str, Any]]:
    """Load all messages from a session's JSONL file."""
    session_file = get_session_file(session_id)
    if not session_file.exists():
        return []

    messages: list[dict[str, Any]] = []
    try:
        with open(session_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        messages.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    except OSError as e:
        logger.warning("Failed to load session: %s", e)

    return messages


def list_sessions(limit: int = 20) -> list[dict[str, Any]]:
    """List recent sessions with metadata.

    Returns list of dicts with: session_id, date, first_prompt, message_count.
    """
    sessions_dir = get_sessions_dir()
    session_files = sorted(
        sessions_dir.glob("*.jsonl"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )[:limit]

    sessions: list[dict[str, Any]] = []
    for session_file in session_files:
        session_id = session_file.stem
        try:
            messages = load_session(session_id)
            first_prompt = ""
            for msg in messages:
                if msg.get("role") == "user":
                    content = msg.get("content", "")
                    if isinstance(content, str):
                        first_prompt = content[:100]
                    break

            sessions.append({
                "session_id": session_id,
                "date": session_file.stat().st_mtime,
                "first_prompt": first_prompt,
                "message_count": len(messages),
            })
        except Exception:
            continue

    return sessions


def delete_session(session_id: str) -> bool:
    """Delete a session file."""
    session_file = get_session_file(session_id)
    if session_file.exists():
        session_file.unlink()
        return True
    return False
