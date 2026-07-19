"""T9 — world stores round-trip and paginate exactly like LotStore (id>cursor, full-page cursor)."""

from __future__ import annotations

from datetime import UTC, datetime

from lzt_testnet.world.models import ForumPost, ForumThread, ForumUser, SellerQuality, SellerRecord
from lzt_testnet.world.stores import ForumStore, SellerStore

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _seller(sid: int, quality: SellerQuality = SellerQuality.GOOD) -> SellerRecord:
    return SellerRecord(sid, f"tok{sid}", f"seller{sid}", quality, reputation=sid)


def test_seller_get_and_by_token() -> None:
    store = SellerStore()
    store.add(_seller(7))
    assert store.get(7) is not None
    assert store.by_token("tok7").seller_id == 7
    assert store.get(99) is None
    assert store.by_token("nope") is None


def test_seller_quality_filter() -> None:
    store = SellerStore()
    store.add(_seller(1, SellerQuality.GOOD))
    store.add(_seller(2, SellerQuality.SPAM))
    spam, _ = store.list(SellerQuality.SPAM, cursor=None, limit=10)
    assert [s.seller_id for s in spam] == [2]


def test_seller_cursor_pagination_matches_lotstore() -> None:
    store = SellerStore()
    for sid in range(1, 6):
        store.add(_seller(sid))
    page1, cursor1 = store.list(None, cursor=None, limit=2)
    assert [s.seller_id for s in page1] == [1, 2]
    assert cursor1 == 2
    page2, cursor2 = store.list(None, cursor=cursor1, limit=2)
    assert [s.seller_id for s in page2] == [3, 4]
    assert cursor2 == 4
    page3, cursor3 = store.list(None, cursor=cursor2, limit=2)
    assert [s.seller_id for s in page3] == [5]
    assert cursor3 is None  # partial page → no next cursor


def test_seller_limit_zero_no_crash() -> None:
    store = SellerStore()
    for sid in range(1, 4):
        store.add(_seller(sid))
    page, cursor = store.list(None, cursor=None, limit=0)  # 0 == len([]) must not IndexError
    assert page == []
    assert cursor is None


def test_forum_users_threads_posts() -> None:
    store = ForumStore()
    store.add_user(ForumUser(1, "alice", 100, _NOW))
    store.add_thread(ForumThread(1, author_id=1, title="hi", created_at=_NOW))
    store.add_post(ForumPost(2, thread_id=1, author_id=1, body="b", created_at=_NOW))
    store.add_post(ForumPost(1, thread_id=1, author_id=1, body="a", created_at=_NOW))

    users, _ = store.list_users(cursor=None, limit=10)
    assert [u.username for u in users] == ["alice"]
    threads, _ = store.list_threads(cursor=None, limit=10)
    assert [t.title for t in threads] == ["hi"]
    assert [p.post_id for p in store.posts_of(1)] == [1, 2]  # sorted by id
