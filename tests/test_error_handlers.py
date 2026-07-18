"""Tests for `register_error_handlers` — one test route per `TestnetError` subclass."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from lzt_testnet.api.error_handlers import register_error_handlers
from lzt_testnet.errors import (
    AuthFailed,
    BadRequest,
    NotFound,
    PaymentFailed,
    RateLimited,
    TransportError,
)


def _build_test_app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/raise/rate-limited")
    async def raise_rate_limited() -> None:
        raise RateLimited(retry_after=12.5)

    @app.get("/raise/auth-failed")
    async def raise_auth_failed() -> None:
        raise AuthFailed(token_id="tok-1")

    @app.get("/raise/not-found")
    async def raise_not_found() -> None:
        raise NotFound(item_id=42)

    @app.get("/raise/bad-request")
    async def raise_bad_request() -> None:
        raise BadRequest(field="price")

    @app.get("/raise/transport-error")
    async def raise_transport_error() -> None:
        raise TransportError(status=503)

    @app.get("/raise/payment-failed")
    async def raise_payment_failed() -> None:
        raise PaymentFailed()

    return app


def test_rate_limited_maps_to_429() -> None:
    client = TestClient(_build_test_app())
    response = client.get("/raise/rate-limited")
    assert response.status_code == 429
    assert response.json() == {"error": "RateLimited", "retry_after": 12.5}


def test_auth_failed_maps_to_401() -> None:
    client = TestClient(_build_test_app())
    response = client.get("/raise/auth-failed")
    assert response.status_code == 401
    assert response.json() == {"error": "AuthFailed", "token_id": "tok-1"}


def test_not_found_maps_to_404() -> None:
    client = TestClient(_build_test_app())
    response = client.get("/raise/not-found")
    assert response.status_code == 404
    assert response.json() == {"error": "NotFound", "item_id": 42}


def test_bad_request_maps_to_400() -> None:
    client = TestClient(_build_test_app())
    response = client.get("/raise/bad-request")
    assert response.status_code == 400
    assert response.json() == {"error": "BadRequest", "field": "price"}


def test_transport_error_maps_to_its_status_field() -> None:
    client = TestClient(_build_test_app())
    response = client.get("/raise/transport-error")
    assert response.status_code == 503
    assert response.json() == {"error": "TransportError", "status": 503}


def test_payment_failed_maps_to_402() -> None:
    client = TestClient(_build_test_app())
    response = client.get("/raise/payment-failed")
    assert response.status_code == 402
    assert response.json() == {"error": "PaymentFailed"}
