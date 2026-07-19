"""Plugin-author test helpers: build an armed chaos client and assert survival properties.

These are the assertions a plugin's own test-suite calls to prove it handles the market's failures
(``assert_idempotent`` here; ``assert_survives``/``assert_blacklists``/``run_oracle`` land in L4).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from httpx import ASGITransport, AsyncClient, Response

from lzt_testnet.api.app import create_app
from lzt_testnet.chaos.planner import FaultPlanner
from lzt_testnet.chaos.profiles import Intensity, profile_for
from lzt_testnet.chaos.seed import SeedController
from lzt_testnet.world.arm import build_world
from lzt_testnet.world.builder import WorldConfig

_TRANSIENT = frozenset({429, 500, 502, 503, 504})


def chaos_client(*, mode: Intensity = Intensity.OFF, seed: int = 0) -> AsyncClient:
    """An AsyncClient over an app armed at `mode`/`seed`. `raise_app_exceptions=False` so a
    connection_drop surfaces as a truncated Response, not an exception (W3.5/R3). A world is armed
    (roster + forum + lazy lots) whenever `mode` is not OFF."""
    app = create_app()
    controller = SeedController(seed)
    controller.seed_generation()
    app.state.seed = controller
    app.state.fault_planner = FaultPlanner(profile_for(mode))
    if mode is not Intensity.OFF:
        app.state.world = build_world(
            seed=seed,
            config=WorldConfig(),
            lots=app.state.lot_store,
            scenario=app.state.scenario_store,
            generator=app.state.fake_generator,
        )
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    return AsyncClient(transport=transport, base_url="http://testserver")


async def drive_to_convergence(
    buy_call: Callable[[], Awaitable[Response]], *, max_attempts: int = 25
) -> Response:
    """Retry `buy_call` past transient (retry_storm / 5xx) responses until it settles."""
    resp = await buy_call()
    for _ in range(max_attempts - 1):
        if resp.status_code not in _TRANSIENT:
            return resp
        resp = await buy_call()
    return resp


async def assert_idempotent(
    client: AsyncClient, buy_call: Callable[[], Awaitable[Response]], *, item_id: int, token: str
) -> Response:
    """Under retry_storm, drive `buy_call` to convergence; assert EXACTLY ONE PaymentRecord."""
    resp = await drive_to_convergence(buy_call)
    payments = await client.get(
        "/testnet/stateful/payments", headers={"Authorization": f"Bearer {token}"}
    )
    matches = [p for p in payments.json() if p["item_id"] == item_id]
    assert len(matches) == 1, f"expected one payment for {item_id}, got {len(matches)}"
    return resp


async def assert_blacklists(client: AsyncClient, *, category: str = "steam", limit: int = 20) -> None:
    """Assert spam-seller lots appear in the world listing AND deterministically fail their check."""
    listed = await client.get("/testnet/world/lots", params={"category": category, "limit": limit})
    items = listed.json()["items"]
    assert items, "world listing was empty"
    blacklisted = []
    for lot in items:
        first = await client.get(f"/testnet/world/lots/{lot['item_id']}/check")
        again = await client.get(f"/testnet/world/lots/{lot['item_id']}/check")
        assert first.json()["valid"] == again.json()["valid"], "check must be deterministic"
        if not first.json()["valid"]:
            blacklisted.append(lot["item_id"])
    assert blacklisted, "expected at least one blacklisted (spam-seller) lot"
