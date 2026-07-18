"""Tests for lzt_testnet.api.dependencies."""

from __future__ import annotations

import httpx
import pytest
from fastapi import Depends, FastAPI

from lzt_testnet import errors
from lzt_testnet.api.dependencies import force_error_header, get_bearer_token


def _build_app() -> FastAPI:
    app = FastAPI()

    @app.get("/token")
    async def token_route(token: str = Depends(get_bearer_token)) -> dict[str, str]:
        return {"token": token}

    @app.get("/force-error")
    async def force_error_route(
        value: str | None = Depends(force_error_header),
    ) -> dict[str, str | None]:
        return {"value": value}

    return app


@pytest.fixture
def client() -> httpx.AsyncClient:
    app = _build_app()
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_missing_authorization_header_raises_auth_failed(client: httpx.AsyncClient) -> None:
    async with client:
        with pytest.raises(errors.AuthFailed):
            await client.get("/token")


async def test_malformed_authorization_header_raises_auth_failed(client: httpx.AsyncClient) -> None:
    async with client:
        with pytest.raises(errors.AuthFailed):
            await client.get("/token", headers={"Authorization": "Basic abc123"})


async def test_empty_token_after_bearer_prefix_raises_auth_failed(
    client: httpx.AsyncClient,
) -> None:
    async with client:
        with pytest.raises(errors.AuthFailed):
            await client.get("/token", headers={"Authorization": "Bearer "})


async def test_well_formed_bearer_header_returns_token(client: httpx.AsyncClient) -> None:
    async with client:
        response = await client.get("/token", headers={"Authorization": "Bearer abc123"})
    assert response.status_code == 200
    assert response.json() == {"token": "abc123"}


async def test_force_error_header_present_returns_value(client: httpx.AsyncClient) -> None:
    async with client:
        response = await client.get("/force-error", headers={"X-Testnet-Force-Error": "not_found"})
    assert response.status_code == 200
    assert response.json() == {"value": "not_found"}


async def test_force_error_header_absent_returns_none(client: httpx.AsyncClient) -> None:
    async with client:
        response = await client.get("/force-error")
    assert response.status_code == 200
    assert response.json() == {"value": None}
