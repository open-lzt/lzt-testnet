"""FastAPI application factory wiring the mock lzt.market testnet server."""

from __future__ import annotations

from fastapi import FastAPI

from lzt_testnet.api.catch_all import router as catch_all_router
from lzt_testnet.api.control import router as control_router
from lzt_testnet.api.error_handlers import register_error_handlers
from lzt_testnet.api.stateful import router as stateful_router
from lzt_testnet.catalog.route_table import build_route_table
from lzt_testnet.api.forum import router as forum_router
from lzt_testnet.chaos.middleware import FaultInjectionMiddleware
from lzt_testnet.chaos.planner import FaultPlanner
from lzt_testnet.chaos.profiles import Intensity, profile_for
from lzt_testnet.chaos.seed import SeedController
from lzt_testnet.config import get_settings
from lzt_testnet.fake.generator import FakeGenerator
from lzt_testnet.state.lot_store import LotStore
from lzt_testnet.state.payment_store import PaymentStore
from lzt_testnet.state.scenario_store import ScenarioStore
from lzt_testnet.world.arm import WorldBundle, build_world
from lzt_testnet.world.builder import WorldConfig

# stateful.py's 6 routes live under their own /testnet/stateful/* prefix, disjoint
# from the real pylzt path templates the catch-all table matches against —
# nothing to exclude here.
STATEFUL_PATHS: frozenset[str] = frozenset()


def create_app() -> FastAPI:
    """Build and wire the mock lzt.market testnet FastAPI app."""
    route_table = build_route_table(exclude_paths=STATEFUL_PATHS)

    app = FastAPI()
    settings = get_settings()

    # The determinism spine: one seed fixes every fault decision and every generated datum (D1).
    seed = SeedController(settings.chaos_seed)
    seed.seed_generation()

    app.state.route_table = route_table
    app.state.fake_generator = FakeGenerator()
    app.state.lot_store = LotStore()
    app.state.payment_store = PaymentStore()
    app.state.scenario_store = ScenarioStore()
    app.state.settings = settings
    app.state.seed = seed
    app.state.fault_planner = FaultPlanner(profile_for(settings.chaos_mode))
    app.state.chaos_counters = {}  # seed-scoped per-item ticks for retry_storm / delayed_settlement

    # The stateful world (roster + forum + lazy lots) is armed only when chaos is active, so the
    # default mock stays clean and the pre-existing suite is unaffected (D2).
    world: WorldBundle | None = None
    if settings.chaos_mode is not Intensity.OFF:
        world = build_world(
            seed=settings.chaos_seed,
            config=WorldConfig(),
            lots=app.state.lot_store,
            scenario=app.state.scenario_store,
            generator=app.state.fake_generator,
        )
    app.state.world = world

    @app.get("/testnet/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    register_error_handlers(app)
    app.include_router(control_router)
    app.include_router(stateful_router)
    app.include_router(forum_router)
    app.include_router(catch_all_router)
    app.add_middleware(FaultInjectionMiddleware)

    return app
