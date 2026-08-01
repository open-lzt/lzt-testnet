"""`POST /testnet/inject-lot` — the verb that makes a catalog listing change."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

_AUTH = {"Authorization": "Bearer testnet-fake-token"}


async def _items(client: AsyncClient, path: str) -> list[dict[str, object]]:
    body = (await client.get(path, headers=_AUTH)).json()
    items = body["items"]
    assert isinstance(items, list)
    return items


@pytest.mark.anyio
async def test_injected_lot_heads_its_category(client: AsyncClient) -> None:
    before = await _items(client, "/steam?pmax=10")

    response = await client.post(
        "/testnet/inject-lot",
        json={"category": "steam", "price": 7, "title": "свежий лот"},
    )
    assert response.status_code == 200
    item_id = response.json()["item_id"]

    after = await _items(client, "/steam?pmax=10")
    assert len(after) == len(before) + 1
    assert after[0]["item_id"] == item_id
    assert after[0]["price"] == 7
    assert after[0]["title"] == "свежий лот"


@pytest.mark.anyio
async def test_injected_lot_stays_out_of_other_categories(client: AsyncClient) -> None:
    await client.post("/testnet/inject-lot", json={"category": "steam", "price": 7, "title": "x"})

    assert all(item["title"] != "x" for item in await _items(client, "/fortnite"))


@pytest.mark.anyio
async def test_reset_clears_injections(client: AsyncClient) -> None:
    before = await _items(client, "/steam")
    await client.post("/testnet/inject-lot", json={"category": "steam", "price": 7, "title": "x"})
    await client.post("/testnet/reset", json={})

    assert len(await _items(client, "/steam")) == len(before)
