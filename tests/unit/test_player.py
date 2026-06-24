"""Tests for cadence.player."""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass
from typing import cast
from unittest.mock import patch

import discord
import pytest

from cadence.interfaces import ResolvedTrack
from cadence.player import Player
from cadence.state import StateStore, Track
from tests.fakes import (
    FakeAudioSource,
    FakeGuild,
    FakeTextChannel,
    FakeVoiceClient,
    run_after,
)


@dataclass(slots=True)
class FakeClient:
    """Minimal Discord client exposing the event loop."""

    loop: asyncio.AbstractEventLoop


@dataclass
class FakePCMVolumeTransformer:
    """Lightweight stand-in for discord.PCMVolumeTransformer in tests."""

    source: object
    volume: float = 1.0


def resolved_track_for(
    track: Track,
    *,
    stream_url: str = "https://stream.example/audio",
) -> ResolvedTrack:
    """Build a ResolvedTrack matching a queued Track."""
    return ResolvedTrack(
        title=track.title,
        webpage_url=track.webpage_url,
        stream_url=stream_url,
        duration=track.duration,
    )


def make_player(
    *,
    store: StateStore | None = None,
    source: FakeAudioSource | None = None,
    loop: asyncio.AbstractEventLoop | None = None,
) -> tuple[Player, StateStore, FakeAudioSource, FakeClient]:
    """Wire a Player with fakes for unit tests."""
    resolved_loop = loop or asyncio.get_running_loop()
    fake_client = FakeClient(loop=resolved_loop)
    resolved_store = store or StateStore()
    resolved_source = source or FakeAudioSource()
    player = Player(
        cast(discord.Client, fake_client),
        resolved_store,
        resolved_source,
    )
    return player, resolved_store, resolved_source, fake_client


def guild_as_discord(fake_guild: FakeGuild) -> discord.Guild:
    """Cast a FakeGuild to discord.Guild for typed Player APIs."""
    return cast(discord.Guild, fake_guild)


@pytest.fixture
def patch_voice_source(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid spawning real FFmpeg processes in tests."""

    def fake_transformer(
        source: object,
        volume: float = 1.0,
    ) -> FakePCMVolumeTransformer:
        return FakePCMVolumeTransformer(source=source, volume=volume)

    monkeypatch.setattr(
        "cadence.player.discord.FFmpegPCMAudio",
        lambda stream_url, **kwargs: f"pcm:{stream_url}",
    )
    monkeypatch.setattr("cadence.player.discord.PCMVolumeTransformer", fake_transformer)


@pytest.mark.asyncio
async def test_play_next_pops_queue_plays_and_posts_now_playing(
    fake_guild: FakeGuild,
    fake_voice_client: FakeVoiceClient,
    patch_voice_source: None,
) -> None:
    """C1-01: play_next pops the queue, sets current, plays, posts now playing."""
    _ = fake_voice_client
    player, store, source, _ = make_player()
    guild = guild_as_discord(fake_guild)
    text_channel = FakeTextChannel(id=300)
    state = store.get(fake_guild.id)
    state.text_channel = text_channel
    track = Track(
        title="Test Song",
        webpage_url="https://www.youtube.com/watch?v=abc",
        requested_by=42,
    )
    state.queue.append(track)
    source.resolve_results = deque([resolved_track_for(track)])

    await player.play_next(guild)

    assert state.current == track
    assert len(state.queue) == 0
    assert source.resolve_calls == [track.webpage_url]
    assert fake_guild.voice_client is not None
    assert fake_guild.voice_client.source is not None
    assert state.voice_source is not None
    assert state.voice_source.volume == 0.5
    assert len(text_channel.sent) == 1
    assert text_channel.sent[0].content == "▶️ Now playing: **Test Song**"


@pytest.mark.asyncio
async def test_play_next_skips_announce_when_requested(
    fake_guild: FakeGuild,
    fake_voice_client: FakeVoiceClient,
    patch_voice_source: None,
) -> None:
    """play_next with announce=False skips the text-channel now playing post."""
    _ = fake_voice_client
    player, store, source, _ = make_player()
    guild = guild_as_discord(fake_guild)
    text_channel = FakeTextChannel(id=300)
    state = store.get(fake_guild.id)
    state.text_channel = text_channel
    track = Track(
        title="Quiet Start",
        webpage_url="https://www.youtube.com/watch?v=quiet",
        requested_by=42,
    )
    state.queue.append(track)
    source.resolve_results = deque([resolved_track_for(track)])

    await player.play_next(guild, announce=False)

    assert state.current == track
    assert text_channel.sent == []


@pytest.mark.asyncio
async def test_play_next_loop_replays_without_now_playing(
    fake_guild: FakeGuild,
    fake_voice_client: FakeVoiceClient,
    patch_voice_source: None,
) -> None:
    """C1-02: loop on replays current without dequeuing or posting now playing."""
    _ = fake_voice_client
    player, store, source, _ = make_player()
    guild = guild_as_discord(fake_guild)
    text_channel = FakeTextChannel(id=300)
    state = store.get(fake_guild.id)
    state.text_channel = text_channel
    track = Track(
        title="Loop Song",
        webpage_url="https://www.youtube.com/watch?v=loop",
        requested_by=1,
    )
    state.current = track
    state.loop = True
    source.resolve_results = deque([resolved_track_for(track)])

    await player.play_next(guild)

    assert state.current == track
    assert len(state.queue) == 0
    assert text_channel.sent == []


@pytest.mark.asyncio
async def test_play_next_empty_queue_stays_connected(
    fake_guild: FakeGuild,
    fake_voice_client: FakeVoiceClient,
    patch_voice_source: None,
) -> None:
    """C1-03/04: empty queue leaves current None and stays connected."""
    _ = patch_voice_source
    _ = fake_voice_client
    player, store, _, _ = make_player()
    guild = guild_as_discord(fake_guild)
    state = store.get(fake_guild.id)
    state.current = Track(
        title="Last",
        webpage_url="https://example.com",
        requested_by=1,
    )

    await player.play_next(guild)

    assert state.current is None
    assert state.voice_source is None
    assert fake_guild.voice_client is not None
    assert fake_guild.voice_client.disconnect_calls == 0


@pytest.mark.asyncio
async def test_play_next_resolve_failure_skips_and_advances(
    fake_guild: FakeGuild,
    fake_voice_client: FakeVoiceClient,
    patch_voice_source: None,
) -> None:
    """C1-05/06: resolve failure posts warning, clears current, plays next."""
    _ = patch_voice_source
    _ = fake_voice_client
    player, store, source, _ = make_player()
    guild = guild_as_discord(fake_guild)
    text_channel = FakeTextChannel(id=300)
    state = store.get(fake_guild.id)
    state.text_channel = text_channel
    bad = Track(title="Bad", webpage_url="https://bad.example", requested_by=1)
    good = Track(title="Good", webpage_url="https://good.example", requested_by=2)
    state.queue.extend([bad, good])
    source.resolve_results = deque([RuntimeError("resolve failed"), resolved_track_for(good)])

    await player.play_next(guild)

    assert state.current == good
    assert state.voice_source is not None
    assert len(state.queue) == 0
    assert len(text_channel.sent) == 2
    assert text_channel.sent[0].content == "⚠️ Skipping **Bad** (couldn't load audio)."
    assert text_channel.sent[1].content == "▶️ Now playing: **Good**"


@pytest.mark.asyncio
async def test_after_schedules_play_next_via_run_coroutine_threadsafe(
    fake_guild: FakeGuild,
    fake_voice_client: FakeVoiceClient,
    patch_voice_source: None,
) -> None:
    """C2-01: after callback schedules play_next on the client loop."""
    _ = patch_voice_source
    player, store, source, fake_client = make_player()
    guild = guild_as_discord(fake_guild)
    track = Track(title="A", webpage_url="https://a.example", requested_by=1)
    track2 = Track(title="B", webpage_url="https://b.example", requested_by=2)
    state = store.get(fake_guild.id)
    state.queue.extend([track, track2])
    source.resolve_results = deque([
        resolved_track_for(track),
        resolved_track_for(track2),
    ])
    scheduled: list[asyncio.Future[object]] = []

    def capture_schedule(coro: object, loop: asyncio.AbstractEventLoop) -> asyncio.Future[object]:
        future = asyncio.ensure_future(coro, loop=loop)  # type: ignore[arg-type]
        scheduled.append(future)
        return future

    with patch("cadence.player.asyncio.run_coroutine_threadsafe", side_effect=capture_schedule):
        await player.play_next(guild)
        assert fake_guild.voice_client is not None
        run_after(fake_guild.voice_client)

    assert len(scheduled) == 1
    await scheduled[0]
    assert source.resolve_calls == [track.webpage_url, track2.webpage_url]
    assert state.current == track2


@pytest.mark.asyncio
async def test_after_logs_playback_error(
    fake_guild: FakeGuild,
    fake_voice_client: FakeVoiceClient,
    patch_voice_source: None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """C2-02: playback errors passed to after are logged."""
    _ = patch_voice_source
    player, store, source, _ = make_player()
    guild = guild_as_discord(fake_guild)
    track = Track(title="A", webpage_url="https://a.example", requested_by=1)
    store.get(fake_guild.id).queue.append(track)
    source.resolve_results = deque([resolved_track_for(track)])

    with caplog.at_level(logging.ERROR):
        await player.play_next(guild)
        assert fake_guild.voice_client is not None
        run_after(fake_guild.voice_client, error=RuntimeError("playback failed"))

    assert "Playback error" in caplog.text


@pytest.mark.asyncio
async def test_skip_clears_current_and_bypasses_loop(
    fake_guild: FakeGuild,
    fake_voice_client: FakeVoiceClient,
    patch_voice_source: None,
) -> None:
    """C2-03/04: skip clears current so loop is bypassed for one transition."""
    _ = fake_voice_client
    player, store, source, _ = make_player()
    guild = guild_as_discord(fake_guild)
    current = Track(title="Loop", webpage_url="https://loop.example", requested_by=1)
    nxt = Track(title="Next", webpage_url="https://next.example", requested_by=2)
    state = store.get(fake_guild.id)
    state.current = current
    state.loop = True
    state.queue.append(nxt)
    source.resolve_results = deque([resolved_track_for(current), resolved_track_for(nxt)])

    await player.play_next(guild)

    scheduled: list[asyncio.Future[object]] = []

    def capture_schedule(coro: object, loop: asyncio.AbstractEventLoop) -> asyncio.Future[object]:
        future = asyncio.ensure_future(coro, loop=loop)  # type: ignore[arg-type]
        scheduled.append(future)
        return future

    with patch("cadence.player.asyncio.run_coroutine_threadsafe", side_effect=capture_schedule):
        await player.skip(guild)
        assert len(scheduled) == 1
        await scheduled[0]

    assert state.current == nxt
    assert source.resolve_calls == [current.webpage_url, nxt.webpage_url]


@pytest.mark.asyncio
async def test_skip_while_paused_advances(
    fake_guild: FakeGuild,
    fake_voice_client: FakeVoiceClient,
    patch_voice_source: None,
) -> None:
    """skip works while paused (§5.4: clear current + stop, no is_playing guard)."""
    _ = fake_voice_client
    player, store, source, _ = make_player()
    guild = guild_as_discord(fake_guild)
    current = Track(title="Paused", webpage_url="https://paused.example", requested_by=1)
    nxt = Track(title="Next", webpage_url="https://next.example", requested_by=2)
    state = store.get(fake_guild.id)
    state.queue.extend([current, nxt])
    source.resolve_results = deque([resolved_track_for(current), resolved_track_for(nxt)])

    await player.play_next(guild)
    await player.pause(guild)
    assert fake_guild.voice_client is not None
    assert fake_guild.voice_client.is_paused() is True

    scheduled: list[asyncio.Future[object]] = []

    def capture_schedule(coro: object, loop: asyncio.AbstractEventLoop) -> asyncio.Future[object]:
        future = asyncio.ensure_future(coro, loop=loop)  # type: ignore[arg-type]
        scheduled.append(future)
        return future

    with patch("cadence.player.asyncio.run_coroutine_threadsafe", side_effect=capture_schedule):
        await player.skip(guild)
        assert len(scheduled) == 1
        await scheduled[0]

    assert state.current == nxt


@pytest.mark.asyncio
async def test_set_loop_updates_state(
    fake_guild: FakeGuild,
) -> None:
    """C3-01/02: set_loop toggles the guild loop flag."""
    player, store, _, _ = make_player()
    guild = guild_as_discord(fake_guild)
    state = store.get(fake_guild.id)

    player.set_loop(guild, enabled=True)
    assert state.loop is True
    player.set_loop(guild, enabled=False)
    assert state.loop is False


@pytest.mark.asyncio
async def test_pause_and_resume_call_voice_client(
    fake_guild: FakeGuild,
    fake_voice_client: FakeVoiceClient,
    patch_voice_source: None,
) -> None:
    """C3-03/04: pause/resume delegate to voice client; safe when idle."""
    _ = patch_voice_source
    player, store, source, _ = make_player()
    guild = guild_as_discord(fake_guild)
    track = Track(title="A", webpage_url="https://a.example", requested_by=1)
    store.get(fake_guild.id).queue.append(track)
    source.resolve_results = deque([resolved_track_for(track)])

    await player.pause(guild)
    assert fake_voice_client.is_playing() is False

    await player.play_next(guild)
    await player.pause(guild)
    assert fake_voice_client.is_paused() is True

    await player.resume(guild)
    assert fake_voice_client.is_playing() is True


@pytest.mark.asyncio
async def test_set_volume_clamps_and_updates_live_source(
    fake_guild: FakeGuild,
    fake_voice_client: FakeVoiceClient,
    patch_voice_source: None,
) -> None:
    """C3-05/06: set_volume clamps 0-100 and updates live voice_source."""
    _ = fake_voice_client
    player, store, source, _ = make_player()
    guild = guild_as_discord(fake_guild)
    track = Track(title="A", webpage_url="https://a.example", requested_by=1)
    store.get(fake_guild.id).queue.append(track)
    source.resolve_results = deque([resolved_track_for(track)])

    await player.play_next(guild)
    player.set_volume(guild, 150)
    state = store.get(fake_guild.id)
    assert state.volume == 100
    assert state.voice_source is not None
    assert state.voice_source.volume == 1.0

    player.set_volume(guild, 25)
    assert state.volume == 25
    assert state.voice_source.volume == 0.25


@pytest.mark.asyncio
async def test_stop_clears_state_and_disconnects(
    fake_guild: FakeGuild,
    fake_voice_client: FakeVoiceClient,
    patch_voice_source: None,
) -> None:
    """C4-01/02: stop clears queue, resets state, and disconnects."""
    _ = patch_voice_source
    player, store, source, _ = make_player()
    guild = guild_as_discord(fake_guild)
    track = Track(title="A", webpage_url="https://a.example", requested_by=1)
    state = store.get(fake_guild.id)
    state.queue.append(track)
    state.current = track
    state.loop = True
    source.resolve_results = deque([resolved_track_for(track)])
    await player.play_next(guild)

    await player.stop(guild)

    assert len(state.queue) == 0
    assert state.current is None
    assert state.loop is False
    assert state.voice_source is None
    assert fake_guild.voice_client is None


@pytest.mark.asyncio
async def test_snapshot_returns_current_and_queue_copy(
    fake_guild: FakeGuild,
) -> None:
    """C4-03/04: snapshot returns current and a copy of the queue."""
    player, store, _, _ = make_player()
    guild = guild_as_discord(fake_guild)
    current = Track(title="Now", webpage_url="https://now.example", requested_by=1)
    upcoming = Track(title="Later", webpage_url="https://later.example", requested_by=2)
    state = store.get(fake_guild.id)
    state.current = current
    state.queue.append(upcoming)

    snap_current, snap_upcoming = player.snapshot(guild)

    assert snap_current == current
    assert snap_upcoming == [upcoming]
    state.queue.clear()
    assert snap_upcoming == [upcoming]


@pytest.mark.asyncio
async def test_enqueue_appends_to_queue(
    fake_guild: FakeGuild,
) -> None:
    """enqueue appends a track to the guild queue."""
    player, store, _, _ = make_player()
    guild = guild_as_discord(fake_guild)
    track = Track(title="Queued", webpage_url="https://q.example", requested_by=1)

    await player.enqueue(guild, track)

    assert list(store.get(fake_guild.id).queue) == [track]


@pytest.mark.asyncio
async def test_play_next_no_voice_client_is_noop(
    fake_guild: FakeGuild,
    patch_voice_source: None,
) -> None:
    """play_next returns immediately when not connected to voice."""
    _ = patch_voice_source
    player, store, source, _ = make_player()
    guild = guild_as_discord(fake_guild)
    fake_guild.voice_client = None
    track = Track(title="A", webpage_url="https://a.example", requested_by=1)
    store.get(fake_guild.id).queue.append(track)

    await player.play_next(guild)

    assert source.resolve_calls == []


@pytest.mark.asyncio
async def test_enqueue_raises_when_queue_full(
    fake_guild: FakeGuild,
) -> None:
    """enqueue raises QueueFullError at QUEUE_LIMIT."""
    from cadence.player import QueueFullError
    from cadence.state import QUEUE_LIMIT

    player, store, _, _ = make_player()
    guild = guild_as_discord(fake_guild)
    state = store.get(fake_guild.id)
    for index in range(QUEUE_LIMIT):
        state.queue.append(
            Track(title=f"T{index}", webpage_url=f"https://example.com/{index}", requested_by=1)
        )
    track = Track(title="Overflow", webpage_url="https://overflow.example", requested_by=1)

    with pytest.raises(QueueFullError):
        await player.enqueue(guild, track)


@pytest.mark.asyncio
async def test_clear_queue_preserves_current(
    fake_guild: FakeGuild,
    fake_voice_client: FakeVoiceClient,
) -> None:
    """clear_queue empties upcoming tracks but leaves current playing."""
    _ = fake_voice_client
    player, store, _, _ = make_player()
    guild = guild_as_discord(fake_guild)
    state = store.get(fake_guild.id)
    current = Track(title="Now", webpage_url="https://now.example", requested_by=1)
    state.current = current
    state.queue.append(Track(title="Next", webpage_url="https://next.example", requested_by=1))

    count = await player.clear_queue(guild)

    assert count == 1
    assert state.current is current
    assert list(state.queue) == []


@pytest.mark.asyncio
async def test_remove_at_position_one_clears_without_voice(
    fake_guild: FakeGuild,
) -> None:
    """remove_at(1) clears current even when not connected to voice."""
    player, store, _, _ = make_player()
    guild = guild_as_discord(fake_guild)
    state = store.get(fake_guild.id)
    state.current = Track(title="Now", webpage_url="https://now.example", requested_by=1)
    fake_guild.voice_client = None

    removed = await player.remove_at(guild, 1)

    assert removed.title == "Now"
    assert state.current is None


@pytest.mark.asyncio
async def test_remove_at_position_one_stops_voice(
    fake_guild: FakeGuild,
    fake_voice_client: FakeVoiceClient,
) -> None:
    """remove_at(1) stops the voice client when connected."""
    player, store, _, _ = make_player()
    guild = guild_as_discord(fake_guild)
    state = store.get(fake_guild.id)
    state.current = Track(title="Now", webpage_url="https://now.example", requested_by=1)
    fake_voice_client.play("source")

    removed = await player.remove_at(guild, 1)

    assert removed.title == "Now"
    assert state.current is None
    assert fake_voice_client._playing is False


@pytest.mark.asyncio
async def test_remove_at_position_n_removes_from_queue(
    fake_guild: FakeGuild,
) -> None:
    """remove_at(N) removes the Nth upcoming track."""
    player, store, _, _ = make_player()
    guild = guild_as_discord(fake_guild)
    state = store.get(fake_guild.id)
    one = Track(title="One", webpage_url="https://one.example", requested_by=1)
    two = Track(title="Two", webpage_url="https://two.example", requested_by=1)
    state.queue.extend([one, two])

    removed = await player.remove_at(guild, 2)

    assert removed.title == "Two"
    assert list(state.queue) == [one]


@pytest.mark.asyncio
async def test_interrupt_clears_and_stops(
    fake_guild: FakeGuild,
    fake_voice_client: FakeVoiceClient,
) -> None:
    """interrupt clears queue, disables loop, and stops active playback."""
    player, store, _, _ = make_player()
    guild = guild_as_discord(fake_guild)
    state = store.get(fake_guild.id)
    state.loop = True
    state.current = Track(title="Now", webpage_url="https://now.example", requested_by=1)
    state.queue.append(Track(title="Next", webpage_url="https://next.example", requested_by=1))
    fake_voice_client.play("source")

    was_active = await player.interrupt(guild)

    assert was_active is True
    assert state.loop is False
    assert state.current is None
    assert list(state.queue) == []


@pytest.mark.asyncio
async def test_remove_at_invalid_position_raises(
    fake_guild: FakeGuild,
) -> None:
    """remove_at raises ValueError for out-of-range positions."""
    player, store, _, _ = make_player()
    guild = guild_as_discord(fake_guild)
    state = store.get(fake_guild.id)
    state.queue.append(Track(title="One", webpage_url="https://one.example", requested_by=1))

    with pytest.raises(ValueError, match="No track at position"):
        await player.remove_at(guild, 5)

    state.queue.clear()
    with pytest.raises(ValueError, match="No track at position"):
        await player.remove_at(guild, 1)


@pytest.mark.asyncio
async def test_interrupt_idle_returns_false(
    fake_guild: FakeGuild,
) -> None:
    """interrupt returns False when voice is not active."""
    player, _, _, _ = make_player()
    guild = guild_as_discord(fake_guild)

    was_active = await player.interrupt(guild)

    assert was_active is False
