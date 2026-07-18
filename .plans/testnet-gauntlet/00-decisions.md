# Decisions — testnet Gauntlet

Each tagged: `verified-by-code:<file>:<line>` (read the source this run) / `verified-by-doc` /
`decided-by-user` / `unverified`. The user overrides any line.

## D1 — Layered mode, module tier
User explicitly chose **layered** ("layered."). The four layers L1→L4 are the build order inside one
plan (`04-tasks.yaml` DAG), each task carrying its own tests ("каждый шаг покрыт тестами"). New
multi-layer subsystem (~1.8–2.6k LOC) → module tier. `decided-by-user`.

## D2 — Chaos OFF by default, gated in Settings
Add `chaos_mode: Intensity = OFF`, `chaos_seed: int = 0` to `Settings` (env `LZT_TESTNET_CHAOS_MODE/
_SEED`). Middleware is a no-op when OFF so the existing 17 test files see zero drift.
`verified-by-code:src/lzt_testnet/config.py:10` (Settings is a plain `BaseSettings`, trivially extended).

## D3 — Unify the existing force-error seam, do NOT fork it
`X-Testnet-Force-Error` + `_FORCE_ERROR_MAP` exist and are **duplicated** in two files. The chaos
fault registry becomes the single source; `X-Chaos` is the new arming header; `X-Testnet-Force-Error`
stays as a back-compat alias mapping into the same registry. No third pattern.
`verified-by-code:src/lzt_testnet/api/catch_all.py:16` + `src/lzt_testnet/api/stateful.py:36` (identical maps).

## D4 — Determinism via one seeded RNG + polyfactory seeding
A single `SeedController(seed)` owns a `random.Random(seed)` for fault decisions AND seeds polyfactory
so generated data is reproducible. **W3.5-confirmed:** `SeedController.seed_generation()` calls
`ModelFactory.seed_random(seed)` ONCE before the first `.build()` — a `BaseFactory` classmethod
(polyfactory `base.py:495`) that sets `cls.__random__ = Random(seed)` + `cls.__faker__.seed_instance(seed)`.
`create_factory()` builds bare subclasses that inherit the one seeded RNG/Faker via MRO, so seeding
order vs factory creation is irrelevant — only "seed before first build". Caveat: `__random__`/`__faker__`
are process-wide shared across all model factories, so reproducibility needs the same build call ORDER
across models — the plan's deterministic world/population order (via SeedController) already guarantees it.
`verified-by-code:polyfactory/factories/base.py:495` (W3.5 audit) + `src/lzt_testnet/fake/generator.py:30`
(no seeding exists today — must be added).

## D5 — Transport/byzantine faults via middleware; domain faults in-handler
L1 transport + byzantine body faults apply in a `FaultInjectionMiddleware` (single choke point over all
responses). L2 domain faults inject inside the stateful handlers via the registry (they need store
state). Two mechanisms, one registry. `verified-by-code:src/lzt_testnet/api/catch_all.py:82` (catch-all
returns `model_dump` — post-response body mutation is only clean at the middleware layer).

## D6 — Per-app id generation, seed-scoped (fixes a determinism leak)
`_item_id_counter`/`_operation_id_counter` are **module-global `itertools.count`** — they persist across
`create_app()` calls, so id sequences depend on process history, not seed. Move id generation into an
app-state, seed-scoped allocator so replay is deterministic. `verified-by-code:src/lzt_testnet/api/stateful.py:33`.

## D7 — CLI flags are env sugar
`uvicorn --factory` cannot pass unknown flags to `create_app`. Add a thin `cli.py` (typer, already-absent
dep — but stdlib `argparse` is enough and adds no dep) that reads `--chaos/--seed`, sets the env vars, then
launches uvicorn. Primary contract stays env vars (fits Settings). Prefer **argparse** over adding typer.
`verified-by-code:scripts/run.sh:9` (launch is `uvicorn ... --factory`, no CLI wrapper today).

## D8 — Scenarios are DATA (yaml), validated by a pydantic ScenarioSpec
`scenarios/*.yaml` loaded + validated against a `ScenarioSpec` model; CI validates the catalog. Mirrors
the FLOW-module-vs-plugin trust split. Adds `pyyaml` dep. `decided-by-user` (brief).

## D9 — Release-ready floor adapted for a non-data-bearing test tool
No `backup.sh/restore.sh` (in-memory, stateless — nothing to back up). The load-test criterion maps to a
**soak-fuzz** run. Documented so W3 waves-cohesion doesn't flag a missing backup script. `unverified`
(judgment call; user may want it stricter).

## D10 — Reuse polyfactory, do NOT add faker
The brief said "faker"; testnet already uses **polyfactory** (which wraps Faker). Generate via the
existing `FakeGenerator` + polyfactory seeding — one generation idiom, no new faker dep. Realistic forum
text uses polyfactory providers / overrides. `verified-by-code:src/lzt_testnet/fake/generator.py:8`.
