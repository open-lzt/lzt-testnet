"""In-memory world stores — dict-backed with cursor pagination matching ``LotStore`` semantics."""

from __future__ import annotations

from collections.abc import Callable

from lzt_testnet.world.models import (
    ForumPost,
    ForumThread,
    ForumUser,
    SellerQuality,
    SellerRecord,
)


def _page[T](
    records: list[T], key: Callable[[T], int], cursor: int | None, limit: int
) -> tuple[list[T], int | None]:
    """Cursor page: sort by id, take ids > cursor, next_cursor only on a full page."""
    ordered = sorted(records, key=key)
    if cursor is not None:
        ordered = [r for r in ordered if key(r) > cursor]
    page = ordered[:limit] if limit > 0 else []
    next_cursor = key(page[-1]) if page and len(page) == limit else None
    return page, next_cursor


class SellerStore:
    """Seeded seller roster, keyed by id, with a token index (mirrors LotStore)."""

    def __init__(self) -> None:
        self._records: dict[int, SellerRecord] = {}
        self._by_token: dict[str, int] = {}

    def add(self, record: SellerRecord) -> SellerRecord:
        self._records[record.seller_id] = record
        self._by_token[record.token] = record.seller_id
        return record

    def get(self, seller_id: int) -> SellerRecord | None:
        return self._records.get(seller_id)

    def by_token(self, token: str) -> SellerRecord | None:
        seller_id = self._by_token.get(token)
        return self._records.get(seller_id) if seller_id is not None else None

    def list(
        self, quality: SellerQuality | None, cursor: int | None, limit: int
    ) -> tuple[list[SellerRecord], int | None]:
        candidates = [r for r in self._records.values() if quality is None or r.quality is quality]
        return _page(candidates, lambda r: r.seller_id, cursor, limit)

    def reset(self) -> None:
        self._records.clear()
        self._by_token.clear()


class ForumStore:
    """Seeded forum: users, threads, and posts — each cursor-paginated by its own id."""

    def __init__(self) -> None:
        self.users: dict[int, ForumUser] = {}
        self.threads: dict[int, ForumThread] = {}
        self.posts: dict[int, ForumPost] = {}

    def add_user(self, user: ForumUser) -> None:
        self.users[user.user_id] = user

    def add_thread(self, thread: ForumThread) -> None:
        self.threads[thread.thread_id] = thread

    def add_post(self, post: ForumPost) -> None:
        self.posts[post.post_id] = post

    def list_users(self, cursor: int | None, limit: int) -> tuple[list[ForumUser], int | None]:
        return _page(list(self.users.values()), lambda u: u.user_id, cursor, limit)

    def list_threads(self, cursor: int | None, limit: int) -> tuple[list[ForumThread], int | None]:
        return _page(list(self.threads.values()), lambda t: t.thread_id, cursor, limit)

    def posts_of(self, thread_id: int) -> list[ForumPost]:
        posts = [p for p in self.posts.values() if p.thread_id == thread_id]
        return sorted(posts, key=lambda p: p.post_id)

    def reset(self) -> None:
        self.users.clear()
        self.threads.clear()
        self.posts.clear()
