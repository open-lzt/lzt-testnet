# 02 — Files

New sub-packages follow the existing `src/lzt_testnet/<area>/` layout + `app.state` DI + store-dataclass
conventions (00-audit "follow").

## New — L1 (seed + transport faults)
| File | Purpose |
|---|---|
| `src/lzt_testnet/chaos/__init__.py` | package marker |
| `src/lzt_testnet/chaos/faults.py` | `FaultKind` StrEnum, `Fault` DTO, `FaultContext` DTO |
| `src/lzt_testnet/chaos/seed.py` | `SeedController` (root rng, per-seq stream, `next_id`, `seed_generation`) |
| `src/lzt_testnet/chaos/profiles.py` | `Intensity` StrEnum, `ChaosProfile`, 4 built-in profiles, weight roll |
| `src/lzt_testnet/chaos/planner.py` | `FaultPlanner.decide(ctx)`; arming precedence + legacy-name map |
| `src/lzt_testnet/chaos/middleware.py` | `FaultInjectionMiddleware` (pure-ASGI); pre/post response application |
| `src/lzt_testnet/chaos/render.py` | fault → HTTP effect (nginx-502 HTML, byzantine body rewrite, truncate, malformed) |

## New — L2 (domain faults)
| File | Purpose |
|---|---|
| `src/lzt_testnet/chaos/domain.py` | `maybe_inject(ctx, view)` for buy/payment/check faults; retry-storm counter |

## New — L3 (world)
| File | Purpose |
|---|---|
| `src/lzt_testnet/world/__init__.py` | package marker |
| `src/lzt_testnet/world/models.py` | `SellerRecord`+`SellerQuality`, `ForumUser/Thread/Post` dataclasses |
| `src/lzt_testnet/world/stores.py` | `SellerStore`, `ForumStore` (dict + cursor list, mirrors `lot_store`) |
| `src/lzt_testnet/world/builder.py` | `WorldBuilder(seed)` — populate roster + forum + seeded lots/dynamics |
| `src/lzt_testnet/api/forum.py` | forum read routers (users/threads/posts), registered in `create_app` |

## New — L4 (scenarios / report / cli / docs / ci)
| File | Purpose |
|---|---|
| `src/lzt_testnet/chaos/scenario.py` | `ScenarioSpec` pydantic model + `load_scenario(name)` + schema validate |
| `src/lzt_testnet/chaos/report.py` | `GauntletRecorder`, `GauntletReport`, `FailedProbe` DTOs |
| `src/lzt_testnet/cli.py` | argparse wrapper: `--chaos/--seed/--scenario` → env → launch uvicorn (D7) |
| `scenarios/*.yaml` | data catalog: black-friday-meltdown, auth-expiry-storm, seller-spam-flood, nginx-down, pagination-hell |
| `scenarios/README.md` | contributor schema for scenario YAML |
| `docs/gauntlet.md` | clone→run a scenario; header/env/scenario arming; oracle usage |
| `scripts/gauntlet-soak.sh` | seeded soak-fuzz run + faults/sec baseline |
| `.github/workflows/ci.yml` | run `pytest` incl. a seeded chaos smoke (TD-4) |
| `tests/helpers/gauntlet.py` | `chaos_client`, `assert_survives`, `assert_idempotent`, `assert_blacklists`, oracle runner |

## Modified
| File | Change |
|---|---|
| `src/lzt_testnet/config.py` | + `chaos_mode: Intensity=OFF`, `chaos_seed:int=0`, `chaos_scenario:str\|None=None` (D2) |
| `src/lzt_testnet/api/app.py` | build `SeedController`, seed generation, register `FaultInjectionMiddleware` + forum router, put `seed`/`world`/`recorder` on `app.state`; id allocator from seed (D6) |
| `src/lzt_testnet/api/dependencies.py` | `force_error_header` stays; add `x_chaos_header` dep |
| `src/lzt_testnet/api/catch_all.py` | drop local `_FORCE_ERROR_MAP`; route force-error through `chaos.planner` (TD-1) |
| `src/lzt_testnet/api/stateful.py` | replace `_raise_forced_error`/local map with `chaos.domain`; seed-scoped ids (TD-1/2) |
| `src/lzt_testnet/state/scenario_store.py` | id allocation moves to `SeedController`; keep revoked/bought sets |
| `scripts/run.sh` | call `python -m lzt_testnet.cli` (or pass chaos env) instead of raw uvicorn |
| `pyproject.toml` | + `pyyaml` (scenarios). polyfactory already present; no faker (D10) |
| `.env.example` | + `LZT_TESTNET_CHAOS_MODE/_SEED/_SCENARIO` |
| `tests/conftest.py` | add `chaos_client` fixture factory (armed app per scenario/seed) |

## Parallel-safety
Disjoint `files` per parallel task in `04-tasks.yaml`. The shared edits to `app.py`/`stateful.py`/
`config.py` are sequenced via `depends_on` (never two parallel tasks on the same file).
