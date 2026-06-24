"""Tests for cadence.sources.youtube."""

from __future__ import annotations

import threading

import pytest

from cadence.interfaces import AudioSource, ResolvedTrack
from cadence.sources import youtube as youtube_module
from cadence.sources.youtube import (
    FFMPEG_OPTS,
    SourceError,
    YouTubeSource,
    make_ffmpeg_source,
)
from tests.fakes import (
    FakeYoutubeDL,
    patch_ytdl,
    search_result,
    ytdl_entry,
)


def test_youtube_source_satisfies_audio_source_protocol() -> None:
    assert isinstance(YouTubeSource(), AudioSource)


async def test_fetch_search_returns_first_ytsearch_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeYoutubeDL(results=[search_result()])
    patch_ytdl(monkeypatch, fake)

    source = YouTubeSource()
    track = await source.fetch("foo", is_url=False)

    assert track == ResolvedTrack(
        title="Foo Song",
        webpage_url="https://youtube.com/watch?v=abc",
        stream_url="https://stream.example/audio",
        duration=180,
    )
    assert fake.calls == [("ytsearch1:foo", False)]


async def test_resolve_returns_fresh_stream_url_each_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeYoutubeDL(
        results=[
            ytdl_entry(url="https://stream.example/first"),
            ytdl_entry(url="https://stream.example/second"),
        ],
    )
    patch_ytdl(monkeypatch, fake)
    source = YouTubeSource()
    url = "https://youtube.com/watch?v=abc"

    first = await source.resolve(url)
    second = await source.resolve(url)

    assert first.stream_url == "https://stream.example/first"
    assert second.stream_url == "https://stream.example/second"
    assert fake.calls == [(url, False), (url, False)]


@pytest.mark.parametrize(
    "result",
    [
        None,
        {"entries": []},
        {"entries": [None]},
    ],
)
async def test_fetch_raises_source_error_on_empty_result(
    monkeypatch: pytest.MonkeyPatch,
    result: dict[str, object] | None,
) -> None:
    fake = FakeYoutubeDL(results=[result])
    patch_ytdl(monkeypatch, fake)
    source = YouTubeSource()

    with pytest.raises(SourceError, match="No result"):
        await source.fetch("foo", is_url=False)


async def test_resolve_raises_source_error_on_empty_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeYoutubeDL(results=[None])
    patch_ytdl(monkeypatch, fake)
    source = YouTubeSource()

    with pytest.raises(SourceError, match="No result"):
        await source.resolve("https://youtube.com/watch?v=abc")


async def test_fetch_builds_webpage_url_from_video_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeYoutubeDL(
        results=[
            {
                "entries": [
                    {
                        "title": "Fallback Song",
                        "id": "xyz123",
                        "url": "https://stream.example/audio",
                        "duration": 200.0,
                    },
                ],
            },
        ],
    )
    patch_ytdl(monkeypatch, fake)
    source = YouTubeSource()

    track = await source.fetch("fallback", is_url=False)

    assert track == ResolvedTrack(
        title="Fallback Song",
        webpage_url="https://www.youtube.com/watch?v=xyz123",
        stream_url="https://stream.example/audio",
        duration=200,
    )


async def test_fetch_raises_source_error_when_stream_url_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeYoutubeDL(results=[{"entries": [{"title": "No URL", "id": "abc"}]}])
    patch_ytdl(monkeypatch, fake)
    source = YouTubeSource()

    with pytest.raises(SourceError, match="No stream URL"):
        await source.fetch("foo", is_url=False)


async def test_fetch_wraps_ytdlp_exceptions_in_source_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenYDL:
        def extract_info(self, _target: str, *, download: bool) -> dict[str, object]:
            _ = download
            msg = "network down"
            raise RuntimeError(msg)

    monkeypatch.setattr(youtube_module, "_shared_ytdl", None)
    monkeypatch.setattr(
        youtube_module.yt_dlp,
        "YoutubeDL",
        lambda _opts: BrokenYDL(),
    )
    source = YouTubeSource()

    with pytest.raises(SourceError, match="Failed to extract") as exc_info:
        await source.fetch("foo", is_url=False)

    assert isinstance(exc_info.value.__cause__, RuntimeError)


def test_youtube_source_instances_share_one_ytdl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeYoutubeDL(results=[search_result()])
    patch_ytdl(monkeypatch, fake)

    first = YouTubeSource()
    second = YouTubeSource()

    assert first._ytdl is second._ytdl


async def test_blocking_extract_runs_off_event_loop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main_thread = threading.get_ident()
    thread_ids: list[int] = []

    def on_extract(_target: str, _download: bool) -> None:
        thread_ids.append(threading.get_ident())

    fake = FakeYoutubeDL(results=[search_result()], on_extract=on_extract)
    patch_ytdl(monkeypatch, fake)
    source = YouTubeSource()

    await source.fetch("foo", is_url=False)

    assert thread_ids
    assert thread_ids[0] != main_thread


def test_make_ffmpeg_source_wraps_pcm_at_volume(monkeypatch: pytest.MonkeyPatch) -> None:
    constructed: dict[str, object] = {}

    class FakeFFmpegPCMAudio:
        def __init__(self, stream_url: str, **kwargs: str) -> None:
            constructed["stream_url"] = stream_url
            constructed["ffmpeg_opts"] = kwargs

    class FakePCMVolumeTransformer:
        def __init__(self, raw: object, *, volume: float) -> None:
            constructed["raw"] = raw
            constructed["volume"] = volume

    monkeypatch.setattr(youtube_module.discord, "FFmpegPCMAudio", FakeFFmpegPCMAudio)
    monkeypatch.setattr(youtube_module.discord, "PCMVolumeTransformer", FakePCMVolumeTransformer)

    result = make_ffmpeg_source("https://stream.example/audio", 40)

    assert isinstance(result, FakePCMVolumeTransformer)
    assert constructed["stream_url"] == "https://stream.example/audio"
    assert constructed["ffmpeg_opts"] == FFMPEG_OPTS
    assert constructed["volume"] == 0.4


async def test_fetch_url_uses_direct_resolve_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeYoutubeDL(results=[ytdl_entry()])
    patch_ytdl(monkeypatch, fake)
    source = YouTubeSource()
    url = "https://youtu.be/x"

    await source.fetch(url, is_url=True)

    assert fake.calls == [(url, False)]


async def test_fetch_search_uses_ytsearch_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeYoutubeDL(results=[search_result()])
    patch_ytdl(monkeypatch, fake)
    source = YouTubeSource()

    await source.fetch("some terms", is_url=False)

    assert fake.calls == [("ytsearch1:some terms", False)]
