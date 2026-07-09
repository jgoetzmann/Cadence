"""Tests for shared test fakes."""

from __future__ import annotations

import pytest

from cadence.interfaces import AudioSource, Player, ResolvedTrack
from cadence.state import LoopMode, Track
from tests.fakes import (
    FakeAudioSource,
    FakeGuild,
    FakeInteraction,
    FakePlayer,
    FakeTextChannel,
    FakeVoiceChannel,
    FakeVoiceClient,
    FakeVoiceState,
    run_after,
)


def test_fake_voice_client_play_captures_after_without_firing() -> None:
    guild = FakeGuild(id=1)
    channel = FakeVoiceChannel(id=2, guild=guild)
    client = FakeVoiceClient(channel=channel)
    fired: list[Exception | None] = []

    def after(error: Exception | None) -> None:
        fired.append(error)

    client.play("source", after=after)
    assert client.source == "source"
    assert client.is_playing() is True
    assert fired == []


def test_run_after_invokes_captured_callback() -> None:
    guild = FakeGuild(id=1)
    channel = FakeVoiceChannel(id=2, guild=guild)
    client = FakeVoiceClient(channel=channel)
    fired: list[Exception | None] = []

    def after(error: Exception | None) -> None:
        fired.append(error)

    client.play("source", after=after)
    run_after(client)
    assert fired == [None]
    assert client.after is None


def test_run_after_forwards_error() -> None:
    guild = FakeGuild(id=1)
    channel = FakeVoiceChannel(id=2, guild=guild)
    client = FakeVoiceClient(channel=channel)
    fired: list[Exception | None] = []
    error = RuntimeError("playback failed")

    def after(exc: Exception | None) -> None:
        fired.append(exc)

    client.play("source", after=after)
    run_after(client, error=error)
    assert fired == [error]


def test_run_after_raises_when_no_callback() -> None:
    guild = FakeGuild(id=1)
    channel = FakeVoiceChannel(id=2, guild=guild)
    client = FakeVoiceClient(channel=channel)
    with pytest.raises(AssertionError, match="No after callback"):
        run_after(client)


def test_fake_voice_client_pause_resume_and_stop() -> None:
    guild = FakeGuild(id=1)
    channel = FakeVoiceChannel(id=2, guild=guild)
    client = FakeVoiceClient(channel=channel)
    fired: list[Exception | None] = []

    def after(error: Exception | None) -> None:
        fired.append(error)

    client.play("source", after=after)
    client.pause()
    assert client.is_paused() is True
    assert client.is_playing() is False
    client.resume()
    assert client.is_playing() is True
    client.stop()
    assert client.is_playing() is False
    assert fired == [None]


@pytest.mark.asyncio
async def test_fake_voice_channel_connect_sets_guild_voice_client() -> None:
    guild = FakeGuild(id=1)
    channel = FakeVoiceChannel(id=2, guild=guild)
    client = await channel.connect()
    assert isinstance(client, FakeVoiceClient)
    assert guild.voice_client is client


@pytest.mark.asyncio
async def test_fake_interaction_records_defer_and_replies() -> None:
    guild = FakeGuild(id=1)
    channel = FakeVoiceChannel(id=2, guild=guild)
    text_channel = FakeTextChannel(id=300)
    interaction = FakeInteraction(
        guild=guild,
        voice_channel=channel,
        channel=text_channel,
    )

    await interaction.defer(ephemeral=True)
    await interaction.response.defer(ephemeral=False)
    await interaction.response.send_message("direct", ephemeral=False)
    await interaction.followup.send("followup", ephemeral=True)

    assert interaction.deferred == [{"ephemeral": True}, {"ephemeral": False}]
    assert interaction.channel is text_channel
    assert interaction.responses[0].content == "direct"
    assert interaction.responses[0].ephemeral is False
    assert interaction.followups[0].content == "followup"
    assert interaction.followups[0].ephemeral is True
    assert interaction.user.voice is not None
    assert interaction.user.voice.channel is channel


@pytest.mark.asyncio
async def test_fake_interaction_defaults_text_channel() -> None:
    guild = FakeGuild(id=1)
    interaction = FakeInteraction(guild=guild)
    assert isinstance(interaction.channel, FakeTextChannel)
    assert interaction.channel.id == 300


@pytest.mark.asyncio
async def test_fake_interaction_voice_channel_is_settable() -> None:
    guild = FakeGuild(id=1)
    interaction = FakeInteraction(guild=guild)
    assert interaction.user.voice is None

    first = FakeVoiceChannel(id=2, guild=guild)
    interaction.user.voice = FakeVoiceState(channel=first)
    assert interaction.user.voice.channel is first

    second = FakeVoiceChannel(id=3, guild=guild)
    assert interaction.user.voice is not None
    interaction.user.voice.channel = second
    assert interaction.user.voice.channel is second


@pytest.mark.asyncio
async def test_fake_voice_client_move_to() -> None:
    guild = FakeGuild(id=1)
    first = FakeVoiceChannel(id=2, guild=guild)
    second = FakeVoiceChannel(id=3, guild=guild)
    client = FakeVoiceClient(channel=first)
    await client.move_to(second)
    assert client.channel is second
    assert client.move_to_calls == [second]
    channel = FakeTextChannel(id=1)
    await channel.send("hello", ephemeral=True)
    assert channel.sent[0].content == "hello"
    assert channel.sent[0].ephemeral is True


@pytest.mark.asyncio
async def test_fake_audio_source_scripted_success_and_failure() -> None:
    track = ResolvedTrack(
        title="Song",
        webpage_url="https://example.com/watch?v=1",
        stream_url="https://stream.example/audio",
        duration=120,
    )
    source = FakeAudioSource(
        fetch_results=[track],
        resolve_results=[RuntimeError("resolve failed")],
        playback_results=[object()],
    )

    fetched = await source.fetch("query", is_url=False)
    assert fetched == track
    assert source.fetch_calls == [("query", False)]

    with pytest.raises(RuntimeError, match="resolve failed"):
        await source.resolve(track.webpage_url)
    assert source.resolve_calls == [track.webpage_url]

    playback = await source.create_playback_source(track.webpage_url, 50)
    assert playback is not None
    assert source.playback_calls == [(track.webpage_url, 50)]


@pytest.mark.asyncio
async def test_fake_player_records_calls_and_snapshot() -> None:
    player = FakePlayer()
    track = Track(
        title="Queued",
        webpage_url="https://example.com/watch?v=2",
        requested_by=7,
    )
    player.snapshot_current = track
    player.snapshot_upcoming = [track]

    class _Guild:
        id = 99

    guild = _Guild()  # type: ignore[assignment]

    await player.enqueue(guild, track)  # type: ignore[arg-type]
    await player.play_next(guild)  # type: ignore[arg-type]
    await player.skip(guild)  # type: ignore[arg-type]
    await player.pause(guild)  # type: ignore[arg-type]
    await player.resume(guild)  # type: ignore[arg-type]
    await player.stop(guild)  # type: ignore[arg-type]
    player.set_loop_mode(guild, LoopMode.TRACK)  # type: ignore[arg-type]
    player.set_volume(guild, 25)  # type: ignore[arg-type]

    current, upcoming = player.snapshot(guild)  # type: ignore[arg-type]
    assert current == track
    assert upcoming == [track]
    assert player.loop_mode is LoopMode.TRACK
    assert player.volume == 25
    assert len(player.enqueued) == 1
    assert len(player.play_next_calls) == 1


def test_fake_protocols_are_runtime_checkable() -> None:
    assert isinstance(FakeAudioSource(), AudioSource)
    assert isinstance(FakePlayer(), Player)
