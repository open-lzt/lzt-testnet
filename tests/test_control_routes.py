"""Tests for the testnet control routes (reset, revoke-token)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from lzt_testnet.api.control import router
from lzt_testnet.api.error_handlers import register_error_handlers
from lzt_testnet.config import get_settings
from lzt_testnet.state.lot_store import LotRecord, LotStore
from lzt_testnet.state.payment_store import PaymentStore
from lzt_testnet.state.scenario_store import ScenarioStore


def _build_app() -> FastAPI:
    app = FastAPI()
    app.state.lot_store = LotStore()
    app.state.payment_store = PaymentStore()
    app.state.scenario_store = ScenarioStore()
    register_error_handlers(app)
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


@pytest.mark.asyncio
async def test_reset_is_rejected_without_the_configured_control_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LZT_TESTNET_CONTROL_KEY", "s3cret")
    get_settings.cache_clear()
    try:
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

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            missing = await client.post("/testnet/reset")
            wrong = await client.post("/testnet/reset", headers={"X-Testnet-Control-Key": "guess"})
            assert missing.status_code == 401
            assert wrong.status_code == 401
            # The guard has to stop the wipe, not merely the 200 — assert before the key is used.
            assert lot_store.get(1) is not None

            correct = await client.post(
                "/testnet/reset", headers={"X-Testnet-Control-Key": "s3cret"}
            )

        assert correct.status_code == 200
        assert lot_store.get(1) is None
    finally:
        get_settings.cache_clear()
