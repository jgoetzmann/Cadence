"""Shared pytest fixtures for Cadence tests.

pytest-asyncio ``asyncio_mode=auto`` is configured in ``pyproject.toml``.
"""

from __future__ import annotations

import logging

import pytest

from cadence.commands.deps import CommandDeps
from cadence.config import Settings
from cadence.state import StateStore
from tests.fakes import (
    FakeAudioSource,
    FakeGuild,
    FakeInteraction,
    FakePlayer,
    FakeVoiceChannel,
    FakeVoiceClient,
    run_after,
)

__all__ = ["run_after", "settings"]


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear Cadence env vars before each test."""
    monkeypatch.setattr("cadence.config.load_dotenv", lambda *_args, **_kwargs: None)
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    monkeypatch.delenv("DISCORD_GUILD_ID", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("CADENCE_DEFAULT_VOLUME", raising=False)
    monkeypatch.delenv("YTDLP_COOKIE_FILE", raising=False)
    monkeypatch.delenv("YTDLP_PROXY", raising=False)
    monkeypatch.delenv("YTDLP_IMPERSONATE", raising=False)


@pytest.fixture
def settings() -> Settings:
    """Default test settings without loading from the environment."""
    return Settings(
        token="test-token",
        guild_id=None,
        log_level=logging.INFO,
        default_volume=50,
    )


@pytest.fixture
def fake_guild() -> FakeGuild:
    """Guild with no active voice client."""
    return FakeGuild(id=100)


@pytest.fixture
def fake_voice_client(fake_guild: FakeGuild) -> FakeVoiceClient:
    """Connected voice client on a default voice channel."""
    channel = FakeVoiceChannel(id=200, guild=fake_guild)
    client = FakeVoiceClient(channel=channel)
    fake_guild.voice_client = client
    return client


@pytest.fixture
def fake_interaction(fake_guild: FakeGuild) -> FakeInteraction:
    """Interaction with the caller in a voice channel."""
    channel = FakeVoiceChannel(id=200, guild=fake_guild)
    return FakeInteraction(guild=fake_guild, voice_channel=channel)


@pytest.fixture
def command_deps() -> CommandDeps:
    """Default command dependencies with fakes."""
    return CommandDeps(
        player=FakePlayer(),
        source=FakeAudioSource(),
        store=StateStore(),
    )
