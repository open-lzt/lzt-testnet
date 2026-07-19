"""Eager world construction — a SMALL seeded roster of sellers and a small forum.

Lots are deliberately NOT built here: they are lazily materialized on fetch (see ``Materializer``,
D11), which is what lets the world serve an effectively infinite streaming account list from a
finite, reproducible seed. Only the roster + forum, which are bounded, are populated up front.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from random import Random

from lzt_testnet.world.models import (
    ForumPost,
    ForumThread,
    ForumUser,
    SellerQuality,
    SellerRecord,
)
from lzt_testnet.world.stores import ForumStore, SellerStore

_BASE_TS = datetime(2026, 1, 1, tzinfo=UTC)  # fixed so builds are byte-stable (no wall-clock)


@dataclass(frozen=True, slots=True)
class WorldConfig:
    roster_size: int = 12
    spam_ratio: float = 0.4
    lots_per_spam_seller: int = 50
    forum_users: int = 30
    forum_threads: int = 20


class WorldBuilder:
    """Fills the seller roster and forum deterministically from one seed."""

    def __init__(self, seed: int, config: WorldConfig) -> None:
        self._rng = Random(f"{seed}:world")
        self._config = config

    def populate(self, *, sellers: SellerStore, forum: ForumStore) -> None:
        self._populate_sellers(sellers)
        self._populate_forum(forum)

    def _populate_sellers(self, sellers: SellerStore) -> None:
        cfg = self._config
        spam_count = round(cfg.roster_size * cfg.spam_ratio)
        qualities = [SellerQuality.SPAM] * spam_count + [SellerQuality.GOOD] * (
            cfg.roster_size - spam_count
        )
        self._rng.shuffle(qualities)
        for sid in range(1, cfg.roster_size + 1):
            sellers.add(
                SellerRecord(
                    seller_id=sid,
                    token=f"seller-tok-{sid}",
                    username=f"seller{sid}",
                    quality=qualities[sid - 1],
                    reputation=self._rng.randint(0, 1000),
                )
            )

    def _populate_forum(self, forum: ForumStore) -> None:
        cfg = self._config
        for uid in range(1, cfg.forum_users + 1):
            forum.add_user(ForumUser(uid, f"user{uid}", self._rng.randint(0, 5000), _BASE_TS))
        post_id = 0
        for tid in range(1, cfg.forum_threads + 1):
            thread = ForumThread(
                thread_id=tid,
                author_id=self._rng.randint(1, cfg.forum_users),
                title=f"thread {tid}",
                created_at=_BASE_TS,
            )
            forum.add_thread(thread)
            for _ in range(self._rng.randint(1, 4)):
                post_id += 1
                forum.add_post(
                    ForumPost(
                        post_id=post_id,
                        thread_id=tid,
                        author_id=self._rng.randint(1, cfg.forum_users),
                        body=f"post {post_id}",
                        created_at=_BASE_TS,
                    )
                )
                thread.post_ids.append(post_id)
