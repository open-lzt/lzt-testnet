"""Turns a decided `Fault` into an actual HTTP effect — the only place that knows what a fault
*looks like on the wire* (a raw nginx 502, a lying JSON body, a truncated stream)."""

from __future__ import annotations

import json
from dataclasses import dataclass

from lzt_testnet.chaos.faults import Fault, FaultKind

NGINX_502_HTML: str = (
    "<html>\r\n<head><title>502 Bad Gateway</title></head>\r\n"
    "<body>\r\n<center><h1>502 Bad Gateway</h1></center>\r\n"
    "<hr><center>nginx</center>\r\n</body>\r\n</html>\r\n"
)

Header = tuple[bytes, bytes]
_JSON: list[Header] = [(b"content-type", b"application/json")]
_HTML: list[Header] = [(b"content-type", b"text/html")]


@dataclass(frozen=True, slots=True)
class ResponseEffect:
    """Short-circuit response for a pre-response fault. ``drop`` = raise after start (reset)."""

    status: int
    headers: list[Header]
    body: bytes
    drop: bool = False


def _body(payload: object) -> bytes:
    return json.dumps(payload).encode()


def apply_pre_response(fault: Fault) -> ResponseEffect:
    """Build the short-circuit response for a PRE_RESPONSE fault (the handler never runs)."""
    kind = fault.kind
    if kind is FaultKind.HTTP_500:
        return ResponseEffect(500, list(_JSON), _body({"error": "internal server error"}))
    if kind is FaultKind.HTTP_503:
        return ResponseEffect(503, list(_JSON), _body({"error": "service unavailable"}))
    if kind is FaultKind.HTTP_504:
        return ResponseEffect(504, list(_JSON), _body({"error": "gateway timeout"}))
    if kind is FaultKind.HTTP_502_NGINX:
        return ResponseEffect(502, list(_HTML), NGINX_502_HTML.encode())
    if kind is FaultKind.RATE_LIMITED_429:
        retry_after = str(fault.params.get("retry_after", 1.0))
        headers = [*_JSON, (b"retry-after", retry_after.encode())]
        return ResponseEffect(429, headers, _body({"error": "rate limited"}))
    if kind is FaultKind.AUTH_DROP_401:
        return ResponseEffect(401, list(_JSON), _body({"error": "token expired"}))
    if kind is FaultKind.UNKNOWN_ERROR_CODE:
        return ResponseEffect(418, list(_JSON), _body({"code": "E_UNMAPPED_9001"}))
    if kind in (FaultKind.CONNECTION_DROP, FaultKind.TIMEOUT):
        return ResponseEffect(502, list(_HTML), b"", drop=True)
    raise ValueError(f"{kind} is not a pre-response fault")


def apply_post_response(
    fault: Fault, status: int, headers: list[Header], body: bytes
) -> tuple[int, list[Header], bytes]:
    """Mutate a real response for a POST_RESPONSE fault. ``SLOW`` is a no-op here (mw sleeps)."""
    kind = fault.kind
    if kind is FaultKind.SLOW:
        return status, headers, body
    if kind is FaultKind.MALFORMED_JSON:
        return status, headers, body + b'}{"broken":'
    if kind is FaultKind.TRUNCATED_BODY:
        return status, headers, body[: len(body) // 2]
    if kind in (
        FaultKind.BYZANTINE_MISSING_FIELD,
        FaultKind.BYZANTINE_NULL,
        FaultKind.BYZANTINE_WRONG_TYPE,
    ):
        return status, headers, _byzantine(kind, fault, body)
    raise ValueError(f"{kind} is not a post-response fault")


def _byzantine(kind: FaultKind, fault: Fault, body: bytes) -> bytes:
    """200 OK, but the JSON lies. Non-JSON bodies pass through unchanged."""
    try:
        data = json.loads(body)
    except (ValueError, TypeError):
        return body
    if not isinstance(data, dict) or not data:
        return body
    name = str(fault.params.get("drop_field") or next(iter(data)))
    if name not in data:
        return body
    if kind is FaultKind.BYZANTINE_MISSING_FIELD:
        del data[name]
    elif kind is FaultKind.BYZANTINE_NULL:
        data[name] = None
    else:  # BYZANTINE_WRONG_TYPE
        data[name] = ["unexpected", "list"]
    return json.dumps(data).encode()
