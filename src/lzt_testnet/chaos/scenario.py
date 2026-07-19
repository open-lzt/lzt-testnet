"""Named chaos scenarios as DATA — a validated ``ScenarioSpec`` from ``scenarios/<name>.yaml``.

Community contributors add a scenario by dropping in a YAML file; the schema (this model) is the
contract, and CI validates every shipped scenario against it (T16). A scenario compiles to a
``ChaosProfile`` (transport rolls) plus an optional ``WorldConfig`` (the stateful roster/forum).
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError

from lzt_testnet.chaos.faults import FaultKind
from lzt_testnet.chaos.profiles import ChaosProfile, Intensity, profile_for
from lzt_testnet.errors import ScenarioError
from lzt_testnet.world.builder import WorldConfig

_SCENARIO_ROOT = Path(__file__).resolve().parents[3] / "scenarios"


class ScenarioSpec(BaseModel):
    """The validated shape of a scenario file. Unknown fault names fail validation."""

    name: str
    seed: int = 0
    intensity: Intensity = Intensity.HOSTILE
    fault_probability: float | None = None
    weights: dict[FaultKind, float] | None = None
    per_endpoint: dict[str, dict[FaultKind, float]] = {}
    world: WorldConfig | None = None
    oracle: bool = False

    def to_profile(self) -> ChaosProfile:
        """Compile to the ChaosProfile the planner rolls against — scenario weights override the
        intensity's built-in menu; scenario probability overrides its rate."""
        base = profile_for(self.intensity)
        weights = self.weights if self.weights is not None else (base.weights if base else {})
        probability = (
            self.fault_probability
            if self.fault_probability is not None
            else (base.fault_probability if base else 0.5)
        )
        return ChaosProfile(
            name=self.name,
            weights=weights,
            per_endpoint=self.per_endpoint,
            fault_probability=probability,
        )


def load_scenario(name: str, *, root: str | Path | None = None) -> ScenarioSpec:
    """Read ``<root>/<name>.yaml`` and validate it into a ScenarioSpec. Raises ScenarioError."""
    base = Path(root) if root is not None else _SCENARIO_ROOT
    path = base / f"{name}.yaml"
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ScenarioError(f"scenario '{name}' not found at {path}") from exc
    except yaml.YAMLError as exc:
        raise ScenarioError(f"scenario '{name}' is not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ScenarioError(f"scenario '{name}' must be a mapping, got {type(raw).__name__}")
    try:
        return ScenarioSpec(**raw)
    except ValidationError as exc:
        raise ScenarioError(f"scenario '{name}' failed schema validation: {exc}") from exc
