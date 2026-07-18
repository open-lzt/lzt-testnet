"""Tests for FakeGenerator against real pylzt models."""

from __future__ import annotations

from pylzt.models.lot import Lot

from lzt_testnet.fake.generator import FakeGenerator


def test_build_applies_overrides() -> None:
    generator = FakeGenerator()

    lot = generator.build(Lot, overrides={"item_id": 42})

    assert lot.item_id == 42


def test_build_round_trips_through_from_raw() -> None:
    generator = FakeGenerator()
    lot = generator.build(Lot, overrides={"item_id": 42})

    raw = lot.model_dump(mode="json")
    rebuilt = Lot.from_raw(raw)

    assert rebuilt.item_id == 42


def test_build_caches_factory_per_model() -> None:
    generator = FakeGenerator()

    generator.build(Lot)
    generator.build(Lot)

    assert len(generator._factories) == 1
