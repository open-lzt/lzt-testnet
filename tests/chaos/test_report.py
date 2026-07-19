"""T13 — GauntletRecorder tallies injected faults; failed probes carry the exact fault+seed."""

from __future__ import annotations

from random import Random

from httpx import ASGITransport, AsyncClient

from lzt_testnet.api.app import create_app
from lzt_testnet.chaos.faults import Fault, FaultContext, FaultKind
from lzt_testnet.chaos.planner import FaultPlanner
from lzt_testnet.chaos.profiles import Intensity, profile_for
from lzt_testnet.chaos.report import GauntletRecorder
from lzt_testnet.chaos.seed import SeedController


def _ctx(seq: int, path: str) -> FaultContext:
    return FaultContext(method="GET", path=path, seq=seq, endpoint="*", rng=Random(0))


def test_recorder_counts_injected_and_survived() -> None:
    rec = GauntletRecorder(42)
    rec.record(_ctx(1, "/a"), Fault(FaultKind.HTTP_500, {}))
    rec.record(_ctx(2, "/b"), Fault(FaultKind.SLOW, {}))
    rec.fail(_ctx(2, "/b"), Fault(FaultKind.SLOW, {}), "client hung")
    report = rec.report()
    assert report.injected == 2
    assert report.survived == 1
    assert len(report.failed) == 1


def test_failed_probe_carries_seed_and_fault() -> None:
    rec = GauntletRecorder(7)
    rec.fail(_ctx(3, "/buy"), Fault(FaultKind.CHARGE_THEN_FAIL, {}), "double charge")
    probe = rec.report().failed[0]
    assert probe.seed == 7
    assert probe.fault is FaultKind.CHARGE_THEN_FAIL
    assert probe.seq == 3


def test_scorecard_renders() -> None:
    rec = GauntletRecorder(99)
    rec.record(_ctx(1, "/a"), Fault(FaultKind.HTTP_502_NGINX, {}))
    rec.fail(_ctx(1, "/a"), Fault(FaultKind.HTTP_502_NGINX, {}), "parsed nginx html as json")
    card = rec.report().as_scorecard()
    assert "seed=99" in card
    assert "injected: 1" in card
    assert "http_502_nginx" in card


async def test_injected_matches_forced_faults() -> None:
    app = create_app()
    controller = SeedController(1)
    controller.seed_generation()
    app.state.seed = controller
    app.state.fault_planner = FaultPlanner(profile_for(Intensity.OFF))
    app.state.recorder = GauntletRecorder(1)
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        for _ in range(5):
            await ac.get(
                "/testnet/stateful/lots",
                headers={"Authorization": "Bearer t", "X-Chaos": "http_500@*"},
            )
    assert app.state.recorder.report().injected == 5
