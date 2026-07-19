"""Legacy ``X-Testnet-Force-Error`` → typed error, shared by catch_all and stateful (TD-1).

Both routers used to carry an identical ``_FORCE_ERROR_MAP``; this is the single source of truth.
It maps to the same typed errors the app already renders, so response bodies are unchanged.
"""

from __future__ import annotations

from lzt_testnet import errors


def raise_legacy_forced_error(name: str | None, item_id: int | str | None = None) -> None:
    """Raise the typed error requested via ``X-Testnet-Force-Error``. Unknown names fall through."""
    if name is None:
        return
    if name == "rate_limited":
        raise errors.RateLimited(retry_after=1.0)
    if name == "auth_failed":
        raise errors.AuthFailed(token_id="")
    if name == "transport_error":
        raise errors.TransportError(status=500)
    if name == "payment_failed":
        raise errors.PaymentFailed()
    if name == "not_found":
        raise errors.NotFound(item_id=item_id if item_id is not None else "unknown")
