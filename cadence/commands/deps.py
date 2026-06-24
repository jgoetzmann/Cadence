"""Shared dependencies injected into slash command handlers."""

from __future__ import annotations

from dataclasses import dataclass

from cadence.interfaces import AudioSource, Player
from cadence.state import StateStore

__all__ = ["CommandDeps"]


@dataclass(frozen=True, slots=True)
class CommandDeps:
    """Concrete services wired into command handlers at registration time."""

    player: Player
    source: AudioSource
    store: StateStore
