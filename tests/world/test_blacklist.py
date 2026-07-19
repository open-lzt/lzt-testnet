"""T11 — blacklist: spam-seller lots are listed AND their check fails deterministically."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from lzt_testnet.api.app import create_app
from lzt_testnet.chaos.seed import SeedController
from lzt_testnet.world.arm import build_world
from lzt_testnet.world.builder import WorldConfig
from tests.helpers.gauntlet import assert_blacklists


@pytest_asyncio.fixture
async def world_client() -> AsyncIterator[AsyncClient]:
    seed = 5
    app = create_app()
    controller = SeedController(seed)
    controller.seed_generation()
    app.state.seed = controller
    app.state.world = build_world(
        seed=seed,
        config=WorldConfig(roster_size=10, spam_ratio=0.5),
        lots=app.state.lot_store,
        scenario=app.state.scenario_store,
        generator=app.state.fake_generator,
    )
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


async def test_assert_blacklists(world_client: AsyncClient) -> None:
    await assert_blacklists(world_client, category="steam", limit=20)


async def test_check_is_stable_across_pages(world_client: AsyncClient) -> None:
    listed = (await world_client.get("/testnet/world/lots", params={"limit": 10})).json()["items"]
    invalid_ids = {
        lot["item_id"]
        for lot in listed
        if not (await world_client.get(f"/testnet/world/lots/{lot['item_id']}/check")).json()["valid"]
    }
    # re-list the same page → the same lots remain blacklisted
    for lot in listed:
        valid = (await world_client.get(f"/testnet/world/lots/{lot['item_id']}/check")).json()["valid"]
        assert (lot["item_id"] in invalid_ids) is (not valid)
