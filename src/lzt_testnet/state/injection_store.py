"""Lots pushed into a catalog listing on demand, so a poller can observe a change.

The catalog itself is generated once per model and cached, which makes every listing of a
category byte-identical forever. That is correct for a mock — a caller gets a stable world —
but it makes the whole class of "something new appeared" behaviour unobservable: a diffing
consumer seeds its baseline on the first poll and then sees a zero diff for the rest of time.

An injected lot is the missing verb. It is stored per category, prepended to that category's
next listings, and cleared by `POST /testnet/reset` along with every other piece of state.
"""

from __future__ import annotations

from itertools import count
from typing import Any


class InjectionStore:
    """Per-category lots that the catch-all prepends to a generated listing."""

    def __init__(self) -> None:
        self._by_category: dict[str, list[dict[str, Any]]] = {}
        self._ids = count(900_000_001)

    def next_item_id(self) -> int:
        """Ids from a band the generator never mints, so an injected lot is recognisable."""
        return next(self._ids)

    def add(self, category: str, lot: dict[str, Any]) -> None:
        self._by_category.setdefault(category, []).append(lot)

    def for_category(self, category: str) -> list[dict[str, Any]]:
        return list(self._by_category.get(category, ()))

    def reset(self) -> None:
        self._by_category.clear()
