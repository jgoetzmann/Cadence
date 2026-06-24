"""Unit tests for /debug slash command."""

from __future__ import annotations

from typing import cast

import discord
import pytest

from cadence import __version__
from cadence.commands.debug import format_debug_report, handle_debug
from cadence.commands.deps import CommandDeps
from cadence.state import LoopMode, StateStore, Track
from tests.fakes import FakeGuild, FakeInteraction, FakePlayer, FakeVoiceChannel, FakeVoiceClient


def test_format_debug_report_shows_guild_state() -> None:
    store = StateStore(default_volume=40)
    state = store.get(99)
    state.loop_mode = LoopMode.QUEUE
    state.volume = 25
    state.idle_minutes = 30
    state.last_command_at = 1000.0
    state.last_song_started_at = 950.0
    state.alone_since = None
    state.current = Track(
        title="Now Playing",
        webpage_url="https://youtube.com/watch?v=now",
        requested_by=42,
        duration=200,
    )
    state.queue.append(
        Track(
            title="Next Up",
            webpage_url="https://youtube.com/watch?v=next",
            requested_by=77,
        )
    )

    player = FakePlayer()
    player.snapshot_current = state.current
    player.snapshot_upcoming = list(state.queue)

    guild = cast(discord.Guild, FakeGuild(id=99))
    report = format_debug_report(guild, store, cast(object, player), now=1100.0)

    assert "guild 99" in report
    assert f"version: {__version__}" in report
    assert "default_volume: 40" in report
    assert "loop_mode: Queue" in report
    assert "volume: 25" in report
    assert "idle_minutes: 30" in report
    assert "1000.0 (100s ago)" in report
    assert "Now Playing" in report
    assert "Next Up" in report
    assert "queue: 1/30" in report


def test_format_debug_report_without_stored_entry() -> None:
    store = StateStore()
    player = FakePlayer()
    guild = cast(discord.Guild, FakeGuild(id=5))

    report = format_debug_report(guild, store, cast(object, player), now=0.0)

    assert "no stored entry for this guild yet" in report
    assert "connected: no" in report


def test_format_debug_report_includes_voice_client() -> None:
    store = StateStore()
    store.get(1)
    player = FakePlayer()
    fake_guild = FakeGuild(id=1)
    channel = FakeVoiceChannel(id=10, guild=fake_guild, name="Lobby")
    fake_guild.voice_client = FakeVoiceClient(channel=channel)
    fake_guild.voice_client.play("source")

    report = format_debug_report(
        cast(discord.Guild, fake_guild),
        store,
        cast(object, player),
        now=0.0,
    )

    assert "channel: **Lobby**" in report
    assert "playing: True" in report


@pytest.mark.asyncio
async def test_debug_replies_ephemeral(command_deps: CommandDeps) -> None:
    guild = FakeGuild(id=1)
    command_deps.store.get(1).volume = 33
    interaction = FakeInteraction(guild=guild)

    await handle_debug(cast(discord.Interaction, interaction), command_deps)

    assert len(interaction.responses) == 1
    assert interaction.responses[0].ephemeral is True
    assert "guild 1" in interaction.responses[0].content
    assert "volume: 33" in interaction.responses[0].content


def test_format_debug_report_lists_other_guilds() -> None:
    store = StateStore()
    store.get(1)
    store.get(2)
    player = FakePlayer()
    guild = cast(discord.Guild, FakeGuild(id=1))

    report = format_debug_report(guild, store, cast(object, player), now=0.0)

    assert "other_guild_ids: 2" in report


def test_format_debug_report_shows_text_channel_and_voice_source() -> None:
    store = StateStore()
    state = store.get(1)
    state.text_channel = cast(discord.abc.Messageable, type("Ch", (), {"id": 555})())
    state.voice_source = cast(
        discord.PCMVolumeTransformer[discord.AudioSource],
        type("VS", (), {"volume": 0.5})(),
    )
    player = FakePlayer()
    guild = cast(discord.Guild, FakeGuild(id=1))

    report = format_debug_report(guild, store, cast(object, player), now=0.0)

    assert "text_channel_id: 555" in report
    assert "voice_source: active (transformer volume 0.50)" in report


def test_format_debug_report_truncates_long_output() -> None:
    store = StateStore()
    state = store.get(1)
    for index in range(30):
        state.queue.append(
            Track(
                title=f"Very Long Song Title Number {index} " * 3,
                webpage_url=f"https://youtube.com/watch?v={index}",
                requested_by=1,
            )
        )
    player = FakePlayer()
    guild = cast(discord.Guild, FakeGuild(id=1))

    report = format_debug_report(guild, store, cast(object, player), now=0.0)

    assert len(report) <= 2000
    assert report.endswith("… (truncated)")
