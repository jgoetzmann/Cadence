"""Playback engine — queue management and voice controls."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import cast

import discord

from cadence.interfaces import AudioSource
from cadence.state import QUEUE_LIMIT, StateStore, Track

__all__ = ["FFMPEG_OPTS", "Player", "QueueFullError"]


class QueueFullError(Exception):
    """Raised when the guild queue has reached QUEUE_LIMIT."""

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
        state = self._store.get(guild.id)
        if len(state.queue) >= QUEUE_LIMIT:
            raise QueueFullError
        state.queue.append(track)

    def reset_lineup(self, guild: discord.Guild) -> None:
        """Clear the queue, disable loop, and reset the current track."""
        state = self._store.get(guild.id)
        state.queue.clear()
        state.loop = False
        state.current = None

    async def clear_queue(self, guild: discord.Guild) -> int:
        """Clear upcoming tracks without stopping the current song. Returns count removed."""
        state = self._store.get(guild.id)
        count = len(state.queue)
        state.queue.clear()
        return count

    async def remove_at(self, guild: discord.Guild, position: int) -> Track:
        """Remove a track by 1-based display position (see /queue)."""
        state = self._store.get(guild.id)
        if position < 1:
            msg = f"Invalid queue position: {position}"
            raise ValueError(msg)

        if state.current is not None:
            if position == 1:
                track = state.current
                state.current = None
                voice_client = guild.voice_client
                if voice_client is not None:
                    cast(discord.VoiceClient, voice_client).stop()
                return track
            queue_index = position - 2
            max_position = 1 + len(state.queue)
        else:
            queue_index = position - 1
            max_position = len(state.queue)

        if position > max_position or queue_index < 0:
            msg = f"No track at position {position}"
            raise ValueError(msg)
        if state.current is not None and position > QUEUE_LIMIT + 1:
            msg = f"Invalid queue position: {position}"
            raise ValueError(msg)

        queue_list = list(state.queue)
        removed = queue_list.pop(queue_index)
        state.queue.clear()
        state.queue.extend(queue_list)
        return removed

    async def interrupt(self, guild: discord.Guild) -> bool:
        """Clear queue, disable loop, and stop playback. Returns True if voice was active."""
        self.reset_lineup(guild)
        voice_client = guild.voice_client
        if voice_client is None:
            return False
        vc = cast(discord.VoiceClient, voice_client)
        if vc.is_playing() or vc.is_paused():
            vc.stop()
            return True
        return False

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
