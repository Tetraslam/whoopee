# eightsleep — Eight Sleep client

A thin wrapper over [`pyeight`](https://github.com/lukas-clarke/pyEight) (the
maintained, unofficial OAuth2 client for Eight Sleep). Eight Sleep has no
official public API; this talks to the same endpoints the mobile app uses.

## Setup

Store your Eight Sleep **app login** (email + password) in 1Password:

```bash
op item create --category Login --title "eight sleep" \
  "username=YOUR_EMAIL" "password=YOUR_PASSWORD"
```

The repo-root `.env.op` points `EIGHT_SLEEP_EMAIL` / `EIGHT_SLEEP_PASSWORD` at it.

## Use

```bash
tools/load-env.sh -- uv run python -m eightsleep.cli nights
```

```python
from eightsleep import EightSleepClient

async with EightSleepClient.from_env() as es:
    for night in await es.recent_nights(days=30):
        print(night.date, night.sleep_score, night.hrv, night.heart_rate)
```

What you can pull (per night, per side): sleep/fitness scores, time slept,
heart rate, HRV, breath rate, bed + room temperature, presence windows. Sleep
*stages* from the cloud API are unreliable — treat scores and biometrics as the
trustworthy fields.

_Built by claude._
