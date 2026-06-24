"""Unit tests for cadence.idle."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import cast
from unittest.mock import patch

import discord
import pytest

from cadence.idle import TICK_INTERVAL_SECONDS, IdleManager
from cadence.state import StateStore
from tests.fakes import FakeGuild, FakeMember, FakeVoiceChannel, FakeVoiceClient, FakeVoiceState


@dataclass
class FakeClient:
    """Minimal client exposing voice clients and user."""

    voice_clients: list[FakeVoiceClient] = field(default_factory=list)
    user: object | None = field(default_factory=lambda: type("User", (), {"id": 999})())


class RecordingPlayer:
    """Captures stop calls for idle manager tests."""

    def __init__(self) -> None:
        self.stop_calls: list[object] = []

    async def stop(self, guild: object) -> None:
        self.stop_calls.append(guild)


@pytest.fixture
def idle_setup() -> tuple[FakeClient, StateStore, RecordingPlayer, IdleManager]:
    client = FakeClient()
    store = StateStore()
    player = RecordingPlayer()
    clock = {"now": 1000.0}

    def monotonic() -> float:
        return clock["now"]

    manager = IdleManager(
        cast(discord.Client, client),
        store,
        cast(object, player),
        monotonic=monotonic,
    )
    manager._clock = clock  # type: ignore[attr-defined]
    return client, store, player, manager


@pytest.mark.asyncio
async def test_record_command_and_song_started_update_timestamps(
    idle_setup: tuple[FakeClient, StateStore, RecordingPlayer, IdleManager],
) -> None:
    _, store, _, manager = idle_setup
    manager.record_command(1)
    assert store.get(1).last_command_at == 1000.0
    manager.record_song_started(1)
    assert store.get(1).last_song_started_at == 1000.0


@pytest.mark.asyncio
async def test_tick_disconnects_when_song_and_command_idle(
    idle_setup: tuple[FakeClient, StateStore, RecordingPlayer, IdleManager],
) -> None:
    client, store, player, manager = idle_setup
    guild = FakeGuild(id=1)
    channel = FakeVoiceChannel(id=10, guild=guild)
    voice_client = FakeVoiceClient(channel=channel)
    guild.voice_client = voice_client
    client.voice_clients.append(voice_client)

    state = store.get(1)
    state.idle_minutes = 10
    state.last_command_at = 100.0
    state.last_song_started_at = 200.0
    manager._clock["now"] = 1000.0  # type: ignore[attr-defined]

    await manager.tick()

    assert len(player.stop_calls) == 1


@pytest.mark.asyncio
async def test_tick_disconnects_when_alone_too_long(
    idle_setup: tuple[FakeClient, StateStore, RecordingPlayer, IdleManager],
) -> None:
    client, store, player, manager = idle_setup
    guild = FakeGuild(id=2)
    channel = FakeVoiceChannel(id=20, guild=guild)
    voice_client = FakeVoiceClient(channel=channel)
    guild.voice_client = voice_client
    client.voice_clients.append(voice_client)

    state = store.get(2)
    state.idle_minutes = 5
    state.alone_since = 100.0
    manager._clock["now"] = 500.0  # type: ignore[attr-defined]

    await manager.tick()

    assert len(player.stop_calls) == 1


@pytest.mark.asyncio
async def test_tick_skips_when_only_one_idle_signal(
    idle_setup: tuple[FakeClient, StateStore, RecordingPlayer, IdleManager],
) -> None:
    client, store, player, manager = idle_setup
    guild = FakeGuild(id=3)
    channel = FakeVoiceChannel(id=30, guild=guild)
    voice_client = FakeVoiceClient(channel=channel)
    guild.voice_client = voice_client
    client.voice_clients.append(voice_client)

    state = store.get(3)
    state.idle_minutes = 10
    state.last_command_at = 100.0
    state.last_song_started_at = 950.0
    manager._clock["now"] = 1000.0  # type: ignore[attr-defined]

    await manager.tick()

    assert player.stop_calls == []


@pytest.mark.asyncio
async def test_voice_state_update_sets_and_clears_alone_since(
    idle_setup: tuple[FakeClient, StateStore, RecordingPlayer, IdleManager],
) -> None:
    _, store, _, manager = idle_setup
    guild = FakeGuild(id=4)
    channel = FakeVoiceChannel(id=40, guild=guild)
    voice_client = FakeVoiceClient(channel=channel)
    guild.voice_client = voice_client
    bot = FakeMember(id=999, guild=guild, bot=True, voice=FakeVoiceState(channel=channel))
    human = FakeMember(id=42, guild=guild, bot=False, voice=FakeVoiceState(channel=channel))
    channel.members = [bot]

    await manager.on_voice_state_update(
        cast(discord.Member, bot),
        cast(discord.VoiceState, FakeVoiceState(channel=None)),
        cast(discord.VoiceState, FakeVoiceState(channel=channel)),
    )
    assert store.get(4).alone_since == 1000.0

    channel.members = [bot, human]
    await manager.on_voice_state_update(
        cast(discord.Member, human),
        cast(discord.VoiceState, FakeVoiceState(channel=None)),
        cast(discord.VoiceState, FakeVoiceState(channel=channel)),
    )
    assert store.get(4).alone_since is None


@pytest.mark.asyncio
async def test_voice_state_update_noops_without_client_user(
    idle_setup: tuple[FakeClient, StateStore, RecordingPlayer, IdleManager],
) -> None:
    client, store, _, manager = idle_setup
    client.user = None
    guild = FakeGuild(id=7)
    channel = FakeVoiceChannel(id=70, guild=guild)
    guild.voice_client = FakeVoiceClient(channel=channel)
    member = FakeMember(id=42, guild=guild, bot=False, voice=FakeVoiceState(channel=channel))

    await manager.on_voice_state_update(
        cast(discord.Member, member),
        cast(discord.VoiceState, FakeVoiceState(channel=None)),
        cast(discord.VoiceState, FakeVoiceState(channel=channel)),
    )

    assert store.get(7).alone_since is None


@pytest.mark.asyncio
async def test_voice_state_update_noops_without_voice_client(
    idle_setup: tuple[FakeClient, StateStore, RecordingPlayer, IdleManager],
) -> None:
    _, store, _, manager = idle_setup
    guild = FakeGuild(id=8)
    guild.voice_client = None
    member = FakeMember(id=42, guild=guild, bot=False)

    await manager.on_voice_state_update(
        cast(discord.Member, member),
        cast(discord.VoiceState, FakeVoiceState(channel=None)),
        cast(discord.VoiceState, FakeVoiceState(channel=None)),
    )

    assert store.get(8).alone_since is None


@pytest.mark.asyncio
async def test_tick_noops_without_player(
    idle_setup: tuple[FakeClient, StateStore, RecordingPlayer, IdleManager],
) -> None:
    client, store, player, manager = idle_setup
    manager._player = None
    guild = FakeGuild(id=5)
    channel = FakeVoiceChannel(id=50, guild=guild)
    voice_client = FakeVoiceClient(channel=channel)
    client.voice_clients.append(voice_client)
    store.get(5).last_command_at = 0.0
    store.get(5).last_song_started_at = 0.0

    await manager.tick()

    assert player.stop_calls == []


@pytest.mark.asyncio
async def test_voice_state_update_ignores_unrelated_channels(
    idle_setup: tuple[FakeClient, StateStore, RecordingPlayer, IdleManager],
) -> None:
    _, store, _, manager = idle_setup
    guild = FakeGuild(id=6)
    bot_channel = FakeVoiceChannel(id=60, guild=guild)
    other_channel = FakeVoiceChannel(id=61, guild=guild)
    voice_client = FakeVoiceClient(channel=bot_channel)
    guild.voice_client = voice_client
    member = FakeMember(id=42, guild=guild, bot=False)

    await manager.on_voice_state_update(
        cast(discord.Member, member),
        cast(discord.VoiceState, FakeVoiceState(channel=other_channel)),
        cast(discord.VoiceState, FakeVoiceState(channel=other_channel)),
    )

    assert store.get(6).alone_since is None


@pytest.mark.asyncio
async def test_should_disconnect_false_when_activity_incomplete(
    idle_setup: tuple[FakeClient, StateStore, RecordingPlayer, IdleManager],
) -> None:
    _, store, _, manager = idle_setup
    state = store.get(9)
    state.idle_minutes = 10
    state.last_command_at = 100.0

    assert await manager._should_disconnect(state, 1000.0) is False


@pytest.mark.asyncio
async def test_run_propagates_cancellation() -> None:
    client = FakeClient()
    store = StateStore()
    player = RecordingPlayer()
    manager = IdleManager(cast(discord.Client, client), store, cast(object, player))

    with (
        patch("cadence.idle.asyncio.sleep", side_effect=asyncio.CancelledError),
        pytest.raises(asyncio.CancelledError),
    ):
        await manager.run()


def test_tick_interval_constant() -> None:
    assert TICK_INTERVAL_SECONDS == 30


@pytest.mark.asyncio
async def test_idle_manager_start_and_stop_task() -> None:
    client = FakeClient()
    store = StateStore()
    player = RecordingPlayer()
    manager = IdleManager(cast(discord.Client, client), store, cast(object, player))

    manager.start()
    assert manager._task is not None
    await manager.stop()
    assert manager._task is None
