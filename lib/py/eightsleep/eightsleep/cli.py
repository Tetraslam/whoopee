"""Tiny CLI for the Eight Sleep client.

tools/load-env.sh -- uv run python -m eightsleep.cli nights
tools/load-env.sh -- uv run python -m eightsleep.cli nights --days 60
"""

from __future__ import annotations

import json
import sys

from .client import EightSleepClient


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    cmd = argv[0] if argv else "help"

    if cmd in ("help", "-h", "--help"):
        print(__doc__)
        return 0

    days = 35
    if "--days" in argv:
        days = int(argv[argv.index("--days") + 1])

    client = EightSleepClient.from_env()

    if cmd == "nights":
        nights = client.recent_nights(days=days)
        for n in nights:
            print(
                f"{n.date}  score={n.sleep_score}  hrv={n.hrv}  hr={n.heart_rate}  "
                f"resp={n.respiratory_rate}  sleep={(n.sleep_duration or 0) // 3600}h"
            )
        print(f"\n{len(nights)} nights")
        return 0

    if cmd == "json":
        nights = client.recent_nights(days=days)
        print(json.dumps([n.to_dict() for n in nights], indent=2))
        return 0

    print(f"unknown command: {cmd}\n{__doc__}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
