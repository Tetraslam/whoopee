"""Eight Sleep client — clean per-night records over the vendored pyeight OAuth2 API.

Eight Sleep has no official API. We vendor lukas-clarke's OAuth2 client (the
maintained reverse-engineered one) under `eightsleep.pyeight` and expose a small,
synchronous-friendly surface that yields tidy `Night` records — the fields that
matter for analysis and fusion with WHOOP (sleep score, stages, HRV, heart rate,
respiratory rate, temps, tossing & turning, sleep debt).

Usage:

    from eightsleep import EightSleepClient

    es = EightSleepClient.from_env()
    nights = es.recent_nights(days=35)   # runs the async client under the hood
    for n in nights:
        print(n.date, n.sleep_score, n.hrv, n.heart_rate)
"""

from .client import EightSleepClient, Night

__all__ = ["EightSleepClient", "Night"]
