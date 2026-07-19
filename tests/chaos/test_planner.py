"""Arming precedence + legacy unification + deterministic profile roll."""

from __future__ import annotations

import pytest

from lzt_testnet.chaos.faults import FaultContext, FaultKind
from lzt_testnet.chaos.planner import FaultPlanner, parse_x_chaos
from lzt_testnet.chaos.profiles import Intensity, profile_for
from lzt_testnet.chaos.seed import SeedController
from lzt_testnet.errors import UnknownFaultError


def _ctx(endpoint: str = "buy", seq: int = 1, seed: int = 42) -> FaultContext:
    return FaultContext(
        method="POST", path="/x", seq=seq, endpoint=endpoint, rng=SeedController(seed).stream(seq)
    )


def test_parse_x_chaos() -> None:
    assert parse_x_chaos("http_502_nginx@buy") == (FaultKind.HTTP_502_NGINX, "buy")
    assert parse_x_chaos("http_500") == (FaultKind.HTTP_500, None)
    with pytest.raises(UnknownFaultError):
        parse_x_chaos("not_a_real_fault")


def test_x_chaos_forces_exactly_that_fault() -> None:
    planner = FaultPlanner(None)  # no profile — proves X-Chaos wins even with chaos otherwise off
    fault = planner.decide(_ctx(), x_chaos="rate_limited_429", legacy=None)
    assert fault is not None and fault.kind is FaultKind.RATE_LIMITED_429


def test_x_chaos_endpoint_filter() -> None:
    planner = FaultPlanner(None)
    assert planner.decide(_ctx(endpoint="list"), x_chaos="http_500@buy", legacy=None) is None
    hit = planner.decide(_ctx(endpoint="buy"), x_chaos="http_500@buy", legacy=None)
    assert hit is not None and hit.kind is FaultKind.HTTP_500


@pytest.mark.parametrize(
    ("legacy", "expected"),
    [
        ("rate_limited", FaultKind.RATE_LIMITED_429),
        ("auth_failed", FaultKind.AUTH_DROP_401),
        ("transport_error", FaultKind.HTTP_500),
        ("payment_failed", FaultKind.CHARGE_THEN_FAIL),
        ("not_found", FaultKind.ALREADY_SOLD),
    ],
)
def test_legacy_force_error_names_unified(legacy: str, expected: FaultKind) -> None:
    fault = FaultPlanner(None).decide(_ctx(), x_chaos=None, legacy=legacy)
    assert fault is not None and fault.kind is expected


def test_no_arming_is_clean() -> None:
    assert FaultPlanner(None).decide(_ctx(), x_chaos=None, legacy=None) is None


def test_profile_roll_is_deterministic_by_seed_and_seq() -> None:
    planner = FaultPlanner(profile_for(Intensity.HOSTILE))
    a = planner.decide(_ctx(seq=5), x_chaos=None, legacy=None)
    b = planner.decide(_ctx(seq=5), x_chaos=None, legacy=None)  # same seed+seq -> same decision
    assert (a is None) == (b is None)
    if a is not None and b is not None:
        assert a.kind is b.kind
