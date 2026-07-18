"""FastAPI dependencies enforcing the mock's auth/error-injection contract."""

from __future__ import annotations

from fastapi import Header

from lzt_testnet import errors

_BEARER_PREFIX = "Bearer "


async def get_bearer_token(authorization: str | None = Header(default=None)) -> str:
    """Extracts the bearer token from `Authorization`, raising `AuthFailed` on any defect."""
    if authorization is None or not authorization.startswith(_BEARER_PREFIX):
        raise errors.AuthFailed(token_id="")
    token = authorization[len(_BEARER_PREFIX) :]
    if not token:
        raise errors.AuthFailed(token_id="")
    return token


async def force_error_header(
    x_testnet_force_error: str | None = Header(default=None),
) -> str | None:
    """Passes through the raw `X-Testnet-Force-Error` header value, unvalidated."""
    return x_testnet_force_error
