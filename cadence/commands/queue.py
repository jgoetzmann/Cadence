"""Queue slash commands: /queue, /nowplaying."""

from __future__ import annotations

import discord
from discord import app_commands

from cadence.commands.deps import CommandDeps
from cadence.state import Track

__all__ = ["handle_nowplaying", "handle_queue", "register_queue"]

MAX_QUEUE_DISPLAY = 10

_NOTHING_PLAYING = "Nothing is playing."
_QUEUE_EMPTY = "The queue is empty."


def _format_queue(current: Track | None, upcoming: list[Track]) -> str:
    lines: list[str] = []
    if current is not None:
        lines.append(f"▶️ Now playing: **{current.title}**")
    display = upcoming[:MAX_QUEUE_DISPLAY]
    for index, track in enumerate(display, start=1):
        lines.append(f"{index}. **{track.title}**")
    remaining = len(upcoming) - len(display)
    if remaining > 0:
        lines.append(f"+{remaining} more")
    return "\n".join(lines)


async def handle_queue(interaction: discord.Interaction, deps: CommandDeps) -> None:
    """Show the current track and upcoming queue."""
    guild = interaction.guild
    if guild is None:
        return

    current, upcoming = deps.player.snapshot(guild)
    if current is None and not upcoming:
        await interaction.response.send_message(_QUEUE_EMPTY)
        return

    await interaction.response.send_message(_format_queue(current, upcoming))


async def handle_nowplaying(interaction: discord.Interaction, deps: CommandDeps) -> None:
    """Show the track that is currently playing."""
    guild = interaction.guild
    if guild is None:
        return

    current, _ = deps.player.snapshot(guild)
    if current is None:
        await interaction.response.send_message(_NOTHING_PLAYING)
        return

    await interaction.response.send_message(
        f"▶️ **{current.title}** (<@{current.requested_by}>)"
    )


def register_queue(tree: app_commands.CommandTree, deps: CommandDeps) -> None:
    """Register queue slash commands on the command tree."""

    @tree.command(name="queue", description="Show the current queue")
    async def queue(interaction: discord.Interaction) -> None:
        await handle_queue(interaction, deps)

    @tree.command(name="nowplaying", description="Show the currently playing track")
    async def nowplaying(interaction: discord.Interaction) -> None:
        await handle_nowplaying(interaction, deps)
