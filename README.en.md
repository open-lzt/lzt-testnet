<p align="right"><b>English</b> · <a href="README.md">Русский</a></p>

# lzt-testnet

**A mock FastAPI server that reproduces the `lzt.market` / `lolzteam` API surface for
offline testing against [`pylzt`](../aiolzt).** No live tokens, no real money, no
rate limits — and it can reproduce edge cases (rate-limiting, token revocation,
non-idempotent double-buy) the real API won't hand you on demand.

[AI-agent docs](docs/for_ai/index.en.md) — module map + invariants, read this before the source.

> Private repo, part of the lolzteam-ecosystem sibling set (`pylzt`, `lzt-eventus`,
> `lzt-flow`, `lzt-testnet`). No secrets, no real tokens anywhere — it's a fake server.

## Quickstart

```bash
cp .env.example .env   # optional — defaults already match
uv sync --extra dev
scripts/run.sh
```

The server listens on `http://127.0.0.1:8765` by default (override via
`LZT_TESTNET_HOST` / `LZT_TESTNET_PORT`, either exported or in `.env`).

```bash
curl http://127.0.0.1:8765/testnet/health
# {"status":"ok"}
```

## Operating it

| Task | Command |
|---|---|
| Reset all in-memory state (server must be running) | `scripts/reset.sh` |
| Revoke a bearer token mid-session | `curl -X POST .../testnet/revoke-token -d '{"token":"..."}'` |
| Health check | `curl .../testnet/health` |
| Shut down | Ctrl-C the `scripts/run.sh` process — state is in-memory only, nothing to clean up |

## How the ~206 stateless routes are derived

`src/lzt_testnet/catalog/registry.py` walks `pylzt.methods` with
`pkgutil.walk_packages`, importing every submodule so all concrete `BaseMethod`
subclasses register, then collects them recursively via `__subclasses__()`.
`src/lzt_testnet/catalog/route_table.py` turns each collected class into a
`RouteEntry` — compiling its `__url__` path template into a matchable regex and
recording its HTTP method and declared `__returning__` response model. A single
catch-all route (`src/lzt_testnet/api/catch_all.py`, `/{path:path}`) matches incoming
requests against this table and returns a `polyfactory`-generated fake instance of the
matched method's response model.

This means the route table is **generated from pylzt's own typed methods**, not
hand-copied — it tracks pylzt's method catalog automatically as methods are added.

## Examples

Four non-overlapping ways to drive this server, matching the four layers of the test
suite (see [`docs/for_ai/index.en.md`](docs/for_ai/index.en.md#test-suite-shape) for the full
picture).

### 1. Point a real `pylzt.Client` at it (the intended integration path)

In pytest — one line via the `testnet_client` fixture (the pytest plugin ships with
`lzt-testnet`; the mock runs in-process over ASGI, no socket):

```python
async def test_my_autobuy(testnet_client):   # a pylzt.Client already aimed at the mock
    lot = await testnet_client.market.get_lot(item_id=123)
```

Outside pytest — `ClientConfig.for_testnet()` replaces the hand-written `base_url` wiring:

```python
from pylzt import Client, ClientConfig

client = Client.from_token("fake-token", config=ClientConfig.for_testnet())
lot = await client.market.get_lot(item_id=123)
```

Every `BaseMethod` call now round-trips through the mock server instead of the live API.

### 2. Drive the stateful lot lifecycle directly over HTTP

Use this when testing flow-authoring code that depends on real create/buy semantics
(not just response *shape*) — e.g. proving your own retry logic handles a non-idempotent
`fast-buy` correctly:

```bash
curl -X POST http://127.0.0.1:8765/testnet/stateful/lots \
  -H "Authorization: Bearer seller-token" \
  -d '{"category":"games","price":"10.00","currency":"USD","title":"test lot"}'
# {"item_id":1,...}

curl -X POST http://127.0.0.1:8765/testnet/stateful/lots/1/buy \
  -H "Authorization: Bearer buyer-token"
# 200 — first buy succeeds

curl -X POST http://127.0.0.1:8765/testnet/stateful/lots/1/buy \
  -H "Authorization: Bearer buyer-token"
# 404 NotFound — second buy on the same item_id, proving non-idempotency isn't hidden
```

### 3. Force a deterministic error scenario

Use this for testing your own error-handling paths (retry-on-`RateLimited`, alert-on-
`PaymentFailed`) without waiting for the real API to misbehave:

```bash
curl -i http://127.0.0.1:8765/market/lot/123 \
  -H "Authorization: Bearer any-token" \
  -H "X-Testnet-Force-Error: rate_limited"
# HTTP/1.1 429 — {"error":"RateLimited","retry_after":1.0}
```

Values: `rate_limited` (429) · `auth_failed` (401) · `not_found` (404) ·
`transport_error` (500) · `payment_failed` (402). Checked before any state
mutation, on both the catch-all route and all 6 stateful routes.

### 4. Boot it in-process for your own test suite

Use this in a CI job that needs a real socket (e.g. testing a client that isn't
ASGI-transport-testable) without a separate process to manage:

```python
import threading
import uvicorn
from lzt_testnet.api.app import create_app

config = uvicorn.Config(create_app(), host="127.0.0.1", port=0, log_level="warning")
server = uvicorn.Server(config)
thread = threading.Thread(target=server.run, daemon=True)
thread.start()
# poll /testnet/health until server.started, then use server.servers[0].sockets[0]
# for the bound port — see tests/test_lztforge_client_smoke.py for the full fixture.
```

## Auth

Every route requires `Authorization: Bearer <token>` — missing or malformed → 401
`AuthFailed`. `POST /testnet/revoke-token` with body `{"token": "<bearer-token>"}`
revokes a token; subsequent requests using it then fail with 401, even though the
token string itself was never valid against any real credential store.

## Config

`src/lzt_testnet/config.py` — `Settings` (`pydantic-settings`, prefix `LZT_TESTNET_`):

| Variable | Default |
|---|---|
| `LZT_TESTNET_HOST` | `127.0.0.1` |
| `LZT_TESTNET_PORT` | `8765` |
| `LZT_TESTNET_LOG_LEVEL` | `INFO` |

## Contributing

Local dev, no CI configured yet:

```bash
uv sync --extra dev
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv run pytest -q
```

## License

[MIT](LICENSE)
