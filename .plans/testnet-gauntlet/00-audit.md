# Audit — testnet blast radius

Grounded first-hand this run (file:line cites). Tags: `critical|high|medium|low` × `follow|fix|defer`.

## Existing patterns to FOLLOW
- **App factory + `app.state` DI.** `create_app()` wires stores/generator/settings onto `app.state`,
  handlers read them via `Depends(_getter)`. New chaos/world stores follow the same pattern.
  `src/lzt_testnet/api/app.py:24`. `follow`.
- **In-memory store dataclasses.** `LotRecord`/`LotStore` etc. are dataclasses + a dict/list store with
  cursor pagination `list(...)->(records, next_cursor)`. New `SellerStore`/forum stores mirror this.
  `src/lzt_testnet/state/lot_store.py:10`. `follow`.
- **Settings via pydantic-settings, `LZT_TESTNET_` prefix, `get_settings()` lru_cache.**
  `src/lzt_testnet/config.py:10`. Chaos config extends this. `follow`.
- **Error-injection already request-armed.** `force_error_header()` dep + `_FORCE_ERROR_MAP` + typed
  errors in `errors.py`. `src/lzt_testnet/api/dependencies.py:22`. Extend, don't replace. `follow`.
- **Generation via `FakeGenerator.build(model, overrides)`.** `fake/generator.py:18`. `follow`.
- **Test style.** `client` fixture = httpx `AsyncClient` + `ASGITransport(create_app())`, fresh app per
  test, `asyncio_mode="auto"`. `tests/conftest.py:11`. New chaos fixtures extend this. `follow`.

## Inconsistencies / tech debt IN the blast radius
- **TD-1 `_FORCE_ERROR_MAP` duplicated** verbatim in `catch_all.py:16` and `stateful.py:36`; `stateful`
  adds `not_found` via `_raise_forced_error`. Two sources of one truth. `medium` → **fix** (unify into
  the chaos registry — W1 does this anyway).
- **TD-2 module-global id counters.** `_item_id_counter`/`_operation_id_counter` are process-global
  `itertools.count` (`stateful.py:33`) — leak state across `create_app()`, break seed-determinism and
  test isolation. `high` → **fix** (W1/W2, D6).
- **TD-3 no seeding anywhere.** polyfactory + any `random` use are unseeded (`fake/generator.py`),
  so nothing is reproducible today. `high` → **fix** (foundation of W1, D4).
- **TD-4 no CI.** No `.github/workflows/` runs the suite. `medium` → **fix** (W4 adds it).

## Anti-patterns to AVOID (would violate rules)
- String-literal fault names as the domain type → **use a `FaultKind` StrEnum** (rules: no literals).
- A parallel byzantine/response layer duplicating the force-error path → one unified registry (D3).
- A second data generator (faker) beside polyfactory → reuse polyfactory (D10).
- Chaos on by default → OFF, gated, no accidental hostile responses (D2).

## Not verified / out of scope
- polyfactory seeding API name — W3.5 confirms (D4).
- Real lzt.market forum response shapes — the forum sim is testnet-invented (like the stateful routes,
  `stateful.py:11` notes these are testnet inventions), not a catalog-faithful mock. `defer` to W3 detail.
