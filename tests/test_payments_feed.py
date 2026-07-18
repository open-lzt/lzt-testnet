"""Integration test: fast-buy produces one visible PaymentRecord in the payments feed."""

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

_TOKEN = "buyer-token-1"
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
async def test_fast_buy_records_one_payment(client: AsyncClient) -> None:
    create_resp = await client.post(
        "/testnet/stateful/lots",
        json={"category": "steam", "price": "42.50", "currency": "USD", "title": "Acc"},
        headers=_HEADERS,
    )
    item_id = create_resp.json()["item_id"]

    buy_resp = await client.post(f"/testnet/stateful/lots/{item_id}/buy", headers=_HEADERS)
    assert buy_resp.status_code == 200

    payments_resp = await client.get("/testnet/stateful/payments", headers=_HEADERS)
    assert payments_resp.status_code == 200
    payments = payments_resp.json()
    assert len(payments) == 1
    assert payments[0]["item_id"] == item_id
    assert payments[0]["amount"] == "42.50"
    assert payments[0]["operation_type"] == "purchase"
    assert payments[0]["account_token"] == _TOKEN


@pytest.mark.asyncio
async def test_payments_feed_scoped_to_token(client: AsyncClient) -> None:
    create_resp = await client.post(
        "/testnet/stateful/lots",
        json={"category": "steam", "price": "10.00", "currency": "USD", "title": "Acc"},
        headers=_HEADERS,
    )
    item_id = create_resp.json()["item_id"]
    await client.post(f"/testnet/stateful/lots/{item_id}/buy", headers=_HEADERS)

    other_resp = await client.get(
        "/testnet/stateful/payments", headers={"Authorization": "Bearer other-token"}
    )
    assert other_resp.json() == []
