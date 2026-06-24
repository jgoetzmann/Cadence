"""Discord client construction and command sync."""

from __future__ import annotations

import logging

import discord
from discord import app_commands

from cadence.config import Settings

__all__ = ["build_client", "sync_commands"]

log = logging.getLogger(__name__)


def build_client(settings: Settings) -> tuple[discord.Client, app_commands.CommandTree]:
    """Build a Discord client and command tree with default intents."""
    _ = settings  # reserved for future client configuration
    intents = discord.Intents.default()
    intents.voice_states = True
    client = discord.Client(intents=intents)
    tree = app_commands.CommandTree(client)
    return client, tree


async def sync_commands(tree: app_commands.CommandTree, settings: Settings) -> None:
    """Sync slash commands globally or to a single guild for fast iteration."""
    if settings.guild_id is not None:
        guild = discord.Object(id=settings.guild_id)
        tree.copy_global_to(guild=guild)
        await tree.sync(guild=guild)
        log.info("Synced commands to guild %s", settings.guild_id)
    else:
        await tree.sync()
        log.info("Synced commands globally")
