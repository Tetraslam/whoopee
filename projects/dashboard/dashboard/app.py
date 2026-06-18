"""Flask app: serves the fused dashboard JSON + the static frontend.

    tools/load-env.sh --dir projects/dashboard -- uv run python -m dashboard.app
    # then open http://localhost:8787

Endpoints:
    GET /              -> the dashboard SPA
    GET /api/summary   -> fused nights + trust + comeback (cached)
    GET /api/summary?refresh=1 -> force a re-pull
"""

from __future__ import annotations

from pathlib import Path

from eightsleep import Night
from flask import Flask, jsonify, request, send_from_directory

from . import data
from .fusion import build_nights, comeback_report, trust_report

STATIC = Path(__file__).resolve().parent.parent / "static"

app = Flask(__name__, static_folder=None)


@app.get("/")
def index():
    return send_from_directory(STATIC, "index.html")


@app.get("/<path:path>")
def static_files(path: str):
    return send_from_directory(STATIC, path)


@app.get("/api/summary")
def summary():
    refresh = request.args.get("refresh") in ("1", "true", "yes")
    raw = data.load(refresh=refresh)
    es_nights = [Night.from_dict(d) for d in raw["eightsleep_nights"]]
    nights = build_nights(raw["whoop_recoveries"], raw["whoop_sleeps"], es_nights)
    return jsonify(
        {
            "pulled_at": raw["pulled_at"],
            "nights": [n.to_dict() for n in nights],
            "trust": trust_report(nights),
            "comeback": comeback_report(nights),
        }
    )


def main() -> None:
    app.run(host="127.0.0.1", port=8787, debug=True)


if __name__ == "__main__":
    main()
