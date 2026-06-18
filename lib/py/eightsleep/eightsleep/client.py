"""Tidy Eight Sleep client built on the vendored OAuth2 pyeight library.

Exposes per-night `Night` records and hides the async/raw-JSON details. The
underlying pyeight client is async; we run it via asyncio.run() in the sync
helpers so callers (scripts, a Flask backend) don't have to care.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Any

from .pyeight.eight import EightSleep


def _g(d: dict, *path: str) -> Any:
    """Safe nested get: _g(day, 'sleepQualityScore', 'hrv', 'current')."""
    cur: Any = d
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


@dataclass
class Night:
    """One night of Eight Sleep data, normalized.

    Durations are seconds. Temperatures are the API's raw scale (relative, not
    degrees) unless noted. HRV/HR/respiratory are the night's representative
    ("current") values that line up with WHOOP's nightly metrics.
    """

    date: str  # YYYY-MM-DD (the morning the session ended)
    side: str
    sleep_score: int | None
    # vitals (for cross-validation with WHOOP)
    hrv: float | None
    heart_rate: float | None
    respiratory_rate: float | None
    # sleep architecture
    sleep_duration: int | None
    deep_duration: int | None
    rem_duration: int | None
    light_duration: int | None
    tnt: int | None  # tossing & turning count
    sleep_debt: float | None
    # timing
    sleep_start: str | None
    sleep_end: str | None
    incomplete: bool = False

    @classmethod
    def from_trend_day(cls, day: dict, side: str) -> Night:
        return cls(
            date=day.get("day"),
            side=side,
            sleep_score=day.get("score"),
            hrv=_g(day, "sleepQualityScore", "hrv", "current"),
            heart_rate=_g(day, "sleepQualityScore", "heartRate", "current"),
            respiratory_rate=_g(day, "sleepQualityScore", "respiratoryRate", "current"),
            sleep_duration=day.get("sleepDuration"),
            deep_duration=day.get("deepDuration"),
            rem_duration=day.get("remDuration"),
            light_duration=day.get("lightDuration"),
            tnt=day.get("tnt"),
            sleep_debt=_g(day, "sleepQualityScore", "sleepDebt", "current"),
            sleep_start=day.get("sleepStart"),
            sleep_end=day.get("sleepEnd"),
            incomplete=bool(day.get("incomplete", False)),
        )

    def to_dict(self) -> dict:
        return asdict(self)


class EightSleepClient:
    def __init__(self, *, email: str, password: str, timezone: str) -> None:
        self.email = email
        self.password = password
        self.timezone = timezone

    @classmethod
    def from_env(cls) -> EightSleepClient:
        """Build from EIGHT_SLEEP_EMAIL / _PASSWORD / _TIMEZONE.

        Pair with tools/load-env.sh to resolve them from 1Password.
        """
        try:
            return cls(
                email=os.environ["EIGHT_SLEEP_EMAIL"],
                password=os.environ["EIGHT_SLEEP_PASSWORD"],
                timezone=os.environ.get("EIGHT_SLEEP_TIMEZONE", "America/Los_Angeles"),
            )
        except KeyError as e:
            raise RuntimeError(
                f"{e.args[0]} not set. Run via tools/load-env.sh to resolve "
                "Eight Sleep creds from 1Password."
            ) from e

    # --- async core ---------------------------------------------------------

    async def _fetch_nights(self, start: str, end: str) -> list[Night]:
        es = EightSleep(self.email, self.password, self.timezone)
        try:
            ok = await es.start()
            if not ok:
                raise RuntimeError("Eight Sleep auth failed")
            nights: list[Night] = []
            for user in es.users.values():
                await user.update_trend_data(start, end)
                for day in user.trends:
                    nights.append(Night.from_trend_day(day, user.side))
            nights.sort(key=lambda n: n.date or "")
            return nights
        finally:
            await es.stop()

    # --- sync helpers -------------------------------------------------------

    def nights(self, *, start: str, end: str) -> list[Night]:
        """Per-night records for an inclusive ISO date range (YYYY-MM-DD)."""
        return asyncio.run(self._fetch_nights(start, end))

    def recent_nights(self, *, days: int = 35) -> list[Night]:
        end = date.today()
        start = end - timedelta(days=days)
        return self.nights(start=start.isoformat(), end=end.isoformat())
