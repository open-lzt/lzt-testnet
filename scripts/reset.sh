#!/usr/bin/env bash
# Clears all in-memory state (lots/payments/scenarios) on an already-running instance.
set -euo pipefail

# The header goes out only when LZT_TESTNET_CONTROL_KEY is set — an open local instance expects
# no header at all, and an empty one would be rejected by a guarded server.
HEADER=()
if [[ -n "${LZT_TESTNET_CONTROL_KEY:-}" ]]; then
  HEADER=(-H "X-Testnet-Control-Key: ${LZT_TESTNET_CONTROL_KEY}")
fi

curl -sf -X POST "${HEADER[@]}" "http://${LZT_TESTNET_HOST:-127.0.0.1}:${LZT_TESTNET_PORT:-8765}/testnet/reset"
