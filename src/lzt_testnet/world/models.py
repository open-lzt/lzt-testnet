"""The persistent world entities — a seeded roster of sellers and a small forum.

Plain mutable dataclasses mirroring the state-store record style (``LotRecord``): data + ids, no
behaviour. A ``SPAM`` seller is the deterministic blacklist signal — its lots fail the check.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class SellerQuality(StrEnum):
    """A seller is either honest or a spam-flooder whose lots fail verification."""

    GOOD = "good"
    SPAM = "spam"


@dataclass(slots=True)
class SellerRecord:
    seller_id: int
    token: str
    username: str
    quality: SellerQuality
    reputation: int
    lot_ids: list[int] = field(default_factory=list)


@dataclass(slots=True)
class ForumUser:
    user_id: int
    username: str
    reputation: int
    joined_at: datetime


@dataclass(slots=True)
class ForumThread:
    thread_id: int
    author_id: int
    title: str
    created_at: datetime
    post_ids: list[int] = field(default_factory=list)


@dataclass(slots=True)
class ForumPost:
    post_id: int
    thread_id: int
    author_id: int
    body: str
    created_at: datetime
