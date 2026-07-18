# 06 — Review (W3 solo self-review)

Cold re-read of every plan file + W3.0 validator + W3.5 code audits. Grouped `severity | file | problem | fix`.

## Goal coverage (every success criterion → task)
| Criterion | Tasks |
|---|---|
| 1 OFF = no drift | T6 |
| 2 same seed = identical sequence | T1, T5 |
| 3 502 = nginx HTML | T4, T5 |
| 4 legacy header works | T3 |
| 5 bad-seller lot fails check | T10, T11 |
| 6 assert_survives scorecard | T14 |
| 7 differential-oracle | T14 |
All 7 covered. No orphan task (each traces to a criterion or a must-include TD).

## Pattern conformance
- Every `follow` in 00-audit is followed in 02-files (app.state DI, store dataclass, Settings, generation, test style). ✓
- Every `fix` has a task: TD-1→T3/T7, TD-2→T7, TD-3→T1, TD-4→T16. ✓
- Every `defer` is in 05-risks: forum-shape fidelity (R8), separate repo (FP-5). ✓

## Findings (found + fixed this pass)
| Sev | File | Problem | Fix |
|---|---|---|---|
| 🟡 | 05-risks R5 ↔ 01-logic | R5 said "X-Chaos honoured only when mode≠OFF" but the middleware fast-path processes X-Chaos even when OFF — contradiction | Reconciled R5: X-Chaos is explicit per-request arming, works regardless of mode; OFF disables only the global roll. (applied) |
| 🟡 | 04-tasks T11 | edits `app.py` (also edited by T5) but only depended on T10 → parallel-edit conflict | `depends_on: [T10, T5]` (applied) |
| 🟡 | 04-tasks T13 | edits `domain.py` (created by T7) without depending on T7 | `depends_on: [T12, T7]` (applied) |
| 🟡 | 04-tasks T14 | edits `tests/helpers/gauntlet.py` (also T8) without depending on T8 | `depends_on: [T13, T8]` (applied) |
| 🟢 | 04-tasks | est_loc sum ≈ 2750 (incl. tests); max task 260 — within module tier + task-size cap | none |

## W3.0 validator
`PASS (with warnings)` — 0 errors, 45 warnings (all "file created by plan", expected). DAG acyclic,
ids unique, depends_on resolve, RELEASE-READY present. Decisions: 8 verified-by-code, 3 unverified
(D4 later upgraded by W3.5 → 2 remaining: D9 + R5/R1 defaults). Re-run after the DAG edits: still PASS.

## W3.5 code audits
Both CONFIRMED (see 07-verification.md). No 🔴, no backend-contract corrections. polyfactory seeding +
pure-ASGI connection-drop mechanisms pinned and folded into D4/R3/03-types.

## Verdict
No blocking findings survive. All 🟡 fixes applied. Plan is internally consistent, goal-complete,
source-grounded, and DAG-safe for parallel execution.
