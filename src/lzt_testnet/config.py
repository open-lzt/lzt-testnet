"""Runtime settings for the lzt-testnet mock server."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from lzt_testnet.chaos.profiles import Intensity


class Settings(BaseSettings):
    """Server settings, sourced from `LZT_TESTNET_*` environment variables."""

    model_config = SettingsConfigDict(env_prefix="LZT_TESTNET_")

    host: str = "127.0.0.1"
    port: int = 8765
    log_level: str = "INFO"

    # Shared secret for the /testnet/* control plane (reset, revoke-token). Unset means the
    # control routes are open, which is fine on the default 127.0.0.1 bind and is what every
    # local harness expects. Set it whenever `host` is anything else: those routes wipe all
    # state, so on a shared CI box or a mapped container port they are an unauthenticated
    # reset button for everyone else's test run.
    control_key: str | None = None

    # The stateful world (seller roster, forum, lazily materialised lots). Off by default so
    # the plain mock stays stateless, but a switch of its own: it used to be armed only as a
    # side effect of turning the chaos harness on, which made a populated world and injected
    # faults the same decision.
    world: bool = False

    # Gauntlet chaos harness — OFF by default so the server stays a clean mock (D2).
    chaos_mode: Intensity = Intensity.OFF
    chaos_seed: int = 0
    chaos_scenario: str | None = None


@lru_cache
def get_settings() -> Settings:
    """Return the cached process-wide `Settings` instance."""
    return Settings()
