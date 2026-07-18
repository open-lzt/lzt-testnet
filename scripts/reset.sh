#!/usr/bin/env bash
# Clears all in-memory state (lots/payments/scenarios) on an already-running instance.
set -euo pipefail

curl -sf -X POST "http://${LZT_TESTNET_HOST:-127.0.0.1}:${LZT_TESTNET_PORT:-8765}/testnet/reset"
