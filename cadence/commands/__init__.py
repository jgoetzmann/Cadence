"""Slash command registration and handlers."""

from __future__ import annotations

from discord import app_commands

from cadence.commands.deps import CommandDeps
from cadence.commands.playback import register_playback
from cadence.commands.queue import register_queue
from cadence.commands.settings import register_settings

__all__ = ["CommandDeps", "register"]

COMMAND_NAMES = frozenset(
    {
        "play",
        "forceplay",
        "move",
        "skip",
        "pause",
        "resume",
        "stop",
        "queue",
        "nowplaying",
        "remove",
        "clear",
        "loop",
        "volume",
    }
)


def register(tree: app_commands.CommandTree, deps: CommandDeps) -> None:
    """Register all Cadence slash commands on the command tree."""
    register_playback(tree, deps)
    register_queue(tree, deps)
    register_settings(tree, deps)
