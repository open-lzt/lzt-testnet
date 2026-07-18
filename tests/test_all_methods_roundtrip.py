"""Auto-generated round-trip test — one parametrized case per collected `BaseMethod`.

Unlike `test_stateless_roundtrip.py` (a fixed 20-method sample), this file discovers
every method via `collect_base_methods()` at collection time, so it grows/shrinks
automatically as pylzt adds/removes methods — no hand-maintained name list.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from lzt_testnet.api.catch_all import router
from lzt_testnet.catalog.registry import collect_base_methods
from lzt_testnet.catalog.route_table import build_route_table
from lzt_testnet.fake.generator import FakeGenerator
from lzt_testnet.state.scenario_store import ScenarioStore


def _build_request_path(url: str) -> str:
    """Fills every `{name}` placeholder in a route URL with a dummy value."""
    path = url
    while "{" in path:
        start = path.index("{")
        end = path.index("}", start)
        path = path[:start] + "123" + path[end + 1 :]
    return path


def _make_app() -> FastAPI:
    app = FastAPI()
    app.state.route_table = build_route_table(exclude_paths=frozenset())
    app.state.scenario_store = ScenarioStore()
    app.state.fake_generator = FakeGenerator()
    app.include_router(router)
    return app


def _all_methods() -> list[type]:  # type: ignore[type-arg]
    # dedupe by URL+http_method: several BaseMethod subclasses can share one route
    # template (e.g. differing only in query-param models), which would otherwise
    # produce redundant parametrize cases exercising the exact same code path.
    # Methods with an empty `__url__` (e.g. ListLotsPage/GetLotsBatch — cursor-
    # pagination helpers that compose another method's request rather than owning
    # a route of their own) are skipped: `build_route_table` doesn't register a
    # route for them either, so there is nothing here for the catch-all to serve.
    seen: set[tuple[str, str]] = set()
    unique: list[type] = []  # type: ignore[type-arg]
    for cls in collect_base_methods():
        if not cls.__url__:
            continue
        key = (cls.__http_method__.value, cls.__url__)
        if key in seen:
            continue
        seen.add(key)
        unique.append(cls)
    return unique


@pytest.mark.parametrize("method_cls", _all_methods(), ids=lambda cls: cls.__name__)
@pytest.mark.asyncio
async def test_method_roundtrip(method_cls: type) -> None:  # type: ignore[type-arg]
    app = _make_app()
    request_path = _build_request_path(method_cls.__url__)
    http_method = method_cls.__http_method__.value

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.request(
            http_method,
            request_path,
            headers={"Authorization": "Bearer testtoken"},
        )

    assert response.status_code == 200
    # `RouteTable.match` is a first-match linear scan (frozen contract): a shared path
    # prefix registered earlier can win over `method_cls`'s own entry, so validate
    # against whichever entry actually resolved for this path, not the method we
    # intended to exercise.
    match = app.state.route_table.match(http_method, request_path)
    assert match is not None
    matched_entry, _ = match
    returning = matched_entry.returning
    if returning is None:
        assert response.json() == {}
    else:
        returning.from_raw(response.json())
