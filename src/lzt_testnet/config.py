"""Runtime settings for the lzt-testnet mock server."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Server settings, sourced from `LZT_TESTNET_*` environment variables."""

    model_config = SettingsConfigDict(env_prefix="LZT_TESTNET_")

    host: str = "127.0.0.1"
    port: int = 8765
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    """Return the cached process-wide `Settings` instance."""
    return Settings()
