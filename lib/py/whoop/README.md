# whoop — WHOOP v2 API client

A small Python client for the [WHOOP v2 API](https://developer.whoop.com/api):
OAuth2 (authorization-code + refresh), on-disk token persistence, and paginated
data pulls for recovery, sleep, cycles, workouts, profile, and body.

## Setup (one time)

1. Register an app at <https://developer.whoop.com> and set its **Redirect URL**
   to exactly `http://localhost:8765/callback`.
2. Store the credentials in 1Password so `tools/load-env.sh` can resolve them:

   ```bash
   op item create --category "API Credential" --title whoop \
     "client id[text]=YOUR_CLIENT_ID" "client secret[password]=YOUR_SECRET"
   ```

   (The refs in the repo-root `.env.op` already point at `op://Personal/whoop/...`.)

## Authorize + smoke test

From the repo root, with secrets injected:

```bash
tools/load-env.sh -- uv run python -m whoop.cli auth      # opens browser once
tools/load-env.sh -- uv run python -m whoop.cli profile   # prints your profile
```

The token is cached at `~/.whoop-token.json` (gitignored), refreshed
automatically, and rotated on every refresh per WHOOP's spec.

## Use it in code

```python
from whoop import WhoopClient

with WhoopClient.from_env() as client:
    # client.authorize()  # only needed the first time / after revoke
    print(client.profile())
    for rec in client.recovery_all(limit=25):
        score = rec["score"]["recovery_score"]
        print(rec["created_at"], score)
```

Collection helpers (`recovery_all`, `sleep_all`, `cycles_all`, `workouts_all`)
follow `next_token` pagination and yield every record. They accept `limit`,
`start`, and `end` (ISO-8601) kwargs.

_Built by claude._
