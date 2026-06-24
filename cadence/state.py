"""In-memory domain models and per-guild state."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import discord

__all__ = ["GuildState", "StateStore", "Track"]


@dataclass(frozen=True, slots=True)
class Track:
    """Immutable queued track. Stores webpage URL, not stream URL."""

    title: str
    webpage_url: str
    requested_by: int
    duration: int | None = None


@dataclass(slots=True)
class GuildState:
    """Mutable per-guild playback state."""

    queue: deque[Track] = field(default_factory=deque)
    current: Track | None = None
    loop: bool = False
    volume: int = 50
    text_channel: discord.abc.Messageable | None = None
    voice_source: discord.PCMVolumeTransformer[discord.AudioSource] | None = None


@dataclass(slots=True)
class StateStore:
    """Registry of per-guild state, keyed by guild ID."""

    default_volume: int = 50
    _states: dict[int, GuildState] = field(default_factory=dict)

    def get(self, guild_id: int) -> GuildState:
        """Return guild state, creating a new entry on first access."""
        if guild_id not in self._states:
            self._states[guild_id] = GuildState(volume=self.default_volume)
        return self._states[guild_id]

    def discard(self, guild_id: int) -> None:
        """Remove state for a guild."""
        self._states.pop(guild_id, None)
