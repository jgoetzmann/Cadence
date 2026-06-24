"""In-memory domain models and per-guild state."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum

import discord

QUEUE_LIMIT = 30
DEFAULT_IDLE_MINUTES = 10
MIN_IDLE_MINUTES = 1
MAX_IDLE_MINUTES = 1500

__all__ = [
    "DEFAULT_IDLE_MINUTES",
    "MAX_IDLE_MINUTES",
    "MIN_IDLE_MINUTES",
    "QUEUE_LIMIT",
    "GuildState",
    "LoopMode",
    "StateStore",
    "Track",
]


class LoopMode(Enum):
    """Per-guild loop behavior."""

    OFF = "off"
    TRACK = "track"
    QUEUE = "queue"
    QUEUE_SHUFFLE = "queue_shuffle"


LOOP_MODE_LABELS: dict[LoopMode, str] = {
    LoopMode.OFF: "Off",
    LoopMode.TRACK: "Current song",
    LoopMode.QUEUE: "Queue",
    LoopMode.QUEUE_SHUFFLE: "Queue shuffle",
}


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
    loop_mode: LoopMode = LoopMode.OFF
    volume: int = 50
    text_channel: discord.abc.Messageable | None = None
    voice_source: discord.PCMVolumeTransformer[discord.AudioSource] | None = None
    idle_minutes: int = DEFAULT_IDLE_MINUTES
    last_command_at: float | None = None
    last_song_started_at: float | None = None
    alone_since: float | None = None


def reset_idle_activity(state: GuildState) -> None:
    """Reset idle timeout and activity timestamps to defaults."""
    state.idle_minutes = DEFAULT_IDLE_MINUTES
    state.last_command_at = None
    state.last_song_started_at = None
    state.alone_since = None


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

    def guild_ids(self) -> tuple[int, ...]:
        """Return guild IDs that currently have stored state."""
        return tuple(self._states)

    def peek(self, guild_id: int) -> GuildState | None:
        """Return stored guild state without creating a new entry."""
        return self._states.get(guild_id)
