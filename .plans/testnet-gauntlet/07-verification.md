# 07 — Code-grounded verification (W3.5)

Two Sonnet audits reconciled the plan's `verified-by-code` claims against real testnet source + the
installed libraries. **Verdict: all claims CONFIRMED; zero 🔴 blockers; 2 external-API facts pinned
down (were `unverified`).**

## Audit A — testnet source claims (7/7 CONFIRMED)
| Claim | Result | Cite |
|---|---|---|
| errors.py has RateLimited(retry_after)/AuthFailed(token_id)/TransportError(status)/PaymentFailed()/NotFound(item_id)/BadRequest(field) | CONFIRMED | `errors.py:17,23,33,43,53,63` |
| ScenarioError/UnknownFaultError absent (plan adds them) | CONFIRMED absent | — |
| `_FORCE_ERROR_MAP` duplicated in catch_all + stateful; stateful adds not_found | CONFIRMED (TD-1) | `catch_all.py:16`, `stateful.py:36,44` |
| create_app registers control→stateful→catch_all (catch-all last); forum router + middleware insertable before it | CONFIRMED | `app.py:42-44` |
| `_item_id_counter`/`_operation_id_counter` module-global itertools.count (TD-2) | CONFIRMED | `stateful.py:33-34` |
| Settings(BaseSettings) env_prefix LZT_TESTNET_, trivially extensible | CONFIRMED | `config.py:10-17` |
| app.state wiring (route_table/fake_generator/lot_store/payment_store/scenario_store/settings) | CONFIRMED | `app.py:30-35` |
| conftest client = AsyncClient+ASGITransport(create_app()), fresh per test, asyncio_mode=auto | CONFIRMED | `conftest.py:13-24`, `pyproject.toml:47` |

→ No plan edits needed; every `verified-by-code` tag on backend contracts holds.

## Audit B — external-library feasibility (both CONFIRMED, mechanisms pinned)
**polyfactory seeding (D4/R4, was `unverified`):** exact call `ModelFactory.seed_random(seed)` —
`BaseFactory` classmethod (`polyfactory/factories/base.py:495-503`), sets `__random__=Random(seed)` +
`__faker__.seed_instance(seed)`. Seed once before first `.build()`; `create_factory()` subclasses inherit
the seeded RNG via MRO (order-independent). Caveat folded into D4: `__random__`/`__faker__` are
process-wide shared → reproducibility needs stable build ORDER (plan guarantees it). → D4 retagged
`verified-by-code:polyfactory/factories/base.py:495`.

**pure-ASGI faults (R3, was a design assertion):** verified vs starlette 1.3.1 + httpx 0.28.1.
(a) byzantine/truncate → pure-ASGI required (BaseHTTPMiddleware can't forge length mismatch).
(b) connection_drop → RAISE after `response.start` (stopping trips ASGITransport's `assert
response_complete`); test client uses `ASGITransport(app, raise_app_exceptions=False)` → truncated
Response. A real socket abort is NOT testable via ASGITransport — the raise IS the mechanism.
(c) timeout → ASGITransport enforces none; delay = N-poll counter + `asyncio.wait_for` in tests.
→ Folded into R3 + 03-types (`chaos_client` uses `raise_app_exceptions=False`; `SeedController.seed_generation`
names the exact call).

## Net result
- 0 🔴 blockers; 0 🟡 corrections to backend contracts.
- 2 `unverified` decisions upgraded to `verified-by-code` (D4, and R3's mechanism pinned).
- Remaining `unverified` after W3.5: D9 (release-ready floor adaptation — judgment call, user may override)
  and the R5/R1 open-question defaults (documented, non-blocking).

## Build outcome (all 16 tasks shipped + tested)
- **L1** (T1-T4): seed engine, fault taxonomy, profiles, planner, render — 24 tests.
- **L2** (T5-T8): pure-ASGI `FaultInjectionMiddleware`, domain faults, seed-scoped ids (TD-2 closed),
  legacy `X-Testnet-Force-Error` unified into one `chaos/legacy.py` (TD-1 closed), idempotency probe.
- **L3** (T9-T11): world models/stores, `WorldBuilder`, lazy `Materializer` (D11 — query-keyed stable
  ids, materialize-on-fetch, byte-stable refetch), forum endpoints, blacklist.
- **L4** (T12-T16): `ScenarioSpec` + 5 shipped YAML scenarios, `GauntletRecorder`/scorecard,
  differential-oracle (RED-GREEN: naive client → `run_oracle` False), CLI + soak, docs + CI.
- **Gates**: ruff clean, `mypy --strict src` clean (38 files), full suite green. OFF = zero drift
  (existing 17-file suite unchanged, confirmed by a full run with the middleware installed).
- **Fixes found by the tests**: tuple-seed `Random` bug; planner type reassignment; a create_app
  contract change caught by 3 bare-app tests (fixed by graceful `_seed`/`_domain_outcome` fallback,
  no test edits); an env-leak in `test_cli` poisoning the `get_settings` cache (teardown + cache_clear).
