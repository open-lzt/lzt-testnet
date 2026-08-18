"""Stateful forum posts on the REAL upstream paths — the three endpoints a giveaway stands on.

Routes (mounted by `app.py` BEFORE the catch-all, with the same urls excluded from the route
table so the two cannot both claim them):

    GET  /posts                    posts_list   — a thread's posts, paged
    POST /posts                    posts_create — publish into a thread
    GET  /posts/{post_id}/likes    posts_likes  — who liked a post

Why these three are not left to the catch-all: upstream declares ``posts_list`` and
``posts_likes`` as ``Passthrough``, so the route table holds no response model and the catch-all
answers ``{}`` with status 200. A flow that collects participants from a thread would then finish
GREEN having seen nobody — a mock that manufactures false proof is worse than no mock.

**Response shapes are taken from the generated forum spec, never from what a caller happens to
expect.** That distinction is the whole point of the file: a mock written to match our own parser
would confirm our guess instead of testing it. Concretely — ``{"posts": [...], "posts_total": N}``
for the list, ``{"users": [{"user_id", "username"}]}`` for the likes, ``{"post": {...}}`` for the
create, and post fields named after ``Resp_PostModel``. ``system_info`` is NOT written here —
``SystemInfoMiddleware`` stamps it onto every JSON object response, so no handler can forget it.

One place the spec is wrong and this file deliberately isn't: ``GET /posts`` declares its ``posts``
array as ``Resp_ThreadModel`` — the THREAD model, which carries no ``post_id`` or ``poster_user_id``
at all. It is a scraping artifact: ``Resp_PostModel`` exists, carries exactly those fields, and
``Resp_ThreadModel.first_post`` points at it. Serving thread models would make every caller of this
endpoint wrong in the same way, so the array holds posts.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Query, Request

from lzt_testnet import errors
from lzt_testnet.state.thread_store import PostRecord, ThreadStore

router = APIRouter()

#: The upstream urls this module owns. `app.py` feeds them to `build_route_table` as exclusions —
#: without that the catch-all's own entry for the same (verb, url) may win and answer `{}`.
FORUM_POST_PATHS: frozenset[str] = frozenset({"/posts", "/posts/{post_id}/likes"})

_DEFAULT_LIMIT = 20
#: Who the mock posts as when a caller writes. The real endpoint infers the author from the token;
#: the testnet has no user table, so it answers as one fixed operator.
_SELF_USER_ID = 1
_SELF_USERNAME = "testnet-operator"


def thread_store(request: Request) -> ThreadStore:
    """Lazily attached, like the injection store — the router must work in bare-app tests."""
    store: ThreadStore | None = getattr(request.app.state, "thread_store", None)
    if store is None:
        store = ThreadStore()
        request.app.state.thread_store = store
    return store


def _post_json(post: PostRecord) -> dict[str, Any]:
    return {
        "post_id": post.post_id,
        "thread_id": post.thread_id,
        "poster_user_id": post.poster_user_id,
        "poster_username": post.poster_username,
        "post_create_date": post.post_create_date,
        "post_body": post.post_body,
        "post_body_html": post.post_body,
    }


@router.get("/posts", operation_id="forum-posts-list")
async def posts_list(
    request: Request,
    thread_id: int | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=_DEFAULT_LIMIT, ge=1, le=100),
) -> dict[str, Any]:
    """A thread's posts. ``thread_id`` is optional upstream, so its absence is a caller error here
    rather than a silent empty page: a giveaway that lost its thread id must not read as a thread
    with no participants."""
    if thread_id is None:
        raise errors.NotFound(item_id="posts?thread_id=")
    store = thread_store(request)
    posts, total = store.page(thread_id, page=page, limit=limit)
    thread = store.get(thread_id)
    return {
        "posts": [_post_json(p) for p in posts],
        "thread": {
            "thread_id": thread_id,
            "thread_title": thread.title if thread else f"Тема {thread_id}",
            "creator_user_id": thread.creator_user_id if thread else _SELF_USER_ID,
            "thread_post_count": total,
        },
        "posts_total": total,
    }


@router.post("/posts", operation_id="forum-posts-create")
async def posts_create(
    request: Request,
    post_body: str = Body(embed=True),
    thread_id: int | None = Body(default=None, embed=True),
    quote_post_id: int | None = Body(default=None, embed=True),
) -> dict[str, Any]:
    """Publish into a thread, and actually KEEP it: the next ``posts_list`` returns it.

    That is the property the giveaway scenario turns on — it publishes a commitment, waits, then
    reads the thread back. A create that returned a generated post without storing it would let the
    whole scenario pass while the commitment existed nowhere.
    """
    del quote_post_id  # accepted because the caller may send it; the mock threads no quotes
    if thread_id is None:
        raise errors.NotFound(item_id="posts (no thread_id)")
    post = thread_store(request).add_post(
        thread_id,
        poster_user_id=_SELF_USER_ID,
        poster_username=_SELF_USERNAME,
        post_body=post_body,
    )
    return {"post": _post_json(post)}


@router.get("/posts/{post_id}/likes", operation_id="forum-posts-likes")
async def posts_likes(
    request: Request,
    post_id: int,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=_DEFAULT_LIMIT, ge=1, le=100),
) -> dict[str, Any]:
    """Who liked a post. ``users``, not ``likes`` — the spec's key, and the one a caller decodes."""
    likers, total = thread_store(request).likers(post_id, page=page, limit=limit)
    return {
        "users": [{"user_id": uid, "username": name} for uid, name in likers],
        "users_total": total,
    }
