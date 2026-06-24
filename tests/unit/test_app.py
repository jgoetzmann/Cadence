"""Tests for cadence.app."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import discord
import pytest
from discord import app_commands

from cadence.app import build_app
from cadence.commands import COMMAND_NAMES, register
from cadence.config import Settings
from cadence.player import Player
from cadence.sources.youtube import YouTubeSource
from tests.fakes import FakeGuild, FakeInteraction


def test_build_app_returns_client_and_configures_logging() -> None:
    settings = Settings(
        token="test-token",
        guild_id=None,
        log_level=logging.DEBUG,
        default_volume=50,
    )
    with patch("cadence.app.configure_logging") as configure_logging:
        client = build_app(settings)
    configure_logging.assert_called_once_with(logging.DEBUG)
    assert isinstance(client, discord.Client)


@pytest.mark.asyncio
async def test_build_app_on_ready_syncs_commands() -> None:
    settings = Settings(
        token="test-token",
        guild_id=123,
        log_level=logging.INFO,
        default_volume=50,
    )
    with (
        patch("cadence.app.configure_logging"),
        patch("cadence.app.sync_commands", new_callable=AsyncMock) as sync_commands,
    ):
        client = build_app(settings)
        await client.on_ready()

    sync_commands.assert_awaited_once()


def test_build_app_wires_thirteen_commands_and_youtube_player() -> None:
    settings = Settings(
        token="test-token",
        guild_id=None,
        log_level=logging.INFO,
        default_volume=40,
    )
    with (
        patch("cadence.app.configure_logging"),
        patch("cadence.app.register", wraps=register) as mock_register,
    ):
        client = build_app(settings)

    mock_register.assert_called_once()
    tree, deps = mock_register.call_args.args
    names = {command.name for command in tree.get_commands()}
    assert names == set(COMMAND_NAMES)
    assert len(tree.get_commands()) == 13
    assert isinstance(deps.source, YouTubeSource)
    assert isinstance(deps.player, Player)
    assert deps.player._source is deps.source
    assert deps.player._client is client
    assert deps.store.default_volume == 40


@pytest.mark.asyncio
async def test_build_app_close_disconnects_voice_clients() -> None:
    settings = Settings(
        token="test-token",
        guild_id=None,
        log_level=logging.INFO,
        default_volume=50,
    )
    with patch("cadence.app.configure_logging"):
        client = build_app(settings)

    vc_one = MagicMock()
    vc_one.disconnect = AsyncMock()
    vc_two = MagicMock()
    vc_two.disconnect = AsyncMock()

    with patch.object(type(client), "voice_clients", new_callable=PropertyMock) as voice_clients:
        voice_clients.return_value = [vc_one, vc_two]
        await client.close()

    vc_one.disconnect.assert_awaited_once_with(force=True)
    vc_two.disconnect.assert_awaited_once_with(force=True)


@pytest.mark.asyncio
async def test_build_app_tree_error_sends_generic_message() -> None:
    settings = Settings(
        token="test-token",
        guild_id=None,
        log_level=logging.INFO,
        default_volume=50,
    )
    with (
        patch("cadence.app.configure_logging"),
        patch("cadence.app.register", wraps=register) as mock_register,
    ):
        build_app(settings)

    tree = mock_register.call_args.args[0]
    assert tree.on_error is not None

    interaction = FakeInteraction(guild=FakeGuild(id=1))
    error = app_commands.CommandInvokeError(MagicMock(), RuntimeError("boom"))

    await tree.on_error(interaction, error)

    assert len(interaction.responses) == 1
    assert interaction.responses[0].content == "Something went wrong."
    assert interaction.responses[0].ephemeral is False


@pytest.mark.asyncio
async def test_build_app_tree_error_uses_followup_when_response_done() -> None:
    settings = Settings(
        token="test-token",
        guild_id=None,
        log_level=logging.INFO,
        default_volume=50,
    )
    with (
        patch("cadence.app.configure_logging"),
        patch("cadence.app.register", wraps=register) as mock_register,
    ):
        build_app(settings)

    tree = mock_register.call_args.args[0]
    interaction = FakeInteraction(guild=FakeGuild(id=1))
    await interaction.response.defer()
    error = app_commands.CommandInvokeError(MagicMock(), RuntimeError("boom"))

    await tree.on_error(interaction, error)

    assert len(interaction.followups) == 1
    assert interaction.followups[0].content == "Something went wrong."
    assert interaction.followups[0].ephemeral is False
