"""Test-harness control routes: reset state and revoke scenario tokens."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from lzt_testnet.api.dependencies import require_control_key

router = APIRouter(dependencies=[Depends(require_control_key)])


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
