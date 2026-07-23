# Cadence — Overview & Specification

> **Internal / historical.** Design spec used while building Cadence. For day-to-day
> use, prefer the [README](../README.md), [commands](commands.md), and [setup](setup.md).

**Stack:** Python 3.11, discord.py 2.x, yt-dlp, FFmpeg · **Persistence:** none (in-memory)

---

## 1. Vision & anti-goals

### 1.1 What Cadence is
Cadence is a self-hosted Discord bot that streams audio from YouTube into a voice
channel using slash commands. It joins the caller's voice channel, plays the
requested track, keeps a per-server queue, and **stays parked in the channel when
the queue empties** rather than disconnecting — so it can sit idle and resume on
the next `/play`. It leaves only on `/stop`.

This project is a restructure of an existing, working single-file bot
(`bot.py`) into a small, testable Python package that multiple agents can build
in parallel without colliding. The runtime behavior of v1 is a strict superset of
the original bot.

### 1.2 What success looks like (v1)
1. The four original commands (`/play`, `/skip`, `/loop`, `/stop`) work exactly as
   they did in the single-file version.
2. Five new commands ship: `/queue`, `/pause`, `/resume`, `/nowplaying`, `/volume`.
3. The codebase is a package with one concern per module, ≥90% test coverage, and
   a clean `ruff` + `mypy --strict` pass.
4. A new contributor (human or agent) can read `docs/` and run the bot in minutes.

### 1.3 Anti-goals (explicitly NOT building in v1)
- **No Spotify integration.** Evaluated and dropped — see §9.3 for the sourced
  rationale. This is a deliberate won't-do, not an oversight.
- **No database / no persistence.** All state is in-memory and resets on restart
  by design (§6). Queues do not survive a process restart.
- **No web dashboard, no HTTP server, no REST API.** The only surface is Discord
  slash commands (§4).
- **No multi-process / sharding / horizontal scaling.** Single process; Discord
  recommends sharding only past ~2,500 guilds, far beyond this project's scope.
- **No music downloading to disk.** Audio is streamed, never saved.
- **No playlist expansion from a single YouTube URL** (`noplaylist=True`); a watch
  URL with `&list=...` plays only that one video.

### 1.4 Deferred (post-v1, designed-for but not built)
- Idle auto-disconnect timeout (leave after N minutes of silence).
- Whole-queue loop mode (loop the entire queue, not just the current track).
- Per-voice-channel queues instead of per-guild.
- Persistence of queue/state across restarts.

---

## 2. Users & personas

### 2.1 Server member (primary)
A person in a Discord server who wants to play music in a voice channel. They run
slash commands from any text channel while sitting in a voice channel. They do not
configure anything; they expect fast, obvious feedback.

### 2.2 Bot operator (secondary)
The person who self-hosts Cadence. They create the Discord application, set
environment variables, install FFmpeg, and run the process. They care about easy
setup, clear logs, and the bot not crashing.

### 2.3 Contributing agent (tertiary)
An automated coding agent (or human contributor) extending the bot. They depend on
this document, `remember.md`, and `progress.md` to work without breaking things or
stepping on a parallel agent.

---

## 3. User stories & flows

Each story has an ID, a flow, and acceptance criteria. Test tasks in
`progress.md` Part T3 reference these IDs for traceability (§14.4).

### 3.1 US-1 — Play when idle
**As a** server member, **I want** to start a song with `/play`, **so that** music
begins in my voice channel.

Flow: member joins voice → `/play lofi beats` → bot connects → resolves the top
YouTube result → plays it → posts "▶️ Now playing".

Acceptance criteria:
- AC-1.1 If the caller is not in a voice channel, the bot replies with an ephemeral
  error and does nothing else.
- AC-1.2 The bot connects to the caller's channel (or moves to it if already
  connected elsewhere in the guild).
- AC-1.3 The interaction is deferred before extraction (§13.3).
- AC-1.4 On success, the bot plays audio and posts a non-ephemeral "now playing"
  message naming the track.

### 3.2 US-2 — Queue while playing
**As a** member, **I want** `/play` to enqueue when something is already playing,
**so that** songs line up.

Acceptance criteria:
- AC-2.1 If a track is currently playing, the new request is appended to the queue.
- AC-2.2 The bot replies "➕ Added to queue: **title**" instead of "now playing".
- AC-2.3 When the current track ends, the next queued track plays automatically.

### 3.3 US-3 — Loop the current song
**As a** member, **I want** `/loop` to repeat the current track.

Acceptance criteria:
- AC-3.1 `/loop` toggles the per-guild loop flag and confirms the new state.
- AC-3.2 While loop is on, the current track replays when it finishes.
- AC-3.3 `/skip` advances past the looped track anyway (§5.2, §5.4).

### 3.4 US-4 — Skip
**As a** member, **I want** `/skip` to move to the next track.

Acceptance criteria:
- AC-4.1 If nothing is playing, reply with an ephemeral "Nothing is playing."
- AC-4.2 Otherwise stop the current track, which triggers the next one.
- AC-4.3 Skipping while loop is on still advances (loop does not trap the skip).

### 3.5 US-5 — See the queue / now playing
**As a** member, **I want** `/queue` and `/nowplaying` to show what's playing and
what's next.

Acceptance criteria:
- AC-5.1 `/nowplaying` shows the current track, or "Nothing is playing."
- AC-5.2 `/queue` shows the current track plus upcoming tracks in order.
- AC-5.3 If the queue is empty, `/queue` says so.
- AC-5.4 Long queues are truncated to a readable length with a "+N more" note.

### 3.6 US-6 — Pause, resume, volume
**As a** member, **I want** to pause/resume and set volume.

Acceptance criteria:
- AC-6.1 `/pause` pauses if playing; otherwise an ephemeral error.
- AC-6.2 `/resume` resumes if paused; otherwise an ephemeral error.
- AC-6.3 `/volume <0-100>` validates the range and applies the change live to the
  current track if one is playing.
- AC-6.4 The chosen volume persists for subsequent tracks within the session.

### 3.7 US-7 — Stop and leave
**As a** member, **I want** `/stop` to clear everything and disconnect.

Acceptance criteria:
- AC-7.1 The queue is cleared, current is reset, loop is turned off.
- AC-7.2 The bot disconnects from voice.
- AC-7.3 The bot confirms with "⏹️ Stopped and left the channel."

### 3.8 US-8 — Idle without disconnecting
**As an** operator, **I want** the bot to stay connected when the queue empties.

Acceptance criteria:
- AC-8.1 When the last track finishes and the queue is empty, `current` becomes
  `None` and the bot remains connected to the voice channel.
- AC-8.2 A later `/play` in the same channel resumes playback without reconnecting.

---

## 4. Surface inventory

The entire surface is nine Discord slash commands. There are no pages, endpoints,
or CLI commands beyond `python -m cadence` (the run entry point).

| Command | Input | Auth requirement | Response style | Purpose |
|---|---|---|---|---|
| `/play` | `query: str` (search terms or a YouTube URL) | caller must be in a voice channel | deferred → followup | Resolve and play, or enqueue if active |
| `/skip` | — | something playing | normal message / ephemeral error | Advance to next track |
| `/pause` | — | something playing | normal / ephemeral error | Pause playback |
| `/resume` | — | something paused | normal / ephemeral error | Resume playback |
| `/loop` | — | — | normal message | Toggle single-track loop |
| `/volume` | `level: int` (0–100) | — | normal / ephemeral error | Set playback volume |
| `/queue` | — | — | normal message | List current + upcoming |
| `/nowplaying` | — | — | normal message | Show current track |
| `/stop` | — | — | normal message | Clear queue & leave |

Process entry point: `python -m cadence` (reads env, connects, syncs commands).

---

## 5. Detailed feature specs

### 5.1 Playback start & enqueue (`/play`)
**Description.** Resolves a query (search terms → top YouTube result; URL → that
video) into a `Track`, appends it to the guild queue, and starts playback if the
bot is idle.

**Data flow.** `interaction` → guard (caller in voice) → `defer()` →
connect/move voice client → `AudioSource.fetch(query)` (off the event loop, §13.5)
→ build `Track` → `state.queue.append(track)` → if idle, `Player.play_next(guild)`.

**Edge cases.**
- Caller not in voice → ephemeral error, no state change (AC-1.1).
- Bot already connected to a different channel in the guild → `move_to` (AC-1.2).
- Extraction returns nothing → friendly followup error, no enqueue.
- `&list=` URL → single video only (`noplaylist=True`, §1.3).

**Error states.** Extraction failure surfaces as "Couldn't find anything for that."
Network/transient errors are logged (§13) and reported without internals.

### 5.2 Playback engine (`play_next`)
**Description.** The core loop. Decides the next track, starts piped playback via
`AudioSource.create_playback_source(webpage_url)`, and schedules itself again when
the track ends. See **`playback-architecture.md`** for the full pipeline.

**Branch logic (in order):**
1. No voice client → return (nothing to do).
2. `loop` is on **and** `current` is set → replay `current` (no "now playing" post).
3. Queue non-empty → pop next into `current` (post "now playing").
4. Else → set `current = None` and **stay connected** (idle, AC-8.1).

**Playback.** Always stream from the canonical `webpage_url` immediately before
playing (G-006). Phase A (`fetch`) resolves metadata; Phase B
(`create_playback_source`) pipes yt-dlp stdout into FFmpeg. On playback failure:
post a skip warning, clear `current`, and recurse to the next track.

**After-callback.** `voice_client.play(source, after=_after)`. `_after` runs on a
worker thread, so it re-enters the event loop via
`asyncio.run_coroutine_threadsafe(play_next(guild), client.loop)` (§13.4, G-004).

### 5.3 Loop (`/loop`)
Toggles `GuildState.loop`. When on, branch 2 of §5.2 replays the current track.
Confirms "🔁 Loop enabled / disabled." Whole-queue loop is deferred (§1.4).

### 5.4 Skip (`/skip`)
Sets `current = None` (so the loop branch is bypassed for exactly this transition)
then calls `voice_client.stop()`, which fires the after-callback and advances. If
nothing is playing, returns an ephemeral "Nothing is playing."

### 5.5 Pause / Resume (`/pause`, `/resume`)
`/pause` calls `voice_client.pause()` if playing; `/resume` calls
`voice_client.resume()` if paused. Each is a no-op-with-error if the precondition
fails (AC-6.1, AC-6.2).

### 5.6 Volume (`/volume`)
Validates `0 ≤ level ≤ 100`. Stores `GuildState.volume`. If a track is currently
playing, updates the live `discord.PCMVolumeTransformer.volume` (mapped `level/100`)
so the change is immediate (AC-6.3). New tracks start at the stored volume.

### 5.7 Queue & Now Playing (`/queue`, `/nowplaying`)
Render from `Player.snapshot(guild)` which returns `(current, list(upcoming))`.
`/nowplaying` shows `current` or an empty-state message. `/queue` lists the current
track then upcoming, truncating beyond a display cap with "+N more" (AC-5.4).

### 5.8 Stop (`/stop`)
Clears the queue, resets `current`, turns loop off, calls `voice_client.stop()` and
`disconnect()`, and confirms. Leaves the guild's `GuildState` in a clean default
state for a future session.

### 5.9 Idle behavior
When branch 4 of §5.2 runs, the bot keeps its voice connection open with no audio.
This is intentional (US-8). An optional idle-timeout that auto-disconnects is
deferred (§1.4) and, if added later, must be an opt-in env toggle.

---

## 6. Data model

All state is **in-memory** and **per-process**. There is no database. Restarting
the process clears everything (§1.3). State is keyed by Discord guild ID, so the
bot is safe across multiple servers in one process.

### 6.1 `Track` (immutable value object — `cadence/state.py`)
A queued item. Stores the canonical page URL, not a stream URL (which expires).

| Field | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `title` | `str` | no | — | Display title from yt-dlp |
| `webpage_url` | `str` | no | — | Canonical YouTube watch URL; re-resolved each play |
| `requested_by` | `int` | no | — | Discord user ID of the requester |
| `duration` | `int \| None` | yes | `None` | Length in seconds, if known |

Constraints: immutable (frozen dataclass). `webpage_url` must be a resolvable URL.

### 6.2 `ResolvedTrack` (transient — `cadence/interfaces.py`)
Returned by an `AudioSource`. Carries the short-lived `stream_url`. Never stored in
the queue; built fresh at play time.

| Field | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `title` | `str` | no | — | Display title |
| `webpage_url` | `str` | no | — | Canonical page URL |
| `stream_url` | `str` | no | — | Direct audio URL; **expires**, do not cache |
| `duration` | `int \| None` | yes | `None` | Seconds |

### 6.3 `GuildState` (mutable — `cadence/state.py`)
Per-guild playback state.

| Field | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `queue` | `deque[Track]` | no | `deque()` | Upcoming tracks (FIFO) |
| `current` | `Track \| None` | yes | `None` | Track currently playing |
| `loop` | `bool` | no | `False` | Repeat current track |
| `volume` | `int` | no | `settings.default_volume` | 0–100 |
| `text_channel` | `discord.abc.Messageable \| None` | yes | `None` | Where "now playing" is posted |
| `voice_source` | `discord.PCMVolumeTransformer \| None` | yes | `None` | Live source for volume control |

Invariants: `0 ≤ volume ≤ 100`. If `current is None`, no audio should be playing
(except during the brief transition window inside `play_next`).

### 6.4 `StateStore` (registry — `cadence/state.py`)
| Field | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `_states` | `dict[int, GuildState]` | no | `{}` | Keyed by guild ID |

Methods: `get(guild_id) -> GuildState` (create-on-miss), `discard(guild_id)`.
`get` must return the **same** instance on repeated calls for one guild (G-001 test).

---

## 7. Command contracts (Discord interactions)

There is no HTTP API. The closest analog to API contracts is the interaction
contract per slash command. "Ephemeral" means only the caller sees the reply.

| Command | Params | Defers? | Success reply | Error replies |
|---|---|---|---|---|
| `/play` | `query: str` | yes | "▶️ Now playing: **t**" or "➕ Added to queue: **t**" | "You need to be in a voice channel first." (ephemeral); "Couldn't find anything for that." |
| `/skip` | — | no | "⏭️ Skipped." | "Nothing is playing." (ephemeral) |
| `/pause` | — | no | "⏸️ Paused." | "Nothing is playing." (ephemeral) |
| `/resume` | — | no | "▶️ Resumed." | "Nothing is paused." (ephemeral) |
| `/loop` | — | no | "🔁 Loop enabled/disabled." | — |
| `/volume` | `level: int` | no | "🔊 Volume set to **N**." | "Volume must be between 0 and 100." (ephemeral) |
| `/queue` | — | no | Rendered list | "The queue is empty." |
| `/nowplaying` | — | no | "▶️ **t**" (+ requester) | "Nothing is playing." |
| `/stop` | — | no | "⏹️ Stopped and left the channel." | — |

Contract rules:
- Any command whose work may exceed 3 seconds **must** `defer()` first (§13.3). Only
  `/play` defers in v1.
- User-error replies are ephemeral; state-change confirmations are normal messages.

---

## 8. Auth & permissions

### 8.1 Discord application setup
- **Scopes** (OAuth2 URL Generator): `bot`, `applications.commands`.
- **Bot permissions** (minimum): Connect, Speak, Send Messages.
- **Privileged intents:** none required. Cadence uses `Intents.default()`, which
  includes `voice_states`. Message Content / Members intents are not used.

### 8.2 In-app permissions
There are no application-level roles. Any member who can use slash commands in a
channel may run them, subject to Discord's own permission system. `/play` adds the
single requirement that the caller is in a voice channel (AC-1.1). Future
role-gating (e.g., DJ role) is out of scope for v1.

---

## 9. External integrations

### 9.1 YouTube via yt-dlp (audio source)
- **What:** Phase A — `yt-dlp` resolves search/URL to metadata (`fetch`). Phase B —
  piped `yt-dlp -o -` → FFmpeg transcodes to PCM for Discord voice. Full diagrams:
  **`playback-architecture.md`**.
- **Auth:** none (optional cookie file on VM for hard cases).
- **Key options:** `format=bestaudio/best`, `noplaylist=True`,
  `default_search=ytsearch`, `source_address=0.0.0.0` (force IPv4, G-202),
  `remote_components=ejs:github` (signature solving).
- **Oracle VM:** `YTDLP_PROXY` (WARP SOCKS), `YTDLP_IMPERSONATE`, POT provider.
- **Fallback behavior:** on resolution failure, the engine skips the track with a
  warning and continues (§5.2). Each play spawns a fresh yt-dlp stream from the
  stored `webpage_url` (G-006).
- **Maintenance:** YouTube changes break extraction periodically; keep yt-dlp
  updated (`pip install -U yt-dlp`).

### 9.2 Discord (gateway, voice, interactions)
- **What:** `discord.py` 2.x handles the gateway connection, slash-command
  registration/sync, and voice. `PyNaCl` is required for voice encryption.
- **Auth:** bot token via `DISCORD_TOKEN` (§10).
- **Command sync:** guild-scoped sync when `DISCORD_GUILD_ID` is set (instant),
  else global sync (can take up to an hour). See §13 and G-101-adjacent gotchas.

### 9.3 Spotify — evaluated and dropped (won't-do)
Spotify integration was investigated and **deliberately excluded** because, as of
the February 2026 Web API changes, it fails the project's "drop it if it costs
money, is annoying, or can't do playlist links" bar:

- Development-Mode apps now require the **app owner to hold a Spotify Premium
  subscription**, and the app stops working if it lapses — i.e. it costs money.
- The headline use case is gone: for any playlist the app owner doesn't own or
  collaborate on, the API returns **metadata only, with no track items**, so
  arbitrary public/friends'/editorial playlist links cannot be expanded.
- Dev-Mode apps are capped at **five users**; the unrestricted tier requires a
  registered business and ~250,000 monthly active users — unreachable for a
  personal bot. Search results are also capped at 10 per request.

A narrow path still works if ever revisited: resolving individual **track/album**
links (catalog lookup), or the owner's **own** playlists via an OAuth login. Even
then, audio could only ever come from YouTube (Spotify audio is DRM-protected and
cannot be streamed by a bot). Revisiting this requires an explicit change to this
section and a new Part in `progress.md`.

---

## 10. Environment variables

Loaded by `cadence/config.py` (via `python-dotenv` for local `.env`). Must match
`remember.md` exactly.

| Name | Scope | Required | Default | Example | Where to get it |
|---|---|---|---|---|---|
| `DISCORD_TOKEN` | runtime | yes | — | `MTIz...` | Discord Developer Portal → your app → Bot → Reset Token |
| `DISCORD_GUILD_ID` | runtime | no | `None` (global sync) | `123456789012345678` | Right-click your server → Copy Server ID (Developer Mode on) |
| `LOG_LEVEL` | runtime | no | `INFO` | `DEBUG` | Any stdlib logging level name |
| `CADENCE_DEFAULT_VOLUME` | runtime | no | `50` | `40` | Integer 0–100; starting volume for new guilds |

**Never commit `.env*` files** (G-001). `.env.example` documents the names with
placeholder values only.

---

## 11. File / folder structure

```
cadence/                      # repo root
├── .cursor/
│   └── rules.mdc             # agent startup + per-turn workflow
├── docs/
│   ├── overview.md           # this file (source of truth)
│   ├── remember.md           # conventions + guardrails
│   └── progress.md           # execution plan / task board
├── cadence/                  # the Python package
│   ├── __init__.py
│   ├── __main__.py           # `python -m cadence` entry point
│   ├── app.py                # composition root: build_app()
│   ├── config.py             # Settings.load() from env (§10)
│   ├── logging_setup.py      # configure_logging()
│   ├── interfaces.py         # ResolvedTrack, AudioSource & Player protocols (§5,§6)
│   ├── state.py              # Track, GuildState, StateStore (§6)
│   ├── client.py             # build_client(), command sync (§9.2)
│   ├── player.py             # Player: play_next, controls (§5.2)
│   ├── sources/
│   │   ├── __init__.py
│   │   └── youtube.py        # YouTubeSource implements AudioSource (§9.1)
│   └── commands/
│       ├── __init__.py       # register(tree, deps) aggregator
│       ├── playback.py       # /play /skip /stop /pause /resume
│       ├── queue.py          # /queue /nowplaying
│       └── settings.py       # /loop /volume
├── tests/
│   ├── conftest.py           # pytest-asyncio config + shared fixtures
│   ├── fakes.py              # FakeInteraction, FakeVoiceClient, FakeAudioSource…
│   ├── unit/                 # per-module unit tests (owned by impl parts)
│   └── integration/          # cross-module + acceptance tests (T2, T3)
├── .env.example
├── .gitignore                # MUST ignore .env*
├── pyproject.toml            # deps + ruff + mypy + pytest config
├── requirements.txt          # runtime deps
├── requirements-dev.txt      # dev/test deps
└── README.md
```

---

## 12. Naming conventions

| Thing | Convention | Example |
|---|---|---|
| Modules / files | `snake_case.py` | `logging_setup.py` |
| Packages | short lowercase | `cadence`, `sources` |
| Classes / Protocols | `PascalCase` | `GuildState`, `AudioSource` |
| Functions / methods / vars | `snake_case` | `play_next`, `state_store` |
| Command callbacks | named for the command | `async def play(...)`, `async def now_playing(...)` |
| Module constants | `UPPER_SNAKE_CASE` | `YTDL_OPTS`, `FFMPEG_OPTS`, `MAX_QUEUE_DISPLAY` |
| Env vars | `UPPER_SNAKE_CASE` | `DISCORD_TOKEN`, `CADENCE_DEFAULT_VOLUME` |
| Test files | `test_<module>.py` | `test_player.py` |
| Fixtures / fakes | `fake_*` / `Fake*` | `fake_interaction`, `FakeVoiceClient` |

Commands map to Discord names with no underscore where natural (`/nowplaying`),
while the Python callback uses `snake_case` (`now_playing`) and sets
`name="nowplaying"` explicitly.

---

## 13. Error handling & logging

### 13.1 Logging
- Use the stdlib `logging` module configured once in `logging_setup.py`.
- The application logger is `cadence` (and child loggers `cadence.player`, etc.).
- `LOG_LEVEL` controls the `cadence` logger; the noisy `discord` logger defaults to
  `WARNING`.
- **Never log secrets.** The token is never written to logs or chat (G-002).

### 13.2 User-facing vs internal errors
User mistakes (not in voice, bad volume) get short, friendly, **ephemeral**
replies. Internal failures (extraction errors, playback errors) get a generic
user message plus a full log entry with traceback. Internals never leak to chat.

### 13.3 The 3-second rule
Discord requires an interaction response within ~3 seconds. Any handler whose work
may exceed that (`/play` extraction) calls `interaction.response.defer()` first,
then replies via `interaction.followup.send(...)`.

### 13.4 Thread-boundary safety
The FFmpeg `after=` callback runs on a worker thread. Re-enter the event loop only
via `asyncio.run_coroutine_threadsafe(coro, client.loop)`. Never call discord
coroutines or mutate discord objects directly from that thread (G-004).

### 13.5 Event-loop hygiene
All blocking calls (yt-dlp extraction, network) run via
`loop.run_in_executor(...)`. Blocking the event loop stutters or drops the voice
connection (G-003).

### 13.6 Command error boundary
`tree.on_error` logs unhandled command exceptions and sends the user a generic
"Something went wrong." rather than crashing the handler silently.

---

## 14. Testing strategy

### 14.1 Goals
≥90% line coverage with low overhead. Fast, deterministic, no real network, no real
Discord connection, no real FFmpeg process. **No snapshot tests.** External services
(`yt-dlp`, Discord, voice client) are mocked/faked.

### 14.2 Tooling
`pytest` + `pytest-asyncio` (`asyncio_mode=auto`) + `pytest-cov`. Shared fakes live
in `tests/fakes.py`; fixtures and async config in `tests/conftest.py` (Part T1).

### 14.3 Red-Green-Refactor
Inside implementation Parts (B, C, D), each unit follows: write the failing test
(RED), write the minimum implementation (GREEN), refactor without breaking it.
Each implementation Part owns its own unit-test file under `tests/unit/` so parts
never edit the same test file (parallel-safe). Dedicated test Parts (T1–T3) add the
harness, cross-module integration, and acceptance coverage.

### 14.4 Acceptance traceability
Every user story in §3 (US-1…US-8) has at least one acceptance test in Part T3 that
references its ID, so coverage of behavior is auditable, not just line coverage.

### 14.5 What to mock
- `yt_dlp.YoutubeDL.extract_info` → return canned info dicts (no network).
- `discord.Interaction` → `FakeInteraction` capturing replies and voice state.
- `discord.VoiceClient` → `FakeVoiceClient` capturing `play/stop/pause/resume` and
  the `after` callback, with a helper to invoke `after` synchronously.
- `AudioSource` → `FakeAudioSource` returning scripted `ResolvedTrack`s or raising.

---

## 15. Style notes (UI)

Cadence has no graphical UI; its only "UI" is the text of Discord replies. The
conventions below keep that surface consistent (enforced as style guardrails in
`remember.md`).

- **Message pattern:** a leading emoji + a short phrase + the track in bold.
  Examples: "▶️ Now playing: **title**", "➕ Added to queue: **title**",
  "🔁 Loop enabled.", "🔊 Volume set to **40**.", "⏹️ Stopped and left the channel."
- **Tone:** short, friendly, no walls of text.
- **Anti-patterns:** no raw tracebacks or yt-dlp output in chat; no logging the
  token; no multi-paragraph replies; don't @-mention everyone.

---

## 16. Glossary

| Term | Meaning |
|---|---|
| **Guild** | Discord's internal name for a "server." State is keyed per guild. |
| **Slash command** | A `/command` interaction registered with Discord's command tree. |
| **Interaction** | The object representing a user invoking a command; must be answered within ~3s. |
| **Defer** | Acknowledging an interaction early so a slow handler has more time. |
| **Voice client** | discord.py's connection to a voice channel; plays audio sources. |
| **Stream URL** | A direct, short-lived audio URL resolved by yt-dlp; expires, so re-resolved each play. |
| **AudioSource** | Protocol for resolving queries/URLs into playable `ResolvedTrack`s (§6.2). |
| **Player** | Protocol/engine that manages the queue and playback for a guild (§5.2). |
| **After-callback** | FFmpeg's `after=` hook, run on a worker thread when a track ends (§13.4). |
| **Composition root** | `app.py`'s `build_app()` that wires concrete implementations together (§11). |
| **Extended Quota Mode** | Spotify's higher API tier requiring a business + ~250k MAU (§9.3). |
