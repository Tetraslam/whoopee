"""OAuth2 token handling for the WHOOP API.

Implements the authorization-code grant with a tiny local callback server, plus
refresh-token rotation and JSON token persistence. WHOOP rotates the refresh
token on every refresh, so we always write the new pair back to disk.
"""

from __future__ import annotations

import http.server
import json
import secrets
import threading
import time
import urllib.parse
import webbrowser
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx

AUTH_URL = "https://api.prod.whoop.com/oauth/oauth2/auth"
TOKEN_URL = "https://api.prod.whoop.com/oauth/oauth2/token"

# All v2 read scopes + offline (required to get a refresh token).
DEFAULT_SCOPES = [
    "offline",
    "read:recovery",
    "read:cycles",
    "read:sleep",
    "read:workout",
    "read:profile",
    "read:body_measurement",
]


class WhoopAuthError(RuntimeError):
    """Raised when an OAuth step fails."""


@dataclass
class Token:
    access_token: str
    refresh_token: str
    expires_at: float  # unix epoch seconds
    scope: str = ""
    token_type: str = "bearer"

    @property
    def expired(self) -> bool:
        # 60s safety margin so we refresh just before the server would 401.
        return time.time() >= self.expires_at - 60

    @classmethod
    def from_response(cls, data: dict) -> Token:
        return cls(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token", ""),
            expires_at=time.time() + float(data.get("expires_in", 3600)),
            scope=data.get("scope", ""),
            token_type=data.get("token_type", "bearer"),
        )


class TokenStore:
    """Persists a Token as JSON on disk (default ~/.whoop-token.json)."""

    def __init__(self, path: str | Path = "~/.whoop-token.json") -> None:
        self.path = Path(path).expanduser()

    def load(self) -> Token | None:
        if not self.path.exists():
            return None
        try:
            return Token(**json.loads(self.path.read_text()))
        except (json.JSONDecodeError, TypeError, KeyError):
            return None

    def save(self, token: Token) -> None:
        self.path.write_text(json.dumps(asdict(token), indent=2))
        self.path.chmod(0o600)


def exchange_code(*, code: str, client_id: str, client_secret: str, redirect_uri: str) -> Token:
    resp = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        },
        timeout=30,
    )
    if resp.status_code != 200:
        raise WhoopAuthError(f"token exchange failed: {resp.status_code} {resp.text}")
    return Token.from_response(resp.json())


def refresh(*, token: Token, client_id: str, client_secret: str) -> Token:
    resp = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": token.refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "offline",
        },
        timeout=30,
    )
    if resp.status_code != 200:
        raise WhoopAuthError(f"token refresh failed: {resp.status_code} {resp.text}")
    return Token.from_response(resp.json())


def authorize_interactive(
    *,
    client_id: str,
    client_secret: str,
    redirect_uri: str = "http://localhost:8765/callback",
    scopes: list[str] | None = None,
    open_browser: bool = True,
) -> Token:
    """Run the full authorization-code flow with a local callback server.

    Spins up a one-shot HTTP server on the redirect port, opens the WHOOP
    consent page, captures the ?code=... redirect, and exchanges it for a token.
    The redirect_uri must be registered exactly in the WHOOP dashboard.
    """
    scopes = scopes or DEFAULT_SCOPES
    state = secrets.token_urlsafe(8)[:8]
    parsed = urllib.parse.urlparse(redirect_uri)
    host, port = parsed.hostname or "localhost", parsed.port or 80

    params = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes),
            "state": state,
        }
    )
    consent_url = f"{AUTH_URL}?{params}"

    holder: dict[str, str] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            holder["code"] = (q.get("code") or [""])[0]
            holder["state"] = (q.get("state") or [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h2>WHOOP authorized.</h2><p>You can close this tab.</p>")

        def log_message(self, *_args):  # silence the default stderr logging
            pass

    server = http.server.HTTPServer((host, port), Handler)
    t = threading.Thread(target=server.handle_request, daemon=True)
    t.start()

    print(f"Opening browser for WHOOP consent...\nIf it doesn't open: {consent_url}")
    if open_browser:
        webbrowser.open(consent_url)
    t.join(timeout=300)
    server.server_close()

    if not holder.get("code"):
        raise WhoopAuthError("no authorization code received (timed out or denied)")
    if holder.get("state") != state:
        raise WhoopAuthError("state mismatch — possible CSRF, aborting")

    return exchange_code(
        code=holder["code"],
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
    )
