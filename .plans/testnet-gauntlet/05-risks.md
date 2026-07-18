# 05 — Risks & edge cases

## R1 — Determinism leaks (the whole feature depends on this) — HIGH
Any un-seeded randomness or wall-clock in a fault decision breaks reproducibility.
- Mitigation: `FaultPlanner.decide` may read randomness ONLY from `ctx.rng` (a `SeedController.stream(seq)`
  child). No `random.*` module calls, no `datetime.now()` in decisions. TD-2 module-global id counters
  removed (T7). Guard: T5 asserts identical sequence over two runs; a lint grep in CI bans bare
  `random.`/`time.time()`/`datetime.now(` inside `chaos/`.
- Edge: `SLOW`/`DELAYED_SETTLEMENT` need a *simulated* delay counter, not real sleep, or determinism +
  test speed both suffer — model delay as "N polls until settled", not seconds, in tests.

## R2 — Middleware breaks the OFF fast-path — HIGH (success criterion #1)
If the middleware touches responses even when OFF, existing behaviour drifts.
- Mitigation: first line of `__call__` returns `await self.app(...)` untouched when `chaos_mode==OFF`
  and no `X-Chaos` header. T6 is the regression gate (full existing suite + identical-body assertion).

## R3 — Pure-ASGI vs BaseHTTPMiddleware for connection-level faults — MEDIUM (W3.5-confirmed)
`CONNECTION_DROP`/`TIMEOUT`/`TRUNCATED_BODY`/byzantine-rewrite cannot be done from Starlette
`BaseHTTPMiddleware` — its `_StreamingResponse` always sends a terminal `more_body:False`, so it cannot
forge a Content-Length/body-length mismatch. Pure-ASGI wrapping the real `send` can. **W3.5 verified
against starlette 1.3.1 + httpx 0.28.1:**
- (a) byzantine rewrite/truncate → pure-ASGI required; correct.
- (b) `connection_drop` mechanism is **RAISE after `http.response.start`**, NOT stopping mid-body
  (stopping trips `ASGITransport`'s `assert response_complete.is_set()`). The test client
  (`chaos_client`) must use `httpx.ASGITransport(app, raise_app_exceptions=False)` → the transport
  swallows the raise and returns a genuinely truncated/empty `Response`. A real socket-level abort is
  **not reliably testable** via ASGITransport — this raise-based truncation IS the mechanism, not a fallback.
- (c) `timeout`: ASGITransport enforces no wall-clock; a real `asyncio.sleep` is never auto-aborted by
  httpx here. So delay MUST be modelled as an N-poll counter (see R1), and any timeout assertion wraps
  the call in `asyncio.wait_for`/`anyio.fail_after` in the test — confirmed necessary, not optional.

## R4 — polyfactory seeding API unknown — MEDIUM (D4, W3.5)
`SeedController.seed_generation()` must actually seed polyfactory. If `ModelFactory.seed_random` isn't the
right call, generated data won't be reproducible.
- Mitigation: W3.5 confirms the exact polyfactory ≥2.18 seeding entrypoint; T1 acceptance includes a
  generation-reproducibility assertion (build the same model twice under one seed → equal).

## R5 — X-Chaos arming semantics (reconciled with the OFF fast-path) — LOW
`X-Chaos` is **explicit per-request arming** and is honoured regardless of `chaos_mode` — that is the
deterministic knob unit tests rely on. The OFF default disables only the **global profile roll**, so a
hostile response can never appear without EITHER an explicit `X-Chaos` header OR an explicit non-OFF
mode. (Resolves the W3 contradiction: the middleware fast-path returns early only when `chaos_mode==OFF`
AND no `X-Chaos` header — so a present `X-Chaos` is always processed, by design.) This is a test tool,
not a real security boundary; documented in docs/gauntlet.md.

## R6 — Forum/world routes colliding with catch-all `/{path:path}` — MEDIUM
The catch-all matches everything; forum routers must be registered BEFORE the catch-all or they never hit.
- Mitigation: T11 registers forum routers ahead of `catch_all_router` in `create_app` (order already
  matters there — control/stateful precede catch-all today). Test asserts a forum path is not swallowed.

## R7 — Scenario YAML as an injection/DoS vector — LOW
`load_scenario` reads yaml.
- Mitigation: `yaml.safe_load` only; validate against `ScenarioSpec` (rejects unknown FaultKind, bad
  weights); scenarios are repo-committed data reviewed by PR (D8), not user-uploaded at runtime.

## R8 — Scope creep into a real world simulation — MEDIUM
The forum/world could balloon.
- Mitigation: world is testnet-invented (like the existing stateful routes), minimal fields (03-types
  WorldConfig), armed only under a scenario/world flag; not a faithful lzt.market forum mirror (00-audit defer).

## Open questions (answered by defaults, user may override)
- Delay model = simulated poll-count, not seconds (R1). `unverified` — user may want real latency for
  soak realism; if so, gate real sleep behind the soak script only, keep tests on poll-count.
- `X-Chaos` honoured only when armed (R5) vs always — chose armed-only for safety.
