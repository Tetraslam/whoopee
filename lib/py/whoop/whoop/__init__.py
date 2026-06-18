"""WHOOP v2 API client.

OAuth2 (authorization-code + refresh) with on-disk token persistence, plus
typed-ish helpers for the v2 data endpoints (recovery, sleep, cycles, workouts,
profile, body). Built on httpx.

Quick start (see lib/py/whoop/README.md for the full flow):

    from whoop import WhoopClient

    client = WhoopClient.from_env()        # reads WHOOP_CLIENT_ID/SECRET
    client.authorize()                     # opens browser, runs local callback
    print(client.profile())
    for rec in client.recovery_all():
        print(rec["score"]["recovery_score"])

Tokens are cached at ~/.whoop-token.json by default so you only authorize once.
"""

from .client import WhoopClient
from .oauth import TokenStore, WhoopAuthError

__all__ = ["WhoopClient", "TokenStore", "WhoopAuthError"]
