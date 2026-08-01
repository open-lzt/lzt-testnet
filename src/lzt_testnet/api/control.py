"""Test-harness control routes: reset state and revoke scenario tokens."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from lzt_testnet.api.catch_all import injection_store
from lzt_testnet.api.dependencies import require_control_key

router = APIRouter(dependencies=[Depends(require_control_key)])


class RevokeTokenBody(BaseModel):
    token: str


class InjectLotBody(BaseModel):
    """One lot to prepend to a category listing. `category` is the URL segment (`steam`)."""

    category: str
    price: int
    title: str
    item_id: int | None = None


@router.post("/testnet/reset")
async def reset_state(request: Request) -> dict[str, str]:
    request.app.state.lot_store.reset()
    request.app.state.payment_store.reset()
    request.app.state.scenario_store.reset()
    injection_store(request).reset()
    return {"status": "reset"}


@router.post("/testnet/inject-lot")
async def inject_lot(request: Request, body: InjectLotBody) -> dict[str, object]:
    """Makes a category listing change, which is the only way a diffing poller emits anything."""
    store = injection_store(request)
    item_id = body.item_id if body.item_id is not None else store.next_item_id()
    store.add(
        body.category.strip("/"),
        {"item_id": item_id, "price": body.price, "title": body.title},
    )
    return {"status": "injected", "item_id": item_id, "category": body.category}


@router.post("/testnet/revoke-token")
async def revoke_token(request: Request, body: RevokeTokenBody) -> dict[str, str]:
    request.app.state.scenario_store.revoke(body.token)
    return {"status": "revoked", "token": body.token}
