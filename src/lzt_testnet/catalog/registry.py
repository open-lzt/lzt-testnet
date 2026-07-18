"""Discovers every concrete `pylzt.methods.base.BaseMethod` subclass.

Importing `pylzt.methods` alone does not transitively import every facade submodule
(`market_*.py`, `forum_*.py`, `antipublic_*.py`, ...) — those only get registered on
`BaseMethod.__subclasses__()` once their module has actually executed. We force that by
walking the package tree with `pkgutil.walk_packages` and importing every submodule found,
then collecting subclasses recursively (a subclass may itself be a base for further
subclasses) so the result is independent of whichever import order happened to run first.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil

import pylzt
import pylzt.methods
from pylzt.methods.base import BaseMethod

__all__ = ["collect_base_methods"]


def _import_all_submodules() -> None:
    """Import every submodule under `pylzt.methods` so its BaseMethod subclasses register."""
    package = pylzt.methods
    for module_info in pkgutil.walk_packages(package.__path__, prefix=f"{package.__name__}."):
        importlib.import_module(module_info.name)


def _is_concrete(cls: type[BaseMethod]) -> bool:  # type: ignore[type-arg]  # frozen contract signature
    """A concrete endpoint: not `__abstract__`, and not a parametrized `BaseMethod[X]`
    intermediate submodel Pydantic mints for every `class Foo(BaseMethod[Resp])`."""
    if cls is BaseMethod or cls.__dict__.get("__abstract__"):
        return False
    origin = cls.__pydantic_generic_metadata__.get("origin")
    return origin is None


def _walk_subclasses(
    cls: type[BaseMethod],  # type: ignore[type-arg]  # frozen contract signature
) -> set[type[BaseMethod]]:  # type: ignore[type-arg]  # frozen contract signature
    """Recurse through `__subclasses__()` — a subclass may itself be a shared base for
    further subclasses (e.g. a hand-written `__abstract__` mixin), so a single flat pass
    over `BaseMethod.__subclasses__()` would silently miss grandchildren."""
    found: set[type[BaseMethod]] = set()  # type: ignore[type-arg]  # frozen contract signature
    for subclass in cls.__subclasses__():
        found.add(subclass)
        found |= _walk_subclasses(subclass)
    return found


def collect_base_methods() -> list[type[BaseMethod]]:  # type: ignore[type-arg]  # frozen contract signature
    """Walks `pylzt.methods` via `pkgutil.walk_packages` + module member inspection,
    returning every concrete (non-abstract) `BaseMethod` subclass found."""
    _ = pylzt  # ensure top-level package import runs before submodule discovery
    _import_all_submodules()

    # inspect.getmembers over every imported submodule ensures classes reachable only via
    # module attributes (not surfaced by __subclasses__ due to import-order edge cases)
    # are still forced into existence before the subclass walk below.
    package = pylzt.methods
    for module_info in pkgutil.walk_packages(package.__path__, prefix=f"{package.__name__}."):
        module = importlib.import_module(module_info.name)
        inspect.getmembers(module, lambda obj: isinstance(obj, type))

    return [cls for cls in _walk_subclasses(BaseMethod) if _is_concrete(cls)]
