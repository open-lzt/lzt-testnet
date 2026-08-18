"""``system_info`` is stamped onto every JSON object response — once, here.

The real forum API attaches this envelope to every response it returns. A mock that leaves it to
each handler gets it right on the handlers somebody remembered and wrong on the rest, and «wrong»
here is silent: a client that reads ``system_info.time`` sees a missing key on exactly the endpoint
nobody thought about. It was already copied into three handlers when this file replaced them, which
is the number at which a repetition stops being a coincidence.

**Middleware, not a dependency or a response model.** A dependency returns a value a handler still
has to place in its own dict — the placement is the part that gets forgotten. A base response model
would force every handler to declare it and would not cover the catch-all, which builds its payload
from a generated model that has no idea this envelope exists.

Deliberately does NOT touch:

* non-JSON and non-object bodies — a list response is not an envelope, and rewriting one would
  invent a shape the upstream never returns;
* a body that already carries ``system_info`` — a handler with a reason to state its own wins,
  and the reason is visible where it is written rather than hidden behind this middleware;
* error responses — an error's shape is its own contract (``lzt_testnet.errors``), and a client
  branching on it must not receive a success envelope glued onto a failure;
* ``/testnet/*`` — the stand's OWN controls (reset, seeding, health, the stateful lot routes).
  They imitate nothing upstream, so stamping an upstream envelope onto them would be a lie about
  whose API they are. Caught by seven tests asserting the exact body of a control response, which
  is the right way for it to be caught.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

_KEY = "system_info"
#: The stand's own control surface — not an imitation of anything upstream.
_STAND_PREFIX = "/testnet/"
#: Who the mock says is looking. The real value comes from the token's owner; the testnet has one.
_VISITOR_ID = 1


def build_system_info() -> dict[str, int]:
    """The envelope itself. Public so a test can assert against the same shape the server sends."""
    now = int(datetime.now(UTC).timestamp())
    return {"visitor_id": _VISITOR_ID, "time": now, "log_id": now}


class SystemInfoMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        if request.url.path.startswith(_STAND_PREFIX):
            return response
        if response.status_code >= 400:
            return response
        if response.media_type is not None and "json" not in response.media_type:
            return response

        # Читается НАЛИЧИЕ потока, а не класс ответа. Первая версия сужала до
        # `StreamingResponse`, и часть ответов уходила мимо конверта: `BaseHTTPMiddleware`
        # оборачивает не всё и не всегда в этот класс. Тест на конверт это и поймал.
        body_iterator = getattr(response, "body_iterator", None)
        if body_iterator is None:
            return response
        chunks: list[bytes] = []
        async for chunk in body_iterator:
            # Starlette types a chunk as str | bytes | memoryview; only bytes join.
            chunks.append(chunk.encode() if isinstance(chunk, str) else bytes(chunk))
        body = b"".join(chunks)
        try:
            payload: Any = json.loads(body)
        except ValueError:
            # Not JSON after all — hand it back byte-for-byte. Streaming bodies pass through here
            # too, and re-encoding one would corrupt it.
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        # ПУСТОЙ объект конверта не получает. `{}` — это ответ catch-all на метод, у которого нет
        # модели: признание «сказать нечего». Конверт делает такую заглушку похожей на настоящий
        # ответ, то есть ровно тем ложным доказательством, против которого писался этот стенд.
        # Поймано в CI: 75 e2e-тестов сверяют такой ответ на точное равенство `{}`.
        if isinstance(payload, dict) and payload and _KEY not in payload:
            payload[_KEY] = build_system_info()

        encoded = json.dumps(payload, ensure_ascii=False).encode()
        headers = dict(response.headers)
        # The body length changed; a stale Content-Length truncates the response at the client and
        # shows up as "unexpected end of JSON", which reads like a client bug for an afternoon.
        headers.pop("content-length", None)
        return Response(
            content=encoded,
            status_code=response.status_code,
            headers=headers,
            media_type=response.media_type or "application/json",
        )
