"""Cached polyfactory-backed fake data generation for arbitrary Pydantic models."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from polyfactory.factories.pydantic_factory import ModelFactory
from pydantic import BaseModel


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
            factory = cast("type[ModelFactory[Any]]", ModelFactory.create_factory(model))
            self._factories[model] = factory
        # polyfactory's **kwargs are field overrides, not the declared `factory_use_construct` bool
        built: BaseModel = factory.build(**(overrides or {}))  # type: ignore[arg-type]
        return built
