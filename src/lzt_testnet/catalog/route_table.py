"""Builds a matchable route table from every collected `BaseMethod` subclass."""

from __future__ import annotations

import re
from dataclasses import dataclass

from pylzt.methods.base import BaseMethod, Passthrough
from pylzt.types import ApiTarget, HttpMethod, RateClass

from lzt_testnet.catalog.registry import collect_base_methods

__all__ = ["RouteEntry", "RouteTable", "build_route_table"]

_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _compile_path_pattern(url: str) -> tuple[re.Pattern[str], tuple[str, ...]]:
    """Converts `__url__`'s `{name}` placeholders into a named-group regex.

    Matches `build_request`'s own placeholder syntax exactly (`_URL_PLACEHOLDERS` in
    `pylzt.methods.base`), so a path this table matches is one `BaseMethod` could build.
    """
    names = tuple(_PLACEHOLDER.findall(url))
    escaped = re.escape(url)
    for name in names:
        escaped = escaped.replace(re.escape(f"{{{name}}}"), f"(?P<{name}>[^/]+)", 1)
    return re.compile(f"^{escaped}$"), names


@dataclass(frozen=True, slots=True)
class RouteEntry:
    """One `BaseMethod` endpoint, ready for reverse-matching against an incoming request."""

    http_method: HttpMethod
    api_target: ApiTarget
    rate_class: RateClass
    returning: type | None
    method_cls: type[BaseMethod]  # type: ignore[type-arg]  # frozen contract signature
    path_pattern: re.Pattern[str]
    path_param_names: tuple[str, ...]


class RouteTable:
    """Linear-scan lookup over `RouteEntry` instances — ~200 entries, fine for a mock server."""

    def __init__(self, entries: list[RouteEntry]) -> None:
        self._entries = entries

    def match(self, http_method: str, path: str) -> tuple[RouteEntry, dict[str, str]] | None:
        """Returns the matched entry + extracted path params, or `None` (-> 404 upstream)."""
        verb = http_method.upper()
        for entry in self._entries:
            if entry.http_method.value != verb:
                continue
            found = entry.path_pattern.fullmatch(path)
            if found is not None:
                return entry, found.groupdict()
        return None


def build_route_table(exclude_paths: frozenset[str]) -> RouteTable:
    """Collects every concrete `BaseMethod` and turns it into a `RouteEntry`.

    `exclude_paths` is checked against the raw `__url__` (exact string match) — the 6
    stateful endpoints handled by a separate named route, added in a later task.
    """
    entries: list[RouteEntry] = []
    for method_cls in collect_base_methods():
        url = method_cls.__url__
        if not url or url in exclude_paths:
            # Some BaseMethod subclasses (e.g. cursor-pagination helpers like
            # ListLotsPage/GetLotsBatch) carry an empty `__url__` — they compose
            # another method's request rather than owning a standalone HTTP route,
            # so there's no distinct path to serve here.
            continue
        returning = method_cls.__returning__
        pattern, param_names = _compile_path_pattern(url)
        entries.append(
            RouteEntry(
                http_method=method_cls.__http_method__,
                api_target=method_cls.__api__,
                rate_class=method_cls.__rate_class__,
                returning=None if isinstance(returning, Passthrough) else returning,
                method_cls=method_cls,
                path_pattern=pattern,
                path_param_names=param_names,
            )
        )
    return RouteTable(entries)
