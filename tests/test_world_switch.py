"""The world is armed by its own setting, and says so when it is off."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from httpx import ASGITransport, AsyncClient

from lzt_testnet.api.app import create_app
from lzt_testnet.config import get_settings

_WORLD_ROUTES = (
    "/testnet/world/lots",
    "/testnet/world/forum/users",
    "/testnet/world/forum/threads",
    "/testnet/world/lots/1/check",
)


async def _get(path: str) -> tuple[int, dict[str, object]]:
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        response = await client.get(path, headers={"Authorization": "Bearer t"})
        return response.status_code, response.json()


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Iterator[None]:
    """Clearing only on the way in leaks: `get_settings` is `lru_cache`d, so the last test here
    left a cached Settings with the world armed and the next file's app was built with it."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.anyio
@pytest.mark.parametrize("path", _WORLD_ROUTES)
async def test_world_off_is_reported_not_faked(
    path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty page here reads as "the mock is broken" rather than "it is switched off"."""
    monkeypatch.delenv("LZT_TESTNET_WORLD", raising=False)
    get_settings.cache_clear()

    status, body = await _get(path)

    assert status == 409
    assert body["error"] == "WorldDisabled"
    assert body["enable_with"] == "LZT_TESTNET_WORLD=1"


@pytest.mark.anyio
async def test_world_setting_arms_it_without_the_chaos_harness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """It used to be reachable only by turning fault injection on."""
    monkeypatch.setenv("LZT_TESTNET_WORLD", "1")
    monkeypatch.delenv("LZT_TESTNET_CHAOS_MODE", raising=False)
    get_settings.cache_clear()

    status, body = await _get("/testnet/world/lots?limit=3")

    assert status == 200
    assert len(body["items"]) == 3  # type: ignore[arg-type]
