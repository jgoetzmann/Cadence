"""Environment-based configuration."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from dotenv import load_dotenv

__all__ = ["ConfigError", "Settings"]


class ConfigError(Exception):
    """Raised when required configuration is missing or invalid."""


def _clamp_volume(value: int) -> int:
    return max(0, min(100, value))


def _parse_log_level(raw: str | None) -> int:
    if raw is None or raw == "":
        return logging.INFO
    level = getattr(logging, raw.upper(), None)
    if not isinstance(level, int):
        msg = f"Invalid LOG_LEVEL: {raw!r}"
        raise ConfigError(msg)
    return level


def _parse_guild_id(raw: str | None) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except ValueError as exc:
        msg = f"Invalid DISCORD_GUILD_ID: {raw!r}"
        raise ConfigError(msg) from exc


def _parse_default_volume(raw: str | None) -> int:
    if raw is None or raw == "":
        return 50
    try:
        return _clamp_volume(int(raw))
    except ValueError as exc:
        msg = f"Invalid CADENCE_DEFAULT_VOLUME: {raw!r}"
        raise ConfigError(msg) from exc


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings loaded from environment variables."""

    token: str
    guild_id: int | None
    log_level: int
    default_volume: int

    def __repr__(self) -> str:
        return (
            f"Settings(guild_id={self.guild_id!r}, "
            f"log_level={self.log_level!r}, "
            f"default_volume={self.default_volume!r})"
        )

    def __str__(self) -> str:
        return self.__repr__()

    @classmethod
    def load(cls) -> Settings:
        """Load settings from the environment (and optional `.env` file)."""
        load_dotenv()
        token = os.environ.get("DISCORD_TOKEN")
        if not token:
            msg = "DISCORD_TOKEN is required but not set"
            raise ConfigError(msg)
        return cls(
            token=token,
            guild_id=_parse_guild_id(os.environ.get("DISCORD_GUILD_ID")),
            log_level=_parse_log_level(os.environ.get("LOG_LEVEL")),
            default_volume=_parse_default_volume(os.environ.get("CADENCE_DEFAULT_VOLUME")),
        )
