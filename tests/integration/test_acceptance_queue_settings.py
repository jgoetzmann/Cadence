"""Acceptance tests for queue and settings commands — T3b."""

from __future__ import annotations

from typing import cast

import discord
import pytest

from cadence.commands.playback import handle_pause, handle_play, handle_resume
from cadence.commands.queue import handle_nowplaying, handle_queue
from cadence.commands.settings import handle_loop, handle_volume
from tests.fakes import FakeVoiceClient
from tests.integration.acceptance_helpers import (
    AcceptanceContext,
    finish_track,
    make_interaction,
    script_play_flow,
)


@pytest.mark.asyncio
async def test_us5_t3_05_queue_and_nowplaying_idle_states(
    acceptance_ctx: AcceptanceContext,
) -> None:
    """US-5 / T3-05: /queue and /nowplaying show empty-state messages when idle."""
    ctx = acceptance_ctx
    queue_interaction = make_interaction(ctx.guild, voice_channel=ctx.voice_channel)
    nowplaying_interaction = make_interaction(ctx.guild, voice_channel=ctx.voice_channel)

    await handle_queue(cast(discord.Interaction, queue_interaction), ctx.deps)
    await handle_nowplaying(cast(discord.Interaction, nowplaying_interaction), ctx.deps)

    assert queue_interaction.responses[0].content == "The queue is empty."
    assert nowplaying_interaction.responses[0].content == "Nothing is playing."


@pytest.mark.asyncio
async def test_us5_t3_05_queue_and_nowplaying_during_playback(
    acceptance_ctx: AcceptanceContext,
) -> None:
    """US-5 / T3-05: /queue and /nowplaying render current and upcoming tracks."""
    ctx = acceptance_ctx
    script_play_flow(ctx, "Current", "Up One", "Up Two")
    play_interaction = make_interaction(ctx.guild, voice_channel=ctx.voice_channel)
    await handle_play(cast(discord.Interaction, play_interaction), "current", ctx.deps)

    for title in ("up one", "up two"):
        extra = make_interaction(ctx.guild, voice_channel=ctx.voice_channel)
        await handle_play(cast(discord.Interaction, extra), title, ctx.deps)

    queue_interaction = make_interaction(ctx.guild, voice_channel=ctx.voice_channel)
    nowplaying_interaction = make_interaction(ctx.guild, voice_channel=ctx.voice_channel)
    await handle_queue(cast(discord.Interaction, queue_interaction), ctx.deps)
    await handle_nowplaying(cast(discord.Interaction, nowplaying_interaction), ctx.deps)

    queue_content = queue_interaction.responses[0].content
    assert "1. ▶️ Now playing: **Current**" in queue_content
    assert "2. **Up One**" in queue_content
    assert "3. **Up Two**" in queue_content
    assert nowplaying_interaction.responses[0].content == "▶️ **Current** (<@42>)"


@pytest.mark.asyncio
async def test_us5_queue_full_blocks_enqueue(acceptance_ctx: AcceptanceContext) -> None:
    """US-5: /play refuses to enqueue when the queue already has QUEUE_LIMIT tracks."""
    from cadence.state import QUEUE_LIMIT

    ctx = acceptance_ctx
    script_play_flow(ctx, "Current", *[f"Track {index}" for index in range(QUEUE_LIMIT)])
    play_interaction = make_interaction(ctx.guild, voice_channel=ctx.voice_channel)
    await handle_play(cast(discord.Interaction, play_interaction), "current", ctx.deps)

    for index in range(QUEUE_LIMIT):
        extra = make_interaction(ctx.guild, voice_channel=ctx.voice_channel)
        await handle_play(cast(discord.Interaction, extra), f"track {index}", ctx.deps)

    full_interaction = make_interaction(ctx.guild, voice_channel=ctx.voice_channel)
    await handle_play(cast(discord.Interaction, full_interaction), "one more", ctx.deps)

    assert full_interaction.responses[0].ephemeral is True
    assert "Queue is full" in full_interaction.responses[0].content


@pytest.mark.asyncio
async def test_us3_us6_t3_06_loop_and_volume_persist_in_session(
    acceptance_ctx: AcceptanceContext,
) -> None:
    """US-3 / US-6 / T3-06: /loop toggles and /volume applies and persists across tracks."""
    ctx = acceptance_ctx
    script_play_flow(ctx, "First", "Second")
    play_interaction = make_interaction(ctx.guild, voice_channel=ctx.voice_channel)
    await handle_play(cast(discord.Interaction, play_interaction), "first", ctx.deps)

    loop_interaction = make_interaction(ctx.guild, voice_channel=ctx.voice_channel)
    await handle_loop(cast(discord.Interaction, loop_interaction), ctx.deps)
    assert loop_interaction.responses[0].content == "🔁 Loop enabled."

    volume_interaction = make_interaction(ctx.guild, voice_channel=ctx.voice_channel)
    await handle_volume(cast(discord.Interaction, volume_interaction), 150, ctx.deps)
    assert volume_interaction.responses[0].ephemeral is True
    assert volume_interaction.responses[0].content == "Volume must be between 0 and 100."

    valid_volume = make_interaction(ctx.guild, voice_channel=ctx.voice_channel)
    await handle_volume(cast(discord.Interaction, valid_volume), 40, ctx.deps)
    assert valid_volume.responses[0].content == "🔊 Volume set to **40**."

    state = ctx.store.get(ctx.guild.id)
    assert state.volume == 40
    assert state.voice_source is not None
    assert state.voice_source.volume == 0.4

    queue_interaction = make_interaction(ctx.guild, voice_channel=ctx.voice_channel)
    await handle_play(cast(discord.Interaction, queue_interaction), "second", ctx.deps)

    disable_loop = make_interaction(ctx.guild, voice_channel=ctx.voice_channel)
    await handle_loop(cast(discord.Interaction, disable_loop), ctx.deps)
    assert disable_loop.responses[0].content == "🔁 Loop disabled."

    voice_client = cast(FakeVoiceClient, ctx.guild.voice_client)
    assert voice_client is not None
    await finish_track(voice_client)

    assert state.volume == 40
    assert state.current is not None
    assert state.current.title == "Second"
    assert state.voice_source is not None
    assert state.voice_source.volume == 0.4


@pytest.mark.asyncio
async def test_us6_pause_and_resume_with_real_player(acceptance_ctx: AcceptanceContext) -> None:
    """US-6: /pause and /resume control playback through the real Player."""
    ctx = acceptance_ctx
    script_play_flow(ctx, "Playing")
    play_interaction = make_interaction(ctx.guild, voice_channel=ctx.voice_channel)
    await handle_play(cast(discord.Interaction, play_interaction), "playing", ctx.deps)

    voice_client = cast(FakeVoiceClient, ctx.guild.voice_client)
    assert voice_client is not None
    assert voice_client.is_playing()

    pause_interaction = make_interaction(ctx.guild, voice_channel=ctx.voice_channel)
    await handle_pause(cast(discord.Interaction, pause_interaction), ctx.deps)
    assert pause_interaction.responses[0].content == "⏸️ Paused."
    assert voice_client.is_paused()

    resume_interaction = make_interaction(ctx.guild, voice_channel=ctx.voice_channel)
    await handle_resume(cast(discord.Interaction, resume_interaction), ctx.deps)
    assert resume_interaction.responses[0].content == "▶️ Resumed."
    assert voice_client.is_playing()
    assert not voice_client.is_paused()


@pytest.mark.asyncio
async def test_us6_pause_and_resume_precondition_errors(
    acceptance_ctx: AcceptanceContext,
) -> None:
    """US-6: /pause and /resume reply ephemeral when preconditions are not met."""
    ctx = acceptance_ctx
    pause_interaction = make_interaction(ctx.guild, voice_channel=ctx.voice_channel)
    await handle_pause(cast(discord.Interaction, pause_interaction), ctx.deps)
    assert pause_interaction.responses[0].ephemeral is True
    assert pause_interaction.responses[0].content == "Nothing is playing."

    resume_interaction = make_interaction(ctx.guild, voice_channel=ctx.voice_channel)
    await handle_resume(cast(discord.Interaction, resume_interaction), ctx.deps)
    assert resume_interaction.responses[0].ephemeral is True
    assert resume_interaction.responses[0].content == "Nothing is paused."
