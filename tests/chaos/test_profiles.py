"""Fault taxonomy partition + profile weights."""

from __future__ import annotations

from lzt_testnet.chaos.faults import DOMAIN, POST_RESPONSE, PRE_RESPONSE, FaultKind
from lzt_testnet.chaos.profiles import Intensity, profile_for


def test_partition_covers_faultkind_without_overlap() -> None:
    """Every FaultKind belongs to exactly one of PRE/POST/DOMAIN — the middleware routes on this."""
    groups = [PRE_RESPONSE, POST_RESPONSE, DOMAIN]
    union = PRE_RESPONSE | POST_RESPONSE | DOMAIN
    assert union == set(FaultKind), "some FaultKind is unclassified"
    for i, g in enumerate(groups):
        for h in groups[i + 1 :]:
            assert not (g & h), "a FaultKind appears in two groups"


def test_profile_for_off_is_none() -> None:
    assert profile_for(Intensity.OFF) is None


def test_builtin_profiles_present_and_scaled() -> None:
    calm = profile_for(Intensity.CALM)
    hostile = profile_for(Intensity.HOSTILE)
    assert calm is not None and hostile is not None
    assert calm.fault_probability < hostile.fault_probability
    assert hostile.menu_for("buy") == hostile.weights  # no per-endpoint override -> base menu
    # every weighted kind is a real FaultKind
    assert all(isinstance(k, FaultKind) for k in hostile.weights)
