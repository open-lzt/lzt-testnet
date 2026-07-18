"""Force-error header coverage for the stateful routes (T13)."""

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

_FORCE_ERROR_STATUS = {
    "rate_limited": 429,
    "auth_failed": 401,
    "not_found": 404,
    "transport_error": 500,
    "payment_failed": 402,
}


def _build_app() -> tuple[FastAPI, LotStore]:
    app = FastAPI()
    lot_store = LotStore()
    app.state.lot_store = lot_store
    app.state.payment_store = PaymentStore()
    app.state.scenario_store = ScenarioStore()
    app.state.fake_generator = FakeGenerator()
    app.include_router(router)
    register_error_handlers(app)
    return app, lot_store


@pytest.fixture
async def client_and_store() -> AsyncIterator[tuple[AsyncClient, LotStore]]:
    app, lot_store = _build_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, lot_store


@pytest.mark.asyncio
@pytest.mark.parametrize("force_error", list(_FORCE_ERROR_STATUS))
async def test_create_lot_force_error_no_mutation(
    client_and_store: tuple[AsyncClient, LotStore], force_error: str
) -> None:
    client, lot_store = client_and_store

    response = await client.post(
        "/testnet/stateful/lots",
        json={"category": "steam", "price": "10.00", "currency": "USD", "title": "Acc #1"},
        headers={**_HEADERS, "X-Testnet-Force-Error": force_error},
    )

    assert response.status_code == _FORCE_ERROR_STATUS[force_error]
    records, _next_cursor = lot_store.list(category=None, seller_token=None, cursor=None, limit=20)
    assert records == []


@pytest.mark.asyncio
async def test_fast_buy_payment_failed_keeps_lot(
    client_and_store: tuple[AsyncClient, LotStore],
) -> None:
    client, lot_store = client_and_store

    create_resp = await client.post(
        "/testnet/stateful/lots",
        json={"category": "steam", "price": "10.00", "currency": "USD", "title": "Acc #1"},
        headers=_HEADERS,
    )
    assert create_resp.status_code == 200
    item_id = create_resp.json()["item_id"]

    buy_resp = await client.post(
        f"/testnet/stateful/lots/{item_id}/buy",
        headers={**_HEADERS, "X-Testnet-Force-Error": "payment_failed"},
    )

    assert buy_resp.status_code == 402
    assert lot_store.get(item_id) is not None
