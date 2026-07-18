"""End-to-end proof: the real, unmodified `pylzt.Client` talks to this mock server.

Unlike the rest of the suite (which drives the ASGI app in-process via
`httpx.ASGITransport`), `pylzt.Client` builds its own `httpx.AsyncClient` internally
and has no transport-injection seam for ASGI — it needs a real socket. So this test
boots `create_app()` under `uvicorn` in a background thread for its duration.

Every market URL `pylzt` calls (`GET /{category}`, `GET /market/{item_id}`,
`POST /fastbuy/{item_id}`, ...) is served by this repo's generic stateless catch-all
route (`lzt_testnet.api.catch_all`), which answers any registered `BaseMethod.__url__`
with schema-shaped fake data (see `test_stateless_roundtrip.py`) — it does not consult
the stateful `LotStore`. So this test proves response *parsing* end-to-end (real client
model validation against the mock's fake bodies), not stateful lot bookkeeping; the
`/testnet/stateful/lots` lifecycle already has its own dedicated coverage in
`test_stateful_lot_lifecycle.py` and is a separate route namespace pylzt never calls.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator

import httpx
import pytest
import uvicorn
from pylzt.client import Client
from pylzt.config import ClientConfig
from pylzt.models.lot import Lot, LotFilter
from pylzt.types import ItemId

from lzt_testnet.api.app import create_app

_STARTUP_TIMEOUT_S = 5.0
_STARTUP_POLL_INTERVAL_S = 0.05


class _ServerNotReady(RuntimeError):
    """The background uvicorn server did not answer `/testnet/health` in time."""

    def __init__(self, timeout_s: float) -> None:
        super().__init__(f"testnet server not ready after {timeout_s}s")


@pytest.fixture
def testnet_base_url() -> Iterator[str]:
    """Run `create_app()` under a real uvicorn server in a background thread.

    `pylzt.Client` is a genuine HTTP client (its own `httpx.AsyncClient` + event
    loop), not ASGI-transport-testable — it needs an actual bound port to hit.
    """
    config = uvicorn.Config(create_app(), host="127.0.0.1", port=0, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + _STARTUP_TIMEOUT_S
    while not server.started:
        if time.monotonic() > deadline:
            server.should_exit = True
            thread.join(timeout=1.0)
            raise _ServerNotReady(_STARTUP_TIMEOUT_S)
        time.sleep(_STARTUP_POLL_INTERVAL_S)

    port = server.servers[0].sockets[0].getsockname()[1]
    base_url = f"http://127.0.0.1:{port}"

    with httpx.Client(timeout=_STARTUP_TIMEOUT_S) as probe:
        while True:
            try:
                resp = probe.get(f"{base_url}/testnet/health")
            except httpx.ConnectError:
                if time.monotonic() > deadline:
                    server.should_exit = True
                    thread.join(timeout=1.0)
                    raise _ServerNotReady(_STARTUP_TIMEOUT_S) from None
                time.sleep(_STARTUP_POLL_INTERVAL_S)
                continue
            if resp.status_code == 200:
                break
            if time.monotonic() > deadline:
                server.should_exit = True
                thread.join(timeout=1.0)
                raise _ServerNotReady(_STARTUP_TIMEOUT_S)
            time.sleep(_STARTUP_POLL_INTERVAL_S)

    yield base_url

    server.should_exit = True
    thread.join(timeout=5.0)


@pytest.mark.asyncio
async def test_real_lztforge_client_parses_mock_responses(testnet_base_url: str) -> None:
    """`Client(config=ClientConfig(base_url=...))` overrides the market host cleanly.

    `ClientConfig.base_url` is wired straight into the `HttpxSession` the constructor
    builds (`Client.__init__` -> `self._raw_transport(self.config.base_url, ...)`) —
    confirmed by reading `pylzt/client.py`, not assumed. No monkeypatch needed.
    """
    client = Client(
        tokens=["testnet-token"],
        config=ClientConfig(base_url=testnet_base_url, forum_base_url=testnet_base_url),
    )
    try:
        lot = await client.market.get_lot(ItemId(123))
        assert isinstance(lot, Lot)

        lots = await client.market.list_lots(LotFilter(category=lot.category)).first_page()
        assert all(isinstance(item, Lot) for item in lots)

        buy_result = await client.market.purchasing_fast_buy(item_id=123)
        assert buy_result is not None
    finally:
        await client.aclose()
