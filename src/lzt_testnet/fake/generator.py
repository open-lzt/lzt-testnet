"""Cached polyfactory-backed fake data generation for arbitrary Pydantic models."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from polyfactory.factories.pydantic_factory import ModelFactory
from pydantic import BaseModel

# polyfactory fills a list field with exactly one element unless told otherwise, so every catalog
# page came back holding a single lot — enough to prove a route answers, useless for exercising a
# caller that pages, sorts, or takes N. A handful of items per page is what a real listing looks
# like, and it is the difference between "the autobuy flow ran" and "the autobuy flow bought three".
#
# The ceiling is deliberately close to the floor: the length is randomized at EVERY nesting level,
# so the cost of a deeply nested response is the range raised to its depth. At 12 the Mihoyo
# category took ~10s to build and timed its caller out; at 7 it is under 3s, and a page still
# holds the several items the floor exists to guarantee.
_MIN_COLLECTION = 5
_MAX_COLLECTION = 7


class _JsonSafeFactory(ModelFactory[Any]):
    """Base for every generated factory, so nested models inherit the provider map.

    polyfactory fills an `Any` field with a bare `object()`, which no JSON encoder can
    serialize — the route then answers 500 instead of a mock response. `Notification.extra` is
    `dict[str, Any]` and hits this on every call. Setting the map on a BASE class matters:
    nested models build through factories derived from the caller's class, so overriding it on
    `ModelFactory` per call never reached them.
    """

    __is_base_factory__ = True
    __provider_map__ = {**ModelFactory.get_provider_map(), Any: lambda: "fake"}


class FakeGenerator:
    """Builds fake instances of any Pydantic model via a cached polyfactory factory."""

    def __init__(self) -> None:
        self._factories: dict[type[BaseModel], type[ModelFactory[Any]]] = {}
        #: One built sample per model. The collection length is randomized at EVERY nesting
        #: level, so a deeply nested response (`CategoryMihoyo`) took ~10s to build and timed
        #: the caller out. Building once and handing out deep copies keeps a page realistically
        #: sized without paying for it on every request; the copy is what keeps a caller that
        #: mutates the payload — `apply_query_filters` folds values in place — from corrupting
        #: the sample for everyone after it.
        self._samples: dict[type[BaseModel], BaseModel] = {}

    def build(
        self,
        model: type[BaseModel],
        overrides: Mapping[str, object] | None = None,
    ) -> BaseModel:
        """Build a fake instance of `model`, with `overrides` taking precedence.

        Args:
            model: the Pydantic model class to fake.
            overrides: field values that must appear verbatim in the result
                (e.g. echoing a path/query param like `item_id` into the response).
        """
        factory = self._factories.get(model)
        if factory is None:
            factory = cast(
                "type[ModelFactory[Any]]",
                _JsonSafeFactory.create_factory(
                    model,
                    __randomize_collection_length__=True,
                    __min_collection_length__=_MIN_COLLECTION,
                    __max_collection_length__=_MAX_COLLECTION,
                ),
            )
            self._factories[model] = factory
        sample = self._samples.get(model)
        if sample is None:
            # polyfactory's **kwargs are field overrides, not the `factory_use_construct` bool
            sample = cast("BaseModel", factory.build())
            _replace_bare_objects(sample)
            self._samples[model] = sample

        built = sample.model_copy(deep=True)
        return built.model_copy(update=dict(overrides)) if overrides else built


def _replace_bare_objects(value: object, depth: int = 0) -> None:
    """Swap polyfactory's bare `object()` fillers for a JSON-safe string, in place.

    `__provider_map__` fixes this for the model a factory is built FOR, but a nested model gets
    its own factory that does not inherit the map — `Notification.extra` (`dict[str, Any]`) sits
    two levels down and still arrived holding `object()`, which made the route answer 500.
    Containers stay mutable on a frozen model, so the fix lands without rebuilding anything.
    """
    if depth > 6:
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if type(item) is object:
                value[key] = "fake"
            else:
                _replace_bare_objects(item, depth + 1)
    elif isinstance(value, list):
        for i, item in enumerate(value):
            if type(item) is object:
                value[i] = "fake"
            else:
                _replace_bare_objects(item, depth + 1)
    elif isinstance(value, BaseModel):
        for name in type(value).model_fields:
            _replace_bare_objects(getattr(value, name, None), depth + 1)
