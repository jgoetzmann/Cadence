"""Tests for cadence.sources.youtube."""

from __future__ import annotations

import io
import logging
import subprocess
import threading
from typing import Any, cast

import pytest
from yt_dlp.networking.impersonate import ImpersonateTarget

from cadence.interfaces import AudioSource, ResolvedTrack
from cadence.sources import youtube as youtube_module
from cadence.sources.youtube import (
    DEFAULT_PLAYER_CLIENTS,
    FFMPEG_OPTS,
    FFMPEG_PIPE_OPTS,
    SourceError,
    YouTubeSource,
    YtDlpConfig,
    _ManagedPipeSource,
    _PrefixedReader,
    _read_first_playback_chunk,
    _ytdlp_playback_command,
    build_ytdl_opts,
    make_ffmpeg_source,
    make_playback_source,
)
from tests.fakes import (
    FakeYoutubeDL,
    patch_ytdl,
    search_result,
    ytdl_entry,
)


def test_build_ytdl_opts_includes_cookie_file_when_set() -> None:
    opts = build_ytdl_opts(YtDlpConfig(cookie_file="/opt/cadence/youtube_cookies.txt"))
    assert opts["cookiefile"] == "/opt/cadence/youtube_cookies.txt"


def test_build_ytdl_opts_omits_cookie_file_by_default() -> None:
    opts = build_ytdl_opts()
    assert "cookiefile" not in opts


def test_build_ytdl_opts_includes_player_client_rotation() -> None:
    opts = build_ytdl_opts()
    assert opts["extractor_args"]["youtube"]["player_client"] == list(DEFAULT_PLAYER_CLIENTS)


def test_build_ytdl_opts_includes_ejs_remote_components() -> None:
    opts = build_ytdl_opts()
    assert opts["remote_components"] == ["ejs:github"]


def test_ffmpeg_pipe_opts_use_low_latency_flags() -> None:
    assert "analyzeduration 0" in FFMPEG_PIPE_OPTS["before_options"]
    assert "nobuffer" in FFMPEG_PIPE_OPTS["before_options"]


def test_prefixed_reader_serves_prefix_before_stream() -> None:
    stream = io.BytesIO(b"world")
    reader = _PrefixedReader(stream, b"hello ")
    assert reader.read(3) == b"hel"
    assert reader.read() == b"lo world"


def test_ytdlp_playback_command_includes_proxy_and_impersonate() -> None:
    cmd = _ytdlp_playback_command(
        "https://www.youtube.com/watch?v=abc",
        YtDlpConfig(
            proxy="socks5h://127.0.0.1:1080",
            impersonate="chrome",
            cookie_file="/opt/cookies.txt",
        ),
    )
    assert cmd[-1] == "https://www.youtube.com/watch?v=abc"
    assert "--proxy" in cmd
    assert "socks5h://127.0.0.1:1080" in cmd
    assert "--impersonate" in cmd
    assert "chrome" in cmd
    assert "--cookies" in cmd
    assert "/opt/cookies.txt" in cmd
    assert f"youtube:player_client={','.join(DEFAULT_PLAYER_CLIENTS)}" in " ".join(cmd)


def test_build_ytdl_opts_sets_proxy_and_impersonate_when_provided() -> None:
    opts = build_ytdl_opts(
        YtDlpConfig(
            proxy="socks5h://127.0.0.1:1080",
            impersonate="chrome",
        ),
    )
    assert opts["proxy"] == "socks5h://127.0.0.1:1080"
    assert opts["impersonate"] == ImpersonateTarget.from_str("chrome")


def test_build_ytdl_opts_sets_socket_timeout() -> None:
    opts = build_ytdl_opts()
    assert opts["socket_timeout"] == 45


def test_build_ytdl_opts_omits_proxy_and_impersonate_when_unset() -> None:
    opts = build_ytdl_opts(YtDlpConfig(proxy=None, impersonate=None))
    assert "proxy" not in opts
    assert "impersonate" not in opts


async def test_fetch_retries_without_impersonate_on_bot_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    class RecordingYDL:
        def __init__(self, opts: dict[str, object]) -> None:
            self._impersonate = opts.get("impersonate")

        def extract_info(self, _target: str, *, download: bool) -> dict[str, object]:
            nonlocal attempts
            _ = download
            attempts += 1
            if self._impersonate is not None:
                msg = "Sign in to confirm you're not a bot"
                raise RuntimeError(msg)
            return ytdl_entry()

    monkeypatch.setattr(youtube_module, "_shared_ytdl", {})
    monkeypatch.setattr(youtube_module.yt_dlp, "YoutubeDL", RecordingYDL)
    source = YouTubeSource(YtDlpConfig(impersonate="chrome"))

    track = await source.fetch("foo", is_url=False)

    assert track.title == "Foo Song"
    assert attempts == 2


def test_youtube_source_is_audio_source(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_ytdl(monkeypatch, FakeYoutubeDL(results=[search_result()]))
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

    monkeypatch.setattr(youtube_module, "_shared_ytdl", {})
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


def test_youtube_source_instances_with_different_configs_do_not_share_ytdl(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeYoutubeDL(results=[search_result()])
    patch_ytdl(monkeypatch, fake)

    without_proxy = YouTubeSource(YtDlpConfig())
    with_proxy = YouTubeSource(YtDlpConfig(proxy="socks5h://127.0.0.1:1080"))

    assert without_proxy._ytdl is not with_proxy._ytdl


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


class _FakeProcess:
    """Stands in for the yt-dlp `subprocess.Popen` handle."""

    def __init__(
        self,
        *,
        stdout: object = None,
        stderr: object = None,
        poll_results: list[int | None] | None = None,
        returncode: int | None = 0,
        wait_raises: bool = False,
    ) -> None:
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode
        self._poll_results = poll_results if poll_results is not None else [None]
        self.kill_calls = 0
        self.wait_calls = 0
        self._wait_raises = wait_raises

    def poll(self) -> int | None:
        if len(self._poll_results) > 1:
            return self._poll_results.pop(0)
        return self._poll_results[0]

    def kill(self) -> None:
        self.kill_calls += 1

    def wait(self, timeout: float | None = None) -> int:
        self.wait_calls += 1
        if self._wait_raises:
            self._wait_raises = False
            raise subprocess.TimeoutExpired(cmd="yt-dlp", timeout=timeout or 0)
        return self.returncode or 0


def test_prefixed_reader_reads_straight_from_stream_once_prefix_is_drained() -> None:
    reader = _PrefixedReader(io.BytesIO(b"world"), b"hi ")

    assert reader.readable() is True
    assert reader.read(3) == b"hi "
    assert reader.read(2) == b"wo"
    assert reader.read() == b"rld"


def test_prefixed_reader_sized_read_spans_prefix_and_stream() -> None:
    reader = _PrefixedReader(io.BytesIO(b"world"), b"hi ")

    assert reader.read(5) == b"hi wo"


def test_read_first_playback_chunk_returns_once_min_bytes_are_buffered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(youtube_module.os, "name", "nt")
    process = _FakeProcess()

    data = _read_first_playback_chunk(io.BytesIO(b"a" * 64), process, min_bytes=16)

    assert data == b"a" * 64


def test_read_first_playback_chunk_stops_early_when_ytdlp_exits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(youtube_module.os, "name", "nt")
    process = _FakeProcess(poll_results=[1])

    data = _read_first_playback_chunk(io.BytesIO(b"short"), process, min_bytes=4096)

    assert data == b"short"


def test_read_first_playback_chunk_retries_while_ytdlp_is_still_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(youtube_module.os, "name", "nt")
    sleeps: list[float] = []
    monkeypatch.setattr(youtube_module.time, "sleep", sleeps.append)
    stream = io.BytesIO(b"")
    process = _FakeProcess(poll_results=[None, 0])

    with pytest.raises(SourceError):
        _read_first_playback_chunk(stream, process, min_bytes=4096)

    assert sleeps == [0.05]


def test_read_first_playback_chunk_raises_when_no_audio_arrives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(youtube_module.os, "name", "nt")
    process = _FakeProcess(poll_results=[1])

    with pytest.raises(SourceError, match="Timed out waiting for playback audio stream"):
        _read_first_playback_chunk(io.BytesIO(b""), process, min_bytes=4096)


def test_read_first_playback_chunk_waits_for_readiness_on_posix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(youtube_module.os, "name", "posix")
    stream = io.BytesIO(b"a" * 32)
    readiness: list[tuple[list[object], list[object], list[object]]] = [
        ([], [], []),
        ([stream], [], []),
    ]
    monkeypatch.setattr(
        youtube_module.select,
        "select",
        lambda *args, **kwargs: readiness.pop(0) if readiness else ([stream], [], []),
    )
    process = _FakeProcess()

    data = _read_first_playback_chunk(stream, process, min_bytes=16)

    assert data == b"a" * 32


def test_read_first_playback_chunk_breaks_when_unready_process_has_exited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(youtube_module.os, "name", "posix")
    monkeypatch.setattr(youtube_module.select, "select", lambda *a, **k: ([], [], []))
    process = _FakeProcess(poll_results=[1])

    with pytest.raises(SourceError):
        _read_first_playback_chunk(io.BytesIO(b""), process, min_bytes=16)


class _FakeFFmpeg:
    def __init__(self, source: object = None, **kwargs: object) -> None:
        self.source = source
        self.kwargs = kwargs
        self.cleaned = False

    def read(self) -> bytes:
        return b"pcm"

    def is_opus(self) -> bool:
        return False

    def cleanup(self) -> None:
        self.cleaned = True


def test_managed_pipe_source_delegates_reads_to_ffmpeg() -> None:
    ffmpeg = _FakeFFmpeg()
    source = _ManagedPipeSource(cast(Any, _FakeProcess()), cast(Any, ffmpeg))

    assert source.read() == b"pcm"
    assert source.is_opus() is False


def test_managed_pipe_source_cleanup_kills_a_running_ytdlp() -> None:
    ffmpeg = _FakeFFmpeg()
    process = _FakeProcess(poll_results=[None])
    source = _ManagedPipeSource(cast(Any, process), cast(Any, ffmpeg))

    source.cleanup()

    assert ffmpeg.cleaned is True
    assert process.kill_calls == 1
    assert process.wait_calls == 1


def test_managed_pipe_source_cleanup_kills_again_when_wait_times_out() -> None:
    process = _FakeProcess(poll_results=[0], wait_raises=True)
    source = _ManagedPipeSource(cast(Any, process), cast(Any, _FakeFFmpeg()))

    source.cleanup()

    assert process.kill_calls == 1


def test_managed_pipe_source_cleanup_logs_stderr_when_ytdlp_failed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    process = _FakeProcess(
        stderr=io.BytesIO(b"ERROR: sign in to confirm\n"),
        poll_results=[2],
        returncode=2,
    )
    source = _ManagedPipeSource(cast(Any, process), cast(Any, _FakeFFmpeg()))

    with caplog.at_level(logging.WARNING, logger="cadence.sources.youtube"):
        source.cleanup()

    assert "sign in to confirm" in caplog.text


def test_managed_pipe_source_cleanup_stays_quiet_on_clean_exit(
    caplog: pytest.LogCaptureFixture,
) -> None:
    process = _FakeProcess(stderr=io.BytesIO(b""), poll_results=[0], returncode=0)
    source = _ManagedPipeSource(cast(Any, process), cast(Any, _FakeFFmpeg()))

    with caplog.at_level(logging.WARNING, logger="cadence.sources.youtube"):
        source.cleanup()

    assert caplog.text == ""


def test_make_playback_source_pipes_ytdlp_stdout_into_ffmpeg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(youtube_module.os, "name", "nt")
    process = _FakeProcess(stdout=io.BytesIO(b"a" * 16_384))
    commands: list[list[str]] = []

    def fake_popen(cmd: list[str], **kwargs: object) -> _FakeProcess:
        commands.append(cmd)
        return process

    transformed: dict[str, object] = {}

    class FakePCMVolumeTransformer:
        def __init__(self, raw: object, *, volume: float) -> None:
            transformed["raw"] = raw
            transformed["volume"] = volume

    monkeypatch.setattr(youtube_module.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(youtube_module.discord, "FFmpegPCMAudio", _FakeFFmpeg)
    monkeypatch.setattr(youtube_module.discord, "PCMVolumeTransformer", FakePCMVolumeTransformer)

    result = make_playback_source("https://youtu.be/abc", 60)

    assert isinstance(result, FakePCMVolumeTransformer)
    assert transformed["volume"] == 0.6
    assert isinstance(transformed["raw"], _ManagedPipeSource)
    assert commands[0][-1] == "https://youtu.be/abc"


def test_make_playback_source_raises_without_a_stdout_pipe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        youtube_module.subprocess,
        "Popen",
        lambda *args, **kwargs: _FakeProcess(stdout=None),
    )

    with pytest.raises(SourceError, match="missing stdout pipe"):
        make_playback_source("https://youtu.be/abc", 50)
