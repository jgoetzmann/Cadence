"""Unit tests for settings slash commands."""

from __future__ import annotations

from typing import cast

import discord
import pytest

from cadence.commands.deps import CommandDeps
from cadence.commands.settings import handle_idle, handle_loop, handle_volume
from cadence.state import LoopMode
from tests.fakes import FakeGuild, FakeInteraction, FakePlayer


@pytest.mark.asyncio
async def test_loop_sets_track_mode(command_deps: CommandDeps) -> None:
    guild = FakeGuild(id=1)
    interaction = FakeInteraction(guild=guild)
    player = cast(FakePlayer, command_deps.player)
    state = command_deps.store.get(guild.id)
    assert state.loop_mode is LoopMode.OFF

    await handle_loop(cast(discord.Interaction, interaction), LoopMode.TRACK, command_deps)

    assert player.loop_mode_calls == [(guild, LoopMode.TRACK)]
    assert player.loop_mode is LoopMode.TRACK
    assert interaction.responses[0].content == "Loop set to **Current song**."


@pytest.mark.asyncio
async def test_loop_sets_off_mode(command_deps: CommandDeps) -> None:
    guild = FakeGuild(id=1)
    interaction = FakeInteraction(guild=guild)
    player = cast(FakePlayer, command_deps.player)
    state = command_deps.store.get(guild.id)
    state.loop_mode = LoopMode.QUEUE

    await handle_loop(cast(discord.Interaction, interaction), LoopMode.OFF, command_deps)

    assert player.loop_mode_calls == [(guild, LoopMode.OFF)]
    assert player.loop_mode is LoopMode.OFF
    assert interaction.responses[0].content == "Loop set to **Off**."


@pytest.mark.asyncio
async def test_loop_sets_queue_mode(command_deps: CommandDeps) -> None:
    guild = FakeGuild(id=1)
    interaction = FakeInteraction(guild=guild)
    player = cast(FakePlayer, command_deps.player)

    await handle_loop(cast(discord.Interaction, interaction), LoopMode.QUEUE, command_deps)

    assert player.loop_mode_calls == [(guild, LoopMode.QUEUE)]
    assert interaction.responses[0].content == "Loop set to **Queue**."


@pytest.mark.asyncio
async def test_idle_sets_minutes(command_deps: CommandDeps) -> None:
    guild = FakeGuild(id=1)
    interaction = FakeInteraction(guild=guild)
    state = command_deps.store.get(guild.id)

    await handle_idle(cast(discord.Interaction, interaction), 30, command_deps)

    assert state.idle_minutes == 30
    assert interaction.responses[0].content == (
        "Auto-disconnect idle time set to **30** minutes."
    )


@pytest.mark.asyncio
async def test_volume_rejects_out_of_range(command_deps: CommandDeps) -> None:
    guild = FakeGuild(id=1)
    interaction = FakeInteraction(guild=guild)
    player = cast(FakePlayer, command_deps.player)

    await handle_volume(cast(discord.Interaction, interaction), 150, command_deps)

    assert player.volume_calls == []
    assert interaction.responses[0].ephemeral is True
    assert interaction.responses[0].content == "Volume must be between 0 and 100."


@pytest.mark.asyncio
async def test_volume_applies_valid_level(command_deps: CommandDeps) -> None:
    guild = FakeGuild(id=1)
    interaction = FakeInteraction(guild=guild)
    player = cast(FakePlayer, command_deps.player)

    await handle_volume(cast(discord.Interaction, interaction), 40, command_deps)

    assert player.volume_calls == [(guild, 40)]
    assert interaction.responses[0].content == "🔊 Volume set to **40**."
