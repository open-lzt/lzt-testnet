"""Smoke tests for the shared `client` fixture and its per-test isolation."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_client_fixture_hits_health(client: AsyncClient) -> None:
    response = await client.get("/testnet/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


_seen_lot_store_ids: set[int] = set()


@pytest.mark.asyncio
async def test_lot_store_is_fresh_per_test_a(client: AsyncClient) -> None:
    """Each `client` fixture invocation must build a brand-new app (and thus a new store)."""
    store = client._transport.app.state.lot_store  # noqa: SLF001 — whitebox isolation check

    assert id(store) not in _seen_lot_store_ids
    _seen_lot_store_ids.add(id(store))


@pytest.mark.asyncio
async def test_lot_store_is_fresh_per_test_b(client: AsyncClient) -> None:
    """A second, independent `client` fixture invocation must not reuse the prior test's store."""
    store = client._transport.app.state.lot_store  # noqa: SLF001 — whitebox isolation check

    assert id(store) not in _seen_lot_store_ids
    _seen_lot_store_ids.add(id(store))
