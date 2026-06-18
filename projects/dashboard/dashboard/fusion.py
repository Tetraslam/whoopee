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
    # whoop recovery
    whoop_recovery: float | None = None
    whoop_hrv_ms: float | None = None
    whoop_rhr: float | None = None
    whoop_resp: float | None = None
    whoop_spo2: float | None = None
    whoop_skin_temp: float | None = None
    # whoop sleep
    whoop_sleep_perf: float | None = None
    whoop_sleep_eff: float | None = None
    whoop_sleep_consistency: float | None = None
    whoop_sleep_hours: float | None = None
    whoop_deep_pct: float | None = None
    whoop_rem_pct: float | None = None
    whoop_light_pct: float | None = None
    # whoop strain (the load side — from the cycle ending this day)
    whoop_strain: float | None = None
    whoop_avg_hr: float | None = None
    whoop_max_hr: float | None = None
    # eight sleep
    es_score: int | None = None
    es_hrv: float | None = None
    es_hr: float | None = None
    es_resp: float | None = None
    es_sleep_hours: float | None = None
    es_deep_pct: float | None = None
    es_rem_pct: float | None = None
    es_tnt: int | None = None
    es_sleep_debt: float | None = None
    # derived
    sources: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def _ms_to_hours(milli: float | None) -> float | None:
    return round(milli / 3_600_000, 2) if milli else None


def _pct(part: float | None, whole: float | None) -> float | None:
    if not part or not whole:
        return None
    return round(100 * part / whole, 1)


def build_nights(whoop_recoveries, whoop_sleeps, es_nights, whoop_cycles=None) -> list[FusedNight]:
    """Merge raw records from both sources into per-night fused records."""
    whoop_cycles = whoop_cycles or []
    nights: dict[str, FusedNight] = {}

    def night(d: str) -> FusedNight:
        return nights.setdefault(d, FusedNight(date=d))

    sleep_by_id = {s["id"]: s for s in whoop_sleeps if not s.get("nap")}

    # WHOOP strain: a cycle is a day; key by the date it ends (or starts if open).
    for cyc in whoop_cycles:
        d = _night_date(cyc.get("end") or cyc.get("start"))
        if not d:
            continue
        n = night(d)
        score = cyc.get("score") or {}
        n.whoop_strain = round(score["strain"], 1) if score.get("strain") is not None else None
        n.whoop_avg_hr = score.get("average_heart_rate")
        n.whoop_max_hr = score.get("max_heart_rate")
        if n.whoop_strain is not None and "whoop" not in n.sources:
            n.sources.append("whoop")

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
        n.whoop_spo2 = round(score["spo2_percentage"], 1) if score.get("spo2_percentage") else None
        n.whoop_skin_temp = (
            round(score["skin_temp_celsius"], 1) if score.get("skin_temp_celsius") else None
        )
        sleep = sleep_by_id.get(rec.get("sleep_id"))
        if sleep:
            ss = sleep.get("score") or {}
            n.whoop_resp = round(ss["respiratory_rate"], 1) if ss.get("respiratory_rate") else None
            n.whoop_sleep_perf = ss.get("sleep_performance_percentage")
            n.whoop_sleep_eff = (
                round(ss["sleep_efficiency_percentage"], 1)
                if ss.get("sleep_efficiency_percentage")
                else None
            )
            n.whoop_sleep_consistency = ss.get("sleep_consistency_percentage")
            stage = ss.get("stage_summary") or {}
            in_bed = stage.get("total_in_bed_time_milli")
            awake = stage.get("total_awake_time_milli") or 0
            asleep = (in_bed - awake) if in_bed else None
            if asleep:
                n.whoop_sleep_hours = _ms_to_hours(asleep)
                n.whoop_deep_pct = _pct(stage.get("total_slow_wave_sleep_time_milli"), asleep)
                n.whoop_rem_pct = _pct(stage.get("total_rem_sleep_time_milli"), asleep)
                n.whoop_light_pct = _pct(stage.get("total_light_sleep_time_milli"), asleep)
        if "whoop" not in n.sources:
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
        es_total = es.sleep_duration
        n.es_sleep_hours = round(es_total / 3600, 2) if es_total else None
        n.es_deep_pct = _pct(es.deep_duration, es_total)
        n.es_rem_pct = _pct(es.rem_duration, es_total)
        n.es_tnt = es.tnt
        n.es_sleep_debt = round(es.sleep_debt / 3600, 2) if es.sleep_debt else None
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


# --- driver analysis: what actually predicts your sleep & recovery -----------

# Each driver: (attr on the night, human label, whether higher is intuitively
# "more" of the thing). We correlate the driver on night N against the OUTCOME
# on night N (same-night inputs like sleep architecture) — sleep score is an
# outcome of that night's sleep. For recovery we also support next-morning.
_SLEEP_DRIVERS = [
    ("es_sleep_hours", "sleep duration"),
    ("es_deep_pct", "deep sleep %"),
    ("es_rem_pct", "REM sleep %"),
    ("es_tnt", "tossing & turning"),
    ("es_sleep_debt", "sleep debt"),
    ("es_resp", "respiratory rate"),
]


def _series(nights, attr):
    return [getattr(n, attr) for n in nights]


def driver_report(nights: list[FusedNight]) -> dict:
    """Rank what moves your Eight Sleep sleep score and your HRV.

    Uses every night Eight Sleep recorded (the long history), correlating each
    candidate driver against the outcome. Returns drivers sorted by |r|, with
    sign, so the UI can say "deep sleep % is your strongest lever (+0.62)".
    """
    have = [n for n in nights if n.es_score is not None]

    def rank_against(outcome_attr, drivers):
        out = _series(have, outcome_attr)
        ranked = []
        for attr, label in drivers:
            r = _pearson(_series(have, attr), out)
            if r is not None:
                ranked.append({"key": attr, "label": label, "r": r})
        ranked.sort(key=lambda d: abs(d["r"]), reverse=True)
        return ranked

    # HRV as outcome: drop hrv itself from drivers
    hrv_drivers = [(a, lbl) for a, lbl in _SLEEP_DRIVERS if a != "es_resp"]

    return {
        "n": len(have),
        "sleep_score_drivers": rank_against("es_score", _SLEEP_DRIVERS),
        "hrv_drivers": rank_against("es_hrv", hrv_drivers),
    }


# --- rolling baselines & today snapshot --------------------------------------


def _rolling_mean(nights, attr, window):
    vals = [getattr(n, attr) for n in nights[-window:] if getattr(n, attr) is not None]
    return round(statistics.mean(vals), 1) if vals else None


def today_report(nights: list[FusedNight]) -> dict:
    """The most recent night vs your rolling baselines (7d, 30d).

    For each headline metric, returns the latest value, the 7- and 30-day means,
    and a z-score of the latest against the 30-day window so the UI can flag
    "today is unusually low/high for you".
    """
    have = [n for n in nights if n.es_score is not None]
    if not have:
        return {}
    latest = have[-1]

    def metric(attr, higher_good=True):
        latest_v = getattr(latest, attr)
        window = [getattr(n, attr) for n in have[-30:] if getattr(n, attr) is not None]
        z = None
        if latest_v is not None and len(window) >= 3:
            mu = statistics.mean(window)
            sd = statistics.pstdev(window) or 1.0
            z = round((latest_v - mu) / sd, 2)
        return {
            "latest": latest_v,
            "avg7": _rolling_mean(have, attr, 7),
            "avg30": _rolling_mean(have, attr, 30),
            "z": z,
            "higher_good": higher_good,
        }

    return {
        "date": latest.date,
        "metrics": {
            "sleep_score": metric("es_score"),
            "hrv": metric("es_hrv"),
            "resting_hr": metric("es_hr", higher_good=False),
            "respiratory": metric("es_resp", higher_good=False),
            "sleep_hours": metric("es_sleep_hours"),
            "deep_pct": metric("es_deep_pct"),
            "rem_pct": metric("es_rem_pct"),
            "sleep_debt": metric("es_sleep_debt", higher_good=False),
        },
    }
