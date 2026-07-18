"""Tests for `build_route_table` / `RouteTable.match`."""

from __future__ import annotations

from lzt_testnet.catalog.route_table import build_route_table


def test_matches_known_path_with_placeholder() -> None:
    table = build_route_table(exclude_paths=frozenset())

    result = table.match("GET", "/posts/12345")

    assert result is not None
    entry, params = result
    assert entry.method_cls.__name__ == "PostsGet"
    assert params == {"post_id": "12345"}


def test_unmatched_path_returns_none() -> None:
    table = build_route_table(exclude_paths=frozenset())

    assert table.match("GET", "/this/path/does/not/exist") is None


def test_build_route_table_collects_roughly_two_hundred_entries() -> None:
    table = build_route_table(exclude_paths=frozenset())

    assert len(table._entries) >= 200  # noqa: SLF001 — internal count check, not public API


def test_exclude_paths_removes_matching_entries() -> None:
    full_table = build_route_table(exclude_paths=frozenset())
    excluded_table = build_route_table(exclude_paths=frozenset({"/posts/{post_id}"}))

    assert len(excluded_table._entries) == len(full_table._entries) - 1  # noqa: SLF001
    assert excluded_table.match("GET", "/posts/12345") is None
