"""
A small Discord music bot that streams audio from YouTube.

Slash commands:
  /play <query>  - search YouTube for the most relevant video and play it
  /skip          - skip the current song
  /loop          - toggle looping the current song
  /stop          - stop playback, clear the queue, and leave the channel

Requires: discord.py, yt-dlp, PyNaCl (pip) and ffmpeg (system binary in PATH).
Set the DISCORD_TOKEN environment variable before running.
"""

import os
import asyncio
from collections import deque

import discord
from discord import app_commands
import yt_dlp


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
TOKEN = os.environ.get("DISCORD_TOKEN")
# Optional: set DISCORD_GUILD_ID to your server's ID for instant command sync
# while testing. Global sync (no guild id) can take up to an hour to appear.
GUILD_ID = os.environ.get("DISCORD_GUILD_ID")

YTDL_OPTS = {
    "format": "bestaudio/best",
    "noplaylist": True,        # a watch URL with &list=... won't expand
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",  # bind to IPv4 (avoids some network issues)
}

# Reconnect options keep the stream alive if the connection hiccups.
FFMPEG_OPTS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",  # audio only
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTS)


# ---------------------------------------------------------------------------
# Per-guild state
# ---------------------------------------------------------------------------
class Track:
    def __init__(self, title, webpage_url, requested_by):
        self.title = title
        self.webpage_url = webpage_url
        self.requested_by = requested_by


class GuildState:
    def __init__(self):
        self.queue = deque()       # upcoming Tracks
        self.current = None        # Track currently playing (or None)
        self.loop = False          # repeat the current track?
        self.text_channel = None   # where to post "now playing" messages


states = {}


def get_state(guild_id):
    if guild_id not in states:
        states[guild_id] = GuildState()
    return states[guild_id]


# ---------------------------------------------------------------------------
# yt-dlp helpers (blocking -> always run in an executor)
# ---------------------------------------------------------------------------
def _extract(query, search=False):
    """Resolve a query/URL with yt-dlp. Returns a single info dict.

    If search=True, query is treated as search terms and the single most
    relevant result is returned.
    """
    target = f"ytsearch1:{query}" if search else query
    info = ytdl.extract_info(target, download=False)
    if info is None:
        raise RuntimeError("No result")
    if "entries" in info:  # search results / playlists come back wrapped
        entries = [e for e in info["entries"] if e]
        if not entries:
            raise RuntimeError("No result")
        info = entries[0]
    return info


async def extract(query, search=False):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: _extract(query, search))


# ---------------------------------------------------------------------------
# Discord client
# ---------------------------------------------------------------------------
intents = discord.Intents.default()  # voice_states is included; no privileged intents needed
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


@client.event
async def on_ready():
    if GUILD_ID:
        guild = discord.Object(id=int(GUILD_ID))
        tree.copy_global_to(guild=guild)
        await tree.sync(guild=guild)
    else:
        await tree.sync()
    print(f"Logged in as {client.user} (id: {client.user.id})")


# ---------------------------------------------------------------------------
# Playback engine
# ---------------------------------------------------------------------------
async def play_next(guild):
    """Play the next track for a guild. Called on /play start and whenever a
    track finishes (via the FFmpeg `after` callback)."""
    state = get_state(guild.id)
    voice_client = guild.voice_client
    if voice_client is None:
        return

    if state.loop and state.current is not None:
        track = state.current
        fresh = False
    elif state.queue:
        track = state.queue.popleft()
        state.current = track
        fresh = True
    else:
        state.current = None
        return  # queue empty; stay connected and idle

    # Resolve a fresh stream URL each time. YouTube stream URLs expire, so
    # re-resolving keeps long loops and queued tracks working reliably.
    try:
        info = await extract(track.webpage_url)
        stream_url = info["url"]
    except Exception:
        if state.text_channel:
            await state.text_channel.send(
                f"⚠️ Skipping **{track.title}** (couldn't load audio)."
            )
        state.current = None
        return await play_next(guild)

    source = discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTS)

    def _after(err):
        if err:
            print(f"Playback error: {err}")
        # The `after` callback runs in a worker thread, so hop back onto the
        # event loop to continue playback.
        asyncio.run_coroutine_threadsafe(play_next(guild), client.loop)

    voice_client.play(source, after=_after)

    if fresh and state.text_channel:
        await state.text_channel.send(f"▶️ Now playing: **{track.title}**")


# ---------------------------------------------------------------------------
# Slash commands
# ---------------------------------------------------------------------------
@tree.command(name="play", description="Search YouTube and play the most relevant result")
@app_commands.describe(query="Search terms or a YouTube URL")
async def play(interaction: discord.Interaction, query: str):
    if not interaction.user.voice or not interaction.user.voice.channel:
        return await interaction.response.send_message(
            "You need to be in a voice channel first.", ephemeral=True
        )

    await interaction.response.defer()  # extraction can take a moment

    channel = interaction.user.voice.channel
    voice_client = interaction.guild.voice_client
    if voice_client is None:
        voice_client = await channel.connect()
    elif voice_client.channel != channel:
        await voice_client.move_to(channel)

    state = get_state(interaction.guild.id)
    state.text_channel = interaction.channel

    is_url = query.startswith("http://") or query.startswith("https://")
    try:
        info = await extract(query, search=not is_url)
    except Exception as e:
        return await interaction.followup.send(f"Couldn't find anything for that. ({e})")

    webpage_url = info.get("webpage_url") or f"https://www.youtube.com/watch?v={info['id']}"
    track = Track(info.get("title", "Unknown title"), webpage_url, interaction.user)
    state.queue.append(track)

    already_active = voice_client.is_playing() or state.current is not None
    if already_active:
        await interaction.followup.send(f"➕ Added to queue: **{track.title}**")
    else:
        await interaction.followup.send(f"🔎 Found **{track.title}**")
        await play_next(interaction.guild)


@tree.command(name="skip", description="Skip the current song")
async def skip(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc is None or not vc.is_playing():
        return await interaction.response.send_message("Nothing is playing.", ephemeral=True)

    state = get_state(interaction.guild.id)
    # Clearing current means the loop branch in play_next is bypassed for this
    # one transition, so skip advances even when looping is on.
    state.current = None
    vc.stop()  # triggers the `after` callback -> play_next
    await interaction.response.send_message("⏭️ Skipped.")


@tree.command(name="loop", description="Toggle looping the current song")
async def loop(interaction: discord.Interaction):
    state = get_state(interaction.guild.id)
    state.loop = not state.loop
    await interaction.response.send_message(
        "🔁 Loop **enabled**." if state.loop else "Loop **disabled**."
    )


@tree.command(name="stop", description="Stop playback, clear the queue, and leave")
async def stop(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    state = get_state(interaction.guild.id)
    state.queue.clear()
    state.current = None
    state.loop = False
    if vc:
        vc.stop()
        await vc.disconnect()
    await interaction.response.send_message("⏹️ Stopped and left the channel.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("Set the DISCORD_TOKEN environment variable before running.")
    client.run(TOKEN)
