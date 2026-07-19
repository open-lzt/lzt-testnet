"""Pure-ASGI fault injection — the one place chaos touches a live request.

Fast-path returns the request untouched when chaos is OFF and no ``X-Chaos`` header is present,
so with default settings the server is byte-identical to the pre-chaos mock (success criterion #1).
It is pure-ASGI (not ``BaseHTTPMiddleware``) because ``CONNECTION_DROP``/``TIMEOUT`` must abort a
response mid-flight, which the request/response middleware API cannot express.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from lzt_testnet.chaos.faults import POST_RESPONSE, PRE_RESPONSE, Fault, FaultContext, FaultKind
from lzt_testnet.chaos.render import apply_post_response, apply_pre_response

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

    from lzt_testnet.chaos.planner import FaultPlanner
    from lzt_testnet.chaos.seed import SeedController

_CHAOS_HEADER = b"x-chaos"
CHAOS_FAULT_SCOPE_KEY = (
    "lzt_chaos"  # where a decided DOMAIN fault is stashed for the in-handler injector
)


class ChaosConnectionDrop(Exception):
    """Raised after ``http.response.start`` to reset the connection before the body (D3).

    The test client uses ``ASGITransport(raise_app_exceptions=False)`` so it surfaces as a
    truncated ``Response`` rather than an exception (W3.5/R3).
    """


def _endpoint_key(path: str) -> str:
    """Coarse endpoint key for ``X-Chaos:kind@endpoint`` targeting and per-endpoint weights."""
    if path.endswith("/buy"):
        return "buy"
    if "/lots" in path:
        return "list_lots"
    if "/payments" in path:
        return "payments"
    return "*"


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers", []):
        if key == name:
            return str(value.decode("latin-1"))
    return None


def _with_content_length(
    headers: list[tuple[bytes, bytes]], body: bytes
) -> list[tuple[bytes, bytes]]:
    """Recompute Content-Length so a mutated (shorter/longer) body is a valid response."""
    out = [(k, v) for (k, v) in headers if k.lower() != b"content-length"]
    out.append((b"content-length", str(len(body)).encode()))
    return out


class FaultInjectionMiddleware:
    """Decides one fault per request (deterministic by seq) and applies it at the ASGI layer."""

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        state = scope["app"].state
        planner: FaultPlanner | None = getattr(state, "fault_planner", None)
        seed: SeedController | None = getattr(state, "seed", None)
        x_chaos = _header(scope, _CHAOS_HEADER)

        # Byte-identical passthrough when nothing is armed.
        if planner is None or seed is None or (not planner.armed and x_chaos is None):
            await self._app(scope, receive, send)
            return

        seq = seed.next_seq()
        ctx = FaultContext(
            method=scope["method"],
            path=scope["path"],
            seq=seq,
            endpoint=_endpoint_key(scope["path"]),
            rng=seed.stream(seq),
        )
        fault = planner.decide(ctx, x_chaos=x_chaos, legacy=None)
        if fault is None:
            await self._app(scope, receive, send)
            return

        recorder = getattr(state, "recorder", None)
        if recorder is not None:
            recorder.record(ctx, fault)

        if fault.kind is FaultKind.SLOW:
            await asyncio.sleep(float(fault.params.get("delay_s", 0.05)))  # type: ignore[arg-type]
            await self._app(scope, receive, send)
            return
        if fault.kind in PRE_RESPONSE:
            await self._send_pre_response(fault, send)
            return
        if fault.kind in POST_RESPONSE:
            await self._apply_post_response(fault, scope, receive, send)
            return
        # DOMAIN fault: stash for the in-handler injector (L2), pass through unchanged.
        scope[CHAOS_FAULT_SCOPE_KEY] = (ctx, fault)
        await self._app(scope, receive, send)

    async def _send_pre_response(self, fault: Fault, send: Send) -> None:
        effect = apply_pre_response(fault)
        await send(
            {"type": "http.response.start", "status": effect.status, "headers": effect.headers}
        )
        if effect.drop:
            raise ChaosConnectionDrop(fault.kind)
        await send({"type": "http.response.body", "body": effect.body})

    async def _apply_post_response(
        self, fault: Fault, scope: Scope, receive: Receive, send: Send
    ) -> None:
        status = 200
        headers: list[tuple[bytes, bytes]] = []
        body = b""

        async def buffering_send(message: Message) -> None:
            nonlocal status, headers, body
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = list(message.get("headers", []))
            elif message["type"] == "http.response.body":
                body += message.get("body", b"")
                if message.get("more_body", False):
                    return
                new_status, new_headers, new_body = apply_post_response(
                    fault, status, headers, body
                )
                await send(
                    {
                        "type": "http.response.start",
                        "status": new_status,
                        "headers": _with_content_length(new_headers, new_body),
                    }
                )
                await send({"type": "http.response.body", "body": new_body})

        await self._app(scope, receive, buffering_send)
