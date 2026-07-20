"""An enveloped endpoint must be served enveloped.

34 of pylzt's ~212 methods declare `__unwrap__` — the single key the real API nests its payload
under (`GET /me` answers `{"user": {...}}`, not the user object flat). The mock served every one
of them flat, so a real client call raised a ValidationError for the RETURN type: the failure
read as "the model is wrong" while the actual fault was a missing envelope.

The round-trip suites did not catch it because they validated `response.json()` directly against
the return model, which is the one code path that never applies the unwrap.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pylzt.methods.base import Passthrough

from lzt_testnet.api.catch_all import router
from lzt_testnet.catalog.registry import collect_base_methods
from lzt_testnet.catalog.route_table import build_route_table
from lzt_testnet.fake.generator import FakeGenerator
from lzt_testnet.state.scenario_store import ScenarioStore


def _make_app() -> FastAPI:
    app = FastAPI()
    app.state.route_table = build_route_table(exclude_paths=frozenset())
    app.state.scenario_store = ScenarioStore()
    app.state.fake_generator = FakeGenerator()
    app.include_router(router)
    return app


def _enveloped_methods() -> list[type]:  # type: ignore[type-arg]
    """Methods that declare an envelope AND parse the result into a real model.

    `Passthrough` methods are excluded deliberately, not overlooked: `parse_response` reads the
    envelope with `body.get(...)` and then prefers `response.text`, so a missing key yields None
    rather than raising. The envelope only becomes load-bearing when `from_raw` runs on what was
    dug out — that is where a flat body turns into a ValidationError about the model.
    """
    seen: set[tuple[str, str]] = set()
    unique: list[type] = []  # type: ignore[type-arg]
    for cls in collect_base_methods():
        returning = cls.__returning__
        if not cls.__url__ or not cls.__unwrap__:
            continue
        if returning is None or isinstance(returning, Passthrough):
            continue
        key = (cls.__http_method__.value, cls.__url__)
        if key in seen:
            continue
        seen.add(key)
        unique.append(cls)
    return unique


def test_there_are_enveloped_methods_to_guard() -> None:
    """Guards the guard: if collection silently returned nothing, every case below would vacuously
    pass and the envelope could regress unnoticed."""
    assert len(_enveloped_methods()) > 5


@pytest.mark.parametrize("method_cls", _enveloped_methods(), ids=lambda cls: cls.__name__)
@pytest.mark.asyncio
async def test_the_payload_is_nested_under_the_declared_key(method_cls: type) -> None:  # type: ignore[type-arg]
    path = method_cls.__url__
    while "{" in path:
        start = path.index("{")
        path = path[:start] + "123" + path[path.index("}", start) + 1 :]

    app = _make_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.request(
            method_cls.__http_method__.value, path, headers={"Authorization": "Bearer t"}
        )

    assert response.status_code == 200
    match = app.state.route_table.match(method_cls.__http_method__.value, path)
    assert match is not None
    entry, _ = match
    unwrap = entry.method_cls.__unwrap__
    # `RouteTable.match` is a first-match linear scan, so a shared path prefix can resolve to a
    # different entry than the one parametrized. Assert against whatever actually answered.
    if not unwrap or entry.returning is None:
        return

    body = response.json()
    assert unwrap in body, f"{method_cls.__name__} served flat; client would fail to parse it"
