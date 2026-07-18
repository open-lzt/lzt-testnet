"""Stateful mock endpoints for the fast-buy / lot-lifecycle testnet scenarios.

Routes (mounted by `app.py` via `app.include_router(router)`):
    POST /testnet/stateful/lots               create-lot
    GET  /testnet/stateful/lots                list-lots
    POST /testnet/stateful/lots/{item_id}/bump bump
    POST /testnet/stateful/lots/{item_id}/price set-price
    POST /testnet/stateful/lots/{item_id}/buy  fast-buy
    GET  /testnet/stateful/payments             payments

These paths are testnet-only inventions (not derived from the real lzt.market
catalog) since they model mutation semantics no catalog spec captures.
"""

from __future__ import annotations

import itertools
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from lzt_testnet import errors
from lzt_testnet.api.dependencies import force_error_header, get_bearer_token
from lzt_testnet.fake.generator import FakeGenerator
from lzt_testnet.state.lot_store import LotRecord, LotStore
from lzt_testnet.state.payment_store import PaymentRecord, PaymentStore
from lzt_testnet.state.scenario_store import ScenarioStore

router = APIRouter(prefix="/testnet/stateful")

_item_id_counter = itertools.count(1)
_operation_id_counter = itertools.count(1)

_FORCE_ERROR_MAP: dict[str, Exception] = {
    "rate_limited": errors.RateLimited(retry_after=1.0),
    "auth_failed": errors.AuthFailed(token_id=""),
    "transport_error": errors.TransportError(status=500),
    "payment_failed": errors.PaymentFailed(),
}


def _raise_forced_error(force_error: str | None, item_id: int | None = None) -> None:
    """Raises the typed error requested via `X-Testnet-Force-Error`, before any state access.

    Mirrors `catch_all._FORCE_ERROR_MAP` (same retry/status/sentinel values) plus
    `not_found`, which stateful routes support but the generic catch-all doesn't need.
    """
    if force_error is None:
        return
    if force_error == "not_found":
        raise errors.NotFound(item_id=item_id if item_id is not None else "unknown")
    mapped = _FORCE_ERROR_MAP.get(force_error)
    if mapped is not None:
        raise mapped


class Lot(BaseModel):
    """Fake response shape for a stateful lot (echoes the stored record's fields)."""

    item_id: int
    category: str
    price: str
    currency: str
    title: str
    attributes: dict[str, str]


class CreateLotRequest(BaseModel):
    """Minimal create-lot request body — real pylzt create-lot DTO not wired here."""

    category: str
    price: str
    currency: str
    title: str
    attributes: dict[str, str] = {}


class SetPriceRequest(BaseModel):
    """Body for set-price; `price` presence is validated explicitly (empty -> BadRequest)."""

    price: str = ""


def _lot_store(request: Request) -> LotStore:
    return request.app.state.lot_store  # type: ignore[no-any-return]


def _payment_store(request: Request) -> PaymentStore:
    return request.app.state.payment_store  # type: ignore[no-any-return]


def _scenario_store(request: Request) -> ScenarioStore:
    return request.app.state.scenario_store  # type: ignore[no-any-return]


def _fake_generator(request: Request) -> FakeGenerator:
    return request.app.state.fake_generator  # type: ignore[no-any-return]


def _lot_response(generator: FakeGenerator, record: LotRecord) -> Lot:
    overrides = {
        "item_id": record.item_id,
        "category": record.category,
        "price": record.price,
        "currency": record.currency,
        "title": record.title,
        "attributes": record.attributes,
    }
    built = generator.build(Lot, overrides=overrides)
    assert isinstance(built, Lot)  # narrows FakeGenerator's BaseModel return
    return built


def _owned_lot(lot_store: LotStore, item_id: int, token: str) -> LotRecord:
    """Looks up `item_id`, raising `NotFound` if absent or owned by another token."""
    record = lot_store.get(item_id)
    if record is None or record.seller_token != token:
        raise errors.NotFound(item_id=item_id)
    return record


@router.post("/lots", operation_id="create-lot")
async def create_lot(
    body: CreateLotRequest,
    token: Annotated[str, Depends(get_bearer_token)],
    force_error: Annotated[str | None, Depends(force_error_header)],
    lot_store: Annotated[LotStore, Depends(_lot_store)],
    generator: Annotated[FakeGenerator, Depends(_fake_generator)],
) -> Lot:
    _raise_forced_error(force_error)
    record = LotRecord(
        item_id=next(_item_id_counter),
        seller_token=token,
        category=body.category,
        price=body.price,
        currency=body.currency,
        title=body.title,
        published_at=datetime.now(UTC),
        attributes=dict(body.attributes),
    )
    lot_store.create(record)
    return _lot_response(generator, record)


@router.get("/lots", operation_id="list-lots")
async def list_lots(
    lot_store: Annotated[LotStore, Depends(_lot_store)],
    generator: Annotated[FakeGenerator, Depends(_fake_generator)],
    force_error: Annotated[str | None, Depends(force_error_header)] = None,
    category: str | None = Query(default=None),
    seller_token: str | None = Query(default=None),
    cursor: int | None = Query(default=None),
    limit: int = Query(default=20),
) -> list[Lot]:
    _raise_forced_error(force_error)
    records, _next_cursor = lot_store.list(
        category=category, seller_token=seller_token, cursor=cursor, limit=limit
    )
    return [_lot_response(generator, record) for record in records]


@router.post("/lots/{item_id}/bump", operation_id="bump")
async def bump(
    item_id: int,
    token: Annotated[str, Depends(get_bearer_token)],
    force_error: Annotated[str | None, Depends(force_error_header)],
    lot_store: Annotated[LotStore, Depends(_lot_store)],
) -> dict[str, object]:
    _raise_forced_error(force_error, item_id)
    _owned_lot(lot_store, item_id, token)
    lot_store.update(item_id, published_at=datetime.now(UTC))
    return {}


@router.post("/lots/{item_id}/price", operation_id="set-price")
async def set_price(
    item_id: int,
    body: SetPriceRequest,
    token: Annotated[str, Depends(get_bearer_token)],
    force_error: Annotated[str | None, Depends(force_error_header)],
    lot_store: Annotated[LotStore, Depends(_lot_store)],
) -> dict[str, object]:
    _raise_forced_error(force_error, item_id)
    if not body.price:
        raise errors.BadRequest(field="price")
    _owned_lot(lot_store, item_id, token)
    lot_store.update(item_id, price=body.price)
    return {}


@router.post("/lots/{item_id}/buy", operation_id="fast-buy")
async def fast_buy(
    item_id: int,
    token: Annotated[str, Depends(get_bearer_token)],
    force_error: Annotated[str | None, Depends(force_error_header)],
    lot_store: Annotated[LotStore, Depends(_lot_store)],
    payment_store: Annotated[PaymentStore, Depends(_payment_store)],
    scenario_store: Annotated[ScenarioStore, Depends(_scenario_store)],
) -> dict[str, object]:
    _raise_forced_error(force_error, item_id)
    record = lot_store.get(item_id)
    if record is None or scenario_store.was_bought(item_id):
        raise errors.NotFound(item_id=item_id)
    lot_store.delete(item_id)
    scenario_store.mark_bought(item_id)
    payment_store.append(
        PaymentRecord(
            operation_id=next(_operation_id_counter),
            account_token=token,
            operation_type="purchase",
            item_id=item_id,
            amount=record.price,
        )
    )
    return {}


@router.get("/payments", operation_id="payments")
async def payments(
    token: Annotated[str, Depends(get_bearer_token)],
    payment_store: Annotated[PaymentStore, Depends(_payment_store)],
    force_error: Annotated[str | None, Depends(force_error_header)] = None,
    cursor: int | None = Query(default=None),
    limit: int = Query(default=20),
) -> list[PaymentRecord]:
    _raise_forced_error(force_error)
    records, _next_cursor = payment_store.list(account_token=token, cursor=cursor, limit=limit)
    return records
