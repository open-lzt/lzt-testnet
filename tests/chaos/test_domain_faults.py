"""T7 — L2 domain faults: account_invalid, already_sold, charge_then_fail, delayed_settlement.

Domain faults are armed with the `X-Chaos: <kind>@buy` header (deterministic, per-test control).
Also asserts item/payment ids come from the seed engine, not a module-global counter (TD-2/D6).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from lzt_testnet.api.app import create_app

_AUTH = {"Authorization": "Bearer buyer"}
_LOT = {"category": "steam", "price": "9.99", "currency": "usd", "title": "acc"}


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=create_app(), raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


async def _make_lot(client: AsyncClient) -> int:
    resp = await client.post("/testnet/stateful/lots", headers=_AUTH, json=_LOT)
    return int(resp.json()["item_id"])


async def _buy(client: AsyncClient, item_id: int, fault: str | None = None) -> AsyncClient:
    headers = dict(_AUTH)
    if fault is not None:
        headers["X-Chaos"] = f"{fault}@buy"
    return await client.post(f"/testnet/stateful/lots/{item_id}/buy", headers=headers)


async def test_account_invalid_marks_bought_but_flags_invalid(client: AsyncClient) -> None:
    item_id = await _make_lot(client)
    resp = await _buy(client, item_id, "account_invalid")
    assert resp.status_code == 200
    assert resp.json() == {"status": "invalid_account", "item_id": item_id}
    # lot is consumed (marked bought) despite the invalid account
    again = await _buy(client, item_id)
    assert again.status_code == 404


async def test_already_sold_exactly_one_winner(client: AsyncClient) -> None:
    item_id = await _make_lot(client)
    first = await _buy(client, item_id, "already_sold")
    second = await _buy(client, item_id, "already_sold")
    statuses = sorted([first.status_code, second.status_code])
    assert statuses == [200, 404]  # exactly one winner


async def test_charge_then_fail_leaves_no_payment(client: AsyncClient) -> None:
    item_id = await _make_lot(client)
    resp = await _buy(client, item_id, "charge_then_fail")
    assert resp.status_code == 402
    payments = await client.get("/testnet/stateful/payments", headers=_AUTH)
    assert all(p["item_id"] != item_id for p in payments.json())
    # the lot was consumed (charged) even though the payment failed
    assert (await _buy(client, item_id)).status_code == 404


async def test_delayed_settlement_pends_then_settles(client: AsyncClient) -> None:
    item_id = await _make_lot(client)
    for _ in range(3):  # default delay_ticks
        pending = await _buy(client, item_id, "delayed_settlement")
        assert pending.status_code == 200
        assert pending.json()["status"] == "pending"
    settled = await _buy(client, item_id, "delayed_settlement")
    assert settled.status_code == 200
    assert settled.json() == {}
    payments = await client.get("/testnet/stateful/payments", headers=_AUTH)
    assert any(p["item_id"] == item_id for p in payments.json())


async def test_ids_are_seed_scoped_not_process_history() -> None:
    # A fresh app starts ids from the seed, independent of any prior app's history (TD-2/D6).
    async def first_two_ids() -> list[int]:
        transport = ASGITransport(app=create_app(), raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            return [await _make_lot(ac), await _make_lot(ac)]

    assert await first_two_ids() == [1, 2]
    assert await first_two_ids() == [1, 2]  # not 3,4 — no module-global drift
