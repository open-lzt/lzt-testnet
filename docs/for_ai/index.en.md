<p align="right"><b>English</b> · <a href="index.md">Русский</a></p>

# lzt-testnet — module map for AI agents

Read this before opening source when working in this repo. Layer order matches
`open-lzt`'s convention (feature-colocated, no `utils.py` dumps).

## Layout

```
src/lzt_testnet/
├── config.py               Settings (pydantic-settings, prefix LZT_TESTNET_)
├── errors.py                TestnetError hierarchy — every route raises these, never a bare Exception
├── catalog/
│   ├── registry.py          collect_base_methods() — walks pylzt.methods, returns every
│   │                        concrete BaseMethod subclass (pkgutil.walk_packages + __subclasses__)
│   └── route_table.py       RouteEntry/RouteTable/build_route_table — turns collected methods
│                            into a linear-scan (path_pattern, http_method) -> RouteEntry table.
│                            Skips methods with an empty __url__ (composite pagination helpers
│                            like ListLotsPage/GetLotsBatch that don't own a standalone route).
├── fake/
│   └── generator.py         FakeGenerator — wraps polyfactory ModelFactory per Pydantic model,
│                            cached per model class, overrides win over generated values
├── state/
│   ├── lot_store.py          LotStore — in-memory dict[item_id, LotRecord], cursor pagination
│   ├── payment_store.py      PaymentStore — in-memory list[PaymentRecord], cursor pagination
│   └── scenario_store.py     ScenarioStore — revoked tokens + bought-item tracking (non-idempotency)
└── api/
    ├── app.py                create_app() — composition root; wires stores onto app.state,
    │                        registers error handlers + all routers (order matters: catch_all
    │                        last, since it's a wildcard `/{path:path}`)
    ├── dependencies.py       get_bearer_token, force_error_header — FastAPI Depends functions
    ├── error_handlers.py     register_error_handlers(app) — one @app.exception_handler per
    │                        TestnetError subclass, maps to the frozen HTTP status table
    ├── catch_all.py          The ~206-route generic dispatcher — matches RouteTable, builds a
    │                        fake response via FakeGenerator, echoes path params into it
    ├── stateful.py            The 6 real-semantics endpoints under /testnet/stateful/* — the
    │                        only routes with actual mutation logic (create/list/bump/set-price/
    │                        fast-buy/payments)
    └── control.py             /testnet/reset, /testnet/revoke-token — test-harness control plane
```

## Invariants worth knowing before editing

- `RouteTable.match` is a **first-match linear scan** — if two `BaseMethod`s share an identical
  path template, whichever was collected first wins; this is a real ambiguity, not a bug (see
  `tests/test_all_methods_roundtrip.py`'s comment on it). Any new stateless-route test must
  validate against the *actually matched* `RouteEntry`, not the method it meant to sample.
- `fast-buy` is deliberately **non-idempotent**: buying twice returns `NotFound` the second time
  (the lot is gone from `LotStore`, and `ScenarioStore.bought_item_ids` remembers it independently
  of the store, so a forced `payment_failed` retry still sees the correct state).
- `X-Testnet-Force-Error` is checked **before any state read/mutation**, in both `catch_all.py`
  and every `stateful.py` handler (via the shared `_raise_forced_error` helper in `stateful.py`).
- `catalog/registry.py` requires `import pylzt` (not just `import pylzt.methods`) before
  walking `__subclasses__()` — otherwise facade submodules (`market.py`/`forum.py`/`antipublic.py`)
  may not have registered their `BaseMethod` subclasses yet.
- `[tool.uv.sources] pylzt = { path = "../aiolzt" }` in `pyproject.toml` is resolved relative
  to wherever `pyproject.toml` physically sits — breaks inside a `git worktree` under
  `.worktrees/<name>/` (two levels deeper than repo root). Workaround used during the original
  build: a local junction `.worktrees/aiolzt -> ../../aiolzt`, not tracked by git.

## Test suite shape

- `test_stateless_roundtrip.py` — fixed 20-method sample, fast, in-process (`httpx.ASGITransport`).
- `test_all_methods_roundtrip.py` — every collected method, auto-generated (no hardcoded name
  list), in-process.
- `test_all_methods_e2e.py` — every collected method, driven over a **real socket** against a
  `uvicorn` server booted in a background thread (module-scoped fixture, one boot for the file).
- `test_lztforge_client_smoke.py` — the real, unmodified `pylzt.Client` against a live socket;
  proves `ClientConfig(base_url=...)` needs no monkeypatch.
- `test_stateful_lot_lifecycle.py` / `test_payments_feed.py` / `test_error_injection.py` — the
  6 stateful endpoints' actual mutation logic.
