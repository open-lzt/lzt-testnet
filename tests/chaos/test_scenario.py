"""T12 — scenario YAML loads + validates; the 5 shipped scenarios parse; bad specs are rejected."""

from __future__ import annotations

from pathlib import Path

import pytest

from lzt_testnet.chaos.faults import FaultKind
from lzt_testnet.chaos.profiles import Intensity
from lzt_testnet.chaos.scenario import ScenarioSpec, load_scenario
from lzt_testnet.errors import ScenarioError

_SHIPPED = [
    "black-friday-meltdown",
    "auth-expiry-storm",
    "seller-spam-flood",
    "nginx-down",
    "pagination-hell",
]


@pytest.mark.parametrize("name", _SHIPPED)
def test_shipped_scenarios_load(name: str) -> None:
    spec = load_scenario(name)
    assert spec.name == name
    profile = spec.to_profile()
    assert 0.0 <= profile.fault_probability <= 1.0


def test_nginx_down_is_502_heavy() -> None:
    spec = load_scenario("nginx-down")
    profile = spec.to_profile()
    assert profile.weights[FaultKind.HTTP_502_NGINX] == max(profile.weights.values())


def test_pagination_hell_targets_list_endpoint() -> None:
    spec = load_scenario("pagination-hell")
    assert FaultKind.TRUNCATED_BODY in spec.per_endpoint["list_lots"]


def test_missing_scenario_raises(tmp_path: Path) -> None:
    with pytest.raises(ScenarioError):
        load_scenario("does-not-exist", root=tmp_path)


def test_malformed_yaml_raises(tmp_path: Path) -> None:
    (tmp_path / "broken.yaml").write_text("name: [unclosed\n", encoding="utf-8")
    with pytest.raises(ScenarioError):
        load_scenario("broken", root=tmp_path)


def test_unknown_fault_rejected(tmp_path: Path) -> None:
    (tmp_path / "bad.yaml").write_text(
        "name: bad\nweights:\n  not_a_real_fault: 1.0\n", encoding="utf-8"
    )
    with pytest.raises(ScenarioError):
        load_scenario("bad", root=tmp_path)


def test_non_mapping_rejected(tmp_path: Path) -> None:
    (tmp_path / "list.yaml").write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(ScenarioError):
        load_scenario("list", root=tmp_path)


def test_spec_defaults() -> None:
    spec = ScenarioSpec(name="x")
    assert spec.intensity is Intensity.HOSTILE
    assert spec.oracle is False
