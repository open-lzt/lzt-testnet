"""Test-harness control routes: reset state and revoke scenario tokens."""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()


class RevokeTokenBody(BaseModel):
    token: str


@router.post("/testnet/reset")
async def reset_state(request: Request) -> dict[str, str]:
    request.app.state.lot_store.reset()
    request.app.state.payment_store.reset()
    request.app.state.scenario_store.reset()
    return {"status": "reset"}


@router.post("/testnet/revoke-token")
async def revoke_token(request: Request, body: RevokeTokenBody) -> dict[str, str]:
    request.app.state.scenario_store.revoke(body.token)
    return {"status": "revoked", "token": body.token}
