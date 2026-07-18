"""FastAPI application factory wiring the mock lzt.market testnet server."""

from __future__ import annotations

from fastapi import FastAPI

from lzt_testnet.api.catch_all import router as catch_all_router
from lzt_testnet.api.control import router as control_router
from lzt_testnet.api.error_handlers import register_error_handlers
from lzt_testnet.api.stateful import router as stateful_router
from lzt_testnet.catalog.route_table import build_route_table
from lzt_testnet.config import get_settings
from lzt_testnet.fake.generator import FakeGenerator
from lzt_testnet.state.lot_store import LotStore
from lzt_testnet.state.payment_store import PaymentStore
from lzt_testnet.state.scenario_store import ScenarioStore

# stateful.py's 6 routes live under their own /testnet/stateful/* prefix, disjoint
# from the real pylzt path templates the catch-all table matches against —
# nothing to exclude here.
STATEFUL_PATHS: frozenset[str] = frozenset()


def create_app() -> FastAPI:
    """Build and wire the mock lzt.market testnet FastAPI app."""
    route_table = build_route_table(exclude_paths=STATEFUL_PATHS)

    app = FastAPI()

    app.state.route_table = route_table
    app.state.fake_generator = FakeGenerator()
    app.state.lot_store = LotStore()
    app.state.payment_store = PaymentStore()
    app.state.scenario_store = ScenarioStore()
    app.state.settings = get_settings()

    @app.get("/testnet/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    register_error_handlers(app)
    app.include_router(control_router)
    app.include_router(stateful_router)
    app.include_router(catch_all_router)

    return app
