"""Shared test doubles for Discord and Cadence protocols."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import discord
import pytest

from cadence.interfaces import ResolvedTrack
from cadence.player import QueueFullError
from cadence.state import LoopMode, Track

__all__ = [
    "FakeAudioSource",
    "FakeMember",
    "FakeGuild",
    "FakeInteraction",
    "FakePlayer",
    "FakeTextChannel",
    "FakeUser",
    "FakeVoiceChannel",
    "FakeVoiceClient",
    "FakeVoiceState",
    "FakeYoutubeDL",
    "SentMessage",
    "patch_ytdl",
    "run_after",
    "search_result",
    "ytdl_entry",
]


@dataclass(slots=True)
class SentMessage:
    """Captured interaction reply."""

    content: str
    ephemeral: bool = False


@dataclass(slots=True)
class FakeTextChannel:
    """Minimal text channel that records outbound messages."""

    id: int
    sent: list[SentMessage] = field(default_factory=list)

    async def send(self, content: str, **kwargs: Any) -> SentMessage:
        message = SentMessage(content=content, ephemeral=kwargs.get("ephemeral", False))
        self.sent.append(message)
        return message


@dataclass(slots=True)
class FakeGuild:
    """Minimal guild with an optional voice client."""

    id: int
    voice_client: FakeVoiceClient | None = None


@dataclass(slots=True)
class FakeVoiceChannel:
    """Minimal voice channel that can spawn a fake voice client."""

    id: int
    guild: FakeGuild
    name: str = "voice"
    members: list[object] = field(default_factory=list)

    async def connect(self, **kwargs: Any) -> FakeVoiceClient:
        client = FakeVoiceClient(channel=self)
        self.guild.voice_client = client
        return client


@dataclass(slots=True)
class FakeVoiceClient:
    """Fake voice client that captures play/stop/pause/resume calls.

    ``play`` stores the ``after`` callback but does not fire it automatically.
    Tests invoke it explicitly via :func:`run_after` (or call ``stop``, which
    fires ``after`` like discord.py does).
    """

    channel: FakeVoiceChannel
    source: object | None = None
    after: Callable[[Exception | None], None] | None = None
    _playing: bool = False
    _paused: bool = False
    disconnect_calls: int = 0
    move_to_calls: list[FakeVoiceChannel] = field(default_factory=list)

    @property
    def guild(self) -> FakeGuild:
        return self.channel.guild

    def play(
        self,
        source: object,
        *,
        after: Callable[[Exception | None], None] | None = None,
    ) -> None:
        self.source = source
        self.after = after
        self._playing = True
        self._paused = False

    def stop(self) -> None:
        self._playing = False
        self._paused = False
        if self.after is not None:
            callback = self.after
            self.after = None
            callback(None)

    def pause(self) -> None:
        if self._playing:
            self._paused = True

    def resume(self) -> None:
        if self._playing:
            self._paused = False

    def is_playing(self) -> bool:
        return self._playing and not self._paused

    def is_paused(self) -> bool:
        return self._playing and self._paused

    async def disconnect(self, *, force: bool = False) -> None:
        self._playing = False
        self._paused = False
        self.disconnect_calls += 1
        self.channel.guild.voice_client = None

    async def move_to(self, channel: FakeVoiceChannel, *, timeout: float | None = None) -> None:
        _ = timeout
        self.move_to_calls.append(channel)
        self.channel = channel


def run_after(voice_client: FakeVoiceClient, *, error: Exception | None = None) -> None:
    """Synchronously invoke the captured FFmpeg ``after=`` callback."""
    if voice_client.after is None:
        msg = "No after callback was captured by play()"
        raise AssertionError(msg)
    callback = voice_client.after
    voice_client.after = None
    voice_client._playing = False
    voice_client._paused = False
    callback(error)


@dataclass(slots=True)
class FakeVoiceState:
    """Voice state attached to a fake user."""

    channel: FakeVoiceChannel | None


@dataclass(slots=True)
class FakeMember:
    """Minimal guild member for voice-state tests."""

    id: int
    guild: FakeGuild
    bot: bool = False
    voice: FakeVoiceState | None = None


@dataclass(slots=True)
class FakeUser:
    """Minimal Discord user."""

    id: int = 42
    voice: FakeVoiceState | None = None


@dataclass(slots=True)
class FakeInteractionResponse:
    """Records direct interaction responses."""

    owner: FakeInteraction

    async def defer(self, *, ephemeral: bool = False) -> None:
        self.owner.deferred.append({"ephemeral": ephemeral})

    async def send_message(self, content: str, *, ephemeral: bool = False) -> SentMessage:
        message = SentMessage(content=content, ephemeral=ephemeral)
        self.owner.responses.append(message)
        return message

    def is_done(self) -> bool:
        return bool(self.owner.deferred or self.owner.responses)


@dataclass(slots=True)
class FakeInteractionFollowup:
    """Records follow-up interaction responses."""

    owner: FakeInteraction

    async def send(self, content: str, *, ephemeral: bool = False) -> SentMessage:
        message = SentMessage(content=content, ephemeral=ephemeral)
        self.owner.followups.append(message)
        return message


class FakeInteraction:
    """Fake slash-command interaction that records replies and deferrals."""

    def __init__(
        self,
        *,
        guild: FakeGuild,
        voice_channel: FakeVoiceChannel | None = None,
        user_id: int = 42,
        channel: FakeTextChannel | None = None,
    ) -> None:
        self.guild = guild
        self.channel = channel if channel is not None else FakeTextChannel(id=300)
        self.user = FakeUser(
            id=user_id,
            voice=FakeVoiceState(channel=voice_channel) if voice_channel is not None else None,
        )
        self.deferred: list[dict[str, bool]] = []
        self.responses: list[SentMessage] = []
        self.followups: list[SentMessage] = []
        self.response = FakeInteractionResponse(owner=self)
        self.followup = FakeInteractionFollowup(owner=self)

    async def defer(self, *, ephemeral: bool = False) -> None:
        self.deferred.append({"ephemeral": ephemeral})


@dataclass
class FakeAudioSource:
    """Scriptable AudioSource for unit tests."""

    fetch_results: deque[ResolvedTrack | Exception] | list[ResolvedTrack | Exception] = field(
        default_factory=list
    )
    resolve_results: deque[ResolvedTrack | Exception] | list[ResolvedTrack | Exception] = field(
        default_factory=list
    )
    playback_results: deque[object | Exception] | list[object | Exception] = field(
        default_factory=list
    )
    fetch_calls: list[tuple[str, bool]] = field(default_factory=list)
    resolve_calls: list[str] = field(default_factory=list)
    playback_calls: list[tuple[str, int]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not isinstance(self.fetch_results, deque):
            self.fetch_results = deque(self.fetch_results)
        if not isinstance(self.resolve_results, deque):
            self.resolve_results = deque(self.resolve_results)
        if not isinstance(self.playback_results, deque):
            self.playback_results = deque(self.playback_results)

    async def fetch(self, query: str, *, is_url: bool) -> ResolvedTrack:
        self.fetch_calls.append((query, is_url))
        if not self.fetch_results:
            msg = "No scripted fetch result remaining"
            raise RuntimeError(msg)
        result = self.fetch_results.popleft()
        if isinstance(result, Exception):
            raise result
        return result

    async def resolve(self, webpage_url: str) -> ResolvedTrack:
        self.resolve_calls.append(webpage_url)
        if not self.resolve_results:
            msg = "No scripted resolve result remaining"
            raise RuntimeError(msg)
        result = self.resolve_results.popleft()
        if isinstance(result, Exception):
            raise result
        return result

    async def create_playback_source(
        self,
        webpage_url: str,
        volume: int,
    ) -> object:
        self.playback_calls.append((webpage_url, volume))
        if not self.playback_results:
            msg = "No scripted playback result remaining"
            raise RuntimeError(msg)
        result = self.playback_results.popleft()
        if isinstance(result, Exception):
            raise result
        if hasattr(result, "volume"):
            result.volume = volume / 100
        return result


@dataclass
class FakePlayer:
    """Recording Player stub for command unit tests."""

    snapshot_current: Track | None = None
    snapshot_upcoming: list[Track] = field(default_factory=list)
    loop_mode: LoopMode = LoopMode.OFF
    volume: int = 50
    enqueued: list[tuple[discord.Guild, Track]] = field(default_factory=list)
    play_next_calls: list[discord.Guild] = field(default_factory=list)
    skip_calls: list[discord.Guild] = field(default_factory=list)
    pause_calls: list[discord.Guild] = field(default_factory=list)
    resume_calls: list[discord.Guild] = field(default_factory=list)
    stop_calls: list[discord.Guild] = field(default_factory=list)
    loop_mode_calls: list[tuple[discord.Guild, LoopMode]] = field(default_factory=list)
    volume_calls: list[tuple[discord.Guild, int]] = field(default_factory=list)
    interrupt_calls: list[discord.Guild] = field(default_factory=list)
    reset_lineup_calls: list[discord.Guild] = field(default_factory=list)
    clear_queue_calls: list[discord.Guild] = field(default_factory=list)
    remove_at_calls: list[tuple[discord.Guild, int]] = field(default_factory=list)
    queue_full: bool = False
    interrupt_returns: bool = False

    def reset_lineup(self, guild: discord.Guild) -> None:
        self.reset_lineup_calls.append(guild)
        self.snapshot_upcoming = []
        self.snapshot_current = None
        self.loop_mode = LoopMode.OFF

    async def enqueue(self, guild: discord.Guild, track: Track) -> None:
        if self.queue_full:
            raise QueueFullError
        self.enqueued.append((guild, track))

    async def clear_queue(self, guild: discord.Guild) -> int:
        self.clear_queue_calls.append(guild)
        count = len(self.snapshot_upcoming)
        self.snapshot_upcoming = []
        return count

    async def remove_at(self, guild: discord.Guild, position: int) -> Track:
        self.remove_at_calls.append((guild, position))
        if self.snapshot_current is not None:
            if position == 1:
                track = self.snapshot_current
                self.snapshot_current = None
                self.skip_calls.append(guild)
                return track
            queue_index = position - 2
            upcoming = self.snapshot_upcoming
        else:
            queue_index = position - 1
            upcoming = self.snapshot_upcoming

        if queue_index < 0 or queue_index >= len(upcoming):
            msg = f"No track at position {position}"
            raise ValueError(msg)
        return upcoming.pop(queue_index)

    async def interrupt(self, guild: discord.Guild) -> bool:
        self.interrupt_calls.append(guild)
        self.snapshot_upcoming = []
        return self.interrupt_returns

    async def play_next(self, guild: discord.Guild, *, announce: bool = True) -> None:
        _ = announce
        self.play_next_calls.append(guild)

    async def skip(self, guild: discord.Guild) -> None:
        self.skip_calls.append(guild)

    async def pause(self, guild: discord.Guild) -> None:
        self.pause_calls.append(guild)

    async def resume(self, guild: discord.Guild) -> None:
        self.resume_calls.append(guild)

    async def stop(self, guild: discord.Guild) -> None:
        self.stop_calls.append(guild)

    def set_loop_mode(self, guild: discord.Guild, mode: LoopMode) -> None:
        self.loop_mode = mode
        self.loop_mode_calls.append((guild, mode))

    def set_volume(self, guild: discord.Guild, level: int) -> None:
        self.volume = level
        self.volume_calls.append((guild, level))

    def snapshot(self, guild: discord.Guild) -> tuple[Track | None, list[Track]]:
        _ = guild
        return self.snapshot_current, list(self.snapshot_upcoming)


def ytdl_entry(**overrides: object) -> dict[str, object]:
    """Build a canned yt-dlp info dict for a single video."""
    base: dict[str, object] = {
        "title": "Foo Song",
        "webpage_url": "https://youtube.com/watch?v=abc",
        "url": "https://stream.example/audio",
        "duration": 180,
        "id": "abc",
    }
    base.update(overrides)
    return base


def search_result(**overrides: object) -> dict[str, object]:
    """Wrap a single entry in yt-dlp search-result shape."""
    return {"entries": [ytdl_entry(**overrides)]}


class FakeYoutubeDL:
    """Scriptable YoutubeDL double for tests."""

    def __init__(
        self,
        *,
        results: list[dict[str, object] | None] | None = None,
        on_extract: Callable[[str, bool], None] | None = None,
    ) -> None:
        self.results = list(results or [])
        self.on_extract = on_extract
        self.calls: list[tuple[str, bool]] = []

    def extract_info(self, target: str, *, download: bool) -> dict[str, object] | None:
        self.calls.append((target, download))
        if self.on_extract is not None:
            self.on_extract(target, download)
        if not self.results:
            return search_result()
        result = self.results.pop(0)
        if result is None:
            return None
        return result


def patch_ytdl(monkeypatch: pytest.MonkeyPatch, fake: FakeYoutubeDL) -> None:
    """Inject FakeYoutubeDL instances into YouTubeSource (one per unique yt-dlp opts)."""
    from cadence.sources import youtube as youtube_module

    cache: dict[tuple[str, str], FakeYoutubeDL] = {}

    def factory(opts: dict[str, object]) -> FakeYoutubeDL:
        key = (
            str(opts.get("cookiefile", "")),
            str(opts.get("proxy", "")),
        )
        if key not in cache:
            if not cache:
                cache[key] = fake
            else:
                cache[key] = FakeYoutubeDL(
                    results=list(fake.results),
                    on_extract=fake.on_extract,
                )
        return cache[key]

    monkeypatch.setattr(youtube_module, "_shared_ytdl", {})
    monkeypatch.setattr(youtube_module.yt_dlp, "YoutubeDL", factory)
