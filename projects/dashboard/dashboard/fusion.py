"""Pull WHOOP + Eight Sleep, align by night, and fuse.

The unit of analysis is a *night*, keyed by the calendar date of the morning you
woke up, in your local timezone (SF). Both devices measure the same sleep; this
module lines them up and computes the things neither app will show you:

- side-by-side HRV / resting-HR / respiratory rate from two independent sensors
- a "trust" signal: how well the two devices agree, night over night
- your recovery baseline from before the WHOOP gap, and the comeback since

WHOOP HRV is RMSSD in milliseconds; Eight Sleep HRV is its own scale. They are
not equal in magnitude — we compare *trends* (z-scored), not raw values.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

LOCAL_TZ = ZoneInfo("America/Los_Angeles")


def _night_date(iso_ts: str | None) -> str | None:
    """Calendar date (local) of a wake/end timestamp -> 'YYYY-MM-DD'."""
    if not iso_ts:
        return None
    ts = iso_ts.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(LOCAL_TZ).date().isoformat()


@dataclass
class FusedNight:
    date: str
    # whoop
    whoop_recovery: float | None = None
    whoop_hrv_ms: float | None = None
    whoop_rhr: float | None = None
    whoop_resp: float | None = None
    whoop_sleep_perf: float | None = None
    whoop_sleep_hours: float | None = None
    # eight sleep
    es_score: int | None = None
    es_hrv: float | None = None
    es_hr: float | None = None
    es_resp: float | None = None
    es_sleep_hours: float | None = None
    es_tnt: int | None = None
    # derived
    sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        return d


def _ms_to_hours(milli: float | None) -> float | None:
    return round(milli / 3_600_000, 2) if milli else None


def build_nights(whoop_recoveries, whoop_sleeps, es_nights) -> list[FusedNight]:
    """Merge raw records from both sources into per-night fused records."""
    nights: dict[str, FusedNight] = {}

    def night(d: str) -> FusedNight:
        return nights.setdefault(d, FusedNight(date=d))

    # WHOOP sleep keyed by id so we can join respiratory/stage data to recovery
    sleep_by_id = {s["id"]: s for s in whoop_sleeps if not s.get("nap")}

    for rec in whoop_recoveries:
        d = _night_date(rec.get("created_at"))
        if not d:
            continue
        n = night(d)
        score = rec.get("score") or {}
        n.whoop_recovery = score.get("recovery_score")
        n.whoop_hrv_ms = (
            round(score["hrv_rmssd_milli"], 1) if score.get("hrv_rmssd_milli") else None
        )
        n.whoop_rhr = score.get("resting_heart_rate")
        sleep = sleep_by_id.get(rec.get("sleep_id"))
        if sleep:
            ss = sleep.get("score") or {}
            n.whoop_resp = round(ss["respiratory_rate"], 1) if ss.get("respiratory_rate") else None
            n.whoop_sleep_perf = ss.get("sleep_performance_percentage")
            stage = ss.get("stage_summary") or {}
            in_bed = stage.get("total_in_bed_time_milli")
            awake = stage.get("total_awake_time_milli") or 0
            if in_bed:
                n.whoop_sleep_hours = _ms_to_hours(in_bed - awake)
        if "whoop" not in n.sources:
            n.sources.append("whoop")

    # WHOOP sleeps that didn't have a recovery (e.g. naps already filtered)
    for sleep in sleep_by_id.values():
        d = _night_date(sleep.get("end"))
        if not d:
            continue
        n = night(d)
        if n.whoop_resp is None:
            ss = sleep.get("score") or {}
            n.whoop_resp = round(ss["respiratory_rate"], 1) if ss.get("respiratory_rate") else None
        if "whoop" not in n.sources and n.whoop_recovery is not None:
            n.sources.append("whoop")

    for es in es_nights:
        d = es.date
        if not d:
            continue
        n = night(d)
        n.es_score = es.sleep_score
        n.es_hrv = es.hrv
        n.es_hr = es.heart_rate
        n.es_resp = es.respiratory_rate
        n.es_sleep_hours = round(es.sleep_duration / 3600, 2) if es.sleep_duration else None
        n.es_tnt = es.tnt
        if "eightsleep" not in n.sources:
            n.sources.append("eightsleep")

    return [nights[d] for d in sorted(nights)]


def _zscores(values: list[float]) -> list[float]:
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return [0.0 for _ in values]
    mu = statistics.mean(vals)
    sd = statistics.pstdev(vals) or 1.0
    return [((v - mu) / sd) if v is not None else None for v in values]


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    pairs = [(x, y) for x, y in zip(xs, ys, strict=False) if x is not None and y is not None]
    if len(pairs) < 3:
        return None
    xa = [p[0] for p in pairs]
    ya = [p[1] for p in pairs]
    mx, my = statistics.mean(xa), statistics.mean(ya)
    num = sum((x - mx) * (y - my) for x, y in pairs)
    den = (sum((x - mx) ** 2 for x in xa) * sum((y - my) ** 2 for y in ya)) ** 0.5
    return round(num / den, 3) if den else None


def trust_report(nights: list[FusedNight]) -> dict:
    """How well do the two devices agree? Correlate trends where both exist.

    Returns per-metric correlation over nights with both sensors, plus a single
    overall agreement score (mean of available correlations, 0..1).
    """
    both = [n for n in nights if "whoop" in n.sources and "eightsleep" in n.sources]
    metrics = {
        "hrv": ([n.whoop_hrv_ms for n in both], [n.es_hrv for n in both]),
        "resting_hr": ([n.whoop_rhr for n in both], [n.es_hr for n in both]),
        "respiratory": ([n.whoop_resp for n in both], [n.es_resp for n in both]),
    }
    corrs: dict[str, float | None] = {}
    for name, (w, e) in metrics.items():
        corrs[name] = _pearson(w, e)
    available = [c for c in corrs.values() if c is not None]
    overall = round(sum(available) / len(available), 3) if available else None
    return {
        "overlapping_nights": len(both),
        "correlations": corrs,
        "overall_agreement": overall,
    }


def comeback_report(nights: list[FusedNight]) -> dict:
    """Eight Sleep covers the WHOOP gap. Find when WHOOP went quiet and (maybe)
    came back, and compare Eight Sleep metrics before vs during the gap vs now.

    Handles two cases: an internal gap bounded by WHOOP on both sides, and a
    trailing gap where WHOOP stopped and Eight Sleep kept going to the present.
    """
    whoop_dates = sorted(n.date for n in nights if n.whoop_recovery is not None)
    es_dates = sorted(n.date for n in nights if n.es_score is not None)
    es_only = [n for n in nights if n.es_score is not None and n.whoop_recovery is None]

    gap = None
    if whoop_dates and es_dates:
        ds = [datetime.fromisoformat(d) for d in whoop_dates]
        # largest internal gap between consecutive whoop nights
        max_delta, last_before, first_after = 0, None, None
        for a, b in zip(ds, ds[1:], strict=False):
            delta = (b - a).days
            if delta > max_delta:
                max_delta, last_before, first_after = (
                    delta,
                    a.date().isoformat(),
                    b.date().isoformat(),
                )
        # trailing gap: whoop's last night to the most recent eight sleep night
        last_whoop = ds[-1].date()
        last_es = datetime.fromisoformat(es_dates[-1]).date()
        trailing = (last_es - last_whoop).days
        if trailing > max_delta:
            gap = {
                "last_worn_before": last_whoop.isoformat(),
                "resumed": None,  # still in the gap / just resuming
                "days": trailing,
                "trailing": True,
            }
        elif max_delta >= 5:
            gap = {
                "last_worn_before": last_before,
                "resumed": first_after,
                "days": max_delta,
                "trailing": False,
            }

    def avg(seq, attr):
        vals = [getattr(n, attr) for n in seq if getattr(n, attr) is not None]
        return round(statistics.mean(vals), 1) if vals else None

    # "baseline" = eight sleep during the stretch WHOOP was last active
    baseline_window = [
        n for n in nights if whoop_dates and n.date <= whoop_dates[-1] and n.es_score is not None
    ]
    # "now" = the most recent 7 eight-sleep nights
    recent = [n for n in nights if n.es_score is not None][-7:]

    return {
        "whoop_active_nights": len(whoop_dates),
        "eightsleep_only_nights": len(es_only),
        "gap": gap,
        "baseline_eightsleep_avg": {
            "sleep_score": avg(baseline_window, "es_score"),
            "hrv": avg(baseline_window, "es_hrv"),
            "hr": avg(baseline_window, "es_hr"),
        },
        "gap_eightsleep_avg": {
            "sleep_score": avg(es_only, "es_score"),
            "hrv": avg(es_only, "es_hrv"),
            "hr": avg(es_only, "es_hr"),
        },
        "recent7_eightsleep_avg": {
            "sleep_score": avg(recent, "es_score"),
            "hrv": avg(recent, "es_hrv"),
            "hr": avg(recent, "es_hr"),
        },
    }
