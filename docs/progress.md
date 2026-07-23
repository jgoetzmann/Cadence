# Cadence — Progress (execution plan)

> **Internal / historical.** Build checklist from the original multi-agent scaffolding.
> Not required to run or contribute to Cadence.

> Status keys: `[ ]` not started · `[~]` in progress · `[x]` complete · `[!]` blocked

## How to use

Tell your agent: **"Read `.cursor/rules.mdc`, then work on Part X."**

Build order in one line: **A → T1 → (B ∥ C ∥ D) → E → (T2 ∥ T3)**.
After Foundation (A) and the test harness (T1) land, Parts B, C, and D run fully in
parallel — each owns its own source files and its own unit-test file under
`tests/unit/`, so no two agents edit the same file. B, C, and D code against the
Protocols defined in Part A (`cadence/interfaces.py`), so none of them needs another
to be finished. Part E is the composition root that wires the concrete pieces
together. T2 and T3 are the cross-module integration/acceptance suites.

Red-Green-Refactor inside implementation Parts: the `RED` task writes a failing
test, the `GREEN` task makes it pass with minimal code, the `Refactor` task cleans up
without breaking it. Coverage target is ≥90% (`overview.md §14`).

### Dependency graph

| Part | Focus | Depends on | Can parallel with |
|---|---|---|---|
| A | Foundation & infrastructure | — | — |
| T1 | Test harness & fixtures | A | — |
| B | YouTube audio source | A, T1 | C, D |
| C | Playback engine | A, T1 | B, D |
| D | Slash commands | A, T1 | B, C |
| E | Composition root & runtime wiring | A, B, C, D | — |
| T2 | Integration tests — source & engine | B, C, E | T3 |
| T3 | Acceptance tests — commands & flows | D, E | T2 |

---

## PART A — Foundation & infrastructure
> Agent instructions: Build the repo skeleton, tooling, config, logging, domain
> models, and the Protocols every other part codes against. Define interfaces
> precisely — B/C/D depend on these signatures. Do NOT implement YouTube logic,
> playback logic, or commands here. Everything else depends on you, so keep the
> public surface stable once published.

### A1 — Repo skeleton & tooling
- [x] A1-01 Create the directory layout from `overview.md §11` with `__init__.py` in every package
- [x] A1-02 Write `pyproject.toml`: metadata, `[tool.ruff]`, `[tool.mypy]` (strict), `[tool.pytest.ini_options]` (`asyncio_mode=auto`), `[tool.coverage]`
- [x] A1-03 Write `requirements.txt` (discord.py, yt-dlp, PyNaCl, python-dotenv) and `requirements-dev.txt` (pytest, pytest-asyncio, pytest-cov, ruff, mypy) per `remember.md §1`
- [x] A1-04 Write `.gitignore` ignoring `.env*`, `__pycache__/`, `.venv/`, `.pytest_cache/`, `.mypy_cache/`, `*.pyc`, `dist/` (G-001)
- [x] A1-05 Write `.env.example` listing every var from `overview.md §10` with placeholder values only
- [x] A1-06 Update `README.md` for the package layout and the `python -m cadence` run command

### A2 — Configuration
- [x] A2-01 RED: test `Settings.load()` raises a clear error when `DISCORD_TOKEN` is missing
- [x] A2-02 GREEN: implement `cadence/config.py` `Settings` dataclass + `load()` (token, guild_id, log_level, default_volume) using python-dotenv
- [x] A2-03 RED: test optional vars default correctly (`guild_id=None`, `default_volume` clamped to 0–100)
- [x] A2-04 GREEN: implement defaults, parsing, and clamping
- [x] A2-05 Refactor: ensure no secret is ever logged or stringified (G-002)

### A3 — Logging
- [x] A3-01 Implement `cadence/logging_setup.py` `configure_logging(level)` using stdlib logging
- [x] A3-02 Default the `discord` logger to WARNING; the `cadence` logger honors `LOG_LEVEL`

### A4 — Domain models & state
- [x] A4-01 RED: test `Track` is immutable and holds title/webpage_url/requested_by/duration
- [x] A4-02 GREEN: implement frozen `Track` dataclass in `cadence/state.py`
- [x] A4-03 RED: test `GuildState` defaults (empty queue, `current=None`, `loop=False`, volume from settings)
- [x] A4-04 GREEN: implement `GuildState`
- [x] A4-05 RED: test `StateStore.get(id)` creates-on-miss and returns the same instance on repeat
- [x] A4-06 GREEN: implement `StateStore` (dict-backed `get` / `discard`)
- [x] A4-07 Refactor: type hints, `__all__`, docstrings

### A5 — Interfaces (Protocols)
- [x] A5-01 Define `ResolvedTrack` dataclass (title, webpage_url, stream_url, duration) in `cadence/interfaces.py`
- [x] A5-02 Define `AudioSource` Protocol: `async fetch(query, *, is_url)->ResolvedTrack`, `async resolve(webpage_url)->ResolvedTrack`
- [x] A5-03 Define `Player` Protocol: `enqueue`, `play_next`, `skip`, `pause`, `resume`, `stop`, `set_loop`, `set_volume`, `snapshot`

### A6 — Discord client shell & entry point
- [x] A6-01 Implement `cadence/client.py` `build_client(settings)->(Client, CommandTree)` with `Intents.default()`
- [x] A6-02 Extract `sync_commands(tree, settings)`: guild copy+sync when `guild_id` set, else global sync; log identity on ready
- [x] A6-03 Implement `cadence/__main__.py` to call `cadence.app.build_app()` and run; `SystemExit` if no token
- [x] A6-04 RED: test `sync_commands` chooses the guild vs global path based on settings (fake tree)
- [x] A6-05 GREEN: make the sync-path selection pass the test

---

## PART T1 — Test harness & fixtures
> Agent instructions: Build the shared test infrastructure every other part imports.
> No production code. Publish stable fixture/fake names early so B/C/D can rely on
> them. Owns `tests/conftest.py` and `tests/fakes.py`.

### T1a — Async test config
- [x] T1-01 `tests/conftest.py`: configure pytest-asyncio (`asyncio_mode=auto`) and a `settings` fixture
- [x] T1-02 Add a `run_after(voice_client)` helper that invokes a captured FFmpeg `after` callback synchronously

### T1b — Discord & source fakes
- [x] T1-03 `FakeInteraction` (capture `defer`, `response.send_message`, `followup.send`; settable `user.voice.channel`)
- [x] T1-04 `FakeVoiceClient` (`play/stop/pause/resume/is_playing/is_paused`; capture `source` and `after`)
- [x] T1-05 `FakeGuild` + `FakeVoiceChannel` + `FakeTextChannel` helpers
- [x] T1-06 `FakeAudioSource` (scripted `ResolvedTrack`s + failure injection) and `FakePlayer`

### T1c — Foundation coverage
- [x] T1-07 Comprehensive `Settings` tests (missing token, bad `LOG_LEVEL`, volume clamp)
- [x] T1-08 `StateStore` isolation across guild IDs + `Track`/`GuildState` invariants
- [x] T1-09 Confirm the foundation package hits ≥90% line coverage locally

---

## PART B — YouTube audio source
> Agent instructions: Implement `YouTubeSource` (an `AudioSource`) in
> `cadence/sources/youtube.py`. Mock `yt_dlp` in tests — never hit the network.
> You own `cadence/sources/youtube.py` and `tests/unit/test_youtube.py`. Do NOT
> touch player or command files.

### B1 — Query resolution
- [x] B1-01 RED: `fetch("foo", is_url=False)` returns the first `ytsearch1` result mapped to `ResolvedTrack` (mock `YoutubeDL`)
- [x] B1-02 GREEN: implement `_extract` + search path (`ytsearch1:` prefix, `entries` unwrap — G-201)
- [x] B1-03 RED: `resolve(url)` returns a fresh `stream_url` for a watch URL (mock)
- [x] B1-04 GREEN: implement `resolve(webpage_url)` (re-resolve each call — G-006)
- [x] B1-05 RED: empty/`None` results raise a typed `SourceError`
- [x] B1-06 GREEN: add `SourceError` and raise on no entries / `None` info

### B2 — Async offloading
- [x] B2-01 RED: assert blocking yt-dlp calls run via `run_in_executor`, not on the loop (G-003)
- [x] B2-02 GREEN: wrap `_extract` in `loop.run_in_executor`; expose async `fetch`/`resolve`
- [x] B2-03 Refactor: single shared `YoutubeDL` instance; `YTDL_OPTS`/`FFMPEG_OPTS` as module constants (G-105, G-202)

### B3 — Stream construction
- [x] B3-01 RED: `make_ffmpeg_source(stream_url, volume)` returns an `FFmpegPCMAudio` wrapped in `PCMVolumeTransformer` at the given volume
- [x] B3-02 GREEN: implement `make_ffmpeg_source` with reconnect `before_options` and `-vn`
- [x] B3-03 RED: URL-vs-search dispatch (http/https → resolve, else search)
- [x] B3-04 GREEN: implement the `is_url` dispatch inside `fetch`

---

## PART C — Playback engine
> Agent instructions: Implement `Player` in `cadence/player.py` against the
> `AudioSource` Protocol (use `FakeAudioSource` in tests — do NOT import YouTube).
> You own `cadence/player.py` and `tests/unit/test_player.py`. Do NOT touch source
> or command files.

### C1 — Track lifecycle
- [x] C1-01 RED: `play_next` pops the queue, sets `current`, plays, posts "now playing"
- [x] C1-02 GREEN: implement the core branch logic (fresh / loop / empty — `overview.md §5.2`)
- [x] C1-03 RED: empty queue leaves `current=None` and stays connected (no disconnect — AC-8.1)
- [x] C1-04 GREEN: implement the idle branch
- [x] C1-05 RED: a resolve failure skips the track with a warning and advances
- [x] C1-06 GREEN: implement try/except around `source.resolve` → skip + recurse

### C2 — After-callback & threading
- [x] C2-01 RED: the `after` callback schedules `play_next` on the loop via `run_coroutine_threadsafe` (G-004)
- [x] C2-02 GREEN: implement `_after`; log playback errors
- [x] C2-03 RED: skip clears `current` so the loop branch is bypassed for one transition (AC-4.3)
- [x] C2-04 GREEN: implement `skip()` (clear `current` + `vc.stop()`)

### C3 — Controls (loop, pause/resume, volume)
- [x] C3-01 RED: `set_loop` toggles `state.loop`
- [x] C3-02 GREEN: implement `set_loop`
- [x] C3-03 RED: `pause()`/`resume()` call the voice client and are safe no-ops otherwise
- [x] C3-04 GREEN: implement `pause`/`resume`
- [x] C3-05 RED: `set_volume` clamps 0–100 and updates the live `PCMVolumeTransformer` when playing (AC-6.3)
- [x] C3-06 GREEN: implement `set_volume`

### C4 — Stop & introspection
- [x] C4-01 RED: `stop()` clears the queue, resets state, disconnects (AC-7.1, AC-7.2)
- [x] C4-02 GREEN: implement `stop()`
- [x] C4-03 RED: `snapshot()` returns `(current, upcoming)` for `/queue` and `/nowplaying`
- [x] C4-04 GREEN: implement `snapshot()`

---

## PART D — Slash commands
> Agent instructions: Implement the nine commands across three files, coding against
> the `Player` Protocol (use `FakePlayer`/`FakeInteraction` in tests). You own
> `cadence/commands/*` and `tests/unit/test_commands_*.py`. Do NOT touch player or
> source internals. D4 depends on D1–D3 inside this Part.

### D1 — Playback commands (`cadence/commands/playback.py`)
- [x] D1-01 RED: `/play` requires the caller in a voice channel (ephemeral error otherwise — AC-1.1)
- [x] D1-02 GREEN: implement the voice guard + `defer()` (G-007)
- [x] D1-03 RED: `/play` connects/moves, enqueues, replies "added" vs "now playing" (US-1, US-2)
- [x] D1-04 GREEN: implement the `/play` body (connect/move → `source.fetch` → enqueue → start if idle)
- [x] D1-05 RED: `/skip` errors when nothing is playing; otherwise advances (AC-4.1)
- [x] D1-06 GREEN: implement `/skip`
- [x] D1-07 RED: `/pause` and `/resume` behavior + precondition errors (AC-6.1, AC-6.2)
- [x] D1-08 GREEN: implement `/pause` and `/resume`
- [x] D1-09 RED: `/stop` clears and leaves (US-7)
- [x] D1-10 GREEN: implement `/stop`

### D2 — Queue commands (`cadence/commands/queue.py`)
- [x] D2-01 RED: `/queue` lists current + upcoming, with an empty-state message (AC-5.2, AC-5.3)
- [x] D2-02 GREEN: implement `/queue` (render from `snapshot`, truncate with "+N more" — AC-5.4)
- [x] D2-03 RED: `/nowplaying` shows the current track or "Nothing is playing." (AC-5.1)
- [x] D2-04 GREEN: implement `/nowplaying`

### D3 — Settings commands (`cadence/commands/settings.py`)
- [x] D3-01 RED: `/loop` toggles and confirms the new state (AC-3.1)
- [x] D3-02 GREEN: implement `/loop`
- [x] D3-03 RED: `/volume` validates 0–100 and applies live (AC-6.3)
- [x] D3-04 GREEN: implement `/volume`

### D4 — Registration (`cadence/commands/__init__.py`)
- [x] D4-01 GREEN: implement `register(tree, deps)` wiring all three command groups
- [x] D4-02 RED: test `register` attaches exactly the nine expected command names
- [x] D4-03 GREEN: ensure every command registers exactly once

---

## PART E — Composition root & runtime wiring
> Agent instructions: Wire concrete implementations together and make the bot
> actually run. You own `cadence/app.py` and `cadence/__main__.py` wiring. This is
> the first Part allowed to import B, C, and D together.

### E1 — Wiring
- [x] E1-01 Implement `cadence/app.py` `build_app()`: settings → logging → client → `StateStore` → `YouTubeSource` → `Player` → `register` commands
- [x] E1-02 Inject the concrete `YouTubeSource` into the `Player`; confirm single event-loop ownership
- [x] E1-03 RED: `build_app()` returns a client with all nine commands registered and a player bound to `YouTubeSource`
- [x] E1-04 GREEN: implement `build_app()` to pass the test

### E2 — Runtime concerns
- [x] E2-01 Graceful shutdown: disconnect any voice clients on close / SIGINT
- [x] E2-02 Implement `tree.on_error` to log unhandled command errors and send a generic message (§13.6)
- [x] E2-03 Append a manual smoke-test checklist to `README.md` (token → invite → `/play` in a server)

### E3 — Packaging & DX
- [x] E3-01 Add `python -m cadence` behavior + a `Makefile` (or task list) for `lint`, `type`, `test`, `run`
- [x] E3-02 Verify `ruff check .` and `mypy cadence` are clean across the package
- [x] E3-03 Confirm the README env-var table matches `overview.md §10` exactly

---

## PART T2 — Integration tests: source & engine
> Agent instructions: Exercise `Player` + `YouTubeSource` together (yt-dlp mocked) and
> close coverage gaps to ≥90%. Owns `tests/integration/test_playback_flow.py` and
> related files. Do NOT modify production code except to fix discovered bugs (log
> them in `remember.md §6`).

### T2a — Source ↔ engine
- [x] T2-01 A full track plays to completion and the after-callback advances to the next (mocked yt-dlp)
- [x] T2-02 Loop integration: one track loops N times, re-resolving the stream URL each cycle (G-006)
- [x] T2-03 Failure integration: a resolve error mid-queue skips and continues (AC-1.x, §5.2)

### T2b — Controls integration
- [x] T2-04 A volume change while playing updates the live `PCMVolumeTransformer`
- [x] T2-05 Pause/resume across a queued transition behaves correctly

### T2c — Coverage
- [x] T2-06 Fill coverage gaps for source + engine to ≥90%
- [x] T2-07 Integration-level guard: assert no blocking yt-dlp call runs on the event loop (G-003)

---

## PART T3 — Acceptance tests: commands & flows
> Agent instructions: Drive the commands end-to-end through a (faked) interaction →
> player → voice client, asserting the acceptance criteria from `overview.md §3`.
> Owns `tests/integration/test_acceptance_*.py`. Every user story must be covered.

### T3a — Command acceptance
- [x] T3-01 `/play` from idle → connects, plays, "now playing" (US-1)
- [x] T3-02 `/play` while active → "added to queue" and auto-advance (US-2)
- [x] T3-03 `/skip` advances; `/skip` with loop on still advances (US-3, US-4)
- [x] T3-04 `/stop` clears + disconnects (US-7)

### T3b — Queue & settings acceptance
- [x] T3-05 `/queue` and `/nowplaying` render correctly across states (US-5)
- [x] T3-06 `/volume` and `/loop` reflect and persist within the session (US-3, US-6)

### T3c — Suite hardening
- [x] T3-07 Full-suite coverage ≥90%; CI runs `ruff` + `mypy` + `pytest`
- [x] T3-08 Traceability: every `US-#` in `overview.md §3` is referenced by ≥1 acceptance test (§14.4)

---

## Blockers log

> Record `[!]` blockers here with task ID, date, and what's needed to unblock.

_(empty)_
