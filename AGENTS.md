# AGENTS.md — whoopee

Hi, claude (or whoever). This is **whoopee** — where tetraslam messes with his
WHOOP. Pull data, build dashboards, run analyses, whatever sounds fun. Same
spirit as the `playground` monorepo next door: move fast, make stuff, keep it
runnable.

## Layout

```
whoopee/
├── lib/
│   ├── py/whoop/    # Python WHOOP v2 client (OAuth2 + data pulls)
│   └── ts/whoop/    # TS mirror of the same client
├── projects/        # the actual experiments — one dir per thing (py OR ts)
├── tools/           # repo tooling (load-env.sh)
├── pyproject.toml   # uv workspace (members: lib/py/*, plus projects you add)
├── pnpm-workspace.yaml
├── .env.op          # op:// secret references (committed, safe)
└── .envrc           # optional direnv: activates .venv
```

## Starting a new project

- **Python:** `mkdir projects/mything`, add a `pyproject.toml` with
  `[project] name = "mything"` and `dependencies = ["whoop"]` (plus
  `[tool.uv.sources] whoop = { workspace = true }`), then add the path to
  `members` in the root `pyproject.toml` and run `uv sync`. Run with
  `uv run python projects/mything/main.py`.
- **TypeScript:** `mkdir projects/mything`, add a `package.json` — the
  `projects/*` glob in `pnpm-workspace.yaml` picks it up — then `pnpm install`.
  Depend on the client with `"@whoopee/whoop": "workspace:*"`.

## Dependencies — use the package manager, never hand-edit

```bash
uv add <pkg>     # Python — NOT editing [project.dependencies]
pnpm add <pkg>   # TS/JS  — NOT editing "dependencies" in package.json
```

This keeps manifest + lockfile in sync and runs real resolution. After adding,
the lockfile is updated automatically (`uv add` / `pnpm add` do this). If you
ever touch a manifest's deps by hand, re-run `uv sync` / `pnpm install`.

## Running Python

**Always `uv run`, never bare `python`/`python3`.** uv manages the interpreter
and the env. For repo tooling with no project deps: `uv run --no-project x.py`.

## Secrets — the op:// pattern

Never commit plaintext secrets. `.env.op` holds only 1Password references and is
committed; resolve them at runtime:

```bash
tools/load-env.sh -- uv run python -m whoop.cli profile
tools/load-env.sh --dir projects/foo -- pnpm --filter foo dev   # layer a project's own .env.op
```

WHOOP needs `WHOOP_CLIENT_ID` + `WHOOP_CLIENT_SECRET` (register an app at
<https://developer.whoop.com>). Store them once:

```bash
op item create --category "API Credential" --title whoop \
  "client id[text]=YOUR_CLIENT_ID" "client secret[password]=YOUR_SECRET"
```

The repo-root `.env.op` already points at `op://Personal/whoop/...`. Resolved
OAuth tokens live at `~/.whoop-token.json` (gitignored) — never commit them.

## The WHOOP client

The shared client (`lib/py/whoop`, mirrored in `lib/ts/whoop`) handles the OAuth
lifecycle and the v2 endpoints (recovery, sleep, cycles, workouts, profile,
body). First-time auth is easiest from Python:

```bash
tools/load-env.sh -- uv run python -m whoop.cli auth      # browser consent, once
tools/load-env.sh -- uv run python -m whoop.cli profile
```

See `lib/py/whoop/README.md` for the full API. The redirect URL must be
registered in the WHOOP dashboard as exactly `http://localhost:8765/callback`.

## House style

- Python: ruff (`ruff check`, `ruff format`). Config in `pyproject.toml`.
- TS/JS: oxlint + prettier; `tsc --noEmit` to typecheck.
- Commits: short, present-tense, lowercase is fine.
- Sign a project with `_Built by <name>._` at the bottom of its README.
- Aim higher than a screenshot — a system that runs over time, an analysis that
  surprises you, a live dashboard beats a static plot.
