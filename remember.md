# Cadence — Remember (conventions + guardrails)

> Read this in full at the start of every session, alongside `overview.md` and
> `progress.md`. **Add new entries at the bottom of each section. Never delete —
> strike through outdated entries** (e.g. ~~old rule~~ → reason).
> Guardrail IDs are stable forever: `G-001`, `G-101`, `G-201`.

---

## 1. Stack & versions

You (the operator) did not pick these — the scaffolding did. Pin in `pyproject.toml`
and the requirements files.

| Component | Version / choice | Notes |
|---|---|---|
| Python | 3.11 | 3.9+ runs, but target and test on 3.11 |
| discord.py | `>=2.4,<3` | slash commands + voice; 2.x API |
| yt-dlp | latest (`>=2025.1`) | update often; YouTube breaks it (G-006-adjacent) |
| PyNaCl | `>=1.5` | required for voice encryption |
| python-dotenv | `>=1.0` | local `.env` loading only |
| FFmpeg | system binary on PATH | NOT a pip package |
| pytest | `>=8` | with `pytest-asyncio` (`asyncio_mode=auto`), `pytest-cov` |
| ruff | latest | lint + format (single tool) |
| mypy | latest | `--strict`, no `Any` |

Run target: `python -m cadence`. Lint/type/test: `ruff check . && mypy cadence && pytest`.

---

## 2. Environment variables

Must match `overview.md §10` exactly. Source of truth is `cadence/config.py`.

| Name | Required | Default | Purpose |
|---|---|---|---|
| `DISCORD_TOKEN` | yes | — | Bot token; the only secret |
| `DISCORD_GUILD_ID` | no | `None` | Guild-scoped instant command sync while testing |
| `LOG_LEVEL` | no | `INFO` | Level for the `cadence` logger |
| `CADENCE_DEFAULT_VOLUME` | no | `50` | Starting volume (0–100) for new guilds |

---

## 3. Auth architecture

- Single bot token, read from `DISCORD_TOKEN`. No user accounts, no OAuth flows, no
  roles inside the app.
- Discord OAuth scopes for the invite URL: `bot`, `applications.commands`. Bot
  permissions: Connect, Speak, Send Messages.
- No privileged intents — `Intents.default()` only.
- Manual setup step (operator): create the app in the Discord Developer Portal,
  reset/copy the token, generate the invite URL, invite the bot.

---

## 4. Database notes

**N/A — Cadence has no database.** All state is in-memory (`StateStore`, keyed by
guild ID) and resets on restart by design (`overview.md §6`, G-005). Do not add a
database, ORM, or on-disk persistence without an `overview.md` change.

---

## 5. Naming conventions

Summary (full table in `overview.md §12`):
- Files/modules `snake_case.py`; classes/Protocols `PascalCase`; functions/vars
  `snake_case`; constants `UPPER_SNAKE_CASE`; env vars `UPPER_SNAKE_CASE`.
- Command callbacks are named for the command (`play`, `now_playing`), with the
  Discord `name="nowplaying"` set explicitly where it differs.
- Test files `test_<module>.py`; fakes `Fake*` / fixtures `fake_*`.

---

## 6. Known gotchas

Problem → solution format. Append as you discover more.

- **Slash commands don't appear after starting the bot** → set `DISCORD_GUILD_ID`
  for instant guild-scoped sync; global sync can take up to an hour to propagate.
- **`ffmpeg` not found / immediate silence** → FFmpeg is a system binary and must
  be on `PATH`; it is not installed via pip. Install via your OS package manager.
- **Bot joins but produces no audio** → usually missing `PyNaCl`, a blocking call
  on the event loop (G-003), or an expired stream URL not being re-resolved (G-006).
- **`InteractionResponded` / "application did not respond"** → you didn't `defer()`
  a slow handler within 3 seconds, or you replied twice (§13.3 in overview).
- **Audio cuts out mid-song on network blips** → ensure FFmpeg `before_options`
  include the reconnect flags and `options` include `-vn` (audio only).
- **Search returns a playlist/odd result** → yt-dlp wraps results under `entries`;
  unwrap and filter falsy entries before indexing (G-201).

---

## 7. 🔴 Hard guardrails (violations break the build or lose data)

- **G-001** Never commit `.env*` files. `.gitignore` must list `.env*`. Secrets come
  from the environment only.
- **G-002** Never hardcode the Discord token (or any secret) in source, tests, logs,
  or chat messages. Reference it only through `Settings`.
- **G-003** Never run blocking work (yt-dlp extraction, network, file IO) on the
  event loop. Offload via `loop.run_in_executor(...)`. Blocking the loop drops the
  voice connection.
- **G-004** The FFmpeg `after=` callback runs on a worker thread. Re-enter the event
  loop only via `asyncio.run_coroutine_threadsafe(coro, client.loop)`. Never call
  discord coroutines or mutate discord objects directly from that thread.
- **G-005** State is in-memory and resets on restart by design. Do not introduce a
  database or persistence without first changing `overview.md` (it is a v1 anti-goal).
- **G-006** Re-resolve the stream URL immediately before every play. YouTube stream
  URLs expire; never cache a `stream_url` across plays or loop cycles. Store the
  `webpage_url` in the queue, not the stream URL.
- **G-007** Defer any interaction whose work may exceed 3 seconds (`/play`) with
  `interaction.response.defer()` before doing work, then reply via `followup`.

---

## 8. 🟡 Style guardrails (violations cause inconsistency)

- **G-101** User-facing messages follow the emoji + short phrase + **bold track**
  pattern from `overview.md §15`. Keep replies short and friendly.
- **G-102** One concern per module. Commands never import `yt_dlp` or touch FFmpeg
  directly — they go through the `AudioSource` and `Player` protocols
  (`cadence/interfaces.py`). Sources never know about Discord interactions.
- **G-103** Type-hint everything; `mypy --strict` must pass; no `Any`. Use the
  Protocols in `cadence/interfaces.py` for dependencies, not concrete classes.
- **G-104** User-error replies are ephemeral; state-change confirmations are normal
  messages. Internal errors get a generic chat message + a full log entry — never a
  raw traceback in chat.
- **G-105** Keep module constants (`YTDL_OPTS`, `FFMPEG_OPTS`, display caps) at module
  top, `UPPER_SNAKE_CASE`. No magic numbers inline.

---

## 9. 🟢 Discovered patterns (grows as agents work)

- **G-201** (seed) `yt_dlp.extract_info` returns search results and playlists wrapped
  under an `entries` key. Always unwrap, filter out falsy entries, and take the first
  before treating the result as a single video.
- **G-202** (seed) Setting `source_address="0.0.0.0"` in `YTDL_OPTS` forces IPv4 and
  avoids intermittent extraction hangs on dual-stack hosts.

---

## 10. Open questions

- [ ] Add an opt-in idle auto-disconnect timeout (leave after N minutes idle)?
- [ ] Whole-queue loop mode in addition to single-track loop?
- [ ] Per-voice-channel queues instead of per-guild?
- [ ] Revisit Spotify track/album-link support only (no playlists) if the operator
  already has Premium? (See `overview.md §9.3`.)

---

## 11. Applied migrations log

**N/A — no database.** This section is intentionally empty and stays empty unless
§4 changes.
