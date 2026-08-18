"""FastAPI application factory wiring the mock lzt.market testnet server."""

from __future__ import annotations

from fastapi import FastAPI

from lzt_testnet.api.catch_all import router as catch_all_router
from lzt_testnet.api.control import router as control_router
from lzt_testnet.api.error_handlers import register_error_handlers
from lzt_testnet.api.forum import router as forum_router
from lzt_testnet.api.forum_posts import FORUM_POST_PATHS
from lzt_testnet.api.forum_posts import router as forum_posts_router
from lzt_testnet.api.stateful import router as stateful_router
from lzt_testnet.api.system_info import SystemInfoMiddleware
from lzt_testnet.catalog.route_table import build_route_table
from lzt_testnet.chaos.middleware import FaultInjectionMiddleware
from lzt_testnet.chaos.planner import FaultPlanner
from lzt_testnet.chaos.profiles import ChaosProfile, Intensity, profile_for
from lzt_testnet.chaos.report import GauntletRecorder
from lzt_testnet.chaos.scenario import load_scenario
from lzt_testnet.chaos.seed import SeedController
from lzt_testnet.config import get_settings
from lzt_testnet.fake.generator import FakeGenerator
from lzt_testnet.state.injection_store import InjectionStore
from lzt_testnet.state.lot_store import LotStore
from lzt_testnet.state.payment_store import PaymentStore
from lzt_testnet.state.scenario_store import ScenarioStore
from lzt_testnet.world.arm import WorldBundle, build_world
from lzt_testnet.world.builder import WorldConfig

# stateful.py's 6 routes live under their own /testnet/stateful/* prefix, disjoint
# from the real pylzt path templates the catch-all table matches against —
# nothing to exclude there.
#
# forum_posts.py is the opposite case and the reason this set is no longer empty: it serves the
# REAL upstream urls, so its three routes and the catch-all's table entries claim the same paths.
# Excluded here, the table stops matching them and the catch-all 404s instead of answering `{}` —
# which is what it did for `posts_list`, upstream having declared it Passthrough.
STATEFUL_PATHS: frozenset[str] = FORUM_POST_PATHS


def create_app() -> FastAPI:
    """Build and wire the mock lzt.market testnet FastAPI app."""
    route_table = build_route_table(exclude_paths=STATEFUL_PATHS)

    app = FastAPI()
    settings = get_settings()

    # A named scenario (if set) overrides the bare intensity/seed; otherwise fall back to the
    # intensity profile. A world is armed for a scenario that declares one, or for any non-OFF mode.
    scenario = load_scenario(settings.chaos_scenario) if settings.chaos_scenario else None
    profile: ChaosProfile | None
    if scenario is not None:
        profile = scenario.to_profile()
        seed_value = settings.chaos_seed or scenario.seed
        world_config: WorldConfig | None = scenario.world
    else:
        profile = profile_for(settings.chaos_mode)
        seed_value = settings.chaos_seed
        world_config = (
            WorldConfig() if settings.world or settings.chaos_mode is not Intensity.OFF else None
        )

    # The determinism spine: one seed fixes every fault decision and every generated datum (D1).
    seed = SeedController(seed_value)
    seed.seed_generation()

    app.state.route_table = route_table
    app.state.fake_generator = FakeGenerator()
    app.state.lot_store = LotStore()
    app.state.injection_store = InjectionStore()
    app.state.payment_store = PaymentStore()
    app.state.scenario_store = ScenarioStore()
    app.state.settings = settings
    app.state.seed = seed
    app.state.fault_planner = FaultPlanner(profile)
    app.state.chaos_counters = {}  # seed-scoped per-item ticks for retry_storm / delayed_settlement
    app.state.recorder = GauntletRecorder(seed_value)

    # The stateful world (roster + forum + lazy lots) stays off by default so the mock is clean
    # and the pre-existing suite is unaffected (D2).
    world: WorldBundle | None = None
    if world_config is not None:
        world = build_world(
            seed=seed_value,
            config=world_config,
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
    # Before the catch-all: whoever registers first wins the path.
    app.include_router(forum_posts_router)
    app.include_router(catch_all_router)
    app.add_middleware(FaultInjectionMiddleware)
    # Added last, so it wraps OUTERMOST and stamps whatever the inner layers produced —
    # including a response a fault-injection rewrite handed back.
    app.add_middleware(SystemInfoMiddleware)

    return app
