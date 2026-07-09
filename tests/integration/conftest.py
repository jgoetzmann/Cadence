"""Fixtures for integration and acceptance tests."""

from __future__ import annotations

from typing import cast

import pytest

from tests.fakes import FakeYoutubeDL, patch_ytdl, ytdl_entry
from tests.integration.acceptance_helpers import AcceptanceContext, make_acceptance_context
from tests.integration.helpers import FakePCMVolumeTransformer

__all__ = [
    "acceptance_ctx",
    "captured_stream_urls",
    "patch_voice_source",
    "patch_ytdl_fixture",
]


@pytest.fixture
def captured_stream_urls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Record stream URLs used during playback in integration tests."""
    urls: list[str] = []

    def fake_transformer(
        source: object,
        volume: float = 1.0,
    ) -> FakePCMVolumeTransformer:
        return FakePCMVolumeTransformer(source=source, volume=volume)

    def fake_pcm(stream_url: str, **kwargs: object) -> str:
        _ = kwargs
        urls.append(stream_url)
        return f"pcm:{stream_url}"

    def fake_make_playback(
        webpage_url: str,
        volume: int,
        config: object,
    ) -> FakePCMVolumeTransformer:
        from cadence.sources.youtube import YtDlpConfig, _extract_with_fallback, make_ffmpeg_source

        cfg = config if isinstance(config, YtDlpConfig) else YtDlpConfig()
        resolved = _extract_with_fallback(cfg, webpage_url, search=False)
        return cast(
            FakePCMVolumeTransformer,
            make_ffmpeg_source(resolved.stream_url, volume),
        )

    monkeypatch.setattr("cadence.sources.youtube.discord.FFmpegPCMAudio", fake_pcm)
    monkeypatch.setattr(
        "cadence.sources.youtube.discord.PCMVolumeTransformer",
        fake_transformer,
    )
    monkeypatch.setattr("cadence.sources.youtube.make_playback_source", fake_make_playback)
    return urls


@pytest.fixture
def patch_voice_source(captured_stream_urls: list[str]) -> list[str]:
    """Avoid spawning real FFmpeg processes; return captured stream URLs."""
    return captured_stream_urls


@pytest.fixture
def patch_ytdl_fixture(monkeypatch: pytest.MonkeyPatch) -> FakeYoutubeDL:
    """Provide a default FakeYoutubeDL patched into YouTubeSource."""
    fake = FakeYoutubeDL(results=[ytdl_entry()])
    patch_ytdl(monkeypatch, fake)
    return fake


@pytest.fixture
async def acceptance_ctx(
    captured_stream_urls: list[str],
) -> AcceptanceContext:
    """Command acceptance harness with a real Player and scripted AudioSource."""
    _ = captured_stream_urls
    return make_acceptance_context()
