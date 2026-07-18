"""Unit tests for the in-memory state stores."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from lzt_testnet.state.lot_store import LotRecord, LotStore
from lzt_testnet.state.payment_store import PaymentRecord, PaymentStore
from lzt_testnet.state.scenario_store import ScenarioStore


def _lot(item_id: int, seller_token: str = "tok-1", category: str = "steam") -> LotRecord:
    return LotRecord(
        item_id=item_id,
        seller_token=seller_token,
        category=category,
        price="10.00",
        currency="USD",
        title=f"lot-{item_id}",
        published_at=datetime.now(UTC),
    )


class TestLotStore:
    def test_create_and_get(self) -> None:
        store = LotStore()
        record = _lot(1)
        store.create(record)
        assert store.get(1) == record
        assert store.get(999) is None

    def test_update_applies_only_given_fields(self) -> None:
        store = LotStore()
        store.create(_lot(1))
        updated = store.update(1, price="20.00")
        assert updated.price == "20.00"
        assert updated.title == "lot-1"

    def test_update_missing_raises_keyerror(self) -> None:
        store = LotStore()
        with pytest.raises(KeyError):
            store.update(1, price="1.00")

    def test_delete(self) -> None:
        store = LotStore()
        store.create(_lot(1))
        store.delete(1)
        assert store.get(1) is None
        with pytest.raises(KeyError):
            store.delete(1)

    def test_list_filters_and_paginates(self) -> None:
        store = LotStore()
        for i in range(1, 6):
            store.create(_lot(i, seller_token="tok-1" if i % 2 else "tok-2"))

        page, next_cursor = store.list(category=None, seller_token=None, cursor=None, limit=2)
        assert [r.item_id for r in page] == [1, 2]
        assert next_cursor == 2

        page2, next_cursor2 = store.list(
            category=None, seller_token=None, cursor=next_cursor, limit=2
        )
        assert [r.item_id for r in page2] == [3, 4]
        assert next_cursor2 == 4

        page3, next_cursor3 = store.list(
            category=None, seller_token=None, cursor=next_cursor2, limit=2
        )
        assert [r.item_id for r in page3] == [5]
        assert next_cursor3 is None

        filtered, _ = store.list(category=None, seller_token="tok-1", cursor=None, limit=10)
        assert {r.item_id for r in filtered} == {1, 3, 5}

    def test_reset(self) -> None:
        store = LotStore()
        store.create(_lot(1))
        store.reset()
        assert store.get(1) is None


class TestPaymentStore:
    def test_append_and_list_cursor_pagination(self) -> None:
        store = PaymentStore()
        for i in range(1, 4):
            store.append(
                PaymentRecord(
                    operation_id=i,
                    account_token="tok-1",
                    operation_type="purchase",
                    item_id=100 + i,
                    amount="5.00",
                )
            )
        store.append(
            PaymentRecord(
                operation_id=99,
                account_token="tok-2",
                operation_type="purchase",
                item_id=1,
                amount="1.00",
            )
        )

        page, next_cursor = store.list(account_token="tok-1", cursor=None, limit=2)
        assert [r.operation_id for r in page] == [1, 2]
        assert next_cursor == 2

        page2, next_cursor2 = store.list(account_token="tok-1", cursor=next_cursor, limit=2)
        assert [r.operation_id for r in page2] == [3]
        assert next_cursor2 is None

        other, _ = store.list(account_token="tok-2", cursor=None, limit=10)
        assert [r.operation_id for r in other] == [99]

    def test_reset(self) -> None:
        store = PaymentStore()
        store.append(
            PaymentRecord(
                operation_id=1,
                account_token="tok-1",
                operation_type="purchase",
                item_id=1,
                amount="1.00",
            )
        )
        store.reset()
        page, _ = store.list(account_token="tok-1", cursor=None, limit=10)
        assert page == []


class TestScenarioStore:
    def test_revoke_and_is_revoked(self) -> None:
        store = ScenarioStore()
        assert store.is_revoked("tok-1") is False
        store.revoke("tok-1")
        assert store.is_revoked("tok-1") is True

    def test_mark_bought_and_was_bought(self) -> None:
        store = ScenarioStore()
        assert store.was_bought(1) is False
        store.mark_bought(1)
        assert store.was_bought(1) is True

    def test_reset(self) -> None:
        store = ScenarioStore()
        store.revoke("tok-1")
        store.mark_bought(1)
        store.reset()
        assert store.is_revoked("tok-1") is False
        assert store.was_bought(1) is False
