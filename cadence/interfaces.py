"""Protocols and transient types shared across Cadence modules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import discord

from cadence.state import Track

__all__ = ["AudioSource", "Player", "ResolvedTrack"]


@dataclass(frozen=True, slots=True)
class ResolvedTrack:
    """Transient extraction result with a short-lived stream URL."""

    title: str
    webpage_url: str
    stream_url: str
    duration: int | None = None


@runtime_checkable
class AudioSource(Protocol):
    """Resolves search queries and webpage URLs into playable tracks."""

    async def fetch(self, query: str, *, is_url: bool) -> ResolvedTrack:
        """Resolve a search query or URL into track metadata and a stream URL."""
        ...

    async def resolve(self, webpage_url: str) -> ResolvedTrack:
        """Re-resolve a webpage URL into a fresh stream URL."""
        ...


@runtime_checkable
class Player(Protocol):
    """Manages per-guild playback queue and voice controls."""

    async def enqueue(self, guild: discord.Guild, track: Track) -> None:
        """Append a track to the guild queue."""
        ...

    async def clear_queue(self, guild: discord.Guild) -> int:
        """Clear upcoming tracks without stopping the current song. Returns count removed."""
        ...

    def reset_lineup(self, guild: discord.Guild) -> None:
        """Clear the queue, disable loop, and reset the current track."""
        ...

    async def remove_at(self, guild: discord.Guild, position: int) -> Track:
        """Remove a track by queue position (0 = now playing, 1+ = upcoming)."""
        ...

    async def interrupt(self, guild: discord.Guild) -> bool:
        """Clear queue, disable loop, and stop playback. Returns True if voice was active."""
        ...

    async def play_next(self, guild: discord.Guild, *, announce: bool = True) -> None:
        """Play the next track for a guild.

        When ``announce`` is False, skip the text-channel "now playing" post
        (used when ``/play`` already replies via interaction followup).
        """
        ...

    async def skip(self, guild: discord.Guild) -> None:
        """Skip the current track and advance."""
        ...

    async def pause(self, guild: discord.Guild) -> None:
        """Pause playback if active."""
        ...

    async def resume(self, guild: discord.Guild) -> None:
        """Resume playback if paused."""
        ...

    async def stop(self, guild: discord.Guild) -> None:
        """Stop playback, clear state, and disconnect."""
        ...

    def set_loop(self, guild: discord.Guild, *, enabled: bool) -> None:
        """Set whether the current track should loop."""
        ...

    def set_volume(self, guild: discord.Guild, level: int) -> None:
        """Set playback volume for a guild (0–100)."""
        ...

    def snapshot(self, guild: discord.Guild) -> tuple[Track | None, list[Track]]:
        """Return the current track and a copy of upcoming queue items."""
        ...
