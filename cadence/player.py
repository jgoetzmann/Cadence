"""Playback engine — queue management and voice controls."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import cast

import discord

from cadence.interfaces import AudioSource
from cadence.state import StateStore, Track

__all__ = ["FFMPEG_OPTS", "Player"]

log = logging.getLogger(__name__)

FFMPEG_OPTS: dict[str, str] = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


def _clamp_volume(level: int) -> int:
    """Clamp a volume level to the 0–100 range."""
    return max(0, min(100, level))


class Player:
    """Concrete playback engine implementing the Player protocol."""

    def __init__(
        self,
        client: discord.Client,
        store: StateStore,
        source: AudioSource,
    ) -> None:
        self._client = client
        self._store = store
        self._source = source

    async def enqueue(self, guild: discord.Guild, track: Track) -> None:
        """Append a track to the guild queue."""
        self._store.get(guild.id).queue.append(track)

    async def play_next(self, guild: discord.Guild, *, announce: bool = True) -> None:
        """Play the next track for a guild."""
        state = self._store.get(guild.id)
        voice_client = guild.voice_client
        if voice_client is None:
            return
        vc = cast(discord.VoiceClient, voice_client)

        fresh = False
        if state.loop and state.current is not None:
            track = state.current
        elif state.queue:
            track = state.queue.popleft()
            state.current = track
            fresh = True
        else:
            state.current = None
            state.voice_source = None
            return

        try:
            resolved = await self._source.resolve(track.webpage_url)
        except Exception:
            log.exception("Failed to resolve stream for %s", track.webpage_url)
            if state.text_channel is not None:
                await state.text_channel.send(
                    f"⚠️ Skipping **{track.title}** (couldn't load audio)."
                )
            state.current = None
            state.voice_source = None
            await self.play_next(guild)
            return

        voice_source = self._build_voice_source(resolved.stream_url, state.volume)
        state.voice_source = voice_source
        vc.play(voice_source, after=self._make_after(guild))

        if fresh and announce and state.text_channel is not None:
            await state.text_channel.send(f"▶️ Now playing: **{track.title}**")

    async def skip(self, guild: discord.Guild) -> None:
        """Skip the current track and advance."""
        state = self._store.get(guild.id)
        voice_client = guild.voice_client
        if voice_client is None:
            return
        vc = cast(discord.VoiceClient, voice_client)
        state.current = None
        vc.stop()

    async def pause(self, guild: discord.Guild) -> None:
        """Pause playback if active."""
        voice_client = guild.voice_client
        if voice_client is None:
            return
        vc = cast(discord.VoiceClient, voice_client)
        if vc.is_playing():
            vc.pause()

    async def resume(self, guild: discord.Guild) -> None:
        """Resume playback if paused."""
        voice_client = guild.voice_client
        if voice_client is None:
            return
        vc = cast(discord.VoiceClient, voice_client)
        if vc.is_paused():
            vc.resume()

    async def stop(self, guild: discord.Guild) -> None:
        """Stop playback, clear state, and disconnect."""
        state = self._store.get(guild.id)
        state.queue.clear()
        state.current = None
        state.loop = False
        state.voice_source = None
        voice_client = guild.voice_client
        if voice_client is not None:
            vc = cast(discord.VoiceClient, voice_client)
            vc.stop()
            await vc.disconnect(force=False)

    def set_loop(self, guild: discord.Guild, *, enabled: bool) -> None:
        """Set whether the current track should loop."""
        self._store.get(guild.id).loop = enabled

    def set_volume(self, guild: discord.Guild, level: int) -> None:
        """Set playback volume for a guild (0–100)."""
        state = self._store.get(guild.id)
        clamped = _clamp_volume(level)
        state.volume = clamped
        if state.voice_source is not None:
            state.voice_source.volume = clamped / 100

    def snapshot(self, guild: discord.Guild) -> tuple[Track | None, list[Track]]:
        """Return the current track and a copy of upcoming queue items."""
        state = self._store.get(guild.id)
        return state.current, list(state.queue)

    def _build_voice_source(
        self,
        stream_url: str,
        volume: int,
    ) -> discord.PCMVolumeTransformer[discord.AudioSource]:
        """Build an FFmpeg PCM source wrapped in a volume transformer."""
        pcm = discord.FFmpegPCMAudio(
            stream_url,
            before_options=FFMPEG_OPTS["before_options"],
            options=FFMPEG_OPTS["options"],
        )
        return discord.PCMVolumeTransformer(pcm, volume=volume / 100)

    def _make_after(self, guild: discord.Guild) -> Callable[[Exception | None], None]:
        """Return the FFmpeg after-callback that schedules the next track."""

        def _after(error: Exception | None) -> None:
            if error is not None:
                log.error("Playback error: %s", error, exc_info=error)
            asyncio.run_coroutine_threadsafe(self.play_next(guild), self._client.loop)

        return _after
