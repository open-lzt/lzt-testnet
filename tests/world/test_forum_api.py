"""T11 — forum + world-lot endpoints serve the seeded world consistently; empty when no world."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from lzt_testnet.api.app import create_app
from lzt_testnet.chaos.seed import SeedController
from lzt_testnet.world.arm import build_world
from lzt_testnet.world.builder import WorldConfig


def _world_app(seed: int = 1):
    """An app with a world armed but transport chaos OFF — deterministic forum/lot reads."""
    app = create_app()
    controller = SeedController(seed)
    controller.seed_generation()
    app.state.seed = controller
    app.state.world = build_world(
        seed=seed,
        config=WorldConfig(forum_users=8, forum_threads=6),
        lots=app.state.lot_store,
        scenario=app.state.scenario_store,
        generator=app.state.fake_generator,
    )
    return app


@pytest_asyncio.fixture
async def world_client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=_world_app(), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


async def test_forum_users_consistent(world_client: AsyncClient) -> None:
    first = (await world_client.get("/testnet/world/forum/users")).json()["items"]
    again = (await world_client.get("/testnet/world/forum/users")).json()["items"]
    assert first == again
    assert len(first) == 8


async def test_forum_threads_and_posts(world_client: AsyncClient) -> None:
    threads = (await world_client.get("/testnet/world/forum/threads")).json()["items"]
    assert len(threads) == 6
    thread_id = threads[0]["thread_id"]
    posts = (await world_client.get(f"/testnet/world/forum/threads/{thread_id}/posts")).json()
    assert all(p["thread_id"] == thread_id for p in posts["items"])


async def test_world_lots_stream_stable(world_client: AsyncClient) -> None:
    p = {"category": "steam", "cursor": 0, "limit": 5}
    first = (await world_client.get("/testnet/world/lots", params=p)).json()
    again = (await world_client.get("/testnet/world/lots", params=p)).json()
    assert [i["item_id"] for i in first["items"]] == [i["item_id"] for i in again["items"]]
    assert first["next_cursor"] == 5


async def test_forum_limit_zero_no_crash(world_client: AsyncClient) -> None:
    resp = await world_client.get("/testnet/world/forum/users", params={"limit": 0})
    assert resp.status_code == 200  # limit=0 must not IndexError to a 500
    assert resp.json() == {"items": [], "next_cursor": None}


async def test_no_world_returns_empty() -> None:
    # default app (chaos OFF) has no world → forum routes are empty, existing suite unaffected.
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        resp = await ac.get("/testnet/world/forum/users")
    assert resp.status_code == 200
    assert resp.json() == {"items": [], "next_cursor": None}
