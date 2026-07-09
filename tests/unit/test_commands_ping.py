"""Unit tests for /ping slash command."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

import discord
import pytest

from cadence import __version__
from cadence.commands.deps import CommandDeps
from cadence.commands.ping import handle_ping
from tests.fakes import FakeGuild, FakeInteraction


@pytest.mark.asyncio
async def test_ping_sends_online_status_with_version_and_latency(
    command_deps: CommandDeps,
) -> None:
    guild = FakeGuild(id=1)
    interaction = FakeInteraction(guild=guild)
    interaction.client = SimpleNamespace(latency=0.042)

    await handle_ping(cast(discord.Interaction, interaction), command_deps)

    assert len(interaction.responses) == 1
    content = interaction.responses[0].content
    assert "online" in content
    assert f"v{__version__}" in content
    assert "42ms" in content
    assert interaction.responses[0].ephemeral is False
