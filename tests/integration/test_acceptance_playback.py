"""Acceptance tests for playback commands — T3a."""

from __future__ import annotations

import asyncio
from collections import deque
from typing import cast
from unittest.mock import patch

import discord
import pytest

from cadence.commands.playback import handle_play, handle_skip, handle_stop
from cadence.commands.settings import handle_loop
from cadence.state import LoopMode
from tests.fakes import FakeVoiceChannel, FakeVoiceClient
from tests.integration.acceptance_helpers import (
    AcceptanceContext,
    finish_track,
    make_interaction,
    script_play_flow,
    script_track,
)


@pytest.mark.asyncio
async def test_us1_t3_01_play_from_idle_connects_and_plays(
    acceptance_ctx: AcceptanceContext,
) -> None:
    """US-1 / T3-01: /play from idle connects, plays, and posts now playing."""
    ctx = acceptance_ctx
    script_play_flow(ctx, "Lofi Beats")
    interaction = make_interaction(ctx.guild, voice_channel=ctx.voice_channel)

    await handle_play(
        cast(discord.Interaction, interaction),
        "lofi beats",
        ctx.deps,
    )

    assert interaction.deferred == [{"ephemeral": False}]
    assert ctx.guild.voice_client is not None
    assert ctx.guild.voice_client.is_playing()
    state = ctx.store.get(ctx.guild.id)
    assert state.current is not None
    assert state.current.title == "Lofi Beats"
    assert len(interaction.followups) == 1
    assert interaction.followups[0].ephemeral is False
    assert interaction.followups[0].content == "▶️ Now playing: **Lofi Beats**"


@pytest.mark.asyncio
async def test_us1_play_requires_voice_channel(acceptance_ctx: AcceptanceContext) -> None:
    """US-1: /play without a voice channel replies ephemeral and does not fetch."""
    ctx = acceptance_ctx
    interaction = make_interaction(ctx.guild, voice_channel=None)

    await handle_play(
        cast(discord.Interaction, interaction),
        "lofi beats",
        ctx.deps,
    )

    assert len(interaction.responses) == 1
    assert interaction.responses[0].ephemeral is True
    assert "voice channel" in interaction.responses[0].content
    assert interaction.deferred == []
    assert ctx.source.fetch_calls == []
    assert ctx.guild.voice_client is None


@pytest.mark.asyncio
async def test_us1_play_moves_when_connected_elsewhere(acceptance_ctx: AcceptanceContext) -> None:
    """US-1: /play moves to the caller's channel when already connected elsewhere."""
    ctx = acceptance_ctx
    old_channel = FakeVoiceChannel(id=201, guild=ctx.guild)
    voice_client = FakeVoiceClient(channel=old_channel)
    ctx.guild.voice_client = voice_client
    script_play_flow(ctx, "Moved")
    interaction = make_interaction(ctx.guild, voice_channel=ctx.voice_channel)

    await handle_play(cast(discord.Interaction, interaction), "moved", ctx.deps)

    assert voice_client.move_to_calls == [ctx.voice_channel]
    assert interaction.followups[0].content == "▶️ Now playing: **Moved**"


@pytest.mark.asyncio
async def test_us2_t3_02_play_while_active_queues_and_auto_advances(
    acceptance_ctx: AcceptanceContext,
) -> None:
    """US-2 / T3-02: /play while active enqueues and auto-advances when the track ends."""
    ctx = acceptance_ctx
    script_play_flow(ctx, "First Song", "Second Song")
    interaction_a = make_interaction(ctx.guild, voice_channel=ctx.voice_channel)

    await handle_play(
        cast(discord.Interaction, interaction_a),
        "first song",
        ctx.deps,
    )
    assert interaction_a.followups[0].content == "▶️ Now playing: **First Song**"

    interaction_b = make_interaction(ctx.guild, voice_channel=ctx.voice_channel)
    await handle_play(
        cast(discord.Interaction, interaction_b),
        "second song",
        ctx.deps,
    )
    assert interaction_b.followups[0].content == "➕ Added to queue: **Second Song**"
    state = ctx.store.get(ctx.guild.id)
    assert state.current is not None
    assert state.current.title == "First Song"
    assert len(state.queue) == 1
    assert state.queue[0].title == "Second Song"

    voice_client = cast(FakeVoiceClient, ctx.guild.voice_client)
    assert voice_client is not None
    await finish_track(voice_client)

    state = ctx.store.get(ctx.guild.id)
    assert state.current is not None
    assert state.current.title == "Second Song"
    assert voice_client.is_playing()


@pytest.mark.asyncio
async def test_us3_t3_03_loop_replays_track_on_finish(acceptance_ctx: AcceptanceContext) -> None:
    """US-3 / T3-03: loop on replays the current track when it finishes."""
    ctx = acceptance_ctx
    track = script_track("Loop Me")
    ctx.source.fetch_results = deque([track])
    ctx.source.resolve_results = deque([track, track])
    interaction = make_interaction(ctx.guild, voice_channel=ctx.voice_channel)
    await handle_play(cast(discord.Interaction, interaction), "loop me", ctx.deps)
    loop_interaction = make_interaction(ctx.guild, voice_channel=ctx.voice_channel)
    await handle_loop(cast(discord.Interaction, loop_interaction), LoopMode.TRACK, ctx.deps)
    assert loop_interaction.responses[0].content == "Loop set to **Current song**."

    voice_client = cast(FakeVoiceClient, ctx.guild.voice_client)
    assert voice_client is not None
    resolve_before = len(ctx.source.resolve_calls)
    await finish_track(voice_client)

    state = ctx.store.get(ctx.guild.id)
    assert state.current is not None
    assert state.current.title == "Loop Me"
    assert len(ctx.source.resolve_calls) == resolve_before + 1
    assert voice_client.is_playing()


@pytest.mark.asyncio
async def test_us4_t3_03_skip_advances_past_looped_track(
    acceptance_ctx: AcceptanceContext,
) -> None:
    """US-3 / US-4 / T3-03: /skip advances past a looped track to the next queued item."""
    ctx = acceptance_ctx
    script_play_flow(ctx, "Loop Song", "Next Song")
    play_interaction = make_interaction(ctx.guild, voice_channel=ctx.voice_channel)
    await handle_play(cast(discord.Interaction, play_interaction), "loop song", ctx.deps)

    loop_interaction = make_interaction(ctx.guild, voice_channel=ctx.voice_channel)
    await handle_loop(cast(discord.Interaction, loop_interaction), LoopMode.TRACK, ctx.deps)

    queue_interaction = make_interaction(ctx.guild, voice_channel=ctx.voice_channel)
    await handle_play(cast(discord.Interaction, queue_interaction), "next song", ctx.deps)

    skip_interaction = make_interaction(ctx.guild, voice_channel=ctx.voice_channel)
    scheduled: list[asyncio.Future[object]] = []

    def capture_schedule(
        coro: object,
        event_loop: asyncio.AbstractEventLoop,
    ) -> asyncio.Future[object]:
        future = asyncio.ensure_future(coro, loop=event_loop)  # type: ignore[arg-type]
        scheduled.append(future)
        return future

    with patch("cadence.player.asyncio.run_coroutine_threadsafe", side_effect=capture_schedule):
        await handle_skip(cast(discord.Interaction, skip_interaction), ctx.deps)

    for future in scheduled:
        await future

    assert skip_interaction.responses[0].content == "⏭️ Skipped."

    state = ctx.store.get(ctx.guild.id)
    assert state.current is not None
    assert state.current.title == "Next Song"
    assert state.loop_mode is LoopMode.OFF


@pytest.mark.asyncio
async def test_us4_skip_errors_when_nothing_playing(acceptance_ctx: AcceptanceContext) -> None:
    """US-4: /skip with nothing playing replies ephemeral and does not advance."""
    ctx = acceptance_ctx
    interaction = make_interaction(ctx.guild, voice_channel=ctx.voice_channel)

    await handle_skip(cast(discord.Interaction, interaction), ctx.deps)

    assert len(interaction.responses) == 1
    assert interaction.responses[0].ephemeral is True
    assert interaction.responses[0].content == "Nothing is playing."


@pytest.mark.asyncio
async def test_us7_t3_04_stop_clears_and_disconnects(acceptance_ctx: AcceptanceContext) -> None:
    """US-7 / T3-04: /stop clears state and disconnects from voice."""
    ctx = acceptance_ctx
    script_play_flow(ctx, "Playing")
    play_interaction = make_interaction(ctx.guild, voice_channel=ctx.voice_channel)
    await handle_play(cast(discord.Interaction, play_interaction), "playing", ctx.deps)

    state = ctx.store.get(ctx.guild.id)
    state.loop_mode = LoopMode.TRACK

    stop_interaction = make_interaction(ctx.guild, voice_channel=ctx.voice_channel)
    await handle_stop(cast(discord.Interaction, stop_interaction), ctx.deps)

    assert stop_interaction.responses[0].content == "⏹️ Stopped and left the channel."
    assert state.current is None
    assert state.loop_mode is LoopMode.OFF
    assert len(state.queue) == 0
    assert ctx.guild.voice_client is None


@pytest.mark.asyncio
async def test_us8_idle_stays_connected_and_reuses_voice_client(
    acceptance_ctx: AcceptanceContext,
) -> None:
    """US-8: when the queue empties the bot stays connected; a later /play reuses the client."""
    ctx = acceptance_ctx
    track = script_track("Only Song")
    ctx.source.fetch_results = deque([track, track])
    ctx.source.resolve_results = deque([track, track])
    interaction = make_interaction(ctx.guild, voice_channel=ctx.voice_channel)

    await handle_play(cast(discord.Interaction, interaction), "only song", ctx.deps)
    voice_client = cast(FakeVoiceClient, ctx.guild.voice_client)
    assert voice_client is not None

    await finish_track(voice_client)

    state = ctx.store.get(ctx.guild.id)
    assert state.current is None
    assert ctx.guild.voice_client is not None
    assert ctx.guild.voice_client.disconnect_calls == 0

    second_interaction = make_interaction(ctx.guild, voice_channel=ctx.voice_channel)
    await handle_play(cast(discord.Interaction, second_interaction), "only song", ctx.deps)

    assert ctx.guild.voice_client is voice_client
    assert ctx.guild.voice_client.disconnect_calls == 0
    assert second_interaction.followups[0].content == "▶️ Now playing: **Only Song**"


@pytest.mark.asyncio
async def test_queue_loop_cycles_tracks(acceptance_ctx: AcceptanceContext) -> None:
    """Queue loop reinserts finished tracks and advances through the queue."""
    ctx = acceptance_ctx
    first = script_track("First")
    second = script_track("Second")
    ctx.source.fetch_results = deque([first, second])
    ctx.source.resolve_results = deque([first, second, first])
    play_first = make_interaction(ctx.guild, voice_channel=ctx.voice_channel)
    await handle_play(cast(discord.Interaction, play_first), "first", ctx.deps)

    queue_second = make_interaction(ctx.guild, voice_channel=ctx.voice_channel)
    await handle_play(cast(discord.Interaction, queue_second), "second", ctx.deps)

    loop_interaction = make_interaction(ctx.guild, voice_channel=ctx.voice_channel)
    await handle_loop(cast(discord.Interaction, loop_interaction), LoopMode.QUEUE, ctx.deps)

    voice_client = cast(FakeVoiceClient, ctx.guild.voice_client)
    assert voice_client is not None
    await finish_track(voice_client)

    state = ctx.store.get(ctx.guild.id)
    assert state.current is not None
    assert state.current.title == "Second"
    assert len(state.queue) == 1
    assert state.queue[0].title == "First"
