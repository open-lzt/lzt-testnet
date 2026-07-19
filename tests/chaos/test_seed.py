"""The determinism spine: a seed must fix RNG streams, id sequences, and generated data."""

from __future__ import annotations

from pydantic import BaseModel

from lzt_testnet.chaos.seed import IdKind, SeedController
from lzt_testnet.fake.generator import FakeGenerator


def test_same_seed_yields_identical_streams() -> None:
    """Two controllers with the same seed produce byte-identical draws for the same seq — this is
    the property the whole harness rests on. Different seq -> independent stream."""
    a, b = SeedController(42), SeedController(42)
    draws_a = [a.stream(7).random() for _ in range(5)]
    draws_b = [b.stream(7).random() for _ in range(5)]
    assert draws_a == draws_b
    assert a.stream(7).random() != a.stream(8).random()  # streams are per-seq independent


def test_different_seed_diverges() -> None:
    assert SeedController(1).stream(0).random() != SeedController(2).stream(0).random()


def test_next_id_is_monotonic_and_seed_scoped() -> None:
    """next_id is per-kind monotonic and depends only on call order (not process history) — so a
    replay from the same seed + same call order reproduces the same ids."""
    c = SeedController(0)
    assert [c.next_id(IdKind.LOT) for _ in range(3)] == [1, 2, 3]
    assert c.next_id(IdKind.PAYMENT) == 1  # independent counter per kind
    assert [c.next_seq() for _ in range(3)] == [1, 2, 3]
    # a fresh controller restarts the sequence identically
    assert SeedController(0).next_id(IdKind.LOT) == 1


class _Sample(BaseModel):
    name: str
    count: int
    tags: list[str]


def test_seed_generation_makes_polyfactory_reproducible() -> None:
    """seed_generation() before the first build makes FakeGenerator output identical across runs."""
    SeedController(123).seed_generation()
    first = FakeGenerator().build(_Sample)
    SeedController(123).seed_generation()
    second = FakeGenerator().build(_Sample)
    assert first == second
