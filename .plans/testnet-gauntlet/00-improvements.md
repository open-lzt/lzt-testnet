# Improvements

## Tech debt to fix in this plan
| ID | Finding | Where | Cost | Decision |
|---|---|---|---|---|
| TD-1 | `_FORCE_ERROR_MAP` duplicated in two files | `catch_all.py:16`, `stateful.py:36` | S | must-include (W1 unifies) |
| TD-2 | module-global id counters leak state, break seed-replay | `stateful.py:33` | S | must-include (W1/W2) |
| TD-3 | nothing is seeded → not reproducible | `fake/generator.py` | S | must-include (W1 foundation) |
| TD-4 | no CI runs the suite | (repo) | S | must-include (W4) |

## Future-proofing proposals
| ID | Proposal | Pays off when | Cost | Tag |
|---|---|---|---|---|
| FP-1 | `FaultKind` StrEnum + `FaultContext` DTO as the typed core | every new fault added later | S | must-include |
| FP-2 | `ScenarioSpec` as pydantic + yaml (data, not code) | community adds scenarios by PR | M | must-include |
| FP-3 | `ChaosProfile` weighted-registry so intensity is data-driven, not branching | tuning without code change | S | must-include |
| FP-4 | seed-scoped id/rng in `app.state` (not module globals) | deterministic replay + test isolation | S | must-include |
| FP-5 | scenario catalog its own repo `lzt-gauntlet` | catalog outgrows testnet | M | defer (D8) |

## Deferred (logged for next plan)
- FP-5: separate `lzt-gauntlet` community scenario repo — only when the in-repo `scenarios/` catalog
  grows past a handful, mirroring how `lzt-flows` split from the monorepo.
- Recording real lzt.market failure HAR captures to seed the byzantine corpus from observed reality.
