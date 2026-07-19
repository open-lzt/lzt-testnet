"""Chaos / fault-injection harness for the testnet mock (the Gauntlet).

OFF by default: nothing here mutates a response until chaos is armed via ``LZT_TESTNET_CHAOS_MODE``
(env / CLI) or a per-request ``X-Chaos`` header. See ``.plans/testnet-gauntlet/`` for the design.
"""
