"""The determinism spine: one seed fixes every fault decision and every generated datum.

A single ``SeedController`` is built once per app and put on ``app.state.seed``. Fault decisions
read randomness only from ``stream(seq)`` (a per-request child RNG), so replaying request ``seq``
never depends on how many requests came before it. ``next_id`` replaces the module-global
``itertools.count`` in ``api/stateful.py`` so id sequences are a function of the seed, not history.
"""

from __future__ import annotations

import itertools
from enum import StrEnum
from random import Random

from polyfactory.factories.pydantic_factory import ModelFactory


class IdKind(StrEnum):
    """The entities whose ids are minted deterministically from the seed."""

    LOT = "lot"
    PAYMENT = "payment"
    SELLER = "seller"
    THREAD = "thread"
    POST = "post"
    USER = "user"


class SeedController:
    """Owns every source of randomness in the harness, all derived from one integer seed."""

    def __init__(self, seed: int) -> None:
        self._seed = seed
        self._root = Random(seed)
        self._seq = itertools.count(1)
        self._ids: dict[IdKind, itertools.count[int]] = {
            kind: itertools.count(1) for kind in IdKind
        }

    @property
    def seed(self) -> int:
        return self._seed

    @property
    def root(self) -> Random:
        """The base RNG. Prefer ``stream(seq)`` for per-request decisions; use ``root`` for
        one-shot world construction where a stable global order already guarantees determinism."""
        return self._root

    def stream(self, seq: int) -> Random:
        """An independent child RNG for request ``seq`` — seeded from ``"{seed}:{seq}"``. A string
        seed is deterministic (unlike a tuple, which ``random`` rejects, or ``hash``, which is
        per-process salted). Independent of call history, so a request replays from its seq."""
        return Random(f"{self._seed}:{seq}")

    def next_seq(self) -> int:
        """The per-app request ordinal fed into ``FaultContext.seq``."""
        return next(self._seq)

    def next_id(self, kind: IdKind) -> int:
        """A seed-scoped, per-app monotonic id for ``kind`` (replaces module-global counters)."""
        return next(self._ids[kind])

    def seed_generation(self) -> None:
        """Seed polyfactory ONCE, before the first ``FakeGenerator.build``, so generated data is
        reproducible. ``seed_random`` sets ``__random__`` + ``__faker__`` on the shared factory
        base; every per-model factory inherits it via MRO, so seed-vs-create order is irrelevant."""
        ModelFactory.seed_random(self._seed)
