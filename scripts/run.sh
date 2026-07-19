#!/usr/bin/env bash
# Boots the lzt-testnet mock server. Idempotent: `uv sync` no-ops if deps are current.
# Gauntlet flags pass straight through, e.g.:
#   ./scripts/run.sh --chaos hostile --seed 42
#   ./scripts/run.sh --scenario nginx-down
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

uv sync --extra dev

exec uv run python -m lzt_testnet.cli \
    --host "${LZT_TESTNET_HOST:-127.0.0.1}" \
    --port "${LZT_TESTNET_PORT:-8765}" \
    "$@"
