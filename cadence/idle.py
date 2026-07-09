"""Idle auto-disconnect manager."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, cast

import discord

from cadence.state import StateStore

if TYPE_CHECKING:
    from cadence.player import Player

__all__ = ["IdleManager", "TICK_INTERVAL_SECONDS"]

log = logging.getLogger(__name__)

TICK_INTERVAL_SECONDS = 30


class IdleManager:
    """Tracks guild activity and disconnects after idle timeouts."""

    def __init__(
        self,
        client: discord.Client,
        store: StateStore,
        player: Player | None = None,
        *,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client
        self._store = store
        self._player = player
        self._monotonic = monotonic
        self._task: asyncio.Task[None] | None = None

    def set_player(self, player: Player) -> None:
        """Attach the player used for idle disconnects."""
        self._player = player

    def record_command(self, guild_id: int) -> None:
        """Record that a slash command was used in the guild."""
        self._store.get(guild_id).last_command_at = self._monotonic()

    def record_song_started(self, guild_id: int) -> None:
        """Record that audio playback started in the guild."""
        self._store.get(guild_id).last_song_started_at = self._monotonic()

    async def run(self) -> None:
        """Run the periodic idle check loop until cancelled."""
        try:
            while True:
                await asyncio.sleep(TICK_INTERVAL_SECONDS)
                await self.tick()
        except asyncio.CancelledError:
            raise

    def start(self) -> None:
        """Start the background idle check task."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self.run())

    async def stop(self) -> None:
        """Cancel the background idle check task."""
        if self._task is not None and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        self._task = None

    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """Update alone-in-channel tracking for the bot's voice channel."""
        if self._client.user is None:
            return

        voice_client = member.guild.voice_client
        if voice_client is None or voice_client.channel is None:
            return

        channel = voice_client.channel
        if before.channel != channel and after.channel != channel:
            return

        humans = self._human_count(channel)
        state = self._store.get(member.guild.id)
        if humans == 0:
            if state.alone_since is None:
                state.alone_since = self._monotonic()
        else:
            state.alone_since = None

    async def tick(self) -> None:
        """Check all connected guilds for idle disconnect conditions."""
        if self._player is None:
            return
        now = self._monotonic()
        for voice_client in list(self._client.voice_clients):
            guild = voice_client.guild
            state = self._store.get(guild.id)
            if await self._should_disconnect(
                state, cast(discord.VoiceClient, voice_client), now
            ):
                log.info("Idle timeout reached for guild %s; disconnecting", guild.id)
                await self._player.stop(guild)

    async def _should_disconnect(
        self,
        state: object,
        voice_client: discord.VoiceClient,
        now: float,
    ) -> bool:
        from cadence.state import GuildState

        if not isinstance(state, GuildState):
            return False

        idle_seconds = state.idle_minutes * 60

        if state.alone_since is not None and (now - state.alone_since) >= idle_seconds:
            return True

        if state.last_song_started_at is None or state.last_command_at is None:
            return False

        song_idle = (now - state.last_song_started_at) >= idle_seconds
        command_idle = (now - state.last_command_at) >= idle_seconds
        if not (song_idle and command_idle):
            return False

        return not self._is_audio_active(voice_client)

    @staticmethod
    def _is_audio_active(voice_client: discord.VoiceClient) -> bool:
        """True while audio is playing or paused (not between tracks)."""
        return voice_client.is_playing() or voice_client.is_paused()

    @staticmethod
    def _human_count(channel: discord.VoiceChannel) -> int:
        return sum(1 for member in channel.members if not member.bot)
