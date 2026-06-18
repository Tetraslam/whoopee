"""Pull both sources and cache to disk so we don't hammer the APIs.

Cache is a single JSON file (raw records from each source). `load(refresh=True)`
re-pulls; otherwise we serve cache if it's fresh enough.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from eightsleep import EightSleepClient
from whoop import WhoopClient

CACHE = Path(__file__).resolve().parent.parent / ".cache" / "data.json"
DEFAULT_TTL = 1800  # 30 min


def _pull(days: int) -> dict:
    whoop = WhoopClient.from_env()
    recoveries = list(whoop.recovery_all(limit=25))
    sleeps = list(whoop.sleep_all(limit=25))
    whoop.close()

    es = EightSleepClient.from_env()
    nights = es.recent_nights(days=days)

    return {
        "pulled_at": time.time(),
        "whoop_recoveries": recoveries,
        "whoop_sleeps": sleeps,
        "eightsleep_nights": [n.to_dict() for n in nights],
    }


def load(*, days: int = 90, refresh: bool = False, ttl: int = DEFAULT_TTL) -> dict:
    if not refresh and CACHE.exists():
        data = json.loads(CACHE.read_text())
        if time.time() - data.get("pulled_at", 0) < ttl:
            return data
    data = _pull(days)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(data))
    return data
