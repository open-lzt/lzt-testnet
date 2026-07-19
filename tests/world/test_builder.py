"""T10 — WorldBuilder fills a small, reproducible roster + forum, deterministic by seed."""

from __future__ import annotations

from lzt_testnet.world.builder import WorldBuilder, WorldConfig
from lzt_testnet.world.models import SellerQuality
from lzt_testnet.world.stores import ForumStore, SellerStore

_CFG = WorldConfig(roster_size=12, spam_ratio=0.4, forum_users=8, forum_threads=6)


def _build(seed: int) -> tuple[SellerStore, ForumStore]:
    sellers, forum = SellerStore(), ForumStore()
    WorldBuilder(seed, _CFG).populate(sellers=sellers, forum=forum)
    return sellers, forum


def test_spam_ratio_holds() -> None:
    sellers, _ = _build(42)
    roster, _ = sellers.list(None, cursor=None, limit=100)
    spam = [s for s in roster if s.quality is SellerQuality.SPAM]
    assert len(roster) == 12
    assert abs(len(spam) - 12 * 0.4) <= 1  # +-1 seller


def test_same_seed_identical_build() -> None:
    a_sellers, a_forum = _build(7)
    b_sellers, b_forum = _build(7)
    a_roster, _ = a_sellers.list(None, cursor=None, limit=100)
    b_roster, _ = b_sellers.list(None, cursor=None, limit=100)
    assert [(s.seller_id, s.quality, s.reputation) for s in a_roster] == [
        (s.seller_id, s.quality, s.reputation) for s in b_roster
    ]
    assert list(a_forum.users) == list(b_forum.users)
    assert list(a_forum.threads) == list(b_forum.threads)


def test_forum_populated() -> None:
    _, forum = _build(1)
    users, _ = forum.list_users(cursor=None, limit=100)
    threads, _ = forum.list_threads(cursor=None, limit=100)
    assert len(users) == 8
    assert len(threads) == 6
    assert all(forum.posts_of(t.thread_id) for t in threads)  # every thread has >=1 post
