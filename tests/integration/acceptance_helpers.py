"""Acceptance-test harness — real Player wired to fakes."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import cast

import discord

from cadence.commands.deps import CommandDeps
from cadence.interfaces import ResolvedTrack
from cadence.player import Player
from cadence.state import StateStore
from tests.fakes import (
    FakeAudioSource,
    FakeGuild,
    FakeInteraction,
    FakeVoiceChannel,
    FakeVoiceClient,
)
from tests.integration.helpers import FakeClient, FakePCMVolumeTransformer, advance_after

__all__ = [
    "AcceptanceContext",
    "finish_track",
    "make_acceptance_context",
    "make_interaction",
    "script_play_flow",
    "script_track",
]


@dataclass
class AcceptanceContext:
    """Wired command-layer acceptance test context with a real Player."""

    guild: FakeGuild
    voice_channel: FakeVoiceChannel
    store: StateStore
    source: FakeAudioSource
    player: Player
    deps: CommandDeps


def script_track(title: str) -> ResolvedTrack:
    """Build a ResolvedTrack for a titled search result."""
    key = title.lower().replace(" ", "-")
    return ResolvedTrack(
        title=title,
        webpage_url=f"https://youtube.com/watch?v={key}",
        stream_url=f"https://stream.example/{key}",
        duration=180,
    )


def script_play_flow(ctx: AcceptanceContext, *titles: str) -> None:
    """Script fetch/playback results for one /play call per title."""
    tracks = [script_track(title) for title in titles]
    ctx.source.fetch_results = deque(tracks)
    ctx.source.playback_results = deque(
        [
            FakePCMVolumeTransformer(source=f"pcm:{track.webpage_url}", volume=0.5)
            for track in tracks
        ],
    )


def make_interaction(
    guild: FakeGuild,
    *,
    voice_channel: FakeVoiceChannel | None,
) -> FakeInteraction:
    """Build a fake slash interaction, optionally with the caller in voice."""
    return FakeInteraction(guild=guild, voice_channel=voice_channel)


def make_acceptance_context() -> AcceptanceContext:
    """Wire a real Player with fakes for acceptance tests."""
    import asyncio

    loop = asyncio.get_running_loop()
    guild = FakeGuild(id=100)
    voice_channel = FakeVoiceChannel(id=200, guild=guild)
    store = StateStore()
    source = FakeAudioSource()
    fake_client = FakeClient(loop=loop)
    player = Player(cast(discord.Client, fake_client), store, source)
    deps = CommandDeps(player=player, source=source, store=store)
    return AcceptanceContext(
        guild=guild,
        voice_channel=voice_channel,
        store=store,
        source=source,
        player=player,
        deps=deps,
    )


async def finish_track(voice_client: FakeVoiceClient) -> None:
    """End the current track and await auto-advance."""
    await advance_after(voice_client)
