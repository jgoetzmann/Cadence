"""Settings slash commands: /loop, /volume, /idle."""

from __future__ import annotations

import discord
from discord import app_commands

from cadence.commands.deps import CommandDeps
from cadence.state import LOOP_MODE_LABELS, LoopMode

__all__ = ["handle_idle", "handle_loop", "handle_volume", "register_settings"]

_VOLUME_RANGE_ERROR = "Volume must be between 0 and 100."


def _loop_mode_from_choice(choice: app_commands.Choice[str]) -> LoopMode:
    return LoopMode(choice.value)


async def handle_loop(
    interaction: discord.Interaction,
    mode: LoopMode,
    deps: CommandDeps,
) -> None:
    """Set loop mode for the guild."""
    guild = interaction.guild
    if guild is None:
        return

    deps.player.set_loop_mode(guild, mode)
    label = LOOP_MODE_LABELS[mode]
    await interaction.response.send_message(f"Loop set to **{label}**.")


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


async def handle_idle(
    interaction: discord.Interaction,
    minutes: int,
    deps: CommandDeps,
) -> None:
    """Set auto-disconnect idle timeout for the guild."""
    guild = interaction.guild
    if guild is None:
        return

    deps.store.get(guild.id).idle_minutes = minutes
    await interaction.response.send_message(
        f"Auto-disconnect idle time set to **{minutes}** minutes."
    )


def register_settings(tree: app_commands.CommandTree, deps: CommandDeps) -> None:
    """Register settings slash commands on the command tree."""

    @tree.command(name="loop", description="Set loop mode (default: off)")
    @app_commands.describe(mode="Loop behavior for playback")
    @app_commands.choices(
        mode=[
            app_commands.Choice(name="Off", value=LoopMode.OFF.value),
            app_commands.Choice(name="Current song", value=LoopMode.TRACK.value),
            app_commands.Choice(name="Queue", value=LoopMode.QUEUE.value),
            app_commands.Choice(name="Queue shuffle", value=LoopMode.QUEUE_SHUFFLE.value),
        ]
    )
    async def loop(
        interaction: discord.Interaction,
        mode: app_commands.Choice[str],
    ) -> None:
        await handle_loop(interaction, _loop_mode_from_choice(mode), deps)

    @tree.command(name="volume", description="Set playback volume (0-100)")
    @app_commands.describe(level="Volume level from 0 to 100")
    async def volume(interaction: discord.Interaction, level: int) -> None:
        await handle_volume(interaction, level, deps)

    @tree.command(name="idle", description="Set auto-disconnect idle timeout in minutes")
    @app_commands.describe(minutes="1–1500 minutes (default 10)")
    async def idle(
        interaction: discord.Interaction,
        minutes: app_commands.Range[int, 1, 1500],
    ) -> None:
        await handle_idle(interaction, minutes, deps)
