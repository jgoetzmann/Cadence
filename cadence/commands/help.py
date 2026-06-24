"""Help slash command: /help."""

from __future__ import annotations

import discord
from discord import app_commands

from cadence.commands.deps import CommandDeps
from cadence.state import QUEUE_LIMIT

__all__ = ["HELP_TEXT", "handle_help", "register_help"]

HELP_TEXT = f"""**Cadence — command overview**

**Playback**
• `/play` — Search YouTube or paste a URL; plays now or adds to queue
• `/forceplay` — Clear the queue and play a query immediately
• `/move` — Join or move the bot to your voice channel
• `/skip` — Skip the current song and play the next
• `/pause` / `/resume` — Pause or resume playback
• `/stop` — Stop playback, clear the queue, and leave voice

**Queue** (position **1** = now playing, **2+** = upcoming)
• `/queue` — Show the current track and up to {QUEUE_LIMIT} upcoming tracks
• `/nowplaying` — Show the song that is playing right now
• `/remove` — Remove by position (**1** skips the current song)
• `/clear` — Remove all upcoming tracks; keeps the current song playing

**Settings**
• `/loop` — **Off**, **Current song**, **Queue**, or **Queue shuffle**
• `/volume` — Set playback volume (**0–100**)
• `/idle` — Auto-disconnect after inactivity (**1–1500** min, default **10**)

You must be in a voice channel for `/play`, `/forceplay`, and `/move`."""


async def handle_help(interaction: discord.Interaction, deps: CommandDeps) -> None:
    """Reply with a brief overview of all slash commands."""
    _ = deps
    await interaction.response.send_message(HELP_TEXT)


def register_help(tree: app_commands.CommandTree, deps: CommandDeps) -> None:
    """Register the /help slash command on the command tree."""

    @tree.command(name="help", description="Show what Cadence commands do")
    async def help_command(interaction: discord.Interaction) -> None:
        await handle_help(interaction, deps)
