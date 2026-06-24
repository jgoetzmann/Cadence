"""YouTube audio source via yt-dlp."""

from __future__ import annotations

import asyncio
from typing import Any, TypedDict, cast

import discord
import yt_dlp  # type: ignore[import-untyped]

from cadence.interfaces import ResolvedTrack

__all__ = ["FFMPEG_OPTS", "SourceError", "YTDL_OPTS", "YouTubeSource", "make_ffmpeg_source"]

YTDL_OPTS: dict[str, Any] = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
}


class FFmpegOpts(TypedDict):
    before_options: str
    options: str


FFMPEG_OPTS: FFmpegOpts = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

_shared_ytdl: yt_dlp.YoutubeDL | None = None


def _get_ytdl() -> yt_dlp.YoutubeDL:
    global _shared_ytdl
    if _shared_ytdl is None:
        _shared_ytdl = yt_dlp.YoutubeDL(YTDL_OPTS)
    return _shared_ytdl


class SourceError(Exception):
    """Raised when yt-dlp cannot resolve a query or URL."""


def _unwrap_entry(info: dict[str, Any] | None) -> dict[str, Any]:
    if info is None:
        msg = "No result from source"
        raise SourceError(msg)
    if "entries" in info:
        entries = [entry for entry in info["entries"] if entry]
        if not entries:
            msg = "No result from source"
            raise SourceError(msg)
        return cast(dict[str, Any], entries[0])
    return info


def _parse_duration(raw: object) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return int(raw)
    return None


def _to_resolved(info: dict[str, Any]) -> ResolvedTrack:
    webpage_url = info.get("webpage_url")
    if not webpage_url:
        video_id = info.get("id")
        if not video_id:
            msg = "No webpage URL in source result"
            raise SourceError(msg)
        webpage_url = f"https://www.youtube.com/watch?v={video_id}"
    stream_url = info.get("url")
    if not stream_url or not isinstance(stream_url, str):
        msg = "No stream URL in source result"
        raise SourceError(msg)
    return ResolvedTrack(
        title=info.get("title", "Unknown title"),
        webpage_url=webpage_url,
        stream_url=stream_url,
        duration=_parse_duration(info.get("duration")),
    )


def _extract(ytdl: yt_dlp.YoutubeDL, query: str, *, search: bool) -> ResolvedTrack:
    target = f"ytsearch1:{query}" if search else query
    try:
        info = ytdl.extract_info(target, download=False)
    except Exception as exc:
        msg = "Failed to extract from source"
        raise SourceError(msg) from exc
    return _to_resolved(_unwrap_entry(info))


class YouTubeSource:
    """Resolves YouTube search queries and URLs into playable tracks."""

    def __init__(self) -> None:
        self._ytdl = _get_ytdl()

    async def _run_extract(self, query: str, *, search: bool) -> ResolvedTrack:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: _extract(self._ytdl, query, search=search),
        )

    async def fetch(self, query: str, *, is_url: bool) -> ResolvedTrack:
        """Resolve a search query or URL into track metadata and a stream URL."""
        return await self._run_extract(query, search=not is_url)

    async def resolve(self, webpage_url: str) -> ResolvedTrack:
        """Re-resolve a webpage URL into a fresh stream URL."""
        return await self._run_extract(webpage_url, search=False)


def make_ffmpeg_source(
    stream_url: str,
    volume: int,
) -> discord.PCMVolumeTransformer[discord.AudioSource]:
    """Build a volume-adjusted FFmpeg PCM source for Discord playback."""
    raw = discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTS)
    return discord.PCMVolumeTransformer(raw, volume=volume / 100)
