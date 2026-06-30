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


def test_build_app_wires_sixteen_commands_and_youtube_player() -> None:
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
    assert len(tree.get_commands()) == 16
    assert isinstance(deps.source, YouTubeSource)
    assert isinstance(deps.player, Player)
    assert deps.player._source is deps.source
    assert deps.player._client is client
    assert deps.store.default_volume == 40


@pytest.mark.asyncio
async def test_build_app_on_ready_starts_idle_manager() -> None:
    settings = Settings(
        token="test-token",
        guild_id=123,
        log_level=logging.INFO,
        default_volume=50,
    )
    with (
        patch("cadence.app.configure_logging"),
        patch("cadence.app.sync_commands", new_callable=AsyncMock),
        patch("cadence.app.IdleManager") as idle_cls,
    ):
        client = build_app(settings)
        idle = idle_cls.return_value
        await client.on_ready()

    idle.start.assert_called_once()
    idle.set_player.assert_called_once()


@pytest.mark.asyncio
async def test_build_app_on_ready_logs_when_user_present() -> None:
    settings = Settings(
        token="test-token",
        guild_id=123,
        log_level=logging.INFO,
        default_volume=50,
    )
    with (
        patch("cadence.app.configure_logging"),
        patch("cadence.app.sync_commands", new_callable=AsyncMock),
        patch("cadence.app.IdleManager"),
        patch("cadence.app.log") as app_log,
    ):
        client = build_app(settings)
        with patch.object(type(client), "user", new_callable=PropertyMock) as user_prop:
            user_prop.return_value = MagicMock(id=123)
            await client.on_ready()

    app_log.info.assert_called_once()


@pytest.mark.asyncio
async def test_build_app_on_interaction_records_slash_commands() -> None:
    settings = Settings(
        token="test-token",
        guild_id=None,
        log_level=logging.INFO,
        default_volume=50,
    )
    with (
        patch("cadence.app.configure_logging"),
        patch("cadence.app.IdleManager") as idle_cls,
    ):
        client = build_app(settings)
        idle = idle_cls.return_value

    interaction = MagicMock()
    interaction.type = discord.InteractionType.application_command
    interaction.guild = MagicMock(id=42)

    await client.on_interaction(interaction)

    idle.record_command.assert_called_once_with(42)


@pytest.mark.asyncio
async def test_build_app_close_stops_idle_manager() -> None:
    settings = Settings(
        token="test-token",
        guild_id=None,
        log_level=logging.INFO,
        default_volume=50,
    )
    with (
        patch("cadence.app.configure_logging"),
        patch("cadence.app.IdleManager") as idle_cls,
    ):
        client = build_app(settings)
        idle = idle_cls.return_value
        idle.stop = AsyncMock()

    with patch.object(type(client), "voice_clients", new_callable=PropertyMock) as voice_clients:
        voice_clients.return_value = []
        await client.close()

    idle.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_build_app_on_voice_state_update_clears_session_when_bot_disconnects() -> None:
    settings = Settings(
        token="test-token",
        guild_id=None,
        log_level=logging.INFO,
        default_volume=50,
    )
    with (
        patch("cadence.app.configure_logging"),
        patch("cadence.app.IdleManager") as idle_cls,
        patch("cadence.app.Player") as player_cls,
    ):
        client = build_app(settings)
        player = player_cls.return_value
        idle = idle_cls.return_value
        idle.on_voice_state_update = AsyncMock()

    guild = MagicMock()
    member = MagicMock(id=7, guild=guild)
    before = MagicMock(channel=MagicMock())
    after = MagicMock(channel=None)
    with patch.object(type(client), "user", new_callable=PropertyMock) as user_prop:
        user_prop.return_value = MagicMock(id=7)
        await client.on_voice_state_update(member, before, after)

    player.clear_session.assert_called_once_with(guild)
    idle.on_voice_state_update.assert_awaited_once_with(member, before, after)


@pytest.mark.asyncio
async def test_build_app_on_voice_state_update_keeps_session_when_bot_moves() -> None:
    settings = Settings(
        token="test-token",
        guild_id=None,
        log_level=logging.INFO,
        default_volume=50,
    )
    with (
        patch("cadence.app.configure_logging"),
        patch("cadence.app.IdleManager") as idle_cls,
        patch("cadence.app.Player") as player_cls,
    ):
        client = build_app(settings)
        player = player_cls.return_value
        idle_cls.return_value.on_voice_state_update = AsyncMock()

    guild = MagicMock()
    member = MagicMock(id=7, guild=guild)
    before = MagicMock(channel=MagicMock())
    after = MagicMock(channel=MagicMock())
    with patch.object(type(client), "user", new_callable=PropertyMock) as user_prop:
        user_prop.return_value = MagicMock(id=7)
        await client.on_voice_state_update(member, before, after)

    player.clear_session.assert_not_called()


@pytest.mark.asyncio
async def test_build_app_on_voice_state_update_delegates_to_idle_manager() -> None:
    settings = Settings(
        token="test-token",
        guild_id=None,
        log_level=logging.INFO,
        default_volume=50,
    )
    with (
        patch("cadence.app.configure_logging"),
        patch("cadence.app.IdleManager") as idle_cls,
    ):
        client = build_app(settings)
        idle = idle_cls.return_value
        idle.on_voice_state_update = AsyncMock()

    member = MagicMock()
    before = MagicMock()
    after = MagicMock()
    await client.on_voice_state_update(member, before, after)

    idle.on_voice_state_update.assert_awaited_once_with(member, before, after)


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
