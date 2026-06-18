"""High-level WHOOP v2 API client.

Wraps the OAuth token lifecycle (load -> refresh-if-needed -> persist) and the
v2 data endpoints. Collection endpoints are paginated via `nextToken`; the
`*_all()` helpers transparently follow pagination and yield every record.

Base URL: https://api.prod.whoop.com/developer/v2
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx

from .oauth import (
    DEFAULT_SCOPES,
    Token,
    TokenStore,
    WhoopAuthError,
    authorize_interactive,
    refresh,
)

BASE_URL = "https://api.prod.whoop.com/developer/v2"


class WhoopClient:
    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        token_store: TokenStore | None = None,
        redirect_uri: str = "http://localhost:8765/callback",
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.store = token_store or TokenStore()
        self._token: Token | None = self.store.load()
        self._http = httpx.Client(base_url=BASE_URL, timeout=30)

    @classmethod
    def from_env(
        cls,
        *,
        token_path: str | Path = "~/.whoop-token.json",
        redirect_uri: str = "http://localhost:8765/callback",
    ) -> WhoopClient:
        """Build from WHOOP_CLIENT_ID / WHOOP_CLIENT_SECRET env vars.

        Pair with tools/load-env.sh to resolve these from 1Password:
            tools/load-env.sh -- uv run python your_script.py
        """
        cid = os.environ.get("WHOOP_CLIENT_ID")
        secret = os.environ.get("WHOOP_CLIENT_SECRET")
        if not cid or not secret:
            raise WhoopAuthError(
                "WHOOP_CLIENT_ID / WHOOP_CLIENT_SECRET not set. "
                "Run via tools/load-env.sh to resolve them from 1Password."
            )
        return cls(
            client_id=cid,
            client_secret=secret,
            token_store=TokenStore(token_path),
            redirect_uri=redirect_uri,
        )

    # --- auth ---------------------------------------------------------------

    def authorize(self, scopes: list[str] | None = None, open_browser: bool = True) -> None:
        """Run the interactive browser OAuth flow and persist the token."""
        token = authorize_interactive(
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=self.redirect_uri,
            scopes=scopes or DEFAULT_SCOPES,
            open_browser=open_browser,
        )
        self._token = token
        self.store.save(token)

    def _ensure_token(self) -> Token:
        if self._token is None:
            raise WhoopAuthError("not authorized — call client.authorize() first")
        if self._token.expired:
            self._token = refresh(
                token=self._token,
                client_id=self.client_id,
                client_secret=self.client_secret,
            )
            self.store.save(self._token)
        return self._token

    # --- raw request --------------------------------------------------------

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict:
        token = self._ensure_token()
        resp = self._http.get(
            path,
            params=params,
            headers={"Authorization": f"Bearer {token.access_token}"},
        )
        if resp.status_code == 401:
            # Token might have been revoked/rotated out-of-band; one retry.
            self._token = refresh(
                token=token, client_id=self.client_id, client_secret=self.client_secret
            )
            self.store.save(self._token)
            resp = self._http.get(
                path,
                params=params,
                headers={"Authorization": f"Bearer {self._token.access_token}"},
            )
        resp.raise_for_status()
        return resp.json()

    def _paginate(
        self, path: str, *, limit: int = 25, start: str | None = None, end: str | None = None
    ) -> Iterator[dict]:
        params: dict[str, Any] = {"limit": limit}
        if start:
            params["start"] = start
        if end:
            params["end"] = end
        while True:
            page = self._get(path, params=params)
            yield from page.get("records", [])
            next_token = page.get("next_token")
            if not next_token:
                break
            params["nextToken"] = next_token

    # --- profile / body -----------------------------------------------------

    def profile(self) -> dict:
        return self._get("/user/profile/basic")

    def body_measurement(self) -> dict:
        return self._get("/user/measurement/body")

    # --- recovery -----------------------------------------------------------

    def recovery_all(self, **kw: Any) -> Iterator[dict]:
        yield from self._paginate("/recovery", **kw)

    def recovery_for_cycle(self, cycle_id: int) -> dict:
        return self._get(f"/cycle/{cycle_id}/recovery")

    # --- cycles -------------------------------------------------------------

    def cycles_all(self, **kw: Any) -> Iterator[dict]:
        yield from self._paginate("/cycle", **kw)

    def cycle(self, cycle_id: int) -> dict:
        return self._get(f"/cycle/{cycle_id}")

    def sleep_for_cycle(self, cycle_id: int) -> dict:
        return self._get(f"/cycle/{cycle_id}/sleep")

    # --- sleep --------------------------------------------------------------

    def sleep_all(self, **kw: Any) -> Iterator[dict]:
        yield from self._paginate("/activity/sleep", **kw)

    def sleep(self, sleep_id: str) -> dict:
        return self._get(f"/activity/sleep/{sleep_id}")

    # --- workouts -----------------------------------------------------------

    def workouts_all(self, **kw: Any) -> Iterator[dict]:
        yield from self._paginate("/activity/workout", **kw)

    def workout(self, workout_id: str) -> dict:
        return self._get(f"/activity/workout/{workout_id}")

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> WhoopClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
