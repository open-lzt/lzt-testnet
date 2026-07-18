# testnet Gauntlet — Overview

**Tier:** module · **Planning mode:** layered · **Parallelization:** solo
**Repo:** `projects/testnet` (published as `open-lzt/lzt-testnet`)

## Goal

Turn the testnet mock from an honest happy-path stub into a **deterministic chaos / fault-injection
harness** that validates third-party software (plugins, bots, tooling) against the failure modes the
real lzt.market exhibits — HTTP faults, lying payloads, auth drops, purchase failures, spam sellers,
a stateful forum world — so a user's software "does not break even where lolz breaks".

## Non-negotiable foundation

**Determinism by seed.** A `chaos_seed` fixes the entire fault + data sequence: same seed → same
faults injected on the same request ordinals, same generated accounts/sellers/threads. Without this
the harness is undebuggable and useless in CI. Everything else is built on the seed engine.

## Scope — four layers, built in dependency order (one coherent plan)

Layered mode: the four layers are the build sequence inside ONE plan (`04-tasks.yaml` orders them
L1→L4 with a `RELEASE-READY` pseudo-task at the end). **Every task carries its own tests in its
acceptance** — no layer is "done" until its tests are green.

- **L1 — Seed engine + transport faults.** Deterministic `SeedController` + `FaultPlanner` +
  `FaultInjectionMiddleware`; HTTP faults (500/502-nginx/503/504/429), auth-drop, latency/timeout,
  byzantine 200-lies, malformed/truncated/connection-drop. OFF by default. Global arming (env/CLI) +
  per-request `X-Chaos` header, unifying the existing `X-Testnet-Force-Error`. Profiles calm→lzt_friday.
- **L2 — Domain purchase/check faults.** account-invalid-after-buy, already-sold race, retry-storm,
  charge-then-fail, delayed settlement, bad-lot check error — injected into the stateful buy/payment flow.
- **L3 — Stateful world.** Persistent seeded seller roster (incl. low-quality spam sellers whose lots
  fail on check), forum entities (users/threads/posts) + endpoints, streaming/infinite account lists,
  price/lot dynamics, seeded edge-data generation.
- **L4 — Scenarios + report + differential-oracle.** YAML scenario catalog + schema, named presets,
  Gauntlet scorecard, differential-oracle harness, pytest helpers, CLI polish, docs, CI. Closes every
  earlier-layer hardcode (profiles/counts/roster become scenario-overridable).

## Non-goals

- Not a load-testing tool (soak-fuzz mode is the analog, L4). No separate `lzt-gauntlet` repo yet —
  scenarios ship as **data** inside testnet; fork later like `lzt-flows` only if the catalog grows.
- Not changing the real lzt.market API surface the mock already emulates.
- No sandboxing/security of the software under test — this is a fault source, not a runner.

## Success criteria (verifiable — W3 goal-verifier checks these)

1. With `LZT_TESTNET_CHAOS_MODE=off` (default) every existing test passes unchanged — zero behaviour drift.
2. Two runs with the same `chaos_seed` inject the identical fault sequence (byte-identical scorecard).
3. `X-Chaos: http_502_nginx` on any request yields a raw nginx-style 502 HTML body, not JSON.
4. `X-Testnet-Force-Error: rate_limited` still works (back-compat) — routed through the unified registry.
5. A bad-seller's lot deterministically fails validation; a good-seller's lot deterministically passes.
6. `assert_survives("seller-spam-flood")` runs a scenario and returns a `GauntletReport` scorecard.
7. Differential-oracle: a purchase flow reaches the same terminal store state under `off` and under a
   retry-storm profile (eventual correctness), for software that retries idempotently.

## Release-ready exit criteria (the `RELEASE-READY` pseudo-task in `04-tasks.yaml`)

- All four layers' capability works end-to-end via `X-Chaos` / env / scenario YAML; every task's tests green.
- Every earlier-layer hardcode closed (profiles/retry-count/roster now scenario-overridable).
- **Soak-fuzz run** (the load-test analog): `scripts/gauntlet-soak.sh` runs a seeded infinite-stream +
  hostile-profile run for N minutes, reports faults/sec + zero harness crashes. Baseline documented.
- Scripts: `scripts/run.sh` gains chaos flags; `scripts/gauntlet-soak.sh` added; both idempotent.
  (No `backup/restore` — the harness is stateless, in-memory, non-data-bearing; see D9.)
- Observability floor: structured chaos log (every injected fault + seq + seed) + the scorecard.
- Security floor: chaos OFF by default; arming requires explicit env/header — no accidental hostile prod.
- Docs floor: `docs/gauntlet.md` (clone→run a scenario) + `scenarios/README` (contributor schema) +
  `.env.example` updated with `LZT_TESTNET_CHAOS_*`.
- CI: a `.github/workflows/` that runs `pytest` incl. a seeded chaos smoke (new — none exists today).

## Worktree

Implementation runs in `../lzt-testnet-testnet-gauntlet` on branch `feat/testnet-gauntlet` off the
testnet default branch (`main`). The executor creates it; this plan does not.

## Files (this plan)

- `00-overview.md` (this) · `00-decisions.md` · `00-audit.md` · `00-improvements.md`
- `01-logic.md` · `02-files.md` · `03-types.md` (frozen contracts) · `04-tasks.yaml` (DAG)
- `05-risks.md` · `06-test-strategy.md` · `06-review.md` (W3) · `07-verification.md` (W3.5)
