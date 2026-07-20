"""Generic catch-all route dispatching stateless endpoints via `RouteTable` + `FakeGenerator`."""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from lzt_testnet import errors
from lzt_testnet.api.dependencies import force_error_header, get_bearer_token
from lzt_testnet.chaos.legacy import raise_legacy_forced_error
from lzt_testnet.fake.generator import FakeGenerator
from lzt_testnet.fake.query_filters import apply_query_filters

router = APIRouter()

_UNCOERCIBLE = object()


def _coerce_override(raw_value: str, model: type[BaseModel], field_name: str) -> object:
    """Best-effort coercion of a path param string to the target field's declared type.

    Returns `_UNCOERCIBLE` when the field is declared `int` but the path segment isn't
    numeric — a mismatched route param (route-table ambiguity on shared path prefixes,
    a frozen upstream property) must not be forced into the model and crash generation.
    """
    field_info = model.model_fields.get(field_name)
    if field_info is not None and field_info.annotation is int:
        try:
            return int(raw_value)
        except ValueError:
            return _UNCOERCIBLE
    return raw_value


@router.api_route(
    "/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
)
async def catch_all(
    request: Request,
    path: str,
    token: str = Depends(get_bearer_token),
    force_error: str | None = Depends(force_error_header),
) -> dict[str, Any]:
    """Matches the request against `RouteTable` and returns a real or faked response."""
    route_table = request.app.state.route_table
    match = route_table.match(request.method, "/" + path)
    if match is None:
        raise errors.NotFound(item_id=path or "unknown")
    entry, path_params = match

    raise_legacy_forced_error(force_error)

    scenario_store = request.app.state.scenario_store
    if scenario_store.is_revoked(token):
        raise errors.AuthFailed(token_id=token)

    if entry.returning is None:
        return {}

    overrides: dict[str, object] = {}
    if issubclass(entry.returning, BaseModel):
        for name in entry.path_param_names:
            if name in entry.returning.model_fields and name in path_params:
                coerced = _coerce_override(path_params[name], entry.returning, name)
                if coerced is not _UNCOERCIBLE:
                    overrides[name] = coerced

    fake_generator = cast("FakeGenerator", request.app.state.fake_generator)
    instance = fake_generator.build(entry.returning, overrides=overrides)
    return apply_query_filters(instance.model_dump(mode="json"), request.query_params)
