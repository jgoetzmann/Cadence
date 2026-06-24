# Cadence — Progress (execution plan)

> Status keys: `[ ]` not started · `[~]` in progress · `[x]` complete · `[!]` blocked
> Update at the end of every agent session. Never delete tasks. Never renumber IDs.

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
- [ ] A1-01 Create the directory layout from `overview.md §11` with `__init__.py` in every package
- [ ] A1-02 Write `pyproject.toml`: metadata, `[tool.ruff]`, `[tool.mypy]` (strict), `[tool.pytest.ini_options]` (`asyncio_mode=auto`), `[tool.coverage]`
- [ ] A1-03 Write `requirements.txt` (discord.py, yt-dlp, PyNaCl, python-dotenv) and `requirements-dev.txt` (pytest, pytest-asyncio, pytest-cov, ruff, mypy) per `remember.md §1`
- [ ] A1-04 Write `.gitignore` ignoring `.env*`, `__pycache__/`, `.venv/`, `.pytest_cache/`, `.mypy_cache/`, `*.pyc`, `dist/` (G-001)
- [ ] A1-05 Write `.env.example` listing every var from `overview.md §10` with placeholder values only
- [ ] A1-06 Update `README.md` for the package layout and the `python -m cadence` run command

### A2 — Configuration
- [ ] A2-01 RED: test `Settings.load()` raises a clear error when `DISCORD_TOKEN` is missing
- [ ] A2-02 GREEN: implement `cadence/config.py` `Settings` dataclass + `load()` (token, guild_id, log_level, default_volume) using python-dotenv
- [ ] A2-03 RED: test optional vars default correctly (`guild_id=None`, `default_volume` clamped to 0–100)
- [ ] A2-04 GREEN: implement defaults, parsing, and clamping
- [ ] A2-05 Refactor: ensure no secret is ever logged or stringified (G-002)

### A3 — Logging
- [ ] A3-01 Implement `cadence/logging_setup.py` `configure_logging(level)` using stdlib logging
- [ ] A3-02 Default the `discord` logger to WARNING; the `cadence` logger honors `LOG_LEVEL`

### A4 — Domain models & state
- [ ] A4-01 RED: test `Track` is immutable and holds title/webpage_url/requested_by/duration
- [ ] A4-02 GREEN: implement frozen `Track` dataclass in `cadence/state.py`
- [ ] A4-03 RED: test `GuildState` defaults (empty queue, `current=None`, `loop=False`, volume from settings)
- [ ] A4-04 GREEN: implement `GuildState`
- [ ] A4-05 RED: test `StateStore.get(id)` creates-on-miss and returns the same instance on repeat
- [ ] A4-06 GREEN: implement `StateStore` (dict-backed `get` / `discard`)
- [ ] A4-07 Refactor: type hints, `__all__`, docstrings

### A5 — Interfaces (Protocols)
- [ ] A5-01 Define `ResolvedTrack` dataclass (title, webpage_url, stream_url, duration) in `cadence/interfaces.py`
- [ ] A5-02 Define `AudioSource` Protocol: `async fetch(query, *, is_url)->ResolvedTrack`, `async resolve(webpage_url)->ResolvedTrack`
- [ ] A5-03 Define `Player` Protocol: `enqueue`, `play_next`, `skip`, `pause`, `resume`, `stop`, `set_loop`, `set_volume`, `snapshot`

### A6 — Discord client shell & entry point
- [ ] A6-01 Implement `cadence/client.py` `build_client(settings)->(Client, CommandTree)` with `Intents.default()`
- [ ] A6-02 Extract `sync_commands(tree, settings)`: guild copy+sync when `guild_id` set, else global sync; log identity on ready
- [ ] A6-03 Implement `cadence/__main__.py` to call `cadence.app.build_app()` and run; `SystemExit` if no token
- [ ] A6-04 RED: test `sync_commands` chooses the guild vs global path based on settings (fake tree)
- [ ] A6-05 GREEN: make the sync-path selection pass the test

---

## PART T1 — Test harness & fixtures
> Agent instructions: Build the shared test infrastructure every other part imports.
> No production code. Publish stable fixture/fake names early so B/C/D can rely on
> them. Owns `tests/conftest.py` and `tests/fakes.py`.

### T1a — Async test config
- [ ] T1-01 `tests/conftest.py`: configure pytest-asyncio (`asyncio_mode=auto`) and a `settings` fixture
- [ ] T1-02 Add a `run_after(voice_client)` helper that invokes a captured FFmpeg `after` callback synchronously

### T1b — Discord & source fakes
- [ ] T1-03 `FakeInteraction` (capture `defer`, `response.send_message`, `followup.send`; settable `user.voice.channel`)
- [ ] T1-04 `FakeVoiceClient` (`play/stop/pause/resume/is_playing/is_paused`; capture `source` and `after`)
- [ ] T1-05 `FakeGuild` + `FakeVoiceChannel` + `FakeTextChannel` helpers
- [ ] T1-06 `FakeAudioSource` (scripted `ResolvedTrack`s + failure injection) and `FakePlayer`

### T1c — Foundation coverage
- [ ] T1-07 Comprehensive `Settings` tests (missing token, bad `LOG_LEVEL`, volume clamp)
- [ ] T1-08 `StateStore` isolation across guild IDs + `Track`/`GuildState` invariants
- [ ] T1-09 Confirm the foundation package hits ≥90% line coverage locally

---

## PART B — YouTube audio source
> Agent instructions: Implement `YouTubeSource` (an `AudioSource`) in
> `cadence/sources/youtube.py`. Mock `yt_dlp` in tests — never hit the network.
> You own `cadence/sources/youtube.py` and `tests/unit/test_youtube.py`. Do NOT
> touch player or command files.

### B1 — Query resolution
- [ ] B1-01 RED: `fetch("foo", is_url=False)` returns the first `ytsearch1` result mapped to `ResolvedTrack` (mock `YoutubeDL`)
- [ ] B1-02 GREEN: implement `_extract` + search path (`ytsearch1:` prefix, `entries` unwrap — G-201)
- [ ] B1-03 RED: `resolve(url)` returns a fresh `stream_url` for a watch URL (mock)
- [ ] B1-04 GREEN: implement `resolve(webpage_url)` (re-resolve each call — G-006)
- [ ] B1-05 RED: empty/`None` results raise a typed `SourceError`
- [ ] B1-06 GREEN: add `SourceError` and raise on no entries / `None` info

### B2 — Async offloading
- [ ] B2-01 RED: assert blocking yt-dlp calls run via `run_in_executor`, not on the loop (G-003)
- [ ] B2-02 GREEN: wrap `_extract` in `loop.run_in_executor`; expose async `fetch`/`resolve`
- [ ] B2-03 Refactor: single shared `YoutubeDL` instance; `YTDL_OPTS`/`FFMPEG_OPTS` as module constants (G-105, G-202)

### B3 — Stream construction
- [ ] B3-01 RED: `make_ffmpeg_source(stream_url, volume)` returns an `FFmpegPCMAudio` wrapped in `PCMVolumeTransformer` at the given volume
- [ ] B3-02 GREEN: implement `make_ffmpeg_source` with reconnect `before_options` and `-vn`
- [ ] B3-03 RED: URL-vs-search dispatch (http/https → resolve, else search)
- [ ] B3-04 GREEN: implement the `is_url` dispatch inside `fetch`

---

## PART C — Playback engine
> Agent instructions: Implement `Player` in `cadence/player.py` against the
> `AudioSource` Protocol (use `FakeAudioSource` in tests — do NOT import YouTube).
> You own `cadence/player.py` and `tests/unit/test_player.py`. Do NOT touch source
> or command files.

### C1 — Track lifecycle
- [ ] C1-01 RED: `play_next` pops the queue, sets `current`, plays, posts "now playing"
- [ ] C1-02 GREEN: implement the core branch logic (fresh / loop / empty — `overview.md §5.2`)
- [ ] C1-03 RED: empty queue leaves `current=None` and stays connected (no disconnect — AC-8.1)
- [ ] C1-04 GREEN: implement the idle branch
- [ ] C1-05 RED: a resolve failure skips the track with a warning and advances
- [ ] C1-06 GREEN: implement try/except around `source.resolve` → skip + recurse

### C2 — After-callback & threading
- [ ] C2-01 RED: the `after` callback schedules `play_next` on the loop via `run_coroutine_threadsafe` (G-004)
- [ ] C2-02 GREEN: implement `_after`; log playback errors
- [ ] C2-03 RED: skip clears `current` so the loop branch is bypassed for one transition (AC-4.3)
- [ ] C2-04 GREEN: implement `skip()` (clear `current` + `vc.stop()`)

### C3 — Controls (loop, pause/resume, volume)
- [ ] C3-01 RED: `set_loop` toggles `state.loop`
- [ ] C3-02 GREEN: implement `set_loop`
- [ ] C3-03 RED: `pause()`/`resume()` call the voice client and are safe no-ops otherwise
- [ ] C3-04 GREEN: implement `pause`/`resume`
- [ ] C3-05 RED: `set_volume` clamps 0–100 and updates the live `PCMVolumeTransformer` when playing (AC-6.3)
- [ ] C3-06 GREEN: implement `set_volume`

### C4 — Stop & introspection
- [ ] C4-01 RED: `stop()` clears the queue, resets state, disconnects (AC-7.1, AC-7.2)
- [ ] C4-02 GREEN: implement `stop()`
- [ ] C4-03 RED: `snapshot()` returns `(current, upcoming)` for `/queue` and `/nowplaying`
- [ ] C4-04 GREEN: implement `snapshot()`

---

## PART D — Slash commands
> Agent instructions: Implement the nine commands across three files, coding against
> the `Player` Protocol (use `FakePlayer`/`FakeInteraction` in tests). You own
> `cadence/commands/*` and `tests/unit/test_commands_*.py`. Do NOT touch player or
> source internals. D4 depends on D1–D3 inside this Part.

### D1 — Playback commands (`cadence/commands/playback.py`)
- [ ] D1-01 RED: `/play` requires the caller in a voice channel (ephemeral error otherwise — AC-1.1)
- [ ] D1-02 GREEN: implement the voice guard + `defer()` (G-007)
- [ ] D1-03 RED: `/play` connects/moves, enqueues, replies "added" vs "now playing" (US-1, US-2)
- [ ] D1-04 GREEN: implement the `/play` body (connect/move → `source.fetch` → enqueue → start if idle)
- [ ] D1-05 RED: `/skip` errors when nothing is playing; otherwise advances (AC-4.1)
- [ ] D1-06 GREEN: implement `/skip`
- [ ] D1-07 RED: `/pause` and `/resume` behavior + precondition errors (AC-6.1, AC-6.2)
- [ ] D1-08 GREEN: implement `/pause` and `/resume`
- [ ] D1-09 RED: `/stop` clears and leaves (US-7)
- [ ] D1-10 GREEN: implement `/stop`

### D2 — Queue commands (`cadence/commands/queue.py`)
- [ ] D2-01 RED: `/queue` lists current + upcoming, with an empty-state message (AC-5.2, AC-5.3)
- [ ] D2-02 GREEN: implement `/queue` (render from `snapshot`, truncate with "+N more" — AC-5.4)
- [ ] D2-03 RED: `/nowplaying` shows the current track or "Nothing is playing." (AC-5.1)
- [ ] D2-04 GREEN: implement `/nowplaying`

### D3 — Settings commands (`cadence/commands/settings.py`)
- [ ] D3-01 RED: `/loop` toggles and confirms the new state (AC-3.1)
- [ ] D3-02 GREEN: implement `/loop`
- [ ] D3-03 RED: `/volume` validates 0–100 and applies live (AC-6.3)
- [ ] D3-04 GREEN: implement `/volume`

### D4 — Registration (`cadence/commands/__init__.py`)
- [ ] D4-01 GREEN: implement `register(tree, deps)` wiring all three command groups
- [ ] D4-02 RED: test `register` attaches exactly the nine expected command names
- [ ] D4-03 GREEN: ensure every command registers exactly once

---

## PART E — Composition root & runtime wiring
> Agent instructions: Wire concrete implementations together and make the bot
> actually run. You own `cadence/app.py` and `cadence/__main__.py` wiring. This is
> the first Part allowed to import B, C, and D together.

### E1 — Wiring
- [ ] E1-01 Implement `cadence/app.py` `build_app()`: settings → logging → client → `StateStore` → `YouTubeSource` → `Player` → `register` commands
- [ ] E1-02 Inject the concrete `YouTubeSource` into the `Player`; confirm single event-loop ownership
- [ ] E1-03 RED: `build_app()` returns a client with all nine commands registered and a player bound to `YouTubeSource`
- [ ] E1-04 GREEN: implement `build_app()` to pass the test

### E2 — Runtime concerns
- [ ] E2-01 Graceful shutdown: disconnect any voice clients on close / SIGINT
- [ ] E2-02 Implement `tree.on_error` to log unhandled command errors and send a generic message (§13.6)
- [ ] E2-03 Append a manual smoke-test checklist to `README.md` (token → invite → `/play` in a server)

### E3 — Packaging & DX
- [ ] E3-01 Add `python -m cadence` behavior + a `Makefile` (or task list) for `lint`, `type`, `test`, `run`
- [ ] E3-02 Verify `ruff check .` and `mypy cadence` are clean across the package
- [ ] E3-03 Confirm the README env-var table matches `overview.md §10` exactly

---

## PART T2 — Integration tests: source & engine
> Agent instructions: Exercise `Player` + `YouTubeSource` together (yt-dlp mocked) and
> close coverage gaps to ≥90%. Owns `tests/integration/test_playback_flow.py` and
> related files. Do NOT modify production code except to fix discovered bugs (log
> them in `remember.md §6`).

### T2a — Source ↔ engine
- [ ] T2-01 A full track plays to completion and the after-callback advances to the next (mocked yt-dlp)
- [ ] T2-02 Loop integration: one track loops N times, re-resolving the stream URL each cycle (G-006)
- [ ] T2-03 Failure integration: a resolve error mid-queue skips and continues (AC-1.x, §5.2)

### T2b — Controls integration
- [ ] T2-04 A volume change while playing updates the live `PCMVolumeTransformer`
- [ ] T2-05 Pause/resume across a queued transition behaves correctly

### T2c — Coverage
- [ ] T2-06 Fill coverage gaps for source + engine to ≥90%
- [ ] T2-07 Integration-level guard: assert no blocking yt-dlp call runs on the event loop (G-003)

---

## PART T3 — Acceptance tests: commands & flows
> Agent instructions: Drive the commands end-to-end through a (faked) interaction →
> player → voice client, asserting the acceptance criteria from `overview.md §3`.
> Owns `tests/integration/test_acceptance_*.py`. Every user story must be covered.

### T3a — Command acceptance
- [ ] T3-01 `/play` from idle → connects, plays, "now playing" (US-1)
- [ ] T3-02 `/play` while active → "added to queue" and auto-advance (US-2)
- [ ] T3-03 `/skip` advances; `/skip` with loop on still advances (US-3, US-4)
- [ ] T3-04 `/stop` clears + disconnects (US-7)

### T3b — Queue & settings acceptance
- [ ] T3-05 `/queue` and `/nowplaying` render correctly across states (US-5)
- [ ] T3-06 `/volume` and `/loop` reflect and persist within the session (US-3, US-6)

### T3c — Suite hardening
- [ ] T3-07 Full-suite coverage ≥90%; CI runs `ruff` + `mypy` + `pytest`
- [ ] T3-08 Traceability: every `US-#` in `overview.md §3` is referenced by ≥1 acceptance test (§14.4)

---

## Blockers log

> Record `[!]` blockers here with task ID, date, and what's needed to unblock.

_(empty)_
