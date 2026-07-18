"""End-to-end round-trip — every collected `BaseMethod` driven over a real socket.

Unlike `test_all_methods_roundtrip.py` (in-process via `httpx.ASGITransport`), this
boots `create_app()` under a real `uvicorn` server (same technique as
`test_lztforge_client_smoke.py`) and drives all ~200 methods over an actual HTTP
connection — the closest proxy to "point pylzt at the running dev server" short of
an external subprocess. One server boot for the whole module (session-scoped fixture)
since booting per-method would dominate runtime for no extra signal.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator

import httpx
import pytest
import uvicorn

from lzt_testnet.api.app import create_app
from lzt_testnet.catalog.registry import collect_base_methods
from lzt_testnet.catalog.route_table import build_route_table

_STARTUP_TIMEOUT_S = 5.0
_STARTUP_POLL_INTERVAL_S = 0.05


class _ServerNotReady(RuntimeError):
    """The background uvicorn server did not answer `/testnet/health` in time."""

    def __init__(self, timeout_s: float) -> None:
        super().__init__(f"testnet server not ready after {timeout_s}s")


@pytest.fixture(scope="module")
def testnet_base_url() -> Iterator[str]:
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


def _build_request_path(url: str) -> str:
    path = url
    while "{" in path:
        start = path.index("{")
        end = path.index("}", start)
        path = path[:start] + "123" + path[end + 1 :]
    return path


def _all_methods() -> list[type]:  # type: ignore[type-arg]
    # Same dedupe/skip rules as test_all_methods_roundtrip.py: collapse methods
    # sharing one route template, and skip empty-`__url__` composite helpers
    # (ListLotsPage/GetLotsBatch) that `build_route_table` doesn't register either.
    seen: set[tuple[str, str]] = set()
    unique: list[type] = []  # type: ignore[type-arg]
    for cls in collect_base_methods():
        if not cls.__url__:
            continue
        key = (cls.__http_method__.value, cls.__url__)
        if key in seen:
            continue
        seen.add(key)
        unique.append(cls)
    return unique


_ROUTE_TABLE = build_route_table(exclude_paths=frozenset())


@pytest.mark.parametrize("method_cls", _all_methods(), ids=lambda cls: cls.__name__)
def test_method_roundtrip_over_real_socket(
    method_cls: type,  # type: ignore[type-arg]
    testnet_base_url: str,
) -> None:
    request_path = _build_request_path(method_cls.__url__)
    http_method = method_cls.__http_method__.value

    with httpx.Client(base_url=testnet_base_url, timeout=5.0) as client:
        response = client.request(
            http_method,
            request_path,
            headers={"Authorization": "Bearer e2e-token"},
        )

    assert response.status_code == 200
    # `RouteTable.match` is a first-match linear scan (frozen contract): a shared path
    # template registered earlier can win over `method_cls`'s own entry, so validate
    # against whichever entry the server actually resolved, not the method we intended
    # to exercise (same reasoning as test_all_methods_roundtrip.py's in-process test).
    match = _ROUTE_TABLE.match(http_method, "/" + request_path.lstrip("/"))
    assert match is not None
    matched_entry, _ = match
    returning = matched_entry.returning
    if returning is None:
        assert response.json() == {}
    else:
        returning.from_raw(response.json())
