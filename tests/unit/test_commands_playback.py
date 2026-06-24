"""Unit tests for playback slash commands."""

from __future__ import annotations

from typing import cast

import discord
import pytest

from cadence.commands.deps import CommandDeps
from cadence.commands.playback import (
    handle_pause,
    handle_play,
    handle_resume,
    handle_skip,
    handle_stop,
)
from cadence.interfaces import ResolvedTrack
from tests.fakes import (
    FakeAudioSource,
    FakeGuild,
    FakeInteraction,
    FakePlayer,
    FakeVoiceChannel,
    FakeVoiceClient,
)


def _interaction(guild: FakeGuild, *, voice_channel: FakeVoiceChannel | None) -> FakeInteraction:
    return FakeInteraction(guild=guild, voice_channel=voice_channel)


@pytest.mark.asyncio
async def test_play_requires_voice_channel(command_deps: CommandDeps) -> None:
    guild = FakeGuild(id=1)
    interaction = _interaction(guild, voice_channel=None)
    source = cast(FakeAudioSource, command_deps.source)

    await handle_play(cast(discord.Interaction, interaction), "lofi beats", command_deps)

    assert len(interaction.responses) == 1
    assert interaction.responses[0].ephemeral is True
    assert "voice channel" in interaction.responses[0].content
    assert interaction.deferred == []
    assert source.fetch_calls == []


@pytest.mark.asyncio
async def test_play_defers_when_caller_in_voice(command_deps: CommandDeps) -> None:
    guild = FakeGuild(id=1)
    voice_channel = FakeVoiceChannel(id=2, guild=guild)
    interaction = _interaction(guild, voice_channel=voice_channel)
    source = cast(FakeAudioSource, command_deps.source)
    source.fetch_results.append(
        ResolvedTrack(
            title="Lofi",
            webpage_url="https://example.com/watch?v=1",
            stream_url="https://stream.example/audio",
        )
    )

    await handle_play(cast(discord.Interaction, interaction), "lofi beats", command_deps)

    assert interaction.deferred == [{"ephemeral": False}]
    assert source.fetch_calls == [("lofi beats", False)]


@pytest.mark.asyncio
async def test_play_idle_starts_playback_and_posts_now_playing(command_deps: CommandDeps) -> None:
    guild = FakeGuild(id=1)
    voice_channel = FakeVoiceChannel(id=2, guild=guild)
    interaction = _interaction(guild, voice_channel=voice_channel)
    player = cast(FakePlayer, command_deps.player)
    source = cast(FakeAudioSource, command_deps.source)
    source.fetch_results.append(
        ResolvedTrack(
            title="Lofi",
            webpage_url="https://example.com/watch?v=1",
            stream_url="https://stream.example/audio",
        )
    )

    await handle_play(cast(discord.Interaction, interaction), "lofi beats", command_deps)

    assert guild.voice_client is not None
    assert len(player.enqueued) == 1
    assert player.enqueued[0][1].title == "Lofi"
    assert player.enqueued[0][1].requested_by == interaction.user.id
    assert player.play_next_calls == [guild]
    assert len(interaction.followups) == 1
    assert interaction.followups[0].content == "▶️ Now playing: **Lofi**"
    assert command_deps.store.get(guild.id).text_channel is interaction.channel


@pytest.mark.asyncio
async def test_play_while_active_enqueues_without_play_next(command_deps: CommandDeps) -> None:
    guild = FakeGuild(id=1)
    voice_channel = FakeVoiceChannel(id=2, guild=guild)
    voice_client = FakeVoiceClient(channel=voice_channel)
    voice_client.play("existing")
    guild.voice_client = voice_client
    interaction = _interaction(guild, voice_channel=voice_channel)
    player = cast(FakePlayer, command_deps.player)
    source = cast(FakeAudioSource, command_deps.source)
    source.fetch_results.append(
        ResolvedTrack(
            title="Next Song",
            webpage_url="https://example.com/watch?v=2",
            stream_url="https://stream.example/audio2",
        )
    )

    await handle_play(cast(discord.Interaction, interaction), "next song", command_deps)

    assert player.play_next_calls == []
    assert len(interaction.followups) == 1
    assert interaction.followups[0].content == "➕ Added to queue: **Next Song**"


@pytest.mark.asyncio
async def test_play_moves_when_connected_elsewhere(command_deps: CommandDeps) -> None:
    guild = FakeGuild(id=1)
    old_channel = FakeVoiceChannel(id=2, guild=guild)
    new_channel = FakeVoiceChannel(id=3, guild=guild)
    voice_client = FakeVoiceClient(channel=old_channel)
    guild.voice_client = voice_client
    interaction = _interaction(guild, voice_channel=new_channel)
    source = cast(FakeAudioSource, command_deps.source)
    source.fetch_results.append(
        ResolvedTrack(
            title="Moved",
            webpage_url="https://example.com/watch?v=3",
            stream_url="https://stream.example/audio3",
        )
    )

    await handle_play(cast(discord.Interaction, interaction), "moved", command_deps)

    assert voice_client.move_to_calls == [new_channel]


@pytest.mark.asyncio
async def test_play_treats_https_query_as_url(command_deps: CommandDeps) -> None:
    guild = FakeGuild(id=1)
    voice_channel = FakeVoiceChannel(id=2, guild=guild)
    interaction = _interaction(guild, voice_channel=voice_channel)
    source = cast(FakeAudioSource, command_deps.source)
    source.fetch_results.append(
        ResolvedTrack(
            title="URL Track",
            webpage_url="https://example.com/watch?v=4",
            stream_url="https://stream.example/audio4",
        )
    )

    await handle_play(
        cast(discord.Interaction, interaction),
        "https://example.com/watch?v=4",
        command_deps,
    )

    assert source.fetch_calls == [("https://example.com/watch?v=4", True)]


@pytest.mark.asyncio
async def test_play_fetch_failure_does_not_enqueue(command_deps: CommandDeps) -> None:
    guild = FakeGuild(id=1)
    voice_channel = FakeVoiceChannel(id=2, guild=guild)
    interaction = _interaction(guild, voice_channel=voice_channel)
    player = cast(FakePlayer, command_deps.player)
    source = cast(FakeAudioSource, command_deps.source)
    source.fetch_results.append(RuntimeError("no results"))

    await handle_play(cast(discord.Interaction, interaction), "missing", command_deps)

    assert player.enqueued == []
    assert player.play_next_calls == []
    assert len(interaction.followups) == 1
    assert interaction.followups[0].content == "Couldn't find anything for that."


@pytest.mark.asyncio
async def test_skip_errors_when_nothing_playing(command_deps: CommandDeps) -> None:
    guild = FakeGuild(id=1)
    interaction = FakeInteraction(guild=guild)

    await handle_skip(cast(discord.Interaction, interaction), command_deps)

    assert len(interaction.responses) == 1
    assert interaction.responses[0].ephemeral is True
    assert interaction.responses[0].content == "Nothing is playing."


@pytest.mark.asyncio
async def test_skip_advances_when_playing(command_deps: CommandDeps) -> None:
    guild = FakeGuild(id=1)
    channel = FakeVoiceChannel(id=2, guild=guild)
    voice_client = FakeVoiceClient(channel=channel)
    voice_client.play("source")
    guild.voice_client = voice_client
    interaction = FakeInteraction(guild=guild)
    player = cast(FakePlayer, command_deps.player)

    await handle_skip(cast(discord.Interaction, interaction), command_deps)

    assert player.skip_calls == [guild]
    assert interaction.responses[0].content == "⏭️ Skipped."


@pytest.mark.asyncio
async def test_pause_errors_when_not_playing(command_deps: CommandDeps) -> None:
    guild = FakeGuild(id=1)
    interaction = FakeInteraction(guild=guild)

    await handle_pause(cast(discord.Interaction, interaction), command_deps)

    assert interaction.responses[0].ephemeral is True
    assert interaction.responses[0].content == "Nothing is playing."


@pytest.mark.asyncio
async def test_pause_when_playing(command_deps: CommandDeps) -> None:
    guild = FakeGuild(id=1)
    channel = FakeVoiceChannel(id=2, guild=guild)
    voice_client = FakeVoiceClient(channel=channel)
    voice_client.play("source")
    guild.voice_client = voice_client
    interaction = FakeInteraction(guild=guild)
    player = cast(FakePlayer, command_deps.player)

    await handle_pause(cast(discord.Interaction, interaction), command_deps)

    assert player.pause_calls == [guild]
    assert interaction.responses[0].content == "⏸️ Paused."


@pytest.mark.asyncio
async def test_resume_errors_when_not_paused(command_deps: CommandDeps) -> None:
    guild = FakeGuild(id=1)
    interaction = FakeInteraction(guild=guild)

    await handle_resume(cast(discord.Interaction, interaction), command_deps)

    assert interaction.responses[0].ephemeral is True
    assert interaction.responses[0].content == "Nothing is paused."


@pytest.mark.asyncio
async def test_resume_when_paused(command_deps: CommandDeps) -> None:
    guild = FakeGuild(id=1)
    channel = FakeVoiceChannel(id=2, guild=guild)
    voice_client = FakeVoiceClient(channel=channel)
    voice_client.play("source")
    voice_client.pause()
    guild.voice_client = voice_client
    interaction = FakeInteraction(guild=guild)
    player = cast(FakePlayer, command_deps.player)

    await handle_resume(cast(discord.Interaction, interaction), command_deps)

    assert player.resume_calls == [guild]
    assert interaction.responses[0].content == "▶️ Resumed."


@pytest.mark.asyncio
async def test_stop_delegates_to_player(command_deps: CommandDeps) -> None:
    guild = FakeGuild(id=1)
    interaction = FakeInteraction(guild=guild)
    player = cast(FakePlayer, command_deps.player)

    await handle_stop(cast(discord.Interaction, interaction), command_deps)

    assert player.stop_calls == [guild]
    assert interaction.responses[0].content == "⏹️ Stopped and left the channel."
