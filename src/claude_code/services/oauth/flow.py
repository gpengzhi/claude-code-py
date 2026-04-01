"""OAuth browser flow for claude.ai subscribers.

Maps to OAuth flow in the TypeScript codebase.
Opens the user's browser for authentication and handles the callback.
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from threading import Thread
from typing import Any
from urllib.parse import urlencode, parse_qs, urlparse

from claude_code.utils.config import get_claude_home

logger = logging.getLogger(__name__)

OAUTH_CALLBACK_PORT = 19485
OAUTH_TOKEN_FILE = "oauth_token.json"

# Claude.ai OAuth endpoints
CLAUDE_AI_BASE = "https://claude.ai"
AUTHORIZE_URL = f"{CLAUDE_AI_BASE}/oauth/authorize"
TOKEN_URL = f"{CLAUDE_AI_BASE}/oauth/token"
CLIENT_ID = "claude-code"
REDIRECT_URI = f"http://localhost:{OAUTH_CALLBACK_PORT}/callback"


class OAuthToken:
    """Stored OAuth token with refresh capability."""

    def __init__(
        self,
        access_token: str,
        refresh_token: str | None = None,
        expires_at: float = 0,
        token_type: str = "Bearer",
    ) -> None:
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires_at = expires_at
        self.token_type = token_type

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at - 60  # 60s buffer

    def to_dict(self) -> dict[str, Any]:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "token_type": self.token_type,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OAuthToken:
        return cls(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_at=data.get("expires_at", 0),
            token_type=data.get("token_type", "Bearer"),
        )


def get_token_path() -> Path:
    """Get the OAuth token storage path."""
    return get_claude_home() / OAUTH_TOKEN_FILE


def load_stored_token() -> OAuthToken | None:
    """Load a stored OAuth token from disk."""
    path = get_token_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return OAuthToken.from_dict(data)
    except (json.JSONDecodeError, KeyError, OSError):
        return None


def save_token(token: OAuthToken) -> None:
    """Save an OAuth token to disk."""
    path = get_token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(token.to_dict(), indent=2), encoding="utf-8")
    path.chmod(0o600)


def clear_token() -> None:
    """Remove the stored OAuth token."""
    path = get_token_path()
    if path.exists():
        path.unlink()


async def refresh_token(token: OAuthToken) -> OAuthToken | None:
    """Refresh an expired OAuth token."""
    if not token.refresh_token:
        return None

    try:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.post(
                TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": token.refresh_token,
                    "client_id": CLIENT_ID,
                },
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                new_token = OAuthToken(
                    access_token=data["access_token"],
                    refresh_token=data.get("refresh_token", token.refresh_token),
                    expires_at=time.time() + data.get("expires_in", 3600),
                    token_type=data.get("token_type", "Bearer"),
                )
                save_token(new_token)
                return new_token
    except Exception as e:
        logger.error("Token refresh failed: %s", e)
        return None


async def get_valid_token() -> OAuthToken | None:
    """Get a valid OAuth token, refreshing if needed."""
    token = load_stored_token()
    if token is None:
        return None
    if token.is_expired:
        return await refresh_token(token)
    return token


def start_oauth_flow() -> str:
    """Start the OAuth authorization flow.

    Returns the authorization URL to open in the browser.
    """
    state = secrets.token_urlsafe(32)

    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "state": state,
        "scope": "claude-code",
    }

    return f"{AUTHORIZE_URL}?{urlencode(params)}", state


class _CallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler for the OAuth callback."""

    auth_code: str | None = None
    state: str | None = None

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/callback":
            params = parse_qs(parsed.query)
            _CallbackHandler.auth_code = params.get("code", [None])[0]
            _CallbackHandler.state = params.get("state", [None])[0]

            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                b"<html><body><h1>Authentication successful!</h1>"
                b"<p>You can close this tab and return to the terminal.</p>"
                b"</body></html>"
            )
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        pass  # Suppress default logging


async def complete_oauth_flow(expected_state: str) -> OAuthToken | None:
    """Wait for the OAuth callback and exchange the code for a token."""
    _CallbackHandler.auth_code = None
    _CallbackHandler.state = None

    server = HTTPServer(("localhost", OAUTH_CALLBACK_PORT), _CallbackHandler)
    thread = Thread(target=server.handle_request, daemon=True)
    thread.start()

    # Wait for the callback (max 120 seconds)
    for _ in range(240):
        await asyncio.sleep(0.5)
        if _CallbackHandler.auth_code:
            break

    server.server_close()

    if not _CallbackHandler.auth_code:
        return None

    if _CallbackHandler.state != expected_state:
        logger.error("OAuth state mismatch")
        return None

    # Exchange code for token
    try:
        import aiohttp

        async with aiohttp.ClientSession() as session:
            async with session.post(
                TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": _CallbackHandler.auth_code,
                    "redirect_uri": REDIRECT_URI,
                    "client_id": CLIENT_ID,
                },
            ) as resp:
                if resp.status != 200:
                    logger.error("Token exchange failed: %s", await resp.text())
                    return None
                data = await resp.json()
                token = OAuthToken(
                    access_token=data["access_token"],
                    refresh_token=data.get("refresh_token"),
                    expires_at=time.time() + data.get("expires_in", 3600),
                    token_type=data.get("token_type", "Bearer"),
                )
                save_token(token)
                return token
    except Exception as e:
        logger.error("Token exchange failed: %s", e)
        return None
