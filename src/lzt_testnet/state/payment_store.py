"""In-memory store for payment operations, append-only per account."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PaymentRecord:
    operation_id: int
    account_token: str
    operation_type: str
    item_id: int
    amount: str


class PaymentStore:
    """Plain list-backed payment log, single process, no locking."""

    def __init__(self) -> None:
        self._records: list[PaymentRecord] = []

    def append(self, record: PaymentRecord) -> None:
        self._records.append(record)

    def list(
        self,
        account_token: str,
        cursor: int | None,
        limit: int,
    ) -> tuple[list[PaymentRecord], int | None]:
        candidates = [r for r in self._records if r.account_token == account_token]
        candidates.sort(key=lambda r: r.operation_id)
        if cursor is not None:
            candidates = [r for r in candidates if r.operation_id > cursor]
        page = candidates[:limit]
        next_cursor = page[-1].operation_id if len(page) == limit else None
        return page, next_cursor

    def reset(self) -> None:
        self._records.clear()
