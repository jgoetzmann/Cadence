"""Shared voice-channel helpers for slash commands."""

from __future__ import annotations

from typing import Literal, cast

import discord

__all__ = ["ConnectResult", "connect_or_move", "user_voice_channel", "voice_client"]

ConnectResult = Literal["joined", "moved", "already"]


def user_voice_channel(interaction: discord.Interaction) -> discord.VoiceChannel | None:
    """Return the caller's voice channel, if they are in one."""
    user = interaction.user
    if isinstance(user, discord.Member):
        if user.voice is None:
            return None
        channel = user.voice.channel
        if not isinstance(channel, discord.VoiceChannel):
            return None
        return channel
    voice = getattr(user, "voice", None)
    if voice is None:
        return None
    return getattr(voice, "channel", None)


def voice_client(guild: discord.Guild) -> discord.VoiceClient | None:
    """Return the guild's voice client, if connected."""
    vc = guild.voice_client
    if vc is None:
        return None
    return cast(discord.VoiceClient, vc)


async def connect_or_move(
    guild: discord.Guild,
    voice_channel: discord.VoiceChannel,
) -> ConnectResult:
    """Connect or move to a voice channel."""
    vc = voice_client(guild)
    if vc is None:
        await voice_channel.connect()
        return "joined"
    if vc.channel != voice_channel:
        await vc.move_to(voice_channel)
        return "moved"
    return "already"
