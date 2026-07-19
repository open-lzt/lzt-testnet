"""The arming decision: X-Chaos header → legacy X-Testnet-Force-Error → seeded profile roll.

`decide` is pure given `(profile, ctx.rng)` — no wall-clock, no global random — so the same
seed + seq + profile always yields the same Fault. This unifies the two duplicated
`_FORCE_ERROR_MAP`s (TD-1): the legacy header names now resolve into the one FaultKind registry.
"""

from __future__ import annotations

from lzt_testnet.chaos.faults import Fault, FaultContext, FaultKind
from lzt_testnet.chaos.profiles import ChaosProfile
from lzt_testnet.errors import UnknownFaultError

# Legacy X-Testnet-Force-Error names → FaultKind (absorbs catch_all + stateful _FORCE_ERROR_MAPs).
_LEGACY_NAME_MAP: dict[str, FaultKind] = {
    "rate_limited": FaultKind.RATE_LIMITED_429,
    "auth_failed": FaultKind.AUTH_DROP_401,
    "transport_error": FaultKind.HTTP_500,
    "payment_failed": FaultKind.CHARGE_THEN_FAIL,
    "not_found": FaultKind.ALREADY_SOLD,
}


def parse_x_chaos(value: str) -> tuple[FaultKind, str | None]:
    """``'http_502_nginx@buy'`` → ``(HTTP_502_NGINX, 'buy')``; no ``@`` → ``(kind, None)``.
    Raises ``UnknownFaultError`` when the name isn't a ``FaultKind``."""
    raw, _, endpoint = value.partition("@")
    name = raw.strip()
    try:
        kind = FaultKind(name)
    except ValueError as exc:
        raise UnknownFaultError(name) from exc
    return kind, (endpoint.strip() or None)


def _params_for(kind: FaultKind) -> dict[str, object]:
    """Default shaping params per fault (a scenario can override these later)."""
    if kind is FaultKind.RATE_LIMITED_429:
        return {"retry_after": 1.0}
    if kind in (FaultKind.SLOW, FaultKind.DELAYED_SETTLEMENT):
        return {"delay_ticks": 3}
    if kind is FaultKind.RETRY_STORM:
        return {"transient_count": 3}
    return {}


def _fault(kind: FaultKind) -> Fault:
    return Fault(kind=kind, params=_params_for(kind))


class FaultPlanner:
    """Decides which fault (if any) a request gets, per the arming precedence."""

    def __init__(self, profile: ChaosProfile | None) -> None:
        self._profile = profile

    @property
    def armed(self) -> bool:
        """True when a global profile rolls faults; drives the middleware fast-path."""
        return self._profile is not None

    def decide(self, ctx: FaultContext, *, x_chaos: str | None, legacy: str | None) -> Fault | None:
        if x_chaos is not None:
            kind, endpoint = parse_x_chaos(x_chaos)
            if endpoint is not None and endpoint != "*" and endpoint != ctx.endpoint:
                return None  # header targets a different endpoint ("*" and no-@ both match all)
            return _fault(kind)
        if legacy is not None:
            legacy_kind = _LEGACY_NAME_MAP.get(legacy)
            return _fault(legacy_kind) if legacy_kind is not None else None
        if self._profile is not None:
            return self._roll(ctx, self._profile)
        return None

    def _roll(self, ctx: FaultContext, profile: ChaosProfile) -> Fault | None:
        if ctx.rng.random() >= profile.fault_probability:
            return None
        menu = profile.menu_for(ctx.endpoint)
        if not menu:
            return None
        kinds = list(menu)
        chosen = ctx.rng.choices(kinds, weights=[menu[k] for k in kinds], k=1)[0]
        return _fault(chosen)
