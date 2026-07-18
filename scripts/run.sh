#!/usr/bin/env bash
# Boots the lzt-testnet mock server. Idempotent: `uv sync` no-ops if deps are current.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

uv sync --extra dev

exec uv run uvicorn lzt_testnet.api.app:create_app \
    --factory \
    --host "${LZT_TESTNET_HOST:-127.0.0.1}" \
    --port "${LZT_TESTNET_PORT:-8765}"
