"""Assemble a live world: build the roster + forum and wire the lazy lot Materializer over the
app's real stores. ``app.state.world`` holds this bundle (or ``None`` when no world is armed)."""

from __future__ import annotations

from dataclasses import dataclass

from lzt_testnet.fake.generator import FakeGenerator
from lzt_testnet.state.lot_store import LotStore
from lzt_testnet.state.scenario_store import ScenarioStore
from lzt_testnet.world.builder import WorldBuilder, WorldConfig
from lzt_testnet.world.materializer import Materializer
from lzt_testnet.world.stores import ForumStore, SellerStore


@dataclass(frozen=True, slots=True)
class WorldBundle:
    """The armed world on ``app.state.world``: seller roster, forum, and the lot materializer."""

    sellers: SellerStore
    forum: ForumStore
    materializer: Materializer


def build_world(
    *,
    seed: int,
    config: WorldConfig,
    lots: LotStore,
    scenario: ScenarioStore,
    generator: FakeGenerator,
) -> WorldBundle:
    """Populate a fresh roster + forum and wire a Materializer over the app's lot/scenario stores."""
    sellers, forum = SellerStore(), ForumStore()
    WorldBuilder(seed, config).populate(sellers=sellers, forum=forum)
    materializer = Materializer(seed, generator, lots, sellers, scenario, config)
    return WorldBundle(sellers=sellers, forum=forum, materializer=materializer)
