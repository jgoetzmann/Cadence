"""Composition root — wires concrete implementations together."""

from __future__ import annotations

import logging

import discord
from discord import app_commands

from cadence.client import build_client, sync_commands
from cadence.commands import register
from cadence.commands.deps import CommandDeps
from cadence.config import Settings
from cadence.logging_setup import configure_logging
from cadence.player import Player
from cadence.sources.youtube import YouTubeSource
from cadence.state import StateStore

__all__ = ["build_app"]

log = logging.getLogger(__name__)


def build_app(settings: Settings | None = None) -> discord.Client:
    """Build a fully wired Discord client with slash commands and playback."""
    resolved = settings or Settings.load()
    configure_logging(resolved.log_level)
    client, tree = build_client(resolved)

    store = StateStore(default_volume=resolved.default_volume)
    source = YouTubeSource()
    player = Player(client, store, source)
    deps = CommandDeps(player=player, source=source, store=store)
    register(tree, deps)

    @tree.error
    async def on_app_command_error(
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        underlying = (
            error.original
            if isinstance(error, app_commands.CommandInvokeError)
            else error
        )
        log.exception("Unhandled command error", exc_info=underlying)
        message = "Something went wrong."
        if interaction.response.is_done():
            await interaction.followup.send(message)
        else:
            await interaction.response.send_message(message)

    @client.event
    async def on_ready() -> None:
        await sync_commands(tree, resolved)
        if client.user is not None:
            log.info("Logged in as %s (id: %s)", client.user, client.user.id)

    original_close = client.close

    async def close() -> None:
        for voice_client in list(client.voice_clients):
            await voice_client.disconnect(force=True)
        await original_close()

    client.close = close  # type: ignore[method-assign]

    return client
