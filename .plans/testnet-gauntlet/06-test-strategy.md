# 06 — Test strategy (per `/test-architect`)

## Profile: STANDARD, with a CRITICAL lean on determinism + idempotency
The harness handles no real money and no multi-tenant isolation, so it isn't fully Critical. But its
**entire value proposition is reproducibility**, and it models purchase idempotency — so determinism and
the money-ish idempotency probes get Critical-grade coverage (property + invariant tests), the rest is
Standard integration.

## Metric: few, wide, hard tests through the REAL seam
The seam is the **ASGI app** driven by `httpx.AsyncClient + ASGITransport(create_app())` — the exact
existing `client` fixture (`tests/conftest.py:11`), extended by a `chaos_client(scenario=…, seed=…)`
factory. Tests drive real requests end-to-end; they do NOT unit-test enum membership, pydantic validation,
or dataclass getters (the type system already guarantees those). Nothing is mocked — the mock IS the
system; there is no process boundary to stub (no third-party HTTP, no DB, no clock in decisions).

## Required categories (decision tree, filtered by profile)
| Category | Why required here | Where (tasks) |
|---|---|---|
| **Integration** (always) | drive faults through the real ASGI app | T5, T6, T7, T11, T13, T14 |
| **Property / determinism** | same seed → identical fault + data sequence (the core invariant) | T1, T2, T5 (two-run equality), T10 (roster equality) |
| **Invariant + state** | idempotency: exactly one PaymentRecord under retry-storm; charge_then_fail leaves none | T7, T8 |
| **Chaos** | the feature *is* chaos; the differential-oracle is the chaos-resilience check | T14 (oracle), soak (T15) |
| Concurrency | already-sold race — one winner across two concurrent buys | T7 |
| Load / browser-E2E | N/A — soak-fuzz script is the load analog, no UI | T15 (soak only) |

## Red-green proofs (deliberate double-run tasks)
- **T14 oracle** — the non-idempotent-client case MUST FAIL first (oracle returns False → test asserts
  divergence detected), proving the oracle actually detects state divergence rather than always passing.
- All other tasks are single-run acceptance.

## Bug class each test group catches
- `test_seed` / `test_profiles` → non-reproducible runs (the failure that makes the tool useless).
- `test_middleware` / `test_off_no_drift` → the middleware silently changing OFF behaviour (breaks every
  existing consumer) + a wrong fault rendering (502 as JSON instead of nginx HTML).
- `test_domain_faults` / `test_idempotency` → the harness mis-modelling purchase semantics, so software
  "passes" against a wrong oracle (double-charge, orphan payment, phantom winner).
- `test_builder` / `test_blacklist` → non-deterministic world → flaky blacklist tests downstream.
- `test_scenario` / `test_report` / `test_oracle` → a scenario silently not arming, a scorecard
  miscounting, an oracle that always passes.

## Explicitly NOT covered
- Real network latency realism (delay is modelled as poll-count for determinism; real sleep only in the
  soak script) — see R1/Open questions.
- Faithful lzt.market forum response shapes — the world is testnet-invented (00-audit defer, R8).
- The software-under-test itself — the harness provides faults + an oracle; it does not test anyone's plugin.

## Runner
`pytest` (`asyncio_mode="auto"`, pytest-asyncio 0.24, already configured). New tests live under
`tests/chaos/` and `tests/world/`; helpers in `tests/helpers/gauntlet.py`. Per-feature run while
iterating (`pytest tests/chaos/…`); full `uv run pytest` at the RELEASE-READY gate.
