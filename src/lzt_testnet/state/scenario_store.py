"""In-memory store for forced-scenario flags (revoked tokens, bought items)."""

from __future__ import annotations


class ScenarioStore:
    """Tracks test-scenario state independent of LotStore/PaymentStore data."""

    def __init__(self) -> None:
        self.revoked_tokens: set[str] = set()
        self.bought_item_ids: set[int] = set()

    def revoke(self, token: str) -> None:
        self.revoked_tokens.add(token)

    def is_revoked(self, token: str) -> bool:
        return token in self.revoked_tokens

    def mark_bought(self, item_id: int) -> None:
        self.bought_item_ids.add(item_id)

    def was_bought(self, item_id: int) -> bool:
        return item_id in self.bought_item_ids

    def reset(self) -> None:
        self.revoked_tokens.clear()
        self.bought_item_ids.clear()
