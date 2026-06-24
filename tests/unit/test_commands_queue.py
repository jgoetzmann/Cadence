"""Unit tests for queue slash commands."""

from __future__ import annotations

from typing import cast

import discord
import pytest

from cadence.commands.deps import CommandDeps
from cadence.commands.queue import handle_clear, handle_nowplaying, handle_queue, handle_remove
from cadence.state import QUEUE_LIMIT, Track
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
    assert "1. ▶️ Now playing: **Current**" in content
    assert "2. **One**" in content
    assert "3. **Two**" in content


@pytest.mark.asyncio
async def test_queue_shows_up_to_queue_limit(command_deps: CommandDeps) -> None:
    guild = FakeGuild(id=1)
    interaction = FakeInteraction(guild=guild)
    player = cast(FakePlayer, command_deps.player)
    player.snapshot_current = _track("Current")
    player.snapshot_upcoming = [_track(str(index)) for index in range(QUEUE_LIMIT)]

    await handle_queue(cast(discord.Interaction, interaction), command_deps)

    content = interaction.responses[0].content
    assert "1. ▶️ Now playing: **Current**" in content
    assert f"{QUEUE_LIMIT + 1}. **{QUEUE_LIMIT - 1}**" in content


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


@pytest.mark.asyncio
async def test_remove_position_one_skips_current(command_deps: CommandDeps) -> None:
    guild = FakeGuild(id=1)
    interaction = FakeInteraction(guild=guild)
    player = cast(FakePlayer, command_deps.player)
    player.snapshot_current = _track("Current")

    await handle_remove(cast(discord.Interaction, interaction), 1, command_deps)

    assert player.remove_at_calls == [(guild, 1)]
    assert interaction.responses[0].content == "Skipped **Current**."


@pytest.mark.asyncio
async def test_remove_position_one_idle(command_deps: CommandDeps) -> None:
    guild = FakeGuild(id=1)
    interaction = FakeInteraction(guild=guild)

    await handle_remove(cast(discord.Interaction, interaction), 1, command_deps)

    assert interaction.responses[0].ephemeral is True
    assert interaction.responses[0].content == "Nothing is playing."


@pytest.mark.asyncio
async def test_remove_upcoming_track(command_deps: CommandDeps) -> None:
    guild = FakeGuild(id=1)
    interaction = FakeInteraction(guild=guild)
    player = cast(FakePlayer, command_deps.player)
    player.snapshot_upcoming = [_track("One"), _track("Two")]

    await handle_remove(cast(discord.Interaction, interaction), 2, command_deps)

    assert player.remove_at_calls == [(guild, 2)]
    assert interaction.responses[0].content == "Removed **Two** from the queue."


@pytest.mark.asyncio
async def test_remove_invalid_position(command_deps: CommandDeps) -> None:
    guild = FakeGuild(id=1)
    interaction = FakeInteraction(guild=guild)
    player = cast(FakePlayer, command_deps.player)
    player.snapshot_upcoming = [_track("One")]

    await handle_remove(cast(discord.Interaction, interaction), 5, command_deps)

    assert player.remove_at_calls == []
    assert interaction.responses[0].ephemeral is True
    assert "No track at position **5**" in interaction.responses[0].content


@pytest.mark.asyncio
async def test_clear_removes_upcoming_tracks(command_deps: CommandDeps) -> None:
    guild = FakeGuild(id=1)
    interaction = FakeInteraction(guild=guild)
    player = cast(FakePlayer, command_deps.player)
    player.snapshot_upcoming = [_track("One"), _track("Two")]

    await handle_clear(cast(discord.Interaction, interaction), command_deps)

    assert player.clear_queue_calls == [guild]
    assert interaction.responses[0].content == "Cleared **2** tracks."


@pytest.mark.asyncio
async def test_clear_empty_queue(command_deps: CommandDeps) -> None:
    guild = FakeGuild(id=1)
    interaction = FakeInteraction(guild=guild)

    await handle_clear(cast(discord.Interaction, interaction), command_deps)

    assert interaction.responses[0].content == "Queue is already empty."
