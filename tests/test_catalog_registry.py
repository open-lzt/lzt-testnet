"""Proves `collect_base_methods` discovers the full pylzt method surface."""

from __future__ import annotations

from pylzt.methods.base import BaseMethod

from lzt_testnet.catalog.registry import collect_base_methods


def test_collect_base_methods_finds_the_full_surface() -> None:
    methods = collect_base_methods()

    assert len(methods) > 190
    assert len(set(methods)) == len(methods)
    assert all(issubclass(cls, BaseMethod) for cls in methods)
