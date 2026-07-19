"""T10 — Materializer: byte-stable refetch, spam→check-fails, buy-between-fetches drops the lot."""

from __future__ import annotations

from lzt_testnet.fake.generator import FakeGenerator
from lzt_testnet.state.lot_store import LotStore
from lzt_testnet.state.scenario_store import ScenarioStore
from lzt_testnet.world.builder import WorldBuilder, WorldConfig
from lzt_testnet.world.materializer import Materializer
from lzt_testnet.world.models import SellerQuality
from lzt_testnet.world.stores import ForumStore, SellerStore

_CFG = WorldConfig(roster_size=10, spam_ratio=0.5, forum_users=4, forum_threads=2)


def _materializer(seed: int) -> tuple[Materializer, LotStore, ScenarioStore, SellerStore]:
    sellers, forum = SellerStore(), ForumStore()
    WorldBuilder(seed, _CFG).populate(sellers=sellers, forum=forum)
    lots, scenario = LotStore(), ScenarioStore()
    mat = Materializer(seed, FakeGenerator(), lots, sellers, scenario, _CFG)
    return mat, lots, scenario, sellers


def test_refetch_is_byte_stable() -> None:
    mat, _, _, _ = _materializer(3)
    first = mat.page(category="steam", cursor=0, limit=5)
    second = mat.page(category="steam", cursor=0, limit=5)
    assert [(r.item_id, r.price, r.title, r.seller_token) for r in first] == [
        (r.item_id, r.price, r.title, r.seller_token) for r in second
    ]


def test_same_seed_across_instances() -> None:
    a, _, _, _ = _materializer(9)
    b, _, _, _ = _materializer(9)
    ap = a.page(category="steam", cursor=0, limit=5)
    bp = b.page(category="steam", cursor=0, limit=5)
    assert [r.item_id for r in ap] == [r.item_id for r in bp]
    assert [r.price for r in ap] == [r.price for r in bp]


def test_ids_above_user_lot_space() -> None:
    mat, _, _, _ = _materializer(1)
    page = mat.page(category="steam", cursor=0, limit=3)
    assert all(r.item_id > 1_000_000 for r in page)  # never collides with next_id lots (1,2,...)


def test_lot_check_fails_iff_spam_seller() -> None:
    mat, _, _, _ = _materializer(5)
    page = mat.page(category="steam", cursor=0, limit=20)
    saw_spam = saw_good = False
    for lot in page:
        expected = mat.seller_of(lot.item_id).quality is SellerQuality.SPAM
        assert mat.lot_check_fails(lot.item_id) is expected
        saw_spam |= expected
        saw_good |= not expected
    assert saw_spam and saw_good  # a 50/50 roster over 20 lots must show both


def test_buy_between_fetches_drops_lot() -> None:
    mat, lots, scenario, _ = _materializer(2)
    first = mat.page(category="steam", cursor=0, limit=5)
    victim = first[2].item_id
    lots.delete(victim)
    scenario.mark_bought(victim)
    second = mat.page(category="steam", cursor=0, limit=5)
    assert victim not in {r.item_id for r in second}
    assert len(second) == 4  # one slot skipped
