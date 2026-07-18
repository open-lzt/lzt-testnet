"""In-memory store for market lots, keyed by item_id."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime


@dataclass
class LotRecord:
    item_id: int
    seller_token: str
    category: str
    price: str
    currency: str
    title: str
    published_at: datetime
    attributes: dict[str, str] = field(default_factory=dict)


class LotStore:
    """Plain dict-backed lot storage, single process, no locking."""

    def __init__(self) -> None:
        self._records: dict[int, LotRecord] = {}

    def create(self, record: LotRecord) -> LotRecord:
        self._records[record.item_id] = record
        return record

    def get(self, item_id: int) -> LotRecord | None:
        return self._records.get(item_id)

    def list(
        self,
        category: str | None,
        seller_token: str | None,
        cursor: int | None,
        limit: int,
    ) -> tuple[list[LotRecord], int | None]:
        candidates = [
            r
            for r in self._records.values()
            if (category is None or r.category == category)
            and (seller_token is None or r.seller_token == seller_token)
        ]
        candidates.sort(key=lambda r: r.item_id)
        if cursor is not None:
            candidates = [r for r in candidates if r.item_id > cursor]
        page = candidates[:limit]
        next_cursor = page[-1].item_id if len(page) == limit else None
        return page, next_cursor

    def update(self, item_id: int, **fields: object) -> LotRecord:
        record = self._records.get(item_id)
        if record is None:
            raise KeyError(item_id)
        # partial-field kwargs from **fields are untypeable statically
        updated = replace(record, **fields)  # type: ignore[arg-type]
        self._records[item_id] = updated
        return updated

    def delete(self, item_id: int) -> None:
        if item_id not in self._records:
            raise KeyError(item_id)
        del self._records[item_id]

    def reset(self) -> None:
        self._records.clear()
