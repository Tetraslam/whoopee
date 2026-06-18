"""Tiny CLI for authorizing and smoke-testing the WHOOP client.

tools/load-env.sh -- uv run python -m whoop.cli auth
tools/load-env.sh -- uv run python -m whoop.cli profile
tools/load-env.sh -- uv run python -m whoop.cli recovery
"""

from __future__ import annotations

import json
import sys

from .client import WhoopClient


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    cmd = argv[0] if argv else "help"

    if cmd in ("help", "-h", "--help"):
        print(__doc__)
        return 0

    client = WhoopClient.from_env()

    if cmd == "auth":
        client.authorize()
        print("Authorized. Token cached at", client.store.path)
        return 0

    if cmd == "profile":
        print(json.dumps(client.profile(), indent=2))
        return 0

    if cmd == "recovery":
        for rec in client.recovery_all(limit=10):
            score = rec.get("score", {}).get("recovery_score")
            print(rec.get("created_at"), "recovery:", score)
        return 0

    print(f"unknown command: {cmd}\n{__doc__}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
