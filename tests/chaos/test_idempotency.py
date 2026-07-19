"""T8 — retry_storm exercises the idempotency contract: a retrying client buys exactly once."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import AsyncClient

from tests.helpers.gauntlet import assert_idempotent, chaos_client

_AUTH = {"Authorization": "Bearer buyer"}
_LOT = {"category": "steam", "price": "5.00", "currency": "usd", "title": "acc"}


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with chaos_client() as ac:  # OFF profile; retry_storm armed per-request via header
        yield ac


async def _make_lot(client: AsyncClient) -> int:
    resp = await client.post("/testnet/stateful/lots", headers=_AUTH, json=_LOT)
    return int(resp.json()["item_id"])


async def test_retry_storm_buys_exactly_once(client: AsyncClient) -> None:
    item_id = await _make_lot(client)

    async def buy():
        return await client.post(
            f"/testnet/stateful/lots/{item_id}/buy",
            headers={**_AUTH, "X-Chaos": "retry_storm@buy"},
        )

    resp = await assert_idempotent(client, buy, item_id=item_id, token="buyer")
    assert resp.status_code == 200


async def test_non_retrying_client_sees_transient(client: AsyncClient) -> None:
    item_id = await _make_lot(client)
    resp = await client.post(
        f"/testnet/stateful/lots/{item_id}/buy",
        headers={**_AUTH, "X-Chaos": "retry_storm@buy"},
    )
    assert resp.status_code == 429  # first attempt is transient; no payment yet
    payments = await client.get("/testnet/stateful/payments", headers=_AUTH)
    assert all(p["item_id"] != item_id for p in payments.json())
