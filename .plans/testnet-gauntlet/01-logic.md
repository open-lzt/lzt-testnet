# 01 — Logic

## Request lifecycle with chaos armed

```
request → FaultInjectionMiddleware.dispatch
            │  (no-op fast-path if chaos_mode==OFF and no X-Chaos header)
            ├─ resolve arming: X-Chaos header (deterministic) OR global profile (seeded roll)
            ├─ FaultPlanner.decide(FaultContext) → Fault | None
            │      seq = per-app monotonic request ordinal; rng = SeedController.stream(seq)
            ├─ PRE-response faults (short-circuit, never reach the handler):
            │      http_50x / 429 / auth_drop_401 / unknown_error_code / connection_drop / timeout
            ├─ else call_next(request) → real mock response
            └─ POST-response faults (mutate the real response):
                   slow (delay) / byzantine_* (rewrite JSON body) / malformed_json / truncated_body / http_502_nginx
```

- **Transport + byzantine faults live in the middleware** — the one choke point over every response
  (catch-all `model_dump` at `catch_all.py:82`, stateful dicts, and exception `JSONResponse`es all pass
  through it). D5.
- **Domain faults (L2) live in the stateful handlers** — they need store state (was_bought, payment
  ledger), so they inject via the same registry but from inside `fast_buy`/`payments`, not the middleware.

## Determinism model (the spine)

`SeedController(seed)` is created once in `create_app()` and put on `app.state.seed`. It owns:
- `root = random.Random(seed)`.
- `stream(seq) -> random.Random` — a child RNG derived as `random.Random((seed, seq))` so fault
  decisions for request `seq` are independent of how many requests came before (replay a single request
  by its seq without replaying the whole run).
- `seed_generation()` — seeds polyfactory ONCE so `FakeGenerator` output is reproducible (D4/D10).
- `next_id(kind)` — replaces the module-global `itertools.count` (TD-2/D6): seed-scoped, per-app id
  allocator for lots/payments/sellers/threads so id sequences are a function of seed, not process history.

`FaultPlanner.decide(ctx)` is pure given `(profile, ctx.rng)` — same seed+seq+profile → same Fault.
No wall-clock, no global random.

## Arming precedence
1. `X-Chaos: <fault>[@<endpoint>]` header present → force exactly that fault on this request
   (deterministic, no roll). This is the unit-test knob and the back-compat path.
2. Else `X-Testnet-Force-Error: <name>` present → map legacy name → FaultKind → force it (D3, unifies
   the two duplicated `_FORCE_ERROR_MAP`s).
3. Else global `chaos_mode != OFF` → `FaultPlanner` rolls `ctx.rng` against the active `ChaosProfile`
   weights (optionally per-endpoint filtered).
4. Else → no fault, clean response.

## Profiles (L1) → data later (L4)
`ChaosProfile` = `{FaultKind: weight}` + optional per-endpoint overrides + a base "no-fault" probability.
Four built-ins (`calm/flaky/hostile/lzt_friday`) start as code (`profiles.py`), and L4 lets a
`ScenarioSpec` supply/override the weight map from YAML — profiles stop being hardcoded.

## L2 domain faults — where they hook
Inside `fast_buy` (`stateful.py:193`) and `payments`, after `_raise_forced_error` is replaced by the
unified `chaos.domain.maybe_inject(ctx, store_view)`:
- `account_invalid`: buy "succeeds" (lot deleted, marked bought) but returns an invalid-account payload
  → tests the software's post-buy validation.
- `already_sold`: two concurrent buys of one lot — the second deterministically loses with NotFound
  (already the real behaviour via `was_bought`; the fault forces the race window in a test).
- `retry_storm`: first `N` attempts (seed-counted per item) raise a transient error, then succeed —
  the payment ledger must show exactly ONE charge (idempotency probe).
- `charge_then_fail`: append the payment, then raise — the harness asserts the software reconciles
  (no orphan charge on the software's side); the mock exposes the orphan so the oracle can see it.
- `delayed_settlement`: buy returns `pending`; a later `payments` poll flips it to settled after the
  seeded delay count.

## L3 world — persistence & bad sellers (lazy materialization, D11)
`WorldBuilder(seed)` eagerly builds only the SMALL `SellerStore` roster (`GOOD`/`SPAM`) + forum, at app
start when a world is armed. **Lots are lazy:** a `Materializer` generates+persists a lot the first time
its list page is fetched (query-keyed stable id `stable_id(category, index)` from a
`Random(f"{seed}:{category}:{index}")` stream — NOT `next_id`, so refetch is byte-stable), then serves the
persisted mutable record. Buy mutates the existing `LotStore`/`ScenarioStore`, so the exact id the client
saw in the list is buyable and drops from the next fetch. Seller quality is a seeded function of the id →
spam-seller lots deterministically fail the check endpoint (blacklist signal), computed on the fly.
Listing is spam-dominated by the roster ratio. Infinite streaming = the cursor just keeps advancing the
index; pages materialize on demand, never pre-generated. Forum users/threads/posts are consistent per seed.

## L4 scenarios, report, oracle
- `ScenarioSpec` (yaml) = seed + intensity/profile weights + world config + endpoint targeting + oracle
  flag. `load_scenario(name)` reads `scenarios/<name>.yaml`, validates, returns the spec.
- The middleware + planner + world all read their config from the active spec when a scenario is armed.
- `GauntletRecorder` (on `app.state`) logs every injected fault `(seq, path, FaultKind, seed)`; at run
  end `GauntletReport` = injected / survived / failed(with the exact fault+request+seed).
- Differential-oracle (test helper): run the same client script twice — `off` vs the scenario — and
  assert the terminal store state matches (eventual correctness). A non-idempotent client diverges.
