"""Makes a generated catalog page actually satisfy the query that asked for it.

The generator invents each field independently and knows nothing about the request, so a search
for "steam accounts under 10 ₽, no VAC" came back with thousand-rouble VAC-banned lots: the wiring
looked right and every filter was decorative. Anything built against that mock passes its tests and
breaks on the real marketplace — the worst failure a testnet can have.

The rule here is the one the real API follows: **a filtered search returns only matching items**.
So rather than dropping the generated items (an empty page teaches a caller nothing) each filter
*folds* them into compliance — a price window clamps, an equality filter overwrites, an exclusion
filter picks something else. The page stays full and every item honours the query.

A filter applies only when its field is actually present on the generated item, so one table
serves every category: `steam_country` quietly does nothing on an Instagram item.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

__all__ = ["apply_query_filters"]

_TRUE = frozenset({"1", "true", "yes", "on"})


def _as_int(raw: str) -> int | None:
    try:
        return int(float(raw))
    except ValueError:
        return None


def _split(raw: str) -> list[str]:
    """`a,b` and repeated `?x=a&x=b` both reach us as one comma-joined string."""
    return [part.strip() for part in raw.split(",") if part.strip()]


@dataclass(frozen=True, slots=True)
class _Rule:
    """One query param bound to one item field, plus how it folds a value into compliance."""

    field: str
    fold: Callable[[Any, str], Any]


@dataclass(frozen=True, slots=True)
class _Bound:
    """One half of a numeric window: `pmin`/`pmax` both constrain the same field."""

    field: str
    is_low: bool


def _exact(current: Any, raw: str) -> Any:
    """`origin=brute` — the caller asked for exactly this, so that is what it gets."""
    values = _split(raw)
    if not values:
        return current
    if isinstance(current, int):
        parsed = _as_int(values[0])
        return current if parsed is None else parsed
    return values[0]


def _exclude(current: Any, raw: str) -> Any:
    """`not_origin=brute,stealer` — if the generator picked an excluded value, move off it."""
    banned = {value.casefold() for value in _split(raw)}
    if not banned or not isinstance(current, str):
        return current
    return current if current.casefold() not in banned else "generated"


def _flag_off(current: Any, raw: str) -> Any:
    """`no_vac=1` — the caller wants the flag absent, so clear it."""
    if raw.strip().casefold() not in _TRUE:
        return current
    return 0 if isinstance(current, int) else current


def _flag_on(current: Any, raw: str) -> Any:
    """`mafile=1` — the caller wants the flag present."""
    if raw.strip().casefold() not in _TRUE:
        return current
    return 1 if isinstance(current, int) else current


def _contains(current: Any, raw: str) -> Any:
    """`title=cs2` — a substring search must return titles containing it."""
    needle = raw.strip()
    if not needle or not isinstance(current, str):
        return current
    return current if needle.casefold() in current.casefold() else f"{needle} {current}"


# Query param -> the item field it constrains. Params naming a field the item does not carry are
# skipped, so this one table covers every category the mock serves.
_RULES: Mapping[str, _Rule] = {
    "title": _Rule("title", _contains),
    "origin": _Rule("item_origin", _exact),
    "not_origin": _Rule("item_origin", _exclude),
    "item_domain": _Rule("item_domain", _exact),
    "email_type": _Rule("email_type", _exact),
    "email_provider": _Rule("email_provider", _exact),
    "not_email_provider": _Rule("email_provider", _exclude),
    "country": _Rule("steam_country", _exact),
    "not_country": _Rule("steam_country", _exclude),
    "user_id": _Rule("user_id", _exact),
    "category_id": _Rule("category_id", _exact),
    "nsb": _Rule("nsb", _flag_on),
    "sb": _Rule("nsb", _flag_off),
    "no_vac": _Rule("steam_community_ban", _flag_off),
    "mm_ban": _Rule("steam_community_ban", _flag_off),
    "mafile": _Rule("steam_mafile", _flag_on),
    "trade_ban": _Rule("steam_is_limited", _flag_off),
    "trade_limit": _Rule("steam_is_limited", _flag_off),
}

# Numeric windows. Both halves name the same field on purpose: applying `pmin` and `pmax` as two
# independent folds lets them fight — the low bound pushes a value up, the high bound wraps it back
# under, and `pmin=500&pmax=600` lands on 499. One field, one window, folded once.
_BOUNDS: Mapping[str, _Bound] = {
    "pmin": _Bound("price", True),
    "pmax": _Bound("price", False),
    "reg": _Bound("steam_register_date", True),
    "daybreak": _Bound("steam_last_activity", False),
    "lmin": _Bound("steam_level", True),
    "lmax": _Bound("steam_level", False),
    "balance_min": _Bound("steam_balance", True),
    "balance_max": _Bound("steam_balance", False),
    "inv_min": _Bound("steam_inv_value", True),
    "inv_max": _Bound("steam_inv_value", False),
    "friends_min": _Bound("steam_friend_count", True),
    "friends_max": _Bound("steam_friend_count", False),
    "cs2_profile_rank_min": _Bound("steam_cs2_profile_rank", True),
    "cs2_profile_rank_max": _Bound("steam_cs2_profile_rank", False),
    "faceit_lvl_min": _Bound("steam_faceit_level", True),
    "faceit_lvl_max": _Bound("steam_faceit_level", False),
    "view_count_min": _Bound("view_count", True),
    "view_count_max": _Bound("view_count", False),
}

# `order_by` value -> (item field, descending). The real API sorts server-side; a caller that takes
# "the cheapest" off the top of an unsorted page would be silently wrong here.
_ORDERINGS: Mapping[str, tuple[str, bool]] = {
    "price_to_up": ("price", False),
    "price_to_down": ("price", True),
    "pdate_to_down": ("published_date", True),
    "pdate_to_up": ("published_date", False),
    "edate_to_down": ("edit_date", True),
    "ddate_to_down": ("refreshed_date", True),
}


def _sort_key(item: dict[str, Any], field: str) -> tuple[int, float]:
    value = item.get(field)
    if isinstance(value, int | float):
        return (0, float(value))
    return (1, 0.0)


def _collect_windows(params: Mapping[str, str]) -> dict[str, tuple[int | None, int | None]]:
    """Merge every `*_min`/`*_max` param into one (low, high) window per field."""
    windows: dict[str, tuple[int | None, int | None]] = {}
    for name, raw in params.items():
        bound = _BOUNDS.get(name)
        value = _as_int(raw) if bound is not None else None
        if bound is None or value is None:
            continue
        low, high = windows.get(bound.field, (None, None))
        windows[bound.field] = (value, high) if bound.is_low else (low, value)
    return windows


def _fold_into_window(value: int, low: int | None, high: int | None) -> int:
    """Bring a generated number inside [low, high], keeping some spread across the band."""
    if low is not None and high is not None and high >= low:
        return low + value % (high - low + 1)
    if high is not None:
        # Floor at 1, not 0: a bare `pmax=10` folding a big number down by modulo can land on zero,
        # and a free lot is not something the real catalog ever returns — a caller reasoning about
        # "cheapest" would draw the wrong conclusion from it.
        return value if value <= high else 1 + value % max(high, 1)
    if low is not None:
        return value if value >= low else low + value % max(low, 1)
    return value


def apply_query_filters(payload: dict[str, Any], params: Mapping[str, str]) -> dict[str, Any]:
    """Fold a generated `items` page into compliance with the query, then order it."""
    items = payload.get("items")
    if not isinstance(items, list):
        return payload

    for field, (low, high) in _collect_windows(params).items():
        for item in items:
            if isinstance(item, dict) and isinstance(item.get(field), int):
                item[field] = _fold_into_window(item[field], low, high)

    for name, raw in params.items():
        rule = _RULES.get(name)
        if rule is None:
            continue
        for item in items:
            if isinstance(item, dict) and rule.field in item:
                item[rule.field] = rule.fold(item[rule.field], raw)

    ordering = _ORDERINGS.get(params.get("order_by", ""))
    if ordering is not None:
        field, descending = ordering
        typed: Sequence[dict[str, Any]] = [row for row in items if isinstance(row, dict)]
        if len(typed) == len(items):
            items.sort(key=lambda row: _sort_key(row, field), reverse=descending)
    return payload
