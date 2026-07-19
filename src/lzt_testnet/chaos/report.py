"""The Gauntlet scorecard — what was injected, what survived, and the fault that broke a probe.

The recorder lives on ``app.state.recorder``; the middleware records every fault it injects, so the
report is a byproduct of a run. A ``FailedProbe`` carries the precise (seq, path, fault, seed) so a
failure is reproducible: re-run with that seed and the identical fault fires at the identical seq.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from lzt_testnet.chaos.faults import Fault, FaultContext, FaultKind


@dataclass(frozen=True, slots=True)
class InjectedFault:
    seq: int
    path: str
    fault: FaultKind


@dataclass(frozen=True, slots=True)
class FailedProbe:
    seq: int
    path: str
    fault: FaultKind
    seed: int
    detail: str


@dataclass(frozen=True, slots=True)
class GauntletReport:
    seed: int
    injected: int
    survived: int
    failed: list[FailedProbe]

    def as_scorecard(self) -> str:
        lines = [
            f"Gauntlet scorecard (seed={self.seed})",
            f"  injected: {self.injected}",
            f"  survived: {self.survived}",
            f"  failed:   {len(self.failed)}",
        ]
        for probe in self.failed:
            lines.append(
                f"    seq={probe.seq} path={probe.path} fault={probe.fault.value} — {probe.detail}"
            )
        return "\n".join(lines)


@dataclass(slots=True)
class GauntletRecorder:
    """Accumulates injected faults and failed probes over a run. Lives on ``app.state.recorder``."""

    seed: int
    _injected: list[InjectedFault] = field(default_factory=list)
    _failed: list[FailedProbe] = field(default_factory=list)

    def record(self, ctx: FaultContext, fault: Fault) -> None:
        self._injected.append(InjectedFault(seq=ctx.seq, path=ctx.path, fault=fault.kind))

    def fail(self, ctx: FaultContext, fault: Fault, detail: str) -> None:
        self._failed.append(
            FailedProbe(seq=ctx.seq, path=ctx.path, fault=fault.kind, seed=self.seed, detail=detail)
        )

    def report(self) -> GauntletReport:
        return GauntletReport(
            seed=self.seed,
            injected=len(self._injected),
            survived=len(self._injected) - len(self._failed),
            failed=list(self._failed),
        )
