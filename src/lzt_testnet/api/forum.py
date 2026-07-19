"""L3 world read endpoints — the seeded forum plus the lazily-materialized streaming lot list.

All routes degrade to an empty result when no world is armed (``app.state.world is None``), so the
mock stays a clean server by default and the pre-existing suite is unaffected.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Query, Request

from lzt_testnet.world.arm import WorldBundle

router = APIRouter(prefix="/testnet/world")


def _world(request: Request) -> WorldBundle | None:
    return getattr(request.app.state, "world", None)


def _page(items: list[Any], next_cursor: int | None) -> dict[str, Any]:
    return {"items": [asdict(i) for i in items], "next_cursor": next_cursor}


@router.get("/forum/users", operation_id="world-forum-users")
async def forum_users(
    request: Request,
    cursor: int | None = Query(default=None),
    limit: int = Query(default=20),
) -> dict[str, Any]:
    world = _world(request)
    if world is None:
        return {"items": [], "next_cursor": None}
    users, next_cursor = world.forum.list_users(cursor, limit)
    return _page(users, next_cursor)


@router.get("/forum/threads", operation_id="world-forum-threads")
async def forum_threads(
    request: Request,
    cursor: int | None = Query(default=None),
    limit: int = Query(default=20),
) -> dict[str, Any]:
    world = _world(request)
    if world is None:
        return {"items": [], "next_cursor": None}
    threads, next_cursor = world.forum.list_threads(cursor, limit)
    return _page(threads, next_cursor)


@router.get("/forum/threads/{thread_id}/posts", operation_id="world-forum-posts")
async def forum_posts(request: Request, thread_id: int) -> dict[str, Any]:
    world = _world(request)
    if world is None:
        return {"items": []}
    return {"items": [asdict(p) for p in world.forum.posts_of(thread_id)]}


@router.get("/lots", operation_id="world-lots")
async def world_lots(
    request: Request,
    category: str = Query(default="steam"),
    cursor: int = Query(default=0),
    limit: int = Query(default=20),
) -> dict[str, Any]:
    """The effectively-infinite streaming account list — lots materialize on first fetch."""
    world = _world(request)
    if world is None:
        return {"items": [], "next_cursor": None}
    lots = world.materializer.page(category=category, cursor=cursor, limit=limit)
    return {
        "items": [asdict(lot) for lot in lots],
        "next_cursor": cursor + limit,  # streaming: there is always a next page
    }


@router.get("/lots/{item_id}/check", operation_id="world-lot-check")
async def check_lot(request: Request, item_id: int) -> dict[str, Any]:
    """A bad-lot / blacklist check: a SPAM seller's lot fails deterministically, every time."""
    world = _world(request)
    if world is None:
        return {"item_id": item_id, "valid": True}
    return {"item_id": item_id, "valid": not world.materializer.lot_check_fails(item_id)}
