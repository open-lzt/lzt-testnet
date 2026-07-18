"""Tests for the testnet control routes (reset, revoke-token)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from lzt_testnet.api.control import router
from lzt_testnet.state.lot_store import LotRecord, LotStore
from lzt_testnet.state.payment_store import PaymentStore
from lzt_testnet.state.scenario_store import ScenarioStore


def _build_app() -> FastAPI:
    app = FastAPI()
    app.state.lot_store = LotStore()
    app.state.payment_store = PaymentStore()
    app.state.scenario_store = ScenarioStore()
    app.include_router(router)
    return app


@pytest.mark.asyncio
async def test_reset_clears_lot_store() -> None:
    app = _build_app()
    lot_store: LotStore = app.state.lot_store
    lot_store.create(
        LotRecord(
            item_id=1,
            seller_token="seller-token",
            category="steam",
            price="10.00",
            currency="USD",
            title="test lot",
            published_at=datetime.now(UTC),
        )
    )
    assert lot_store.get(1) is not None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/testnet/reset")

    assert response.status_code == 200
    assert response.json() == {"status": "reset"}
    assert lot_store.get(1) is None


@pytest.mark.asyncio
async def test_revoke_token_marks_token_revoked() -> None:
    app = _build_app()
    scenario_store: ScenarioStore = app.state.scenario_store
    token = "bearer-abc123"
    assert scenario_store.is_revoked(token) is False

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/testnet/revoke-token", json={"token": token})

    assert response.status_code == 200
    assert response.json() == {"status": "revoked", "token": token}
    assert scenario_store.is_revoked(token) is True
