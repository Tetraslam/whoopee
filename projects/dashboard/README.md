# dashboard — WHOOP × Eight Sleep, fused

The instrument panel neither app gives you: two independent sensors (WHOOP wrist
strap, Eight Sleep mattress) measuring the same sleep, lined up night by night.

![dashboard](./examples/dashboard.png)

## What it shows

A calm morning read, top to bottom in order of what matters:

- **Readiness** — one 0–100 number for last night, scored against *your own*
  30-day baseline (50 = typical for you), with a plain-language headline naming
  the biggest factor and component meters showing where each vital fell vs your
  norm. Built from HRV, resting HR, deep/REM %, and sleep duration.
- **Recovery, week over week** — HRV from both sensors, z-scored; hover any night.
- **Back on the wrist** — then → now across the WHOOP gap (Eight Sleep covered it).
- **What moves your numbers** — drivers ranked by correlation with sleep score / HRV.
- **Two sensors checked against each other** — quiet cross-device agreement line.
- **Every night** — the full log (collapsed).

## Run it

```bash
# from the repo root — starts a persistent background server
tools/serve.sh start dashboard
# open http://127.0.0.1:8787
tools/serve.sh logs dashboard     # tail logs
tools/serve.sh stop dashboard
```

The server caches both pulls to `.cache/data.json` (gitignored — it's your
biometric data) for 30 min. The page **polls every 10s** and updates values in
place (no layout movement); hit **re-pull** or `?refresh=1` to force a fresh pull
past the cache.

## How it fits together

- `dashboard/data.py` — pulls WHOOP + Eight Sleep, caches to disk.
- `dashboard/fusion.py` — aligns records into per-night `FusedNight`s (keyed by
  local SF date), computes the trust and comeback reports.
- `dashboard/app.py` — Flask: serves `/api/summary` (JSON) and the static SPA.
- `static/index.html` — self-contained frontend (vanilla JS + canvas, no build).

_Built by claude._
