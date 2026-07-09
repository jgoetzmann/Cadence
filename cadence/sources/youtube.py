"""YouTube audio source via yt-dlp."""

from __future__ import annotations

import asyncio
import io
import logging
import os
import select
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any, TypedDict, cast

import discord
import yt_dlp  # type: ignore[import-untyped]
from yt_dlp.networking.impersonate import ImpersonateTarget

from cadence.interfaces import ResolvedTrack

__all__ = [
    "FFMPEG_OPTS",
    "SourceError",
    "YTDL_OPTS",
    "YtDlpConfig",
    "YouTubeSource",
    "build_ytdl_opts",
    "make_ffmpeg_source",
    "make_playback_source",
]

log = logging.getLogger(__name__)

YTDL_OPTS: dict[str, Any] = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
    # yt-dlp 2025+ needs EJS challenge scripts for YouTube signature/n solving.
    "remote_components": ["ejs:github"],
}

DEFAULT_PLAYER_CLIENTS: tuple[str, ...] = (
    "tv",
    "web_embedded",
    "web",
)


class FFmpegOpts(TypedDict):
    before_options: str
    options: str


FFMPEG_OPTS: FFmpegOpts = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

# Piped yt-dlp stdout cannot use HTTP reconnect flags. Low-latency probe/decode
# avoids buffering away the first second of audio while yt-dlp warms up.
FFMPEG_PIPE_OPTS: FFmpegOpts = {
    "before_options": (
        "-nostdin -analyzeduration 0 -probesize 32 "
        "-fflags +nobuffer+flush_packets"
    ),
    "options": "-vn",
}

_PLAYBACK_PREROLL_BYTES = 16_384
_PLAYBACK_PREROLL_TIMEOUT_SEC = 45.0


@dataclass(frozen=True, slots=True)
class YtDlpConfig:
    """yt-dlp options shared across extraction calls."""

    cookie_file: str | None = None
    proxy: str | None = None
    impersonate: str | None = "chrome"

    def cache_key(self) -> tuple[str, str, str]:
        return (
            self.cookie_file or "",
            self.proxy or "",
            self.impersonate or "",
        )


_shared_ytdl: dict[tuple[str, str, str], yt_dlp.YoutubeDL] = {}


def build_ytdl_opts(config: YtDlpConfig | None = None) -> dict[str, Any]:
    cfg = config or YtDlpConfig()
    opts = dict(YTDL_OPTS)
    opts["extractor_args"] = {
        "youtube": {
            "player_client": list(DEFAULT_PLAYER_CLIENTS),
        },
    }
    if cfg.cookie_file:
        opts["cookiefile"] = cfg.cookie_file
    if cfg.proxy:
        opts["proxy"] = cfg.proxy
    if cfg.impersonate:
        opts["impersonate"] = ImpersonateTarget.from_str(cfg.impersonate.lower())
    opts["socket_timeout"] = 45
    return opts


def _get_ytdl(config: YtDlpConfig) -> yt_dlp.YoutubeDL:
    key = config.cache_key()
    if key not in _shared_ytdl:
        _shared_ytdl[key] = yt_dlp.YoutubeDL(build_ytdl_opts(config))
    return _shared_ytdl[key]


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


def _is_bot_block(exc: Exception) -> bool:
    text = str(exc).casefold()
    return "sign in" in text or "not a bot" in text


def _extract_with_fallback(config: YtDlpConfig, query: str, *, search: bool) -> ResolvedTrack:
    try:
        return _extract(_get_ytdl(config), query, search=search)
    except SourceError as exc:
        if (
            not config.impersonate
            or exc.__cause__ is None
            or not _is_bot_block(exc.__cause__)
        ):
            raise
        plain = YtDlpConfig(
            cookie_file=config.cookie_file,
            proxy=config.proxy,
            impersonate=None,
        )
        return _extract(_get_ytdl(plain), query, search=search)


class YouTubeSource:
    """Resolves YouTube search queries and URLs into playable tracks."""

    def __init__(self, config: YtDlpConfig | None = None) -> None:
        self._config = config or YtDlpConfig()
        self._ytdl = _get_ytdl(self._config)

    async def _run_extract(self, query: str, *, search: bool) -> ResolvedTrack:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: _extract_with_fallback(self._config, query, search=search),
        )

    async def fetch(self, query: str, *, is_url: bool) -> ResolvedTrack:
        """Resolve a search query or URL into track metadata and a stream URL."""
        return await self._run_extract(query, search=not is_url)

    async def resolve(self, webpage_url: str) -> ResolvedTrack:
        """Re-resolve a webpage URL into a fresh stream URL."""
        return await self._run_extract(webpage_url, search=False)

    async def create_playback_source(
        self,
        webpage_url: str,
        volume: int,
    ) -> discord.PCMVolumeTransformer[discord.AudioSource]:
        """Stream audio via yt-dlp piped into FFmpeg (matches extraction proxy/config)."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: make_playback_source(webpage_url, volume, self._config),
        )


def _ytdlp_playback_command(webpage_url: str, config: YtDlpConfig) -> list[str]:
    cmd = [
        sys.executable,
        "-m",
        "yt_dlp",
        "-o",
        "-",
        "-f",
        str(YTDL_OPTS["format"]),
        "--no-playlist",
        "--quiet",
        "--no-warnings",
        "--remote-components",
        "ejs:github",
        "--extractor-args",
        f"youtube:player_client={','.join(DEFAULT_PLAYER_CLIENTS)}",
        "--socket-timeout",
        "45",
    ]
    if config.cookie_file:
        cmd.extend(["--cookies", config.cookie_file])
    if config.proxy:
        cmd.extend(["--proxy", config.proxy])
    if config.impersonate:
        cmd.extend(["--impersonate", config.impersonate.lower()])
    cmd.append(webpage_url)
    return cmd


class _PrefixedReader(io.RawIOBase):
    """Prepends an initial byte buffer before continuing to read from a stream."""

    def __init__(self, stream: io.BufferedIOBase, prefix: bytes) -> None:
        self._stream = stream
        self._prefix = prefix

    def read(self, size: int = -1) -> bytes:
        if not self._prefix:
            return self._stream.read(size)
        if size == -1:
            chunk = self._prefix
            self._prefix = b""
            return chunk + self._stream.read()
        if size <= len(self._prefix):
            chunk = self._prefix[:size]
            self._prefix = self._prefix[size:]
            return chunk
        chunk = self._prefix
        self._prefix = b""
        return chunk + self._stream.read(size - len(chunk))

    def readable(self) -> bool:
        return True


def _read_first_playback_chunk(
    stream: io.BufferedIOBase,
    process: subprocess.Popen[bytes],
    *,
    min_bytes: int = _PLAYBACK_PREROLL_BYTES,
    timeout_sec: float = _PLAYBACK_PREROLL_TIMEOUT_SEC,
) -> bytes:
    """Wait until yt-dlp has written enough muxed audio for FFmpeg to decode."""
    deadline = time.monotonic() + timeout_sec
    chunks: list[bytes] = []
    total = 0
    while total < min_bytes and time.monotonic() < deadline:
        if os.name != "nt":
            remaining = max(0.0, deadline - time.monotonic())
            ready, _, _ = select.select([stream], [], [], min(remaining, 0.2))
            if not ready:
                if process.poll() is not None:
                    break
                continue
        chunk = stream.read(4096)
        if not chunk:
            if process.poll() is not None:
                break
            time.sleep(0.05)
            continue
        chunks.append(chunk)
        total += len(chunk)
    data = b"".join(chunks)
    if not data:
        msg = "Timed out waiting for playback audio stream"
        raise SourceError(msg)
    return data


class _ManagedPipeSource(discord.AudioSource):
    """FFmpeg audio source that terminates the upstream yt-dlp process on cleanup."""

    def __init__(
        self,
        ytdl_process: subprocess.Popen[bytes],
        ffmpeg_source: discord.FFmpegPCMAudio,
    ) -> None:
        self._ytdl = ytdl_process
        self._ffmpeg = ffmpeg_source

    def read(self) -> bytes:
        return self._ffmpeg.read()

    def is_opus(self) -> bool:
        return self._ffmpeg.is_opus()

    def cleanup(self) -> None:
        try:
            self._ffmpeg.cleanup()
        finally:
            if self._ytdl.poll() is None:
                self._ytdl.kill()
            try:
                self._ytdl.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._ytdl.kill()
            stderr = self._ytdl.stderr
            if stderr is not None and self._ytdl.returncode not in (0, None):
                detail = stderr.read().decode(errors="replace").strip()
                if detail:
                    log.warning("yt-dlp playback exited %s: %s", self._ytdl.returncode, detail)


def make_playback_source(
    webpage_url: str,
    volume: int,
    config: YtDlpConfig | None = None,
) -> discord.PCMVolumeTransformer[discord.AudioSource]:
    """Pipe yt-dlp audio into FFmpeg so playback uses the same network path as extraction."""
    cfg = config or YtDlpConfig()
    ytdl_process = subprocess.Popen(  # noqa: S603
        _ytdlp_playback_command(webpage_url, cfg),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )
    if ytdl_process.stdout is None:
        msg = "yt-dlp playback process missing stdout pipe"
        raise SourceError(msg)
    stdout = io.BufferedReader(ytdl_process.stdout)
    prefix = _read_first_playback_chunk(stdout, ytdl_process)
    prefixed_stdout = _PrefixedReader(stdout, prefix)
    ffmpeg_source = discord.FFmpegPCMAudio(
        prefixed_stdout,
        pipe=True,
        **FFMPEG_PIPE_OPTS,
    )
    managed = _ManagedPipeSource(ytdl_process, ffmpeg_source)
    return discord.PCMVolumeTransformer(managed, volume=volume / 100)


def make_ffmpeg_source(
    stream_url: str,
    volume: int,
) -> discord.PCMVolumeTransformer[discord.AudioSource]:
    """Build a volume-adjusted FFmpeg PCM source for Discord playback."""
    raw = discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTS)
    return discord.PCMVolumeTransformer(raw, volume=volume / 100)
