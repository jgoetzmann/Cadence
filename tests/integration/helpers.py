"""Helper utilities for Player + YouTubeSource integration tests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import cast
from unittest.mock import patch

import discord
import pytest

from cadence.player import Player
from cadence.sources.youtube import YouTubeSource
from cadence.state import StateStore, Track
from tests.fakes import FakeGuild, FakeVoiceClient, FakeYoutubeDL, patch_ytdl, run_after

__all__ = [
    "FakeClient",
    "FakePCMVolumeTransformer",
    "advance_after",
    "guild_as_discord",
    "make_integration_player",
    "make_patched_integration_player",
    "make_track",
]


@dataclass(slots=True)
class FakeClient:
    """Minimal Discord client exposing the event loop."""

    loop: asyncio.AbstractEventLoop


@dataclass
class FakePCMVolumeTransformer:
    """Lightweight stand-in for discord.PCMVolumeTransformer in tests."""

    source: object
    volume: float = 1.0


def guild_as_discord(fake_guild: FakeGuild) -> discord.Guild:
    """Cast a FakeGuild to discord.Guild for typed Player APIs."""
    return cast(discord.Guild, fake_guild)


def make_track(
    title: str,
    webpage_url: str,
    *,
    requested_by: int = 42,
) -> Track:
    """Build a Track for integration tests."""
    return Track(title=title, webpage_url=webpage_url, requested_by=requested_by)


def make_integration_player(
    *,
    store: StateStore | None = None,
    loop: asyncio.AbstractEventLoop | None = None,
) -> tuple[Player, StateStore, YouTubeSource, FakeClient]:
    """Wire a Player with a real YouTubeSource for integration tests."""
    resolved_loop = loop or asyncio.get_running_loop()
    fake_client = FakeClient(loop=resolved_loop)
    resolved_store = store or StateStore()
    source = YouTubeSource()
    player = Player(
        cast(discord.Client, fake_client),
        resolved_store,
        source,
    )
    return player, resolved_store, source, fake_client


def make_patched_integration_player(
    monkeypatch: pytest.MonkeyPatch,
    fake_ytdl: FakeYoutubeDL,
    *,
    store: StateStore | None = None,
) -> tuple[Player, StateStore, YouTubeSource, FakeClient]:
    """Patch yt-dlp before constructing YouTubeSource (it caches YoutubeDL at init)."""
    patch_ytdl(monkeypatch, fake_ytdl)
    return make_integration_player(store=store)


async def advance_after(voice_client: FakeVoiceClient) -> None:
    """Invoke the FFmpeg after-callback and await the scheduled play_next."""
    scheduled: list[asyncio.Future[object]] = []

    def capture_schedule(
        coro: object,
        event_loop: asyncio.AbstractEventLoop,
    ) -> asyncio.Future[object]:
        future = asyncio.ensure_future(coro, loop=event_loop)  # type: ignore[arg-type]
        scheduled.append(future)
        return future

    with patch("cadence.player.asyncio.run_coroutine_threadsafe", side_effect=capture_schedule):
        run_after(voice_client)

    for future in scheduled:
        await future
