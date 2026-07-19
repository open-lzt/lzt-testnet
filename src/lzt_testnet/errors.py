"""Typed error hierarchy shared by every lzt-testnet module."""

from __future__ import annotations

from dataclasses import dataclass


class TestnetError(Exception):
    """Base for every typed testnet error. Never raised directly."""


@dataclass
class RateLimited(TestnetError):
    """Maps to HTTP 429."""

    retry_after: float

    def __post_init__(self) -> None:
        super().__init__(self.retry_after)


@dataclass
class AuthFailed(TestnetError):
    """Maps to HTTP 401."""

    token_id: str

    def __post_init__(self) -> None:
        super().__init__(self.token_id)


@dataclass
class NotFound(TestnetError):
    """Maps to HTTP 404."""

    item_id: int | str

    def __post_init__(self) -> None:
        super().__init__(self.item_id)


@dataclass
class BadRequest(TestnetError):
    """Maps to HTTP 400."""

    field: str

    def __post_init__(self) -> None:
        super().__init__(self.field)


@dataclass
class TransportError(TestnetError):
    """Maps to its own `status` field."""

    status: int

    def __post_init__(self) -> None:
        super().__init__(self.status)


@dataclass
class PaymentFailed(TestnetError):
    """Testnet-only: fast-buy's 'money did not go through' scenario. Maps to HTTP 402."""

    def __post_init__(self) -> None:
        super().__init__()


@dataclass
class UnknownFaultError(TestnetError):
    """An `X-Chaos` header named a fault that isn't a `FaultKind`. Maps to HTTP 400."""

    name: str

    def __post_init__(self) -> None:
        super().__init__(self.name)
