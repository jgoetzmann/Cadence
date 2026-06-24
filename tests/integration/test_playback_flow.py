"""Integration tests for Player + YouTubeSource playback flows."""

from __future__ import annotations

import threading

import pytest

from cadence.sources import youtube as youtube_module
from tests.fakes import FakeGuild, FakeTextChannel, FakeVoiceClient, FakeYoutubeDL, ytdl_entry
from tests.integration.helpers import (
    advance_after,
    guild_as_discord,
    make_integration_player,
    make_patched_integration_player,
    make_track,
)


def _resolve_result_for(track_url: str, *, stream_url: str, title: str) -> dict[str, object]:
    """Build a direct-resolve yt-dlp result (no entries wrapper)."""
    return ytdl_entry(title=title, webpage_url=track_url, url=stream_url)


@pytest.mark.asyncio
async def test_full_track_after_callback_advances_to_next_track(
    fake_guild: FakeGuild,
    fake_voice_client: FakeVoiceClient,
    captured_stream_urls: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T2-01: a playing track completes via after-callback and advances to the next."""
    track1 = make_track("First", "https://youtube.com/watch?v=first")
    track2 = make_track("Second", "https://youtube.com/watch?v=second")
    fake_ytdl = FakeYoutubeDL(
        results=[
            _resolve_result_for(
                track1.webpage_url,
                stream_url="https://stream.example/1",
                title="First",
            ),
            _resolve_result_for(
                track2.webpage_url,
                stream_url="https://stream.example/2",
                title="Second",
            ),
        ],
    )
    player, store, _, _ = make_patched_integration_player(monkeypatch, fake_ytdl)
    guild = guild_as_discord(fake_guild)
    text_channel = FakeTextChannel(id=300)
    state = store.get(fake_guild.id)
    state.text_channel = text_channel
    state.queue.extend([track1, track2])

    await player.play_next(guild)

    assert state.current == track1
    assert len(state.queue) == 1
    assert fake_voice_client.is_playing() is True
    assert captured_stream_urls == ["https://stream.example/1"]
    assert len(text_channel.sent) == 1
    assert text_channel.sent[0].content == "▶️ Now playing: **First**"

    await advance_after(fake_voice_client)

    assert state.current == track2
    assert len(state.queue) == 0
    assert fake_ytdl.calls == [
        (track1.webpage_url, False),
        (track2.webpage_url, False),
    ]
    assert fake_voice_client.is_playing() is True
    assert captured_stream_urls == [
        "https://stream.example/1",
        "https://stream.example/2",
    ]
    assert len(text_channel.sent) == 2
    assert text_channel.sent[1].content == "▶️ Now playing: **Second**"


@pytest.mark.asyncio
async def test_loop_re_resolves_stream_url_each_cycle(
    fake_guild: FakeGuild,
    fake_voice_client: FakeVoiceClient,
    captured_stream_urls: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T2-02: loop replays current track and re-resolves a fresh stream URL each cycle."""
    track = make_track("Loop Song", "https://youtube.com/watch?v=loop")
    fake_ytdl = FakeYoutubeDL(
        results=[
            ytdl_entry(url="https://stream.example/a"),
            ytdl_entry(url="https://stream.example/b"),
            ytdl_entry(url="https://stream.example/c"),
        ],
    )
    player, store, _, _ = make_patched_integration_player(monkeypatch, fake_ytdl)
    guild = guild_as_discord(fake_guild)
    text_channel = FakeTextChannel(id=300)
    state = store.get(fake_guild.id)
    state.text_channel = text_channel
    state.current = track
    state.loop = True

    await player.play_next(guild)
    await advance_after(fake_voice_client)
    await advance_after(fake_voice_client)

    assert state.current == track
    assert text_channel.sent == []
    assert fake_ytdl.calls == [
        (track.webpage_url, False),
        (track.webpage_url, False),
        (track.webpage_url, False),
    ]
    assert captured_stream_urls == [
        "https://stream.example/a",
        "https://stream.example/b",
        "https://stream.example/c",
    ]


@pytest.mark.asyncio
async def test_resolve_failure_mid_queue_skips_and_continues(
    fake_guild: FakeGuild,
    fake_voice_client: FakeVoiceClient,
    patch_voice_source: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T2-03: a YouTubeSource resolve failure mid-queue skips and continues (§5.2)."""
    _ = patch_voice_source
    bad = make_track("Bad", "https://youtube.com/watch?v=bad")
    good = make_track("Good", "https://youtube.com/watch?v=good")
    fake_ytdl = FakeYoutubeDL(
        results=[
            None,
            _resolve_result_for(
                good.webpage_url,
                stream_url="https://stream.example/good",
                title="Good",
            ),
        ],
    )
    player, store, _, _ = make_patched_integration_player(monkeypatch, fake_ytdl)
    guild = guild_as_discord(fake_guild)
    text_channel = FakeTextChannel(id=300)
    state = store.get(fake_guild.id)
    state.text_channel = text_channel
    state.queue.extend([bad, good])

    await player.play_next(guild)

    assert state.current == good
    assert state.voice_source is not None
    assert len(state.queue) == 0
    assert len(text_channel.sent) == 2
    assert text_channel.sent[0].content == "⚠️ Skipping **Bad** (couldn't load audio)."
    assert text_channel.sent[1].content == "▶️ Now playing: **Good**"


@pytest.mark.asyncio
async def test_volume_change_updates_live_pcm_transformer(
    fake_guild: FakeGuild,
    fake_voice_client: FakeVoiceClient,
    patch_voice_source: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T2-04: set_volume updates the live PCMVolumeTransformer and persists for next track."""
    _ = patch_voice_source
    track1 = make_track("One", "https://youtube.com/watch?v=one")
    track2 = make_track("Two", "https://youtube.com/watch?v=two")
    fake_ytdl = FakeYoutubeDL(
        results=[
            _resolve_result_for(
                track1.webpage_url,
                stream_url="https://stream.example/1",
                title="One",
            ),
            _resolve_result_for(
                track2.webpage_url,
                stream_url="https://stream.example/2",
                title="Two",
            ),
        ],
    )
    player, store, _, _ = make_patched_integration_player(monkeypatch, fake_ytdl)
    guild = guild_as_discord(fake_guild)
    state = store.get(fake_guild.id)
    state.queue.extend([track1, track2])

    await player.play_next(guild)
    player.set_volume(guild, 75)

    assert state.volume == 75
    assert state.voice_source is not None
    assert state.voice_source.volume == 0.75

    await advance_after(fake_voice_client)

    assert state.current == track2
    assert state.voice_source is not None
    assert state.voice_source.volume == 0.75


@pytest.mark.asyncio
async def test_pause_resume_across_queued_transition(
    fake_guild: FakeGuild,
    fake_voice_client: FakeVoiceClient,
    patch_voice_source: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T2-05: pause state does not leak across queued track transitions."""
    _ = patch_voice_source
    track1 = make_track("Paused", "https://youtube.com/watch?v=paused")
    track2 = make_track("Next", "https://youtube.com/watch?v=next")
    fake_ytdl = FakeYoutubeDL(
        results=[
            _resolve_result_for(
                track1.webpage_url,
                stream_url="https://stream.example/1",
                title="Paused",
            ),
            _resolve_result_for(
                track2.webpage_url,
                stream_url="https://stream.example/2",
                title="Next",
            ),
        ],
    )
    player, store, _, _ = make_patched_integration_player(monkeypatch, fake_ytdl)
    guild = guild_as_discord(fake_guild)
    state = store.get(fake_guild.id)
    state.queue.extend([track1, track2])

    await player.play_next(guild)
    await player.pause(guild)
    assert fake_voice_client.is_paused() is True

    await advance_after(fake_voice_client)

    assert state.current == track2
    assert fake_voice_client.is_playing() is True
    assert fake_voice_client.is_paused() is False

    await player.pause(guild)
    assert fake_voice_client.is_paused() is True

    await player.resume(guild)
    assert fake_voice_client.is_playing() is True


@pytest.mark.asyncio
async def test_ytdlp_extract_runs_off_loop_via_player_play_next(
    fake_guild: FakeGuild,
    fake_voice_client: FakeVoiceClient,
    patch_voice_source: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T2-07: yt-dlp extraction triggered by play_next runs off the event loop."""
    _ = patch_voice_source
    main_thread = threading.get_ident()
    thread_ids: list[int] = []

    def on_extract(_target: str, _download: bool) -> None:
        thread_ids.append(threading.get_ident())

    track = make_track("Thread Test", "https://youtube.com/watch?v=thread")
    fake_ytdl = FakeYoutubeDL(
        results=[
            _resolve_result_for(
                track.webpage_url,
                stream_url="https://stream.example/t",
                title="Thread Test",
            ),
        ],
        on_extract=on_extract,
    )
    player, store, _, _ = make_patched_integration_player(monkeypatch, fake_ytdl)
    guild = guild_as_discord(fake_guild)
    store.get(fake_guild.id).queue.append(track)

    await player.play_next(guild)

    assert thread_ids
    assert thread_ids[0] != main_thread


@pytest.mark.asyncio
async def test_skip_pause_resume_noop_without_voice_client(
    fake_guild: FakeGuild,
    patch_voice_source: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T2-06: skip/pause/resume return early when not connected to voice."""
    _ = patch_voice_source
    fake_ytdl = FakeYoutubeDL()
    player, _, _, _ = make_patched_integration_player(monkeypatch, fake_ytdl)
    guild = guild_as_discord(fake_guild)
    fake_guild.voice_client = None

    await player.skip(guild)
    await player.pause(guild)
    await player.resume(guild)


@pytest.mark.asyncio
async def test_resolve_builds_webpage_url_from_video_id(
    fake_guild: FakeGuild,
    fake_voice_client: FakeVoiceClient,
    patch_voice_source: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T2-06: resolve handles entries missing webpage_url but with video id."""
    _ = patch_voice_source
    track = make_track("Fallback", "https://youtube.com/watch?v=fallback")
    fake_ytdl = FakeYoutubeDL(
        results=[
            {
                "title": "Fallback",
                "id": "fallback",
                "url": "https://stream.example/fallback",
            },
            {
                "title": "Fallback",
                "id": "fallback",
                "url": "https://stream.example/fallback",
            },
        ],
    )
    player, store, source, _ = make_patched_integration_player(monkeypatch, fake_ytdl)
    guild = guild_as_discord(fake_guild)
    store.get(fake_guild.id).queue.append(track)

    resolved = await source.resolve(track.webpage_url)
    assert resolved.webpage_url == "https://www.youtube.com/watch?v=fallback"

    await player.play_next(guild)

    state = store.get(fake_guild.id)
    assert state.current == track
    assert state.voice_source is not None


@pytest.mark.asyncio
async def test_resolve_handles_missing_duration(
    fake_guild: FakeGuild,
    fake_voice_client: FakeVoiceClient,
    patch_voice_source: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T2-06: resolve accepts yt-dlp entries without a duration field."""
    _ = patch_voice_source
    track = make_track("No Duration", "https://youtube.com/watch?v=nodur")
    fake_ytdl = FakeYoutubeDL(
        results=[
            {
                "title": "No Duration",
                "webpage_url": track.webpage_url,
                "url": "https://stream.example/nodur",
            },
        ],
    )
    player, store, _, _ = make_patched_integration_player(monkeypatch, fake_ytdl)
    guild = guild_as_discord(fake_guild)
    store.get(fake_guild.id).queue.append(track)

    await player.play_next(guild)

    state = store.get(fake_guild.id)
    assert state.current == track
    assert state.voice_source is not None


@pytest.mark.asyncio
async def test_resolve_rejects_entry_without_webpage_url_or_id(
    fake_guild: FakeGuild,
    fake_voice_client: FakeVoiceClient,
    patch_voice_source: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T2-06: yt-dlp entries missing both webpage_url and id are skipped via Player."""
    _ = patch_voice_source
    track = make_track("No Url", "https://youtube.com/watch?v=nourl")
    fake_ytdl = FakeYoutubeDL(
        results=[
            {
                "title": "No Url",
                "url": "https://stream.example/nourl",
            },
        ],
    )
    player, store, _, _ = make_patched_integration_player(monkeypatch, fake_ytdl)
    guild = guild_as_discord(fake_guild)
    text_channel = FakeTextChannel(id=300)
    state = store.get(fake_guild.id)
    state.text_channel = text_channel
    state.queue.append(track)

    await player.play_next(guild)

    assert state.current is None
    assert len(text_channel.sent) == 1
    assert text_channel.sent[0].content == "⚠️ Skipping **No Url** (couldn't load audio)."


@pytest.mark.asyncio
async def test_resolve_ignores_unparseable_duration(
    fake_guild: FakeGuild,
    fake_voice_client: FakeVoiceClient,
    patch_voice_source: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T2-06: non-numeric duration values from yt-dlp are treated as unknown."""
    _ = patch_voice_source
    track = make_track("Weird Duration", "https://youtube.com/watch?v=weird")
    fake_ytdl = FakeYoutubeDL(
        results=[
            {
                "title": "Weird Duration",
                "webpage_url": track.webpage_url,
                "url": "https://stream.example/weird",
                "duration": "not-a-number",
            },
            {
                "title": "Weird Duration",
                "webpage_url": track.webpage_url,
                "url": "https://stream.example/weird",
                "duration": "not-a-number",
            },
        ],
    )
    player, store, source, _ = make_patched_integration_player(monkeypatch, fake_ytdl)
    guild = guild_as_discord(fake_guild)
    store.get(fake_guild.id).queue.append(track)

    resolved = await source.resolve(track.webpage_url)
    assert resolved.duration is None

    await player.play_next(guild)

    state = store.get(fake_guild.id)
    assert state.current == track
    assert state.voice_source is not None


@pytest.mark.asyncio
async def test_resolve_failure_raises_source_error_through_player(
    fake_guild: FakeGuild,
    fake_voice_client: FakeVoiceClient,
    patch_voice_source: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T2-06: extract exceptions from yt-dlp surface as SourceError through Player."""
    _ = patch_voice_source
    track = make_track("Broken", "https://youtube.com/watch?v=broken")

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
    player, store, _, _ = make_integration_player()
    guild = guild_as_discord(fake_guild)
    text_channel = FakeTextChannel(id=300)
    state = store.get(fake_guild.id)
    state.text_channel = text_channel
    state.queue.append(track)

    await player.play_next(guild)

    assert state.current is None
    assert len(text_channel.sent) == 1
    assert "Skipping **Broken**" in text_channel.sent[0].content
