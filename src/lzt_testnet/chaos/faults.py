"""The fault taxonomy — one typed enum, never string literals, partitioned by where it applies."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from random import Random


class FaultKind(StrEnum):
    """Every fault the harness can inject. Partitioned by ``PRE_RESPONSE`` / ``POST_RESPONSE`` /
    ``DOMAIN`` below — those three frozensets cover the enum with no overlap."""

    # transport, pre-response (short-circuit — never reaches the handler)
    HTTP_500 = "http_500"
    HTTP_502_NGINX = "http_502_nginx"
    HTTP_503 = "http_503"
    HTTP_504 = "http_504"
    RATE_LIMITED_429 = "rate_limited_429"
    AUTH_DROP_401 = "auth_drop_401"
    UNKNOWN_ERROR_CODE = "unknown_error_code"
    TIMEOUT = "timeout"
    CONNECTION_DROP = "connection_drop"
    # post-response (mutate the real response)
    SLOW = "slow"
    BYZANTINE_MISSING_FIELD = "byzantine_missing_field"
    BYZANTINE_NULL = "byzantine_null"
    BYZANTINE_WRONG_TYPE = "byzantine_wrong_type"
    MALFORMED_JSON = "malformed_json"
    TRUNCATED_BODY = "truncated_body"
    # domain (injected in-handler, needs store state)
    ACCOUNT_INVALID = "account_invalid"
    ALREADY_SOLD = "already_sold"
    RETRY_STORM = "retry_storm"
    CHARGE_THEN_FAIL = "charge_then_fail"
    DELAYED_SETTLEMENT = "delayed_settlement"
    BAD_LOT_CHECK = "bad_lot_check"


PRE_RESPONSE: frozenset[FaultKind] = frozenset(
    {
        FaultKind.HTTP_500,
        FaultKind.HTTP_502_NGINX,
        FaultKind.HTTP_503,
        FaultKind.HTTP_504,
        FaultKind.RATE_LIMITED_429,
        FaultKind.AUTH_DROP_401,
        FaultKind.UNKNOWN_ERROR_CODE,
        FaultKind.TIMEOUT,
        FaultKind.CONNECTION_DROP,
    }
)

POST_RESPONSE: frozenset[FaultKind] = frozenset(
    {
        FaultKind.SLOW,
        FaultKind.BYZANTINE_MISSING_FIELD,
        FaultKind.BYZANTINE_NULL,
        FaultKind.BYZANTINE_WRONG_TYPE,
        FaultKind.MALFORMED_JSON,
        FaultKind.TRUNCATED_BODY,
    }
)

DOMAIN: frozenset[FaultKind] = frozenset(
    {
        FaultKind.ACCOUNT_INVALID,
        FaultKind.ALREADY_SOLD,
        FaultKind.RETRY_STORM,
        FaultKind.CHARGE_THEN_FAIL,
        FaultKind.DELAYED_SETTLEMENT,
        FaultKind.BAD_LOT_CHECK,
    }
)


@dataclass(frozen=True, slots=True)
class Fault:
    """A concrete fault to apply, with its shaping params (retry_after, delay, drop_field, ...)."""

    kind: FaultKind
    params: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FaultContext:
    """Everything a fault decision may read. ``rng`` is the ONLY randomness source it may use."""

    method: str
    path: str
    seq: int
    endpoint: str
    rng: Random
