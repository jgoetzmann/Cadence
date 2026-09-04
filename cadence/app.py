"""Composition root — wires concrete implementations together."""

from __future__ import annotations

import logging

import discord
from discord import app_commands

from cadence.client import build_client, sync_commands
from cadence.commands import register
from cadence.commands.deps import CommandDeps
from cadence.config import Settings
from cadence.idle import IdleManager
from cadence.logging_setup import configure_logging
from cadence.player import Player
from cadence.sources.youtube import YouTubeSource, YtDlpConfig
from cadence.state import StateStore

__all__ = ["build_app"]

log = logging.getLogger(__name__)


def build_app(settings: Settings | None = None) -> discord.Client:
    """Build a fully wired Discord client with slash commands and playback."""
    resolved = settings or Settings.load()
    configure_logging(resolved.log_level)
    client, tree = build_client(resolved)

    store = StateStore(default_volume=resolved.default_volume)
    source = YouTubeSource(
        YtDlpConfig(
            cookie_file=resolved.ytdlp_cookie_file,
            proxy=resolved.ytdlp_proxy,
            impersonate=resolved.ytdlp_impersonate,
        ),
    )
    idle_manager = IdleManager(client, store)
    player = Player(client, store, source, on_song_started=idle_manager.record_song_started)
    idle_manager.set_player(player)
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
        idle_manager.start()
        if client.user is not None:
            log.info("Logged in as %s (id: %s)", client.user, client.user.id)

    @client.event
    async def on_voice_state_update(
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if (
            client.user is not None
            and member.id == client.user.id
            and before.channel is not None
            and after.channel is None
        ):
            player.clear_session(member.guild)
        await idle_manager.on_voice_state_update(member, before, after)

    @client.event
    async def on_interaction(interaction: discord.Interaction) -> None:
        if (
            interaction.type == discord.InteractionType.application_command
            and interaction.guild is not None
        ):
            idle_manager.record_command(interaction.guild.id)

    original_close = client.close

    async def close() -> None:
        await idle_manager.stop()
        for voice_client in list(client.voice_clients):
            await voice_client.disconnect(force=True)
        await original_close()

    client.close = close  # type: ignore[method-assign]

    return client
