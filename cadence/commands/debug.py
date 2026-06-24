"""Debug slash command: /debug."""

from __future__ import annotations

import time
from typing import cast

import discord
from discord import app_commands

from cadence import __version__
from cadence.commands.deps import CommandDeps
from cadence.interfaces import Player
from cadence.state import LOOP_MODE_LABELS, QUEUE_LIMIT, GuildState, StateStore, Track

__all__ = ["DISCORD_MESSAGE_LIMIT", "format_debug_report", "handle_debug", "register_debug"]

DISCORD_MESSAGE_LIMIT = 2000


def _format_timestamp(value: float | None, now: float) -> str:
    if value is None:
        return "none"
    age = max(0.0, now - value)
    return f"{value:.1f} ({age:.0f}s ago)"


def _format_track_line(index: int | None, track: Track) -> str:
    prefix = f"{index}. " if index is not None else ""
    duration = f", {track.duration}s" if track.duration is not None else ""
    return (
        f"{prefix}**{track.title}** "
        f"(by <@{track.requested_by}>{duration})\n"
        f"   {track.webpage_url}"
    )


def _format_guild_state(state: GuildState, now: float) -> list[str]:
    lines = [
        f"loop_mode: {LOOP_MODE_LABELS[state.loop_mode]} (`{state.loop_mode.value}`)",
        f"volume: {state.volume}",
        f"idle_minutes: {state.idle_minutes}",
        f"last_command_at: {_format_timestamp(state.last_command_at, now)}",
        f"last_song_started_at: {_format_timestamp(state.last_song_started_at, now)}",
        f"alone_since: {_format_timestamp(state.alone_since, now)}",
    ]

    if state.current is None:
        lines.append("current: none")
    else:
        lines.append("current:")
        lines.append(_format_track_line(None, state.current))

    lines.append(f"queue: {len(state.queue)}/{QUEUE_LIMIT}")
    if state.queue:
        for index, track in enumerate(state.queue, start=1):
            lines.append(_format_track_line(index, track))
    else:
        lines.append("  (empty)")

    if state.text_channel is None:
        lines.append("text_channel: none")
    else:
        channel_id = getattr(state.text_channel, "id", None)
        lines.append(f"text_channel_id: {channel_id}")

    if state.voice_source is None:
        lines.append("voice_source: none")
    else:
        lines.append(f"voice_source: active (transformer volume {state.voice_source.volume:.2f})")

    return lines


def _format_voice_status(guild: discord.Guild) -> list[str]:
    voice_client = guild.voice_client
    if voice_client is None:
        return ["connected: no"]

    vc = cast(discord.VoiceClient, voice_client)
    channel = vc.channel
    if channel is None:
        return ["connected: yes", "channel: none"]

    lines = [
        "connected: yes",
        f"channel: **{channel.name}** (id {channel.id})",
        f"playing: {vc.is_playing()}",
        f"paused: {vc.is_paused()}",
    ]
    humans = sum(1 for member in channel.members if not member.bot)
    lines.append(f"humans_in_channel: {humans}")
    return lines


def format_debug_report(
    guild: discord.Guild,
    store: StateStore,
    player: Player,
    *,
    now: float | None = None,
) -> str:
    """Build a markdown debug dump for a guild and the in-memory store."""
    clock = now if now is not None else time.monotonic()
    state = store.peek(guild.id)
    player_current, player_upcoming = player.snapshot(guild)

    sections: list[str] = [
        f"**Cadence debug — guild {guild.id}**",
        f"version: {__version__}",
        "",
        "**Store**",
        f"default_volume: {store.default_volume}",
        f"guilds_tracked: {len(store.guild_ids())}",
    ]

    other_guilds = [gid for gid in store.guild_ids() if gid != guild.id]
    if other_guilds:
        sections.append(f"other_guild_ids: {', '.join(str(gid) for gid in other_guilds)}")

    sections.extend(["", "**Guild state**"])
    if state is None:
        sections.append("no stored entry for this guild yet")
    else:
        sections.extend(_format_guild_state(state, clock))

    sections.extend(["", "**Player snapshot**"])
    if player_current is None:
        sections.append("current: none")
    else:
        sections.append(f"current: **{player_current.title}**")
    sections.append(f"upcoming_count: {len(player_upcoming)}")

    sections.extend(["", "**Discord voice**"])
    sections.extend(_format_voice_status(guild))

    text = "\n".join(sections)
    if len(text) <= DISCORD_MESSAGE_LIMIT:
        return text

    truncated = text[: DISCORD_MESSAGE_LIMIT - 20].rstrip()
    return f"{truncated}\n\n… (truncated)"


async def handle_debug(interaction: discord.Interaction, deps: CommandDeps) -> None:
    """Reply with an ephemeral dump of in-memory guild state."""
    guild = interaction.guild
    if guild is None:
        return

    report = format_debug_report(guild, deps.store, deps.player)
    await interaction.response.send_message(report, ephemeral=True)


def register_debug(tree: app_commands.CommandTree, deps: CommandDeps) -> None:
    """Register the /debug slash command on the command tree."""

    @tree.command(
        name="debug",
        description="Dump in-memory playback and idle state for this guild",
    )
    async def debug(interaction: discord.Interaction) -> None:
        await handle_debug(interaction, deps)
