"""FastAPI dependencies enforcing the mock's auth/error-injection contract."""

from __future__ import annotations

from fastapi import Header

from lzt_testnet import errors
from lzt_testnet.config import get_settings

_BEARER_PREFIX = "Bearer "


async def require_control_key(
    x_testnet_control_key: str | None = Header(default=None),
) -> None:
    """Guards the control plane with `Settings.control_key`; a null key leaves it open.

    Deliberately not the bearer token: this is harness control, not marketplace auth, and the
    two must not share a credential — a scenario token is handed to the code under test.
    """
    expected = get_settings().control_key
    if expected and x_testnet_control_key != expected:
        raise errors.AuthFailed(token_id="")


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


async def x_chaos_header(x_chaos: str | None = Header(default=None)) -> str | None:
    """Passes through the raw `X-Chaos` header value; the middleware/planner parse it."""
    return x_chaos
