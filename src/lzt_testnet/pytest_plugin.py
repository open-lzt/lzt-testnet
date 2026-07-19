"""pytest plugin exposing `testnet_client` — a real `pylzt.Client` wired in-process
to a fresh mock app, no uvicorn/socket/manual `ClientConfig` wiring in the caller's
own test.

`HttpxSession.__init__` (`pylzt/transport/session.py`) takes `client:
httpx.AsyncClient | None` to seed its no-proxy connection slot with a caller-owned
client — its own docstring calls this "test injection". `_client_for()` returns that
seeded client whenever a request carries no proxy, which is every request a test
ever makes, so an `httpx.AsyncClient(transport=httpx.ASGITransport(app=app))` there
routes every `pylzt` call straight into `create_app()` in-process — a real socket is
not required (the existing `test_lztforge_client_smoke.py` uvicorn fixture predates
this seam; its docstring claiming "no transport-injection seam for ASGI" is stale).

Registered as a `pytest11` entry point (`pyproject.toml`), so any project depending
on `lzt-testnet[dev]` gets the fixture for free — no explicit `pytest_plugins =`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest_asyncio
from pylzt import Client, ClientConfig
from pylzt.token_pool.base import Token
from pylzt.token_pool.round_robin import RoundRobinTokenPool
from pylzt.transport.session import HttpxSession
from pylzt.types import TokenId

from lzt_testnet.api.app import create_app

_TESTNET_BASE_URL = "http://testnet"


@pytest_asyncio.fixture
async def testnet_client() -> AsyncIterator[Client]:
    """Yield a `pylzt.Client` pointed at a fresh in-process mock app instance.

    `create_app()` builds fresh in-memory stores per call (see `tests/conftest.py`),
    so each test gets isolated state automatically.
    """
    app = create_app()
    asgi_client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=_TESTNET_BASE_URL
    )
    token_pool = RoundRobinTokenPool(
        [Token(token_id=TokenId("testnet-tok0"), credential="testnet-token")]
    )
    session = HttpxSession(client=asgi_client, token_pool=token_pool)
    client = Client(
        token_pool=token_pool,
        transport=session,
        forum_transport=session,
        config=ClientConfig(base_url=_TESTNET_BASE_URL, forum_base_url=_TESTNET_BASE_URL),
    )
    try:
        yield client
    finally:
        await client.aclose()
