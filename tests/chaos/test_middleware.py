"""T5 — FaultInjectionMiddleware: fast-path, X-Chaos short-circuit, determinism, connection drop."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from lzt_testnet.api.app import create_app
from lzt_testnet.chaos.planner import FaultPlanner
from lzt_testnet.chaos.profiles import Intensity, profile_for
from lzt_testnet.chaos.seed import SeedController

_AUTH = {"Authorization": "Bearer tok"}


def _armed_app(*, mode: Intensity = Intensity.OFF, seed: int = 0):
    """A fresh app with chaos armed directly on app.state (bypasses env/Settings cache)."""
    app = create_app()
    controller = SeedController(seed)
    controller.seed_generation()
    app.state.seed = controller
    app.state.fault_planner = FaultPlanner(profile_for(mode))
    return app


def _client(app) -> AsyncClient:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    return AsyncClient(transport=transport, base_url="http://testserver")


@pytest_asyncio.fixture
async def off_client() -> AsyncIterator[AsyncClient]:
    async with _client(_armed_app(mode=Intensity.OFF)) as ac:
        yield ac


async def test_off_fast_path_serves_normally(off_client: AsyncClient) -> None:
    resp = await off_client.get("/testnet/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_x_chaos_502_nginx_html(off_client: AsyncClient) -> None:
    resp = await off_client.get(
        "/testnet/stateful/lots", headers={**_AUTH, "X-Chaos": "http_502_nginx@*"}
    )
    assert resp.status_code == 502
    assert resp.headers["content-type"].startswith("text/html")
    assert "502 Bad Gateway" in resp.text
    assert "nginx" in resp.text


async def test_x_chaos_targets_only_matching_endpoint() -> None:
    async with _client(_armed_app(mode=Intensity.OFF)) as ac:
        # header targets `buy`, but we hit list_lots → passes through untouched
        resp = await ac.get("/testnet/stateful/lots", headers={**_AUTH, "X-Chaos": "http_500@buy"})
    assert resp.status_code == 200


async def test_x_chaos_429_sets_retry_after(off_client: AsyncClient) -> None:
    resp = await off_client.get(
        "/testnet/stateful/lots", headers={**_AUTH, "X-Chaos": "rate_limited_429"}
    )
    assert resp.status_code == 429
    assert resp.headers["retry-after"] == "1.0"


async def test_connection_drop_truncates_body(off_client: AsyncClient) -> None:
    resp = await off_client.get(
        "/testnet/stateful/lots", headers={**_AUTH, "X-Chaos": "connection_drop"}
    )
    # start was sent (status visible) but the body was reset — no full payload.
    assert resp.content == b""


async def test_byzantine_missing_field_is_200_but_lies(off_client: AsyncClient) -> None:
    resp = await off_client.get("/testnet/health", headers={"X-Chaos": "byzantine_missing_field"})
    assert resp.status_code == 200
    assert "status" not in resp.json()  # the only field was dropped


def _fault_sequence(seed: int) -> list[int]:
    """Status codes over a fixed 12-request script under hostile chaos at `seed`."""
    import anyio

    async def run() -> list[int]:
        async with _client(_armed_app(mode=Intensity.HOSTILE, seed=seed)) as ac:
            out: list[int] = []
            for _ in range(12):
                resp = await ac.get("/testnet/stateful/lots", headers=_AUTH)
                out.append(resp.status_code)
            return out

    return anyio.run(run)


def test_same_seed_same_fault_sequence() -> None:
    assert _fault_sequence(42) == _fault_sequence(42)


def test_different_seed_diverges() -> None:
    # Not a hard guarantee, but over 12 hostile requests two seeds must differ somewhere.
    assert _fault_sequence(1) != _fault_sequence(999)
