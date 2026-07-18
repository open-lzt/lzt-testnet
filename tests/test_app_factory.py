"""Tests for the FastAPI app factory."""

from __future__ import annotations

import httpx
import pytest

from lzt_testnet.api.app import create_app
from lzt_testnet.catalog.route_table import RouteTable


@pytest.mark.asyncio
async def test_health_endpoint_returns_ok() -> None:
    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/testnet/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_route_table_is_populated() -> None:
    app = create_app()
    route_table = app.state.route_table

    assert isinstance(route_table, RouteTable)
    assert len(route_table._entries) > 0  # noqa: SLF001 — whitebox check of internal contract state
