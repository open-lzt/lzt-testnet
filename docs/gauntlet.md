# The Gauntlet — chaos harness for lzt.market plugins

The testnet mock is a *happy-path* server by default. The Gauntlet turns it hostile: it injects the
failures the real market throws at you — 502s, dropped auth, byzantine payloads, "already sold"
races, retry storms — all driven by **one seed**, so a failure is reproducible and CI is
deterministic. It is **OFF by default**; the mock stays clean and the existing test-suite is
unaffected until you arm it.

## Three ways to arm it

**1. Globally, from the CLI / env** — the whole server runs hostile:

```bash
./scripts/run.sh --chaos hostile --seed 42
# or a named scenario:
./scripts/run.sh --scenario nginx-down
# equivalently, via env:
LZT_TESTNET_CHAOS_MODE=hostile LZT_TESTNET_CHAOS_SEED=42 ./scripts/run.sh
```

Intensities: `calm` → `flaky` → `hostile` → `lzt_friday` (progressively nastier).

**2. Per request, from a unit test** — the `X-Chaos` header forces one exact, deterministic fault:

```
X-Chaos: http_502_nginx@*      # a raw nginx 502 on any route
X-Chaos: rate_limited_429@*    # 429 with Retry-After
X-Chaos: account_invalid@buy   # the buy "succeeds" but the account is invalid
X-Chaos: retry_storm@buy       # the first N buys are transient, then converge
```

`kind@endpoint` targets one endpoint (`buy` / `list_lots` / `payments`); `kind` or `kind@*` hits all.
The full fault list is the `FaultKind` enum in `src/lzt_testnet/chaos/faults.py`.

**3. A named scenario** — a weighted fault menu (+ optional stateful world) as YAML in `scenarios/`.
Shipped: `black-friday-meltdown`, `auth-expiry-storm`, `seller-spam-flood`, `nginx-down`,
`pagination-hell`. See `scenarios/README.md` for the schema.

## Reading the scorecard

Every injected fault is recorded. After a run, `app.state.recorder.report().as_scorecard()` prints:

```
Gauntlet scorecard (seed=502)
  injected: 51
  survived: 49
  failed:   2
    seq=17 path=/testnet/stateful/lots/3/buy fault=charge_then_fail — double charge
```

A failed probe carries the exact `seed`, request `seq`, and `fault` — re-run with that seed and the
identical fault fires at the identical point.

## Plugin-author helpers (`tests/helpers/gauntlet.py`)

```python
from tests.helpers.gauntlet import assert_idempotent, assert_blacklists, assert_survives, run_oracle

report = await assert_survives("nginx-down", my_client_script)   # runs the scenario, returns a scorecard
await assert_idempotent(client, buy, item_id=id, token=tok)      # retry_storm → exactly one payment
await assert_blacklists(client)                                  # spam-seller lots fail their check
```

### The differential oracle (eventual correctness)

The killer check: run the **same** client script clean and under chaos; a correct (idempotent)
client reaches the **same business outcome** either way.

```python
assert await run_oracle(my_script, seed=1) is True    # idempotent client converges
```

A non-idempotent client diverges and `run_oracle` returns `False` — that is the oracle catching a
real bug the happy-path tests never would.

## Soak

```bash
./scripts/gauntlet-soak.sh nginx-down 200 502   # scenario, requests, seed → faults/sec baseline
```

## Note — deterministic ids

Lot/payment ids are seed-scoped **per app instance** (they start from `1` for each `create_app()`),
not process-global. This is intentional (reproducible ids per run); a single long-lived server is
unaffected, and every test gets a fresh, deterministic id sequence.
