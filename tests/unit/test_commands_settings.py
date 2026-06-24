"""Unit tests for settings slash commands."""

from __future__ import annotations

from typing import cast

import discord
import pytest

from cadence.commands.deps import CommandDeps
from cadence.commands.settings import handle_loop, handle_volume
from tests.fakes import FakeGuild, FakeInteraction, FakePlayer


@pytest.mark.asyncio
async def test_loop_toggles_on(command_deps: CommandDeps) -> None:
    guild = FakeGuild(id=1)
    interaction = FakeInteraction(guild=guild)
    player = cast(FakePlayer, command_deps.player)
    state = command_deps.store.get(guild.id)
    assert state.loop is False

    await handle_loop(cast(discord.Interaction, interaction), command_deps)

    assert player.loop_calls == [(guild, True)]
    assert player.loop_enabled is True
    assert interaction.responses[0].content == "🔁 Loop enabled."


@pytest.mark.asyncio
async def test_loop_toggles_off(command_deps: CommandDeps) -> None:
    guild = FakeGuild(id=1)
    interaction = FakeInteraction(guild=guild)
    player = cast(FakePlayer, command_deps.player)
    state = command_deps.store.get(guild.id)
    state.loop = True

    await handle_loop(cast(discord.Interaction, interaction), command_deps)

    assert player.loop_calls == [(guild, False)]
    assert player.loop_enabled is False
    assert interaction.responses[0].content == "🔁 Loop disabled."


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
