"""HTTP-response mapping for typed testnet errors, registered on a FastAPI app."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from lzt_testnet.errors import (
    AuthFailed,
    BadRequest,
    NotFound,
    PaymentFailed,
    RateLimited,
    TransportError,
)


def register_error_handlers(app: FastAPI) -> None:
    """Register one exception handler per `TestnetError` subclass on `app`."""

    @app.exception_handler(RateLimited)
    async def _handle_rate_limited(_request: Request, exc: RateLimited) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={"error": "RateLimited", "retry_after": exc.retry_after},
        )

    @app.exception_handler(AuthFailed)
    async def _handle_auth_failed(_request: Request, exc: AuthFailed) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content={"error": "AuthFailed", "token_id": exc.token_id},
        )

    @app.exception_handler(NotFound)
    async def _handle_not_found(_request: Request, exc: NotFound) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"error": "NotFound", "item_id": exc.item_id},
        )

    @app.exception_handler(BadRequest)
    async def _handle_bad_request(_request: Request, exc: BadRequest) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"error": "BadRequest", "field": exc.field},
        )

    @app.exception_handler(TransportError)
    async def _handle_transport_error(_request: Request, exc: TransportError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status,
            content={"error": "TransportError", "status": exc.status},
        )

    @app.exception_handler(PaymentFailed)
    async def _handle_payment_failed(_request: Request, _exc: PaymentFailed) -> JSONResponse:
        return JSONResponse(status_code=402, content={"error": "PaymentFailed"})
