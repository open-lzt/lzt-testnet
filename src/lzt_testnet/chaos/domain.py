"""L2 domain faults — the in-handler outcomes that corrupt a *purchase*, not the transport.

Unlike transport faults (applied in the ASGI middleware), these need store state, so the buy
handler asks ``maybe_inject`` what to do. ``retry_storm``/``delayed_settlement`` are stateful:
a per-item counter (seed-scoped, held on ``app.state.chaos_counters``) makes the first N attempts
transient, then converge — deterministic by seed, and exactly what an idempotency probe needs.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from lzt_testnet.chaos.faults import Fault, FaultKind


@dataclass(frozen=True, slots=True)
class DomainView:
    """The read-only slice of buy state a domain fault decision may look at."""

    item_id: int | None
    token: str
    was_bought: bool


class DomainOutcome(StrEnum):
    """What the buy handler must do — decided once, executed by the handler."""

    PROCEED = "proceed"
    FAIL_INVALID = "fail_invalid"
    ALREADY_SOLD = "already_sold"
    TRANSIENT_RETRY = "transient_retry"
    CHARGE_THEN_FAIL = "charge_then_fail"
    PENDING = "pending"


def maybe_inject(fault: Fault | None, view: DomainView, counters: dict[str, int]) -> DomainOutcome:
    """Map the decided domain fault to a buy outcome. Non-domain / no fault → PROCEED.

    ``counters`` is the app's mutable, seed-scoped tick store; retry/settlement advance it so
    repeated attempts converge deterministically.
    """
    if fault is None or view.item_id is None:
        return DomainOutcome.PROCEED
    kind = fault.kind
    if kind in (FaultKind.ACCOUNT_INVALID, FaultKind.BAD_LOT_CHECK):
        return DomainOutcome.FAIL_INVALID
    if kind is FaultKind.ALREADY_SOLD:
        # Deterministic race: the first buyer of this item wins, every later one is sold out.
        key = f"sold:{view.item_id}"
        seen = counters.get(key, 0)
        counters[key] = seen + 1
        return DomainOutcome.PROCEED if seen == 0 else DomainOutcome.ALREADY_SOLD
    if kind is FaultKind.CHARGE_THEN_FAIL:
        return DomainOutcome.CHARGE_THEN_FAIL
    if kind is FaultKind.RETRY_STORM:
        limit = _int_param(fault.params, "transient_count", 3)
        return _tick(counters, f"retry:{view.item_id}", limit, DomainOutcome.TRANSIENT_RETRY)
    if kind is FaultKind.DELAYED_SETTLEMENT:
        limit = _int_param(fault.params, "delay_ticks", 3)
        return _tick(counters, f"settle:{view.item_id}", limit, DomainOutcome.PENDING)
    return DomainOutcome.PROCEED


def _int_param(params: dict[str, object], key: str, default: int) -> int:
    """Read an int shaping param (Fault.params values are ``object``); else the default."""
    value = params.get(key, default)
    return value if isinstance(value, int) else default


def _tick(
    counters: dict[str, int], key: str, limit: int, transient: DomainOutcome
) -> DomainOutcome:
    """First `limit` calls under `key` return `transient`, then PROCEED. Advances the tick."""
    seen = counters.get(key, 0)
    counters[key] = seen + 1
    return transient if seen < limit else DomainOutcome.PROCEED
