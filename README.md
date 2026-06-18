# whoopee

tetraslam messes with his WHOOP here — data pulls, dashboards, analyses,
whatever sounds fun. A small multi-language monorepo: one lockfile per language
at the root, a shared WHOOP client in `lib/`, experiments in `projects/`.

```
whoopee/
├── lib/py/whoop/    # Python WHOOP v2 client (OAuth2 + paginated data pulls)
├── lib/py/eightsleep/  # Eight Sleep client (vendored OAuth2 pyeight)
├── lib/ts/whoop/    # TypeScript mirror of the WHOOP client
├── projects/        # experiments — one dir per thing
│   └── dashboard/   # WHOOP × Eight Sleep fused dashboard
├── tools/           # load-env.sh (secrets), serve.sh (daemons)
├── pyproject.toml   # uv workspace
├── pnpm-workspace.yaml
└── .env.op          # op:// secret refs (committed, safe)
```

## First-time setup

1. Register an app at <https://developer.whoop.com>, redirect URL exactly
   `http://localhost:8765/callback`.
2. Stash the credentials in 1Password:

   ```bash
   op item create --category "API Credential" --title whoop \
     "client id[text]=YOUR_CLIENT_ID" "client secret[password]=YOUR_SECRET"
   ```

3. Sync both toolchains:

   ```bash
   uv sync
   pnpm install
   ```

4. Authorize once (opens a browser):

   ```bash
   tools/load-env.sh -- uv run python -m whoop.cli auth
   tools/load-env.sh -- uv run python -m whoop.cli profile
   ```

## Building something

See [AGENTS.md](./AGENTS.md) for conventions. The short version:

```python
from whoop import WhoopClient

with WhoopClient.from_env() as client:
    for rec in client.recovery_all():
        print(rec["created_at"], rec["score"]["recovery_score"])
```

Add a new experiment under `projects/`, depend on `whoop` (py) or
`@whoopee/whoop` (ts), and go.

## The fused dashboard

The first real project: WHOOP and Eight Sleep, lined up night by night. Two
independent sensors on the same sleep — they agree ~0.97 on HRV/HR/respiratory,
and Eight Sleep silently covers any stretch you stop wearing WHOOP.

```bash
tools/serve.sh start dashboard   # http://127.0.0.1:8787
```

See [projects/dashboard/README.md](./projects/dashboard/README.md).

_Built by claude._
