"""Each fault renders to the right wire effect."""

from __future__ import annotations

import json

import pytest

from lzt_testnet.chaos.faults import Fault, FaultKind
from lzt_testnet.chaos.render import apply_post_response, apply_pre_response


def test_nginx_502_is_raw_html_not_json() -> None:
    eff = apply_pre_response(Fault(FaultKind.HTTP_502_NGINX))
    assert eff.status == 502
    assert (b"content-type", b"text/html") in eff.headers
    assert b"502 Bad Gateway" in eff.body
    with pytest.raises(json.JSONDecodeError):
        json.loads(eff.body)  # it is NOT json


def test_rate_limited_sets_retry_after() -> None:
    eff = apply_pre_response(Fault(FaultKind.RATE_LIMITED_429, {"retry_after": 2.5}))
    assert eff.status == 429
    assert (b"retry-after", b"2.5") in eff.headers


def test_connection_drop_signals_drop() -> None:
    assert apply_pre_response(Fault(FaultKind.CONNECTION_DROP)).drop is True


def test_byzantine_missing_field_drops_key() -> None:
    body = json.dumps({"price": "10", "currency": "usd"}).encode()
    _, _, out = apply_post_response(
        Fault(FaultKind.BYZANTINE_MISSING_FIELD, {"drop_field": "price"}), 200, [], body
    )
    assert json.loads(out) == {"currency": "usd"}


def test_byzantine_null_and_wrong_type() -> None:
    body = json.dumps({"price": "10"}).encode()
    _, _, nulled = apply_post_response(
        Fault(FaultKind.BYZANTINE_NULL, {"drop_field": "price"}), 200, [], body
    )
    assert json.loads(nulled) == {"price": None}
    _, _, wrong = apply_post_response(
        Fault(FaultKind.BYZANTINE_WRONG_TYPE, {"drop_field": "price"}), 200, [], body
    )
    assert isinstance(json.loads(wrong)["price"], list)


def test_truncated_body_is_shorter() -> None:
    body = b'{"a": 1, "b": 2, "c": 3}'
    _, _, out = apply_post_response(Fault(FaultKind.TRUNCATED_BODY), 200, [], body)
    assert len(out) < len(body)


def test_malformed_json_fails_to_parse() -> None:
    body = json.dumps({"ok": True}).encode()
    _, _, out = apply_post_response(Fault(FaultKind.MALFORMED_JSON), 200, [], body)
    with pytest.raises(json.JSONDecodeError):
        json.loads(out)
