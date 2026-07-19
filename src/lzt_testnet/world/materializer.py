"""Lazy lot inventory — materialize-on-fetch (D11).

The world never pre-builds lots. The first time a page is fetched, each slot's lot is generated
from a *query-keyed* seed (``seed:category:index``) and persisted into the real ``LotStore``; a
refetch serves the persisted record, so it is byte-stable. Because the id is a pure function of
(seed, category, index) — NOT ``SeedController.next_id`` (call-order dependent) — the same page
is reproducible across processes, yet a buy between two fetches removes that lot from the second.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from random import Random

from lzt_testnet.fake.generator import FakeGenerator
from lzt_testnet.state.lot_store import LotRecord, LotStore
from lzt_testnet.state.scenario_store import ScenarioStore
from lzt_testnet.world.builder import WorldConfig
from lzt_testnet.world.models import SellerQuality, SellerRecord
from lzt_testnet.world.stores import SellerStore

_BASE_TS = datetime(2026, 1, 1, tzinfo=UTC)


class Materializer:
    """Generates + persists lots on first fetch and tracks each lot's owning seller."""

    def __init__(
        self,
        seed: int,
        generator: FakeGenerator,
        lots: LotStore,
        sellers: SellerStore,
        scenario: ScenarioStore,
        config: WorldConfig,
    ) -> None:
        self._seed = seed
        self._generator = generator
        self._lots = lots
        self._sellers = sellers
        self._scenario = scenario
        self._config = config
        self._owner: dict[int, int] = {}  # materialized item_id -> owning seller_id

    def stable_id(self, category: str, index: int) -> int:
        """Deterministic 48-bit id for slot #index of `category` — a pure function of the seed.

        ponytail: 48-bit space, collision-free at world scale (< millions of lots); sits far above
        the small next_id space so it never clashes with user-created lots.
        """
        digest = hashlib.sha256(f"{self._seed}:{category}:{index}".encode()).digest()
        return int.from_bytes(digest[:6], "big")

    def page(self, *, category: str, cursor: int, limit: int) -> list[LotRecord]:
        """Materialize (or serve) lots for indices [cursor, cursor+limit), skipping bought ids."""
        roster = self._roster()
        out: list[LotRecord] = []
        for index in range(cursor, cursor + limit):
            item_id = self.stable_id(category, index)
            if self._scenario.was_bought(item_id):
                continue  # a buyer took this slot between fetches
            existing = self._lots.get(item_id)
            if existing is not None:
                out.append(existing)
                continue
            out.append(self._materialize(category, index, item_id, roster))
        return out

    def seller_of(self, item_id: int) -> SellerRecord:
        seller = self._sellers.get(self._owner[item_id])
        if seller is None:  # pragma: no cover - owner map only holds valid ids
            raise KeyError(item_id)
        return seller

    def lot_check_fails(self, item_id: int) -> bool:
        """True iff the lot's owning seller is SPAM — the deterministic blacklist / bad-lot signal.

        Only known (already-materialized) lots can fail; an unseen id is treated as clean.
        """
        seller_id = self._owner.get(item_id)
        if seller_id is None:
            return False
        seller = self._sellers.get(seller_id)
        return seller is not None and seller.quality is SellerQuality.SPAM

    def _roster(self) -> list[SellerRecord]:
        records, _ = self._sellers.list(None, cursor=None, limit=10_000)
        return records

    def _materialize(
        self, category: str, index: int, item_id: int, roster: list[SellerRecord]
    ) -> LotRecord:
        rng = Random(f"{self._seed}:{category}:{index}")
        owner = roster[rng.randrange(len(roster))] if roster else None
        record = LotRecord(
            item_id=item_id,
            seller_token=owner.token if owner is not None else "seller-tok-0",
            category=category,
            price=f"{rng.uniform(1.0, 100.0):.2f}",
            currency="usd",
            title=f"{category} account #{index}",
            published_at=_BASE_TS,
        )
        self._lots.create(record)
        if owner is not None:
            self._owner[item_id] = owner.seller_id
        return record
