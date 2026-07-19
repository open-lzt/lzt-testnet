"""Chaos intensity profiles — weighted fault menus. Data now; scenario YAML can override in L4."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from lzt_testnet.chaos.faults import FaultKind


class Intensity(StrEnum):
    """How hostile the global (non-header) chaos roll is. ``OFF`` is the default no-op."""

    OFF = "off"
    CALM = "calm"
    FLAKY = "flaky"
    HOSTILE = "hostile"
    LZT_FRIDAY = "lzt_friday"


@dataclass(frozen=True, slots=True)
class ChaosProfile:
    """A weighted fault menu. ``fault_probability`` gates whether ANY fault fires per request;
    when it does, ``weights`` (optionally overridden ``per_endpoint``) pick which one."""

    name: str
    weights: dict[FaultKind, float]
    per_endpoint: dict[str, dict[FaultKind, float]] = field(default_factory=dict)
    fault_probability: float = 0.0

    def menu_for(self, endpoint: str) -> dict[FaultKind, float]:
        """The weight map for ``endpoint`` — a per-endpoint override if present, else the base."""
        return self.per_endpoint.get(endpoint, self.weights)


# A light, common transport menu shared by the built-ins (scaled by fault_probability).
_TRANSPORT: dict[FaultKind, float] = {
    FaultKind.HTTP_500: 1.0,
    FaultKind.HTTP_502_NGINX: 1.0,
    FaultKind.HTTP_503: 0.7,
    FaultKind.RATE_LIMITED_429: 1.0,
    FaultKind.SLOW: 1.5,
    FaultKind.AUTH_DROP_401: 0.5,
    FaultKind.BYZANTINE_MISSING_FIELD: 0.8,
}

_HOSTILE: dict[FaultKind, float] = {
    **_TRANSPORT,
    FaultKind.HTTP_504: 0.8,
    FaultKind.BYZANTINE_NULL: 0.8,
    FaultKind.MALFORMED_JSON: 0.5,
    FaultKind.TRUNCATED_BODY: 0.5,
    FaultKind.UNKNOWN_ERROR_CODE: 0.5,
    FaultKind.CONNECTION_DROP: 0.4,
}

BUILTIN: dict[Intensity, ChaosProfile] = {
    Intensity.CALM: ChaosProfile("calm", _TRANSPORT, fault_probability=0.05),
    Intensity.FLAKY: ChaosProfile("flaky", _TRANSPORT, fault_probability=0.2),
    Intensity.HOSTILE: ChaosProfile("hostile", _HOSTILE, fault_probability=0.5),
    Intensity.LZT_FRIDAY: ChaosProfile("lzt_friday", _HOSTILE, fault_probability=0.85),
}


def profile_for(intensity: Intensity) -> ChaosProfile | None:
    """The built-in profile for ``intensity`` — ``None`` for ``OFF`` (middleware then no-ops)."""
    return BUILTIN.get(intensity)
