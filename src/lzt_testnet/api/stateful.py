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

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from lzt_testnet import errors
from lzt_testnet.api.dependencies import force_error_header, get_bearer_token
from lzt_testnet.chaos.domain import DomainOutcome, DomainView, maybe_inject
from lzt_testnet.chaos.faults import Fault, FaultContext
from lzt_testnet.chaos.legacy import raise_legacy_forced_error
from lzt_testnet.chaos.middleware import CHAOS_FAULT_SCOPE_KEY
from lzt_testnet.chaos.seed import IdKind, SeedController
from lzt_testnet.fake.generator import FakeGenerator
from lzt_testnet.state.lot_store import LotRecord, LotStore
from lzt_testnet.state.payment_store import PaymentRecord, PaymentStore
from lzt_testnet.state.scenario_store import ScenarioStore

router = APIRouter(prefix="/testnet/stateful")


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


def _seed(request: Request) -> SeedController:
    """The app's SeedController. Lazily attach a default one so the router works when mounted
    without the full chaos wiring (bare-app tests, embedding elsewhere)."""
    seed: SeedController | None = getattr(request.app.state, "seed", None)
    if seed is None:
        seed = SeedController(0)
        request.app.state.seed = seed
    return seed


def _domain_outcome(request: Request, item_id: int, token: str) -> DomainOutcome:
    """Resolve the L2 buy outcome from the fault the middleware decided for this request.
    Degrades to PROCEED when no chaos middleware is present (no stashed fault)."""
    stashed: tuple[FaultContext, Fault] | None = request.scope.get(CHAOS_FAULT_SCOPE_KEY)
    fault = stashed[1] if stashed is not None else None
    counters: dict[str, int] | None = getattr(request.app.state, "chaos_counters", None)
    if counters is None:
        counters = {}
        request.app.state.chaos_counters = counters
    view = DomainView(item_id=item_id, token=token, was_bought=False)
    return maybe_inject(fault, view, counters)


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
    seed: Annotated[SeedController, Depends(_seed)],
) -> Lot:
    raise_legacy_forced_error(force_error)
    record = LotRecord(
        item_id=seed.next_id(IdKind.LOT),
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
    raise_legacy_forced_error(force_error)
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
    raise_legacy_forced_error(force_error, item_id)
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
    raise_legacy_forced_error(force_error, item_id)
    if not body.price:
        raise errors.BadRequest(field="price")
    _owned_lot(lot_store, item_id, token)
    lot_store.update(item_id, price=body.price)
    return {}


@router.post("/lots/{item_id}/buy", operation_id="fast-buy")
async def fast_buy(
    request: Request,
    item_id: int,
    token: Annotated[str, Depends(get_bearer_token)],
    force_error: Annotated[str | None, Depends(force_error_header)],
    lot_store: Annotated[LotStore, Depends(_lot_store)],
    payment_store: Annotated[PaymentStore, Depends(_payment_store)],
    scenario_store: Annotated[ScenarioStore, Depends(_scenario_store)],
    seed: Annotated[SeedController, Depends(_seed)],
) -> dict[str, object]:
    raise_legacy_forced_error(force_error, item_id)
    record = lot_store.get(item_id)
    if record is None or scenario_store.was_bought(item_id):
        raise errors.NotFound(item_id=item_id)

    outcome = _domain_outcome(request, item_id, token)
    if outcome is DomainOutcome.ALREADY_SOLD:
        raise errors.NotFound(item_id=item_id)  # a racing buyer won it first
    if outcome is DomainOutcome.TRANSIENT_RETRY:
        raise errors.RateLimited(retry_after=0.1)  # transient — a retrying client converges
    if outcome is DomainOutcome.PENDING:
        return {"status": "pending", "item_id": item_id}

    # PROCEED / FAIL_INVALID / CHARGE_THEN_FAIL all consume the lot — the money moved.
    lot_store.delete(item_id)
    scenario_store.mark_bought(item_id)
    if outcome is DomainOutcome.CHARGE_THEN_FAIL:
        raise errors.PaymentFailed()  # charged (lot gone) yet no PaymentRecord — a reconciliation trap

    payment_store.append(
        PaymentRecord(
            operation_id=seed.next_id(IdKind.PAYMENT),
            account_token=token,
            operation_type="purchase",
            item_id=item_id,
            amount=record.price,
        )
    )
    if outcome is DomainOutcome.FAIL_INVALID:
        return {"status": "invalid_account", "item_id": item_id}
    return {}


@router.get("/payments", operation_id="payments")
async def payments(
    token: Annotated[str, Depends(get_bearer_token)],
    payment_store: Annotated[PaymentStore, Depends(_payment_store)],
    force_error: Annotated[str | None, Depends(force_error_header)] = None,
    cursor: int | None = Query(default=None),
    limit: int = Query(default=20),
) -> list[PaymentRecord]:
    raise_legacy_forced_error(force_error)
    records, _next_cursor = payment_store.list(account_token=token, cursor=cursor, limit=limit)
    return records
