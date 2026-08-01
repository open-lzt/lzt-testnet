"""T6 — chaos OFF is zero drift: the middleware is a transparent passthrough (success criterion #1).

The primary regression gate is the full pre-existing suite passing unchanged with the middleware
installed (it now is, via create_app). These focused checks assert the fast-path adds nothing.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from lzt_testnet.api.app import create_app
from lzt_testnet.chaos.middleware import FaultInjectionMiddleware

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


async def test_full_response_is_byte_identical_to_a_no_middleware_app() -> None:
    """The claim in this file's name, asserted as a diff rather than spot-checks.

    A spot-check on one field passes while an added header, a re-serialized body or a changed
    content-length sails through — and those are exactly what a passthrough must not do.
    """
    with_chaos = create_app()
    without_chaos = create_app()
    without_chaos.user_middleware = [
        entry
        for entry in without_chaos.user_middleware
        if entry.cls is not FaultInjectionMiddleware
    ]
    without_chaos.middleware_stack = without_chaos.build_middleware_stack()

    # Volatile-by-design headers: `date` is a clock read, and the lot ids on a stateful POST come
    # from a per-app SeedController, so two apps legitimately differ there.
    probes = [
        ("GET", "/testnet/health", None),
        ("GET", "/market/steam?pmin=10&pmax=100", None),
        ("GET", "/market/categories", None),
    ]
    for verb, path, body in probes:
        responses = []
        for app in (with_chaos, without_chaos):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
                responses.append(await ac.request(verb, path, headers=_AUTH, json=body))
        armed, bare = responses
        assert armed.status_code == bare.status_code, path
        assert armed.content == bare.content, path
        assert {k.lower(): v for k, v in armed.headers.items() if k.lower() != "date"} == {
            k.lower(): v for k, v in bare.headers.items() if k.lower() != "date"
        }, path
