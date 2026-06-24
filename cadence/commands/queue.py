"""Queue slash commands: /queue, /nowplaying, /remove, /clear."""

from __future__ import annotations

import discord
from discord import app_commands

from cadence.commands.deps import CommandDeps
from cadence.state import QUEUE_LIMIT, Track

__all__ = [
    "handle_clear",
    "handle_nowplaying",
    "handle_queue",
    "handle_remove",
    "register_queue",
]

_NOTHING_PLAYING = "Nothing is playing."
_QUEUE_EMPTY = "The queue is empty."


def _format_queue(current: Track | None, upcoming: list[Track]) -> str:
    lines: list[str] = []
    start = 1
    if current is not None:
        lines.append(f"1. ▶️ Now playing: **{current.title}**")
        start = 2
    display = upcoming[:QUEUE_LIMIT]
    for index, track in enumerate(display, start=start):
        lines.append(f"{index}. **{track.title}**")
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


async def handle_remove(
    interaction: discord.Interaction,
    position: int,
    deps: CommandDeps,
) -> None:
    """Remove a track by its queue position."""
    guild = interaction.guild
    if guild is None:
        return

    current, upcoming = deps.player.snapshot(guild)

    if position == 1 and current is None and not upcoming:
        await interaction.response.send_message(_NOTHING_PLAYING, ephemeral=True)
        return

    if current is not None:
        if position == 1:
            pass
        elif position < 2 or position > 1 + len(upcoming):
            await interaction.response.send_message(
                f"No track at position **{position}**.",
                ephemeral=True,
            )
            return
    elif position < 1 or position > len(upcoming):
        await interaction.response.send_message(
            f"No track at position **{position}**.",
            ephemeral=True,
        )
        return

    try:
        removed = await deps.player.remove_at(guild, position)
    except ValueError:
        if position == 1 and current is None:
            await interaction.response.send_message(_NOTHING_PLAYING, ephemeral=True)
            return
        await interaction.response.send_message(
            f"No track at position **{position}**.",
            ephemeral=True,
        )
        return

    if position == 1 and current is not None:
        await interaction.response.send_message(f"Skipped **{removed.title}**.")
    else:
        await interaction.response.send_message(f"Removed **{removed.title}** from the queue.")


async def handle_clear(interaction: discord.Interaction, deps: CommandDeps) -> None:
    """Clear the upcoming queue without stopping playback."""
    guild = interaction.guild
    if guild is None:
        return

    count = await deps.player.clear_queue(guild)
    if count == 0:
        await interaction.response.send_message("Queue is already empty.")
    else:
        label = "track" if count == 1 else "tracks"
        await interaction.response.send_message(f"Cleared **{count}** {label}.")


def register_queue(tree: app_commands.CommandTree, deps: CommandDeps) -> None:
    """Register queue slash commands on the command tree."""

    @tree.command(name="queue", description="Show the current queue")
    async def queue(interaction: discord.Interaction) -> None:
        await handle_queue(interaction, deps)

    @tree.command(name="nowplaying", description="Show the currently playing track")
    async def nowplaying(interaction: discord.Interaction) -> None:
        await handle_nowplaying(interaction, deps)

    @tree.command(name="remove", description="Remove a track from the queue by position")
    @app_commands.describe(
        position="1 = now playing, 2–31 = upcoming tracks (see /queue)",
    )
    async def remove(
        interaction: discord.Interaction,
        position: app_commands.Range[int, 1, QUEUE_LIMIT + 1],
    ) -> None:
        await handle_remove(interaction, position, deps)

    @tree.command(name="clear", description="Clear the queue but keep the current song playing")
    async def clear(interaction: discord.Interaction) -> None:
        await handle_clear(interaction, deps)
