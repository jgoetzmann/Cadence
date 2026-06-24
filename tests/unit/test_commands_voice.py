"""Unit tests for shared voice command helpers."""

from __future__ import annotations

from typing import cast

import discord
import pytest

from cadence.commands.voice import connect_or_move, user_voice_channel, voice_client
from tests.fakes import FakeGuild, FakeInteraction, FakeVoiceChannel, FakeVoiceClient


@pytest.mark.asyncio
async def test_connect_or_move_joins_when_disconnected() -> None:
    guild = FakeGuild(id=1)
    channel = FakeVoiceChannel(id=2, guild=guild)

    joined = await connect_or_move(cast(discord.Guild, guild), cast(discord.VoiceChannel, channel))

    assert joined == "joined"
    assert guild.voice_client is not None


@pytest.mark.asyncio
async def test_connect_or_move_moves_when_elsewhere() -> None:
    guild = FakeGuild(id=1)
    old_channel = FakeVoiceChannel(id=2, guild=guild)
    new_channel = FakeVoiceChannel(id=3, guild=guild)
    vc = FakeVoiceClient(channel=old_channel)
    guild.voice_client = vc

    result = await connect_or_move(
        cast(discord.Guild, guild),
        cast(discord.VoiceChannel, new_channel),
    )

    assert result == "moved"
    assert vc.move_to_calls == [new_channel]


def test_user_voice_channel_none_when_not_in_voice() -> None:
    guild = FakeGuild(id=1)
    interaction = FakeInteraction(guild=guild, voice_channel=None)

    assert user_voice_channel(cast(discord.Interaction, interaction)) is None


def test_voice_client_none_when_disconnected() -> None:
    guild = FakeGuild(id=1)

    assert voice_client(cast(discord.Guild, guild)) is None
