"""``python -m lzt_testnet.cli`` — arm the Gauntlet from flags, then launch uvicorn.

Flags set the ``LZT_TESTNET_CHAOS_*`` env vars the app reads through Settings, so arming is the
same whether it comes from the shell, the CLI, or a CI job. ``main(..., launch=False)`` stops before
binding a port, which is what the test drives.
"""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence

from lzt_testnet.chaos.profiles import Intensity


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lzt-testnet", description="Run the mock lzt.market server."
    )
    parser.add_argument("--chaos", choices=[i.value for i in Intensity], help="chaos intensity")
    parser.add_argument("--seed", type=int, help="determinism seed")
    parser.add_argument("--scenario", help="named scenario from scenarios/<name>.yaml")
    parser.add_argument("--host", help="bind host (default from settings)")
    parser.add_argument("--port", type=int, help="bind port (default from settings)")
    return parser


def apply_env(args: argparse.Namespace) -> None:
    """Translate parsed flags into the LZT_TESTNET_CHAOS_* env the app's Settings reads."""
    if args.chaos is not None:
        os.environ["LZT_TESTNET_CHAOS_MODE"] = args.chaos
    if args.seed is not None:
        os.environ["LZT_TESTNET_CHAOS_SEED"] = str(args.seed)
    if args.scenario is not None:
        os.environ["LZT_TESTNET_CHAOS_SCENARIO"] = args.scenario


def main(argv: Sequence[str] | None = None, *, launch: bool = True) -> argparse.Namespace:
    args = build_parser().parse_args(argv)
    apply_env(args)
    if launch:
        _launch(args)
    return args


def _launch(args: argparse.Namespace) -> None:  # pragma: no cover - binds a real port
    import uvicorn

    from lzt_testnet.config import get_settings

    get_settings.cache_clear()  # env may have changed since first access
    settings = get_settings()
    uvicorn.run(
        "lzt_testnet.api.app:create_app",
        factory=True,
        host=args.host or settings.host,
        port=args.port or settings.port,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
