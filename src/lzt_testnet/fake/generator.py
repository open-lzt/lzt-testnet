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
_MIN_COLLECTION = 5
_MAX_COLLECTION = 12


class FakeGenerator:
    """Builds fake instances of any Pydantic model via a cached polyfactory factory."""

    def __init__(self) -> None:
        self._factories: dict[type[BaseModel], type[ModelFactory[Any]]] = {}

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
                ModelFactory.create_factory(
                    model,
                    __randomize_collection_length__=True,
                    __min_collection_length__=_MIN_COLLECTION,
                    __max_collection_length__=_MAX_COLLECTION,
                ),
            )
            self._factories[model] = factory
        # polyfactory's **kwargs are field overrides, not the declared `factory_use_construct` bool
        built: BaseModel = factory.build(**(overrides or {}))  # type: ignore[arg-type]
        return built
