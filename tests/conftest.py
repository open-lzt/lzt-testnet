"""Shared pytest fixtures: an ASGI-wired async client for the mock testnet app."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from lzt_testnet.api.app import create_app


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """Yield an AsyncClient wired to a freshly built app instance.

    `create_app()` constructs new `LotStore`/`PaymentStore`/`ScenarioStore` instances
    on every call, so each test gets isolated in-memory state without needing an
    explicit reset — there is no shared/cached app instance anywhere in the codebase.
    """
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac
