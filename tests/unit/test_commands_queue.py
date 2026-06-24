"""Unit tests for queue slash commands."""

from __future__ import annotations

from typing import cast

import discord
import pytest

from cadence.commands.deps import CommandDeps
from cadence.commands.queue import MAX_QUEUE_DISPLAY, handle_nowplaying, handle_queue
from cadence.state import Track
from tests.fakes import FakeGuild, FakeInteraction, FakePlayer


def _track(title: str) -> Track:
    return Track(
        title=title,
        webpage_url=f"https://example.com/watch?v={title}",
        requested_by=1,
    )


@pytest.mark.asyncio
async def test_queue_empty_state(command_deps: CommandDeps) -> None:
    guild = FakeGuild(id=1)
    interaction = FakeInteraction(guild=guild)

    await handle_queue(cast(discord.Interaction, interaction), command_deps)

    assert interaction.responses[0].content == "The queue is empty."


@pytest.mark.asyncio
async def test_queue_lists_current_and_upcoming(command_deps: CommandDeps) -> None:
    guild = FakeGuild(id=1)
    interaction = FakeInteraction(guild=guild)
    player = cast(FakePlayer, command_deps.player)
    current = _track("Current")
    upcoming = [_track("One"), _track("Two")]
    player.snapshot_current = current
    player.snapshot_upcoming = upcoming

    await handle_queue(cast(discord.Interaction, interaction), command_deps)

    content = interaction.responses[0].content
    assert "▶️ Now playing: **Current**" in content
    assert "1. **One**" in content
    assert "2. **Two**" in content


@pytest.mark.asyncio
async def test_queue_truncates_long_lists(command_deps: CommandDeps) -> None:
    guild = FakeGuild(id=1)
    interaction = FakeInteraction(guild=guild)
    player = cast(FakePlayer, command_deps.player)
    player.snapshot_current = _track("Current")
    player.snapshot_upcoming = [_track(str(index)) for index in range(MAX_QUEUE_DISPLAY + 3)]

    await handle_queue(cast(discord.Interaction, interaction), command_deps)

    content = interaction.responses[0].content
    assert f"+{3} more" in content
    assert f"{MAX_QUEUE_DISPLAY}. **{MAX_QUEUE_DISPLAY - 1}**" in content
    assert f"{MAX_QUEUE_DISPLAY + 1}." not in content


@pytest.mark.asyncio
async def test_nowplaying_shows_current_track(command_deps: CommandDeps) -> None:
    guild = FakeGuild(id=1)
    interaction = FakeInteraction(guild=guild)
    player = cast(FakePlayer, command_deps.player)
    player.snapshot_current = _track("Playing Now")

    await handle_nowplaying(cast(discord.Interaction, interaction), command_deps)

    assert interaction.responses[0].content == "▶️ **Playing Now** (<@1>)"


@pytest.mark.asyncio
async def test_nowplaying_empty_state(command_deps: CommandDeps) -> None:
    guild = FakeGuild(id=1)
    interaction = FakeInteraction(guild=guild)

    await handle_nowplaying(cast(discord.Interaction, interaction), command_deps)

    assert interaction.responses[0].content == "Nothing is playing."
