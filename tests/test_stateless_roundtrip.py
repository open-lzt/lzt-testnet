"""Round-trip tests for the generic stateless catch-all route (T10)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from lzt_testnet.api.catch_all import router
from lzt_testnet.catalog.registry import collect_base_methods
from lzt_testnet.catalog.route_table import build_route_table
from lzt_testnet.state.scenario_store import ScenarioStore

_SAMPLE_METHOD_NAMES = [
    "ProfilePostsUnlike",
    "LinksGet",
    "MangingDelete",
    "PublishingCheck",
    "ProfilePostsUnstick",
    "ManagingPublicUntag",
    "UsersUnfollow",
    "ThreadsPollVote",
    "UsersContents",
    "ManagingSteamPreview",
    "ThreadsPollGet",
    "ManagingAIPrice",
    "ProxyGet",
    "ChatboxGetLeaderboard",
    "ListFavorites",
    "CustomDiscountsGet",
    "NotificationsRead",
    "CategoryVpn",
    "LicenseCheckLicense",
    "ThreadsRecent",
]


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
    from lzt_testnet.fake.generator import FakeGenerator

    app.state.fake_generator = FakeGenerator()
    app.include_router(router)
    return app


def _sample_methods() -> list[type]:  # type: ignore[type-arg]
    by_name = {cls.__name__: cls for cls in collect_base_methods()}
    return [by_name[name] for name in _SAMPLE_METHOD_NAMES]


@pytest.mark.parametrize("method_cls", _sample_methods(), ids=lambda cls: cls.__name__)
@pytest.mark.asyncio
async def test_stateless_route_roundtrip(method_cls: type) -> None:  # type: ignore[type-arg]
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
    # prefix earlier in registration order can win over `method_cls`'s own entry, so
    # validate against whichever entry actually resolved for this path, not the method
    # we intended to sample.
    match = app.state.route_table.match(http_method, request_path)
    assert match is not None
    matched_entry, _ = match
    returning = matched_entry.returning
    if returning is None:
        assert response.json() == {}
    else:
        # Validate the way the CLIENT does. `BaseMethod.parse_response` digs `__unwrap__` out
        # of the body before parsing, so asserting against the raw body instead would demand a
        # flat shape the real API never sends — and this suite passed for exactly that reason
        # while every enveloped endpoint raised a ValidationError in the client.
        raw = response.json()
        unwrap = matched_entry.method_cls.__unwrap__
        returning.from_raw(raw[unwrap] if unwrap else raw)
