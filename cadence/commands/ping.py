"""Ping slash command: /ping."""

from __future__ import annotations

import discord
from discord import app_commands

from cadence import __version__
from cadence.commands.deps import CommandDeps

__all__ = ["handle_ping", "register_ping"]


async def handle_ping(interaction: discord.Interaction, deps: CommandDeps) -> None:
    """Reply with online status, version, and websocket latency."""
    _ = deps
    latency_ms = round(interaction.client.latency * 1000)
    await interaction.response.send_message(
        f"Pong! Cadence is online (v{__version__}) — {latency_ms}ms"
    )


def register_ping(tree: app_commands.CommandTree, deps: CommandDeps) -> None:
    """Register the /ping slash command on the command tree."""

    @tree.command(name="ping", description="Check if Cadence is online")
    async def ping_command(interaction: discord.Interaction) -> None:
        await handle_ping(interaction, deps)
