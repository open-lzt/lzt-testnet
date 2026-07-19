"""Proves the `testnet_client` fixture (`lzt_testnet.pytest_plugin`) round-trips a
real `pylzt.Client` call through the mock app in-process, one line, no manual wiring."""

from __future__ import annotations

from pylzt import Client
from pylzt.models.lot import Lot
from pylzt.types import ItemId


async def test_get_lot_round_trips_through_mock(testnet_client: Client) -> None:
    lot = await testnet_client.market.get_lot(ItemId(123))

    assert isinstance(lot, Lot)
    assert lot.content_hash
