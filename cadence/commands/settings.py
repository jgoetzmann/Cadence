"""Settings slash commands: /loop, /volume."""

from __future__ import annotations

import discord
from discord import app_commands

from cadence.commands.deps import CommandDeps

__all__ = ["handle_loop", "handle_volume", "register_settings"]

_VOLUME_RANGE_ERROR = "Volume must be between 0 and 100."


async def handle_loop(interaction: discord.Interaction, deps: CommandDeps) -> None:
    """Toggle single-track loop for the guild."""
    guild = interaction.guild
    if guild is None:
        return

    state = deps.store.get(guild.id)
    enabled = not state.loop
    deps.player.set_loop(guild, enabled=enabled)

    if enabled:
        await interaction.response.send_message("🔁 Loop enabled.")
    else:
        await interaction.response.send_message("🔁 Loop disabled.")


async def handle_volume(
    interaction: discord.Interaction,
    level: int,
    deps: CommandDeps,
) -> None:
    """Set playback volume for the guild."""
    guild = interaction.guild
    if guild is None:
        return

    if not 0 <= level <= 100:
        await interaction.response.send_message(_VOLUME_RANGE_ERROR, ephemeral=True)
        return

    deps.player.set_volume(guild, level)
    await interaction.response.send_message(f"🔊 Volume set to **{level}**.")


def register_settings(tree: app_commands.CommandTree, deps: CommandDeps) -> None:
    """Register settings slash commands on the command tree."""

    @tree.command(name="loop", description="Toggle looping the current song")
    async def loop(interaction: discord.Interaction) -> None:
        await handle_loop(interaction, deps)

    @tree.command(name="volume", description="Set playback volume (0-100)")
    @app_commands.describe(level="Volume level from 0 to 100")
    async def volume(interaction: discord.Interaction, level: int) -> None:
        await handle_volume(interaction, level, deps)
