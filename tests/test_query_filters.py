"""Direct tests for the query-filter fold — 216 lines that had none.

The module exists because a filter that silently does nothing is indistinguishable from a filter
that works, so each test here asserts the fold actually moved the value.
"""

from __future__ import annotations

from typing import Any

from lzt_testnet.fake.query_filters import apply_query_filters


def _page(*items: dict[str, Any]) -> dict[str, Any]:
    return {"items": [dict(item) for item in items]}


def test_price_window_folds_an_out_of_range_int_inside_the_band() -> None:
    payload = apply_query_filters(_page({"price": 9_999}), {"pmin": "500", "pmax": "600"})
    assert 500 <= payload["items"][0]["price"] <= 600


def test_string_typed_balance_window_folds_and_stays_a_string() -> None:
    """`steam_balance` is declared `str` upstream; an int-only gate skipped it entirely."""
    payload = apply_query_filters(
        _page({"steam_balance": "9999"}), {"balance_min": "10", "balance_max": "20"}
    )
    value = payload["items"][0]["steam_balance"]
    assert isinstance(value, str)
    assert 10 <= int(value) <= 20


def test_pmax_only_never_folds_a_lot_down_to_free() -> None:
    payload = apply_query_filters(_page({"price": 10_000}), {"pmax": "10"})
    assert 1 <= payload["items"][0]["price"] <= 10


def test_a_non_numeric_value_in_a_window_field_is_left_alone() -> None:
    payload = apply_query_filters(_page({"steam_balance": "unknown"}), {"balance_min": "10"})
    assert payload["items"][0]["steam_balance"] == "unknown"


def test_a_window_never_invents_a_field_the_item_does_not_have() -> None:
    payload = apply_query_filters(_page({"price": 100}), {"balance_min": "10"})
    assert "steam_balance" not in payload["items"][0]


def test_exclude_rule_moves_an_excluded_value_away() -> None:
    payload = apply_query_filters(_page({"item_origin": "brute"}), {"not_origin": "brute"})
    assert payload["items"][0]["item_origin"] != "brute"


def test_flag_off_rule_clears_the_flag() -> None:
    payload = apply_query_filters(_page({"steam_community_ban": 1}), {"no_vac": "1"})
    assert not payload["items"][0]["steam_community_ban"]


def test_order_by_price_sorts_ascending() -> None:
    payload = apply_query_filters(
        _page({"price": 30}, {"price": 10}, {"price": 20}), {"order_by": "price_to_up"}
    )
    assert [item["price"] for item in payload["items"]] == [10, 20, 30]


def test_order_by_price_to_down_sorts_descending() -> None:
    payload = apply_query_filters(
        _page({"price": 10}, {"price": 30}, {"price": 20}), {"order_by": "price_to_down"}
    )
    assert [item["price"] for item in payload["items"]] == [30, 20, 10]


def test_an_unknown_param_changes_nothing() -> None:
    before = _page({"price": 100, "item_origin": "brute"})
    after = apply_query_filters(_page({"price": 100, "item_origin": "brute"}), {"nonsense": "1"})
    assert after == before
