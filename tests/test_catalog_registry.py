"""Proves `collect_base_methods` discovers the full pylzt method surface."""

from __future__ import annotations

from pylzt.methods.base import BaseMethod

from lzt_testnet.catalog.registry import collect_base_methods
from lzt_testnet.catalog.route_table import build_route_table

# pylzt declares these routes twice (alias classes). Only the first can ever be served; the
# other is recorded as shadowed. Pinned here so a NEW collision — which would silently steal a
# route from whichever class loses the ordering — fails instead of disappearing.
_KNOWN_SHADOWED = (
    ("POST", "/search", "SearchAll"),
    ("POST", "/claims", "ManagingCreateClaim"),
    ("POST", "/batch", "Batch"),
)


def test_collect_base_methods_finds_the_full_surface() -> None:
    methods = collect_base_methods()

    assert len(methods) > 190
    assert len(set(methods)) == len(methods)
    assert all(issubclass(cls, BaseMethod) for cls in methods)


def test_collect_base_methods_order_is_stable_across_calls() -> None:
    """The walk accumulates into a `set`; unsorted, route precedence would vary per process."""
    keys = [f"{cls.__module__}.{cls.__qualname__}" for cls in collect_base_methods()]
    assert keys == [f"{cls.__module__}.{cls.__qualname__}" for cls in collect_base_methods()]
    assert keys == sorted(keys)


def test_route_table_records_exactly_the_known_route_collisions() -> None:
    assert build_route_table(frozenset()).shadowed == _KNOWN_SHADOWED
