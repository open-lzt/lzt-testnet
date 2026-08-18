"""In-memory store for forum threads: their posts and the likes on each post.

Exists because the catch-all cannot answer these three endpoints honestly. ``posts_list`` and
``posts_likes`` are declared ``Passthrough`` upstream, so the route table carries no response model
for them and the catch-all replies ``{}`` with status 200. A flow that reads participants from a
thread then completes green having seen nobody — the worst shape a mock can take, because the run
looks like proof.

Threads are stateful for the same reason lots are: a giveaway posts a commitment, waits, reads the
thread back and expects to find what it wrote. A stateless generator answers every read with fresh
fake people and the scenario never closes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import count


@dataclass(slots=True)
class PostRecord:
    """One post. Field names mirror ``Resp_PostModel`` from the generated forum spec, not this
    mock's convenience — a caller decoding by those names must get the same keys here."""

    post_id: int
    thread_id: int
    poster_user_id: int
    poster_username: str
    post_body: str
    post_create_date: int


@dataclass(slots=True)
class ThreadRecord:
    thread_id: int
    title: str
    creator_user_id: int
    posts: list[PostRecord] = field(default_factory=list)
    #: post_id -> [(user_id, username)], in the order the likes arrived.
    likes: dict[int, list[tuple[int, str]]] = field(default_factory=dict)


class ThreadStore:
    """Plain dict-backed thread storage, single process, no locking — same posture as LotStore."""

    def __init__(self) -> None:
        self._threads: dict[int, ThreadRecord] = {}
        # Ids ascend so a caller can tell "posted after" from "posted before" without timestamps,
        # which a test would otherwise have to fake with sleeps.
        self._next_post_id = count(1)

    def reset(self) -> None:
        self._threads.clear()
        self._next_post_id = count(1)

    def ensure_thread(
        self, thread_id: int, *, title: str = "", creator_user_id: int = 1
    ) -> ThreadRecord:
        thread = self._threads.get(thread_id)
        if thread is None:
            thread = ThreadRecord(
                thread_id=thread_id,
                title=title or f"Тема {thread_id}",
                creator_user_id=creator_user_id,
            )
            self._threads[thread_id] = thread
        return thread

    def get(self, thread_id: int) -> ThreadRecord | None:
        return self._threads.get(thread_id)

    def add_post(
        self,
        thread_id: int,
        *,
        poster_user_id: int,
        poster_username: str,
        post_body: str,
    ) -> PostRecord:
        thread = self.ensure_thread(thread_id)
        post = PostRecord(
            post_id=next(self._next_post_id),
            thread_id=thread_id,
            poster_user_id=poster_user_id,
            poster_username=poster_username,
            post_body=post_body,
            post_create_date=int(datetime.now(UTC).timestamp()),
        )
        thread.posts.append(post)
        return post

    def page(self, thread_id: int, *, page: int, limit: int) -> tuple[list[PostRecord], int]:
        """One page of a thread's posts, plus the TOTAL count across all pages.

        The total is separate on purpose: a reader deciding whether to fetch page N+1 by the length
        of page N stops early on the last short page, and a giveaway that stops early drops the
        people who posted last. The real endpoint returns ``posts_total`` for exactly this.
        """
        thread = self._threads.get(thread_id)
        if thread is None:
            return [], 0
        start = max(page - 1, 0) * limit
        return thread.posts[start : start + limit], len(thread.posts)

    def like(self, post_id: int, *, user_id: int, username: str) -> bool:
        """Record a like. Returns False if this user already liked this post — the real forum
        counts a person once, and a mock that counted twice would hide a double-entry bug."""
        for thread in self._threads.values():
            if not any(p.post_id == post_id for p in thread.posts):
                continue
            likers = thread.likes.setdefault(post_id, [])
            if any(uid == user_id for uid, _ in likers):
                return False
            likers.append((user_id, username))
            return True
        return False

    def likers(self, post_id: int, *, page: int, limit: int) -> tuple[list[tuple[int, str]], int]:
        for thread in self._threads.values():
            if any(p.post_id == post_id for p in thread.posts):
                likers = thread.likes.get(post_id, [])
                start = max(page - 1, 0) * limit
                return likers[start : start + limit], len(likers)
        return [], 0
