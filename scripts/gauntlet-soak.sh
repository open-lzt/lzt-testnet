#!/usr/bin/env bash
# Bounded, seeded soak-fuzz: drive N in-process requests under a scenario, print a faults/sec
# baseline, exit 0. No port bound — deterministic, CI-safe.
#   ./scripts/gauntlet-soak.sh [scenario] [requests] [seed]
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

SCENARIO="${1:-nginx-down}"
REQUESTS="${2:-200}"
SEED="${3:-502}"

python - "$SCENARIO" "$REQUESTS" "$SEED" <<'PY'
import asyncio
import sys
import time

from httpx import ASGITransport, AsyncClient

from lzt_testnet.api.app import create_app
from lzt_testnet.chaos.planner import FaultPlanner
from lzt_testnet.chaos.report import GauntletRecorder
from lzt_testnet.chaos.scenario import load_scenario
from lzt_testnet.chaos.seed import SeedController

scenario, requests, seed = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
spec = load_scenario(scenario)


async def run() -> None:
    app = create_app()
    controller = SeedController(seed)
    controller.seed_generation()
    app.state.seed = controller
    app.state.fault_planner = FaultPlanner(spec.to_profile())
    app.state.recorder = GauntletRecorder(seed)
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    start = time.perf_counter()
    async with AsyncClient(transport=transport, base_url="http://soak") as ac:
        for _ in range(requests):
            await ac.get("/testnet/stateful/lots", headers={"Authorization": "Bearer soak"})
    elapsed = time.perf_counter() - start
    report = app.state.recorder.report()
    rate = report.injected / elapsed if elapsed else 0.0
    print(
        f"soak scenario={scenario} seed={seed} requests={requests} "
        f"injected={report.injected} faults/sec={rate:.1f} wall={elapsed:.2f}s"
    )


asyncio.run(run())
PY
