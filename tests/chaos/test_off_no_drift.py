"""T6 — chaos OFF is zero drift: the middleware is a transparent passthrough (success criterion #1).

The primary regression gate is the full pre-existing suite passing unchanged with the middleware
installed (it now is, via create_app). These focused checks assert the fast-path adds nothing.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from lzt_testnet.api.app import create_app

_AUTH = {"Authorization": "Bearer tok"}


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app()  # default settings → chaos OFF, middleware present but inert
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


async def test_health_untouched(client: AsyncClient) -> None:
    resp = await client.get("/testnet/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
    assert resp.headers["content-type"] == "application/json"


async def test_no_chaos_headers_injected(client: AsyncClient) -> None:
    resp = await client.get("/testnet/health")
    lowered = {k.lower() for k in resp.headers}
    assert "x-chaos" not in lowered
    assert "retry-after" not in lowered


async def test_stateful_roundtrip_unchanged(client: AsyncClient) -> None:
    created = await client.post(
        "/testnet/stateful/lots",
        headers=_AUTH,
        json={"category": "steam", "price": "10.00", "currency": "usd", "title": "acc"},
    )
    assert created.status_code == 200
    item_id = created.json()["item_id"]

    listed = await client.get("/testnet/stateful/lots", headers=_AUTH)
    assert listed.status_code == 200
    assert any(lot["item_id"] == item_id for lot in listed.json())


async def test_forced_error_still_typed(client: AsyncClient) -> None:
    # legacy X-Testnet-Force-Error path is untouched by the chaos middleware (still typed body).
    resp = await client.get(
        "/testnet/stateful/lots", headers={**_AUTH, "X-Testnet-Force-Error": "rate_limited"}
    )
    assert resp.status_code == 429
    assert resp.json() == {"error": "RateLimited", "retry_after": 1.0}
