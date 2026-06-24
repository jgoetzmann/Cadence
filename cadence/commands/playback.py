"""Playback slash commands: /play, /skip, /pause, /resume, /stop."""

from __future__ import annotations

import logging
from typing import cast

import discord
from discord import app_commands

from cadence.commands.deps import CommandDeps
from cadence.interfaces import Player
from cadence.state import Track

__all__ = [
    "handle_pause",
    "handle_play",
    "handle_resume",
    "handle_skip",
    "handle_stop",
    "register_playback",
]

log = logging.getLogger(__name__)

_NOT_IN_VOICE = "You need to be in a voice channel first."
_NOTHING_PLAYING = "Nothing is playing."
_NOTHING_PAUSED = "Nothing is paused."
_FETCH_FAILED = "Couldn't find anything for that."


def _user_voice_channel(interaction: discord.Interaction) -> discord.VoiceChannel | None:
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


def _voice_client(guild: discord.Guild) -> discord.VoiceClient | None:
    voice_client = guild.voice_client
    if voice_client is None:
        return None
    return cast(discord.VoiceClient, voice_client)


def _is_playback_active(guild: discord.Guild, player: Player) -> bool:
    voice_client = _voice_client(guild)
    current, _ = player.snapshot(guild)
    return voice_client is not None and (voice_client.is_playing() or current is not None)


def _is_url(query: str) -> bool:
    return query.startswith(("http://", "https://"))


async def handle_play(
    interaction: discord.Interaction,
    query: str,
    deps: CommandDeps,
) -> None:
    """Resolve a query and start playback or enqueue."""
    voice_channel = _user_voice_channel(interaction)
    if voice_channel is None:
        await interaction.response.send_message(_NOT_IN_VOICE, ephemeral=True)
        return

    await interaction.response.defer()

    guild = interaction.guild
    if guild is None:
        return

    voice_client = _voice_client(guild)
    if voice_client is None:
        await voice_channel.connect()
    elif voice_client.channel != voice_channel:
        await voice_client.move_to(voice_channel)

    state = deps.store.get(guild.id)
    if interaction.channel is not None:
        state.text_channel = cast(discord.abc.Messageable, interaction.channel)

    try:
        resolved = await deps.source.fetch(query, is_url=_is_url(query))
    except Exception:
        log.exception("Failed to fetch audio for query=%r", query)
        await interaction.followup.send(_FETCH_FAILED)
        return

    track = Track(
        title=resolved.title,
        webpage_url=resolved.webpage_url,
        requested_by=interaction.user.id,
        duration=resolved.duration,
    )

    already_active = _is_playback_active(guild, deps.player)
    await deps.player.enqueue(guild, track)

    if already_active:
        await interaction.followup.send(f"➕ Added to queue: **{track.title}**")
    else:
        await deps.player.play_next(guild, announce=False)
        await interaction.followup.send(f"▶️ Now playing: **{track.title}**")


async def handle_skip(interaction: discord.Interaction, deps: CommandDeps) -> None:
    """Skip the current track."""
    guild = interaction.guild
    if guild is None:
        return

    voice_client = _voice_client(guild)
    if voice_client is None or not voice_client.is_playing():
        await interaction.response.send_message(_NOTHING_PLAYING, ephemeral=True)
        return

    await deps.player.skip(guild)
    await interaction.response.send_message("⏭️ Skipped.")


async def handle_pause(interaction: discord.Interaction, deps: CommandDeps) -> None:
    """Pause playback."""
    guild = interaction.guild
    if guild is None:
        return

    voice_client = _voice_client(guild)
    if voice_client is None or not voice_client.is_playing():
        await interaction.response.send_message(_NOTHING_PLAYING, ephemeral=True)
        return

    await deps.player.pause(guild)
    await interaction.response.send_message("⏸️ Paused.")


async def handle_resume(interaction: discord.Interaction, deps: CommandDeps) -> None:
    """Resume paused playback."""
    guild = interaction.guild
    if guild is None:
        return

    voice_client = _voice_client(guild)
    if voice_client is None or not voice_client.is_paused():
        await interaction.response.send_message(_NOTHING_PAUSED, ephemeral=True)
        return

    await deps.player.resume(guild)
    await interaction.response.send_message("▶️ Resumed.")


async def handle_stop(interaction: discord.Interaction, deps: CommandDeps) -> None:
    """Stop playback and leave the voice channel."""
    guild = interaction.guild
    if guild is None:
        return

    await deps.player.stop(guild)
    await interaction.response.send_message("⏹️ Stopped and left the channel.")


def register_playback(tree: app_commands.CommandTree, deps: CommandDeps) -> None:
    """Register playback slash commands on the command tree."""

    @tree.command(name="play", description="Search YouTube and play the most relevant result")
    @app_commands.describe(query="Search terms or a YouTube URL")
    async def play(interaction: discord.Interaction, query: str) -> None:
        await handle_play(interaction, query, deps)

    @tree.command(name="skip", description="Skip the current song")
    async def skip(interaction: discord.Interaction) -> None:
        await handle_skip(interaction, deps)

    @tree.command(name="pause", description="Pause playback")
    async def pause(interaction: discord.Interaction) -> None:
        await handle_pause(interaction, deps)

    @tree.command(name="resume", description="Resume playback")
    async def resume(interaction: discord.Interaction) -> None:
        await handle_resume(interaction, deps)

    @tree.command(name="stop", description="Stop playback, clear the queue, and leave")
    async def stop(interaction: discord.Interaction) -> None:
        await handle_stop(interaction, deps)
