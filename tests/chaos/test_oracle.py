"""T14 — differential oracle: an idempotent client converges to the clean outcome; a naive one
does not. The naive case failing the oracle (returning False) proves the oracle detects divergence.
"""

from __future__ import annotations

from httpx import AsyncClient

from tests.helpers.gauntlet import assert_survives, run_oracle

_AUTH = {"Authorization": "Bearer oracle"}
_LOT = {"category": "steam", "price": "5.00", "currency": "usd", "title": "acc"}


async def _make_lot(client: AsyncClient) -> int:
    resp = await client.post("/testnet/stateful/lots", headers=_AUTH, json=_LOT)
    return int(resp.json()["item_id"])


async def _idempotent(client: AsyncClient) -> None:
    """Retries past transient buy faults to convergence — reaches the same outcome under chaos."""
    item_id = await _make_lot(client)
    for _ in range(15):
        resp = await client.post(f"/testnet/stateful/lots/{item_id}/buy", headers=_AUTH)
        if resp.status_code not in (429, 500, 502, 503, 504):
            return


async def _naive(client: AsyncClient) -> None:
    """Buys once and gives up on the first transient error — diverges under chaos."""
    item_id = await _make_lot(client)
    await client.post(f"/testnet/stateful/lots/{item_id}/buy", headers=_AUTH)


async def test_oracle_passes_for_idempotent_client() -> None:
    assert await run_oracle(_idempotent, seed=1) is True


async def test_oracle_fails_for_naive_client() -> None:
    # RED: without retry handling the naive client's outcome diverges → oracle catches it.
    assert await run_oracle(_naive, seed=1) is False


async def test_assert_survives_returns_scorecard() -> None:
    async def script(client: AsyncClient) -> None:
        for _ in range(6):
            await client.get("/testnet/stateful/lots", headers=_AUTH)

    report = await assert_survives("nginx-down", script, seed=502)
    card = report.as_scorecard()
    assert "seed=502" in card
    assert report.injected >= 1  # a 502-heavy scenario injects over 6 requests
