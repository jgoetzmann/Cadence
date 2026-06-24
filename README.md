# Cadence

Self-hosted Discord music bot that streams audio from YouTube into voice channels via slash commands.

## Requirements

- Python 3.11+
- [FFmpeg](https://ffmpeg.org/) on your `PATH` (system binary, not installed via pip)
- A Discord bot token from the [Developer Portal](https://discord.com/developers/applications)

## Setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # then edit .env with your token
```

## Environment variables

| Name | Scope | Required | Default | Example | Where to get it |
|---|---|---|---|---|---|
| `DISCORD_TOKEN` | runtime | yes | — | `MTIz...` | Discord Developer Portal → your app → Bot → Reset Token |
| `DISCORD_GUILD_ID` | runtime | no | `None` (global sync) | `123456789012345678` | Right-click your server → Copy Server ID (Developer Mode on) |
| `LOG_LEVEL` | runtime | no | `INFO` | `DEBUG` | Any stdlib logging level name |
| `CADENCE_DEFAULT_VOLUME` | runtime | no | `50` | `40` | Integer 0–100; starting volume for new guilds |

## Run

```bash
python -m cadence
```

## Lint, type-check, test

```bash
ruff check .
mypy cadence
pytest
```

Or use the Makefile:

```bash
make check   # lint + type + test
make run     # start the bot
```

## Manual smoke test

1. Set `DISCORD_TOKEN` (and optionally `DISCORD_GUILD_ID` for instant command sync) in `.env`.
2. Invite the bot with `bot` and `applications.commands` scopes; grant Connect, Speak, and Send Messages.
3. Run `python -m cadence` and confirm login plus command-sync log output.
4. Join a voice channel in your server and run `/play <query>` — confirm audio starts and the bot replies.
5. Run `/skip`, `/queue`, and `/stop` once each to verify basic controls.

## Package layout

```
cadence/           # Python package
  config.py        # Settings from env
  state.py         # Track, GuildState, StateStore
  interfaces.py    # AudioSource & Player protocols
  client.py        # Discord client shell
  app.py           # Composition root: build_app()
  sources/         # Audio sources (YouTube)
  commands/        # Slash commands
tests/
  unit/            # Per-module unit tests
  integration/     # Cross-module tests
docs/              # Spec, progress, conventions
```
