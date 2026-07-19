"""T15 — the CLI translates flags into LZT_TESTNET_CHAOS_* env without binding a port."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from lzt_testnet.cli import apply_env, build_parser, main
from lzt_testnet.config import get_settings

_CHAOS_ENV = ("LZT_TESTNET_CHAOS_MODE", "LZT_TESTNET_CHAOS_SEED", "LZT_TESTNET_CHAOS_SCENARIO")


@pytest.fixture(autouse=True)
def _clean_env() -> Iterator[None]:
    # apply_env writes os.environ directly (not via monkeypatch), so clear the chaos vars on BOTH
    # sides and drop the settings cache — otherwise a leaked var poisons every later create_app().
    for key in _CHAOS_ENV:
        os.environ.pop(key, None)
    get_settings.cache_clear()
    yield
    for key in _CHAOS_ENV:
        os.environ.pop(key, None)
    get_settings.cache_clear()


def test_flags_set_env() -> None:
    args = main(["--chaos", "hostile", "--seed", "42", "--scenario", "nginx-down"], launch=False)
    assert os.environ["LZT_TESTNET_CHAOS_MODE"] == "hostile"
    assert os.environ["LZT_TESTNET_CHAOS_SEED"] == "42"
    assert os.environ["LZT_TESTNET_CHAOS_SCENARIO"] == "nginx-down"
    assert args.chaos == "hostile"


def test_no_flags_leaves_env_unset() -> None:
    main([], launch=False)
    assert all(key not in os.environ for key in _CHAOS_ENV)


def test_invalid_intensity_rejected() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--chaos", "nonsense"])


def test_apply_env_partial() -> None:
    args = build_parser().parse_args(["--seed", "7"])
    apply_env(args)
    assert os.environ["LZT_TESTNET_CHAOS_SEED"] == "7"
    assert "LZT_TESTNET_CHAOS_MODE" not in os.environ
