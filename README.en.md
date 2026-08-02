<p align="right"><b>English</b> · <a href="README.md">Русский</a></p>

# lzt-testnet

A FastAPI mock of the `lzt.market` API. Test your code against [pylzt](https://github.com/open-lzt/pylzt) with no live token, no money, no rate limits.

It does what the real API won't do on demand: 429s, token revocation, buying the same lot twice.

```bash
uv sync --extra dev
scripts/run.sh
curl http://127.0.0.1:8765/testnet/health
# {"status":"ok"}
```

## Install

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12+.

```bash
git clone https://github.com/open-lzt/lzt-testnet.git
cd lzt-testnet
cp .env.example .env      # optional, the defaults work
uv sync --extra dev
```

Run:

```bash
scripts/run.sh                              # 127.0.0.1:8765
scripts/run.sh --host 0.0.0.0 --port 9100
uv run python -m lzt_testnet.cli --port 9100   # the same, directly
```

## Point pylzt at it

In pytest — one fixture. The plugin installs with the package and the mock is served in-process over ASGI, so no socket is involved.

```python
async def test_autobuy(testnet_client):      # a pylzt.Client already aimed at the mock
    lot = await testnet_client.market.get_lot(item_id=123)
```

Outside pytest:

```python
from pylzt import Client, ClientConfig

client = Client.from_token("fake-token", config=ClientConfig.for_testnet())
lot = await client.market.get_lot(item_id=123)
```

From here every `BaseMethod` call goes to the mock instead of the live API.

## Force an error

The `X-Testnet-Force-Error` header is checked before any state mutation — both on the catch-all route and on all 6 stateful routes.

```bash
curl -i http://127.0.0.1:8765/market/lot/123 \
  -H "Authorization: Bearer any-token" \
  -H "X-Testnet-Force-Error: rate_limited"
# HTTP/1.1 429 — {"error":"RateLimited","retry_after":1.0}
```

| Value | Response |
|---|---|
| `rate_limited` | 429 |
| `auth_failed` | 401 |
| `not_found` | 404 |
| `transport_error` | 500 |
| `payment_failed` | 402 |

## Stateful lots

Real create/buy semantics, not just the shape of a response. This is how you prove your retries don't break on a non-idempotent `fast-buy`.

```bash
curl -X POST http://127.0.0.1:8765/testnet/stateful/lots \
  -H "Authorization: Bearer seller-token" \
  -d '{"category":"games","price":"10.00","currency":"USD","title":"test lot"}'
# {"item_id":1,...}

curl -X POST http://127.0.0.1:8765/testnet/stateful/lots/1/buy \
  -H "Authorization: Bearer buyer-token"
# 200 — first purchase

curl -X POST http://127.0.0.1:8765/testnet/stateful/lots/1/buy \
  -H "Authorization: Bearer buyer-token"
# 404 NotFound — same lot, second time
```

## Authentication

Every route requires `Authorization: Bearer <token>`. Missing or malformed header → 401 `AuthFailed`.

```bash
curl -X POST http://127.0.0.1:8765/testnet/revoke-token -d '{"token":"buyer-token"}'
# every later request with that token → 401
```

The token string is never checked against any store — anything not revoked is valid.

## Operating it

| Task | Command |
|---|---|
| Reset all state | `scripts/reset.sh` |
| Health | `curl http://127.0.0.1:8765/testnet/health` |
| Stop | `Ctrl-C` — state is in memory only, nothing to clean up |

## Configuration

`src/lzt_testnet/config.py`, `pydantic-settings`, prefix `LZT_TESTNET_`.

| Variable | Default |
|---|---|
| `LZT_TESTNET_HOST` | `127.0.0.1` |
| `LZT_TESTNET_PORT` | `8765` |
| `LZT_TESTNET_LOG_LEVEL` | `INFO` |
| `LZT_TESTNET_CONTROL_KEY` | empty — key for the `/testnet/*` routes |

## Where the ~206 routes come from

The route table is **generated from pylzt's own typed methods** rather than transcribed by hand — a new method in pylzt shows up here on its own.

- `catalog/registry.py` — walks `pylzt.methods` via `pkgutil.walk_packages` and collects every `BaseMethod` subclass.
- `catalog/route_table.py` — turns each class into a `RouteEntry`: the `__url__` template compiled to a regex, its HTTP method, its declared `__returning__` response model.
- `api/catch_all.py` — the `/{path:path}` route matches a request against that table and returns a `polyfactory`-generated instance of the matched response model.

## A real socket instead of ASGI

For a CI job that needs an actual port:

```python
import threading
import uvicorn
from lzt_testnet.api.app import create_app

config = uvicorn.Config(create_app(), host="127.0.0.1", port=0, log_level="warning")
server = uvicorn.Server(config)
threading.Thread(target=server.run, daemon=True).start()
# wait for server.started, the bound port is in server.servers[0].sockets[0]
```

A ready-made fixture lives in `tests/test_lztforge_client_smoke.py`.

## Development

```bash
uv sync --extra dev
uv run ruff check . && uv run ruff format --check .
uv run mypy src
uv run pytest -q
```

[AI-agent docs](docs/for_ai/index.en.md) — module map and invariants, read before the source.

## Ecosystem

[pylzt](https://github.com/open-lzt/pylzt) · [auto-lzt](https://github.com/open-lzt/auto-lzt) · [lzt-eventus](https://github.com/open-lzt/lzt-eventus) · [lzt-mcp](https://github.com/open-lzt/lzt-mcp) · [the whole stand](https://github.com/open-lzt/open-lzt)

## License

[MIT](LICENSE)
