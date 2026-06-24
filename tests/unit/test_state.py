"""Tests for cadence.state."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from cadence.state import GuildState, LoopMode, StateStore, Track, reset_idle_activity


def test_track_is_immutable() -> None:
    track = Track(
        title="Test Song",
        webpage_url="https://www.youtube.com/watch?v=abc",
        requested_by=42,
        duration=180,
    )
    assert track.title == "Test Song"
    assert track.webpage_url == "https://www.youtube.com/watch?v=abc"
    assert track.requested_by == 42
    assert track.duration == 180
    with pytest.raises(FrozenInstanceError):
        track.title = "Other"  # type: ignore[misc]


def test_track_duration_defaults_to_none() -> None:
    track = Track(
        title="Test",
        webpage_url="https://example.com",
        requested_by=1,
    )
    assert track.duration is None


def test_guild_state_defaults() -> None:
    state = GuildState()
    assert len(state.queue) == 0
    assert state.current is None
    assert state.loop_mode is LoopMode.OFF
    assert state.volume == 50
    assert state.text_channel is None
    assert state.voice_source is None
    assert state.idle_minutes == 10
    assert state.last_command_at is None
    assert state.last_song_started_at is None
    assert state.alone_since is None


def test_guild_state_volume_from_store_default() -> None:
    store = StateStore(default_volume=40)
    state = store.get(1)
    assert state.volume == 40


def test_state_store_get_creates_on_miss() -> None:
    store = StateStore(default_volume=30)
    state = store.get(1)
    assert isinstance(state, GuildState)
    assert state.volume == 30


def test_state_store_get_returns_same_instance() -> None:
    store = StateStore()
    first = store.get(1)
    second = store.get(1)
    assert first is second


def test_state_store_isolates_guilds() -> None:
    store = StateStore()
    state_a = store.get(1)
    state_b = store.get(2)
    assert state_a is not state_b


def test_state_store_discard() -> None:
    store = StateStore()
    state = store.get(1)
    store.discard(1)
    assert store.get(1) is not state


def test_state_store_discard_and_reget_uses_default_volume() -> None:
    store = StateStore(default_volume=35)
    store.get(1)
    store.discard(1)
    state = store.get(1)
    assert state.volume == 35


def test_reset_idle_activity_clears_timestamps_and_default_minutes() -> None:
    state = GuildState(
        idle_minutes=99,
        last_command_at=1.0,
        last_song_started_at=2.0,
        alone_since=3.0,
    )
    reset_idle_activity(state)
    assert state.idle_minutes == 10
    assert state.last_command_at is None
    assert state.last_song_started_at is None
    assert state.alone_since is None


def test_state_store_peek_does_not_create_entry() -> None:
    store = StateStore()
    assert store.peek(99) is None
    store.get(99)
    assert store.peek(99) is not None


def test_state_store_guild_ids() -> None:
    store = StateStore()
    store.get(1)
    store.get(2)
    assert set(store.guild_ids()) == {1, 2}


def test_guild_state_queue_is_mutable() -> None:
    state = GuildState()
    track = Track(
        title="Queued",
        webpage_url="https://example.com/watch?v=1",
        requested_by=1,
    )
    state.queue.append(track)
    assert list(state.queue) == [track]
    state.queue.popleft()
    assert len(state.queue) == 0
