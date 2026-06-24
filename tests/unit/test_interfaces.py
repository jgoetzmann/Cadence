"""Tests for cadence.interfaces."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from cadence.interfaces import AudioSource, Player, ResolvedTrack
from cadence.state import LoopMode, Track


def test_resolved_track_is_immutable() -> None:
    track = ResolvedTrack(
        title="Song",
        webpage_url="https://example.com/watch?v=1",
        stream_url="https://stream.example/audio",
        duration=180,
    )
    assert track.duration == 180
    with pytest.raises(FrozenInstanceError):
        track.title = "Other"  # type: ignore[misc]


class _ConcreteAudioSource:
    async def fetch(self, query: str, *, is_url: bool) -> ResolvedTrack:
        _ = (query, is_url)
        return ResolvedTrack(
            title="Song",
            webpage_url="https://example.com/watch?v=1",
            stream_url="https://stream.example/audio",
        )

    async def resolve(self, webpage_url: str) -> ResolvedTrack:
        return ResolvedTrack(
            title="Song",
            webpage_url=webpage_url,
            stream_url="https://stream.example/audio",
        )


class _ConcretePlayer:
    async def enqueue(self, guild: object, track: Track) -> None:
        _ = (guild, track)

    async def clear_queue(self, guild: object) -> int:
        _ = guild
        return 0

    def reset_lineup(self, guild: object) -> None:
        _ = guild

    async def remove_at(self, guild: object, position: int) -> Track:
        _ = (guild, position)
        return Track(title="X", webpage_url="https://example.com", requested_by=1)

    async def interrupt(self, guild: object) -> bool:
        _ = guild
        return False

    async def play_next(self, guild: object, *, announce: bool = True) -> None:
        _ = (guild, announce)

    async def skip(self, guild: object) -> None:
        _ = guild

    async def pause(self, guild: object) -> None:
        _ = guild

    async def resume(self, guild: object) -> None:
        _ = guild

    async def stop(self, guild: object) -> None:
        _ = guild

    def set_loop_mode(self, guild: object, mode: LoopMode) -> None:
        _ = (guild, mode)

    def set_volume(self, guild: object, level: int) -> None:
        _ = (guild, level)

    def snapshot(self, guild: object) -> tuple[Track | None, list[Track]]:
        _ = guild
        return None, []


def test_protocols_are_runtime_checkable() -> None:
    assert isinstance(_ConcreteAudioSource(), AudioSource)
    assert isinstance(_ConcretePlayer(), Player)
