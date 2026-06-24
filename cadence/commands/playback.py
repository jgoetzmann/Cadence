"""Playback slash commands: /play, /forceplay, /move, /skip, /pause, /resume, /stop."""

from __future__ import annotations

import logging
from typing import cast

import discord
from discord import app_commands

from cadence.commands.deps import CommandDeps
from cadence.commands.voice import connect_or_move, user_voice_channel, voice_client
from cadence.interfaces import Player
from cadence.player import QueueFullError
from cadence.state import QUEUE_LIMIT, Track

__all__ = [
    "handle_forceplay",
    "handle_move",
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
_QUEUE_FULL = "Queue is full — remove something first."


def _is_playback_active(guild: discord.Guild, player: Player) -> bool:
    vc = voice_client(guild)
    current, _ = player.snapshot(guild)
    return vc is not None and (vc.is_playing() or current is not None)


def _is_url(query: str) -> bool:
    return query.startswith(("http://", "https://"))


def _set_text_channel(interaction: discord.Interaction, deps: CommandDeps) -> None:
    guild = interaction.guild
    if guild is None or interaction.channel is None:
        return
    deps.store.get(guild.id).text_channel = cast(discord.abc.Messageable, interaction.channel)


async def handle_play(
    interaction: discord.Interaction,
    query: str,
    deps: CommandDeps,
) -> None:
    """Resolve a query and start playback or enqueue."""
    voice_channel = user_voice_channel(interaction)
    if voice_channel is None:
        await interaction.response.send_message(_NOT_IN_VOICE, ephemeral=True)
        return

    guild = interaction.guild
    if guild is None:
        return

    if _is_playback_active(guild, deps.player):
        _, upcoming = deps.player.snapshot(guild)
        if len(upcoming) >= QUEUE_LIMIT:
            await interaction.response.send_message(_QUEUE_FULL, ephemeral=True)
            return

    await interaction.response.defer()

    await connect_or_move(guild, voice_channel)
    _set_text_channel(interaction, deps)

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
    try:
        await deps.player.enqueue(guild, track)
    except QueueFullError:
        await interaction.followup.send(_QUEUE_FULL)
        return

    if already_active:
        await interaction.followup.send(f"➕ Added to queue: **{track.title}**")
    else:
        await deps.player.play_next(guild, announce=False)
        await interaction.followup.send(f"▶️ Now playing: **{track.title}**")


async def handle_forceplay(
    interaction: discord.Interaction,
    query: str,
    deps: CommandDeps,
) -> None:
    """Clear the queue and play a query immediately."""
    voice_channel = user_voice_channel(interaction)
    if voice_channel is None:
        await interaction.response.send_message(_NOT_IN_VOICE, ephemeral=True)
        return

    await interaction.response.defer()

    guild = interaction.guild
    if guild is None:
        return

    await connect_or_move(guild, voice_channel)
    _set_text_channel(interaction, deps)

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

    vc = voice_client(guild)
    was_active = vc is not None and (vc.is_playing() or vc.is_paused())
    deps.player.reset_lineup(guild)
    await deps.player.enqueue(guild, track)

    if was_active and vc is not None:
        vc.stop()
    else:
        await deps.player.play_next(guild, announce=False)

    await interaction.followup.send(f"▶️ Now playing: **{track.title}**")


async def handle_move(interaction: discord.Interaction, deps: CommandDeps) -> None:
    """Join or move the bot to the caller's voice channel."""
    voice_channel = user_voice_channel(interaction)
    if voice_channel is None:
        await interaction.response.send_message(_NOT_IN_VOICE, ephemeral=True)
        return

    guild = interaction.guild
    if guild is None:
        return

    result = await connect_or_move(guild, voice_channel)
    channel_name = voice_channel.name
    if result == "joined":
        message = f"Joined **{channel_name}**."
    elif result == "moved":
        message = f"Moved to **{channel_name}**."
    else:
        message = f"Already in **{channel_name}**."
    await interaction.response.send_message(message)


async def handle_skip(interaction: discord.Interaction, deps: CommandDeps) -> None:
    """Skip the current track."""
    guild = interaction.guild
    if guild is None:
        return

    vc = voice_client(guild)
    if vc is None or not vc.is_playing():
        await interaction.response.send_message(_NOTHING_PLAYING, ephemeral=True)
        return

    await deps.player.skip(guild)
    await interaction.response.send_message("⏭️ Skipped.")


async def handle_pause(interaction: discord.Interaction, deps: CommandDeps) -> None:
    """Pause playback."""
    guild = interaction.guild
    if guild is None:
        return

    vc = voice_client(guild)
    if vc is None or not vc.is_playing():
        await interaction.response.send_message(_NOTHING_PLAYING, ephemeral=True)
        return

    await deps.player.pause(guild)
    await interaction.response.send_message("⏸️ Paused.")


async def handle_resume(interaction: discord.Interaction, deps: CommandDeps) -> None:
    """Resume paused playback."""
    guild = interaction.guild
    if guild is None:
        return

    vc = voice_client(guild)
    if vc is None or not vc.is_paused():
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

    @tree.command(
        name="forceplay",
        description="Clear the queue and play a query immediately",
    )
    @app_commands.describe(query="Search terms or a YouTube URL")
    async def forceplay(interaction: discord.Interaction, query: str) -> None:
        await handle_forceplay(interaction, query, deps)

    @tree.command(name="move", description="Move the bot to your voice channel")
    async def move(interaction: discord.Interaction) -> None:
        await handle_move(interaction, deps)

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
