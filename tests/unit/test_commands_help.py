"""Unit tests for /help slash command."""

from __future__ import annotations

from typing import cast

import discord
import pytest

from cadence.commands.deps import CommandDeps
from cadence.commands.help import HELP_TEXT, handle_help
from tests.fakes import FakeGuild, FakeInteraction


@pytest.mark.asyncio
async def test_help_sends_overview(command_deps: CommandDeps) -> None:
    guild = FakeGuild(id=1)
    interaction = FakeInteraction(guild=guild)

    await handle_help(cast(discord.Interaction, interaction), command_deps)

    assert len(interaction.responses) == 1
    assert interaction.responses[0].content == HELP_TEXT
    assert "/play" in interaction.responses[0].content
    assert "/loop" in interaction.responses[0].content
    assert "/idle" in interaction.responses[0].content
    assert "/ping" in interaction.responses[0].content
