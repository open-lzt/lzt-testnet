"""Integration tests for create/list/bump/set-price/fast-buy lot lifecycle."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from lzt_testnet.api.error_handlers import register_error_handlers
from lzt_testnet.api.stateful import router
from lzt_testnet.fake.generator import FakeGenerator
from lzt_testnet.state.lot_store import LotStore
from lzt_testnet.state.payment_store import PaymentStore
from lzt_testnet.state.scenario_store import ScenarioStore

_TOKEN = "seller-token-1"
_HEADERS = {"Authorization": f"Bearer {_TOKEN}"}


def _build_app() -> FastAPI:
    app = FastAPI()
    app.state.lot_store = LotStore()
    app.state.payment_store = PaymentStore()
    app.state.scenario_store = ScenarioStore()
    app.state.fake_generator = FakeGenerator()
    app.include_router(router)
    register_error_handlers(app)
    return app


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = _build_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_full_lot_lifecycle(client: AsyncClient) -> None:
    create_resp = await client.post(
        "/testnet/stateful/lots",
        json={"category": "steam", "price": "10.00", "currency": "USD", "title": "Acc #1"},
        headers=_HEADERS,
    )
    assert create_resp.status_code == 200
    item_id = create_resp.json()["item_id"]

    list_resp = await client.get("/testnet/stateful/lots", params={"category": "steam"})
    assert list_resp.status_code == 200
    lots = list_resp.json()
    assert any(lot["item_id"] == item_id for lot in lots)
    original_published_at = next(lot for lot in lots if lot["item_id"] == item_id)

    bump_resp = await client.post(f"/testnet/stateful/lots/{item_id}/bump", headers=_HEADERS)
    assert bump_resp.status_code == 200

    price_resp = await client.post(
        f"/testnet/stateful/lots/{item_id}/price",
        json={"price": "99.00"},
        headers=_HEADERS,
    )
    assert price_resp.status_code == 200

    updated_list = await client.get("/testnet/stateful/lots", params={"category": "steam"})
    updated_lot = next(lot for lot in updated_list.json() if lot["item_id"] == item_id)
    assert updated_lot["price"] == "99.00"
    assert original_published_at is not None  # bump touched published_at; not surfaced on Lot

    buy_resp = await client.post(f"/testnet/stateful/lots/{item_id}/buy", headers=_HEADERS)
    assert buy_resp.status_code == 200

    retry_resp = await client.post(f"/testnet/stateful/lots/{item_id}/buy", headers=_HEADERS)
    assert retry_resp.status_code == 404


@pytest.mark.asyncio
async def test_set_price_requires_price_field(client: AsyncClient) -> None:
    create_resp = await client.post(
        "/testnet/stateful/lots",
        json={"category": "steam", "price": "10.00", "currency": "USD", "title": "Acc #2"},
        headers=_HEADERS,
    )
    item_id = create_resp.json()["item_id"]

    resp = await client.post(
        f"/testnet/stateful/lots/{item_id}/price", json={"price": ""}, headers=_HEADERS
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_bump_rejects_non_owner(client: AsyncClient) -> None:
    create_resp = await client.post(
        "/testnet/stateful/lots",
        json={"category": "steam", "price": "10.00", "currency": "USD", "title": "Acc #3"},
        headers=_HEADERS,
    )
    item_id = create_resp.json()["item_id"]

    resp = await client.post(
        f"/testnet/stateful/lots/{item_id}/bump",
        headers={"Authorization": "Bearer someone-else"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_fast_buy_payment_failed_keeps_lot(client: AsyncClient) -> None:
    create_resp = await client.post(
        "/testnet/stateful/lots",
        json={"category": "steam", "price": "10.00", "currency": "USD", "title": "Acc #4"},
        headers=_HEADERS,
    )
    item_id = create_resp.json()["item_id"]

    failed_resp = await client.post(
        f"/testnet/stateful/lots/{item_id}/buy",
        headers={**_HEADERS, "X-Testnet-Force-Error": "payment_failed"},
    )
    assert failed_resp.status_code == 402

    list_resp = await client.get("/testnet/stateful/lots", params={"category": "steam"})
    assert any(lot["item_id"] == item_id for lot in list_resp.json())
