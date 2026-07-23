# Cadence

Self-hosted Discord music bot. Streams YouTube audio into voice channels via slash commands (`/play`, queue, volume, loop). State is in-memory — a restart clears queues by design.

## Stack

| | |
|---|---|
| Language | Python 3.11+ |
| Discord | [discord.py](https://github.com/Rapptz/discord.py) 2.x + PyNaCl (voice) |
| Audio | [yt-dlp](https://github.com/yt-dlp/yt-dlp) → FFmpeg (system binary) → Discord PCM |
| Config | `.env` via python-dotenv |

No database. Optional Oracle Cloud deploy tooling lives under `tools/oracle/`.

## Setup

Windows examples use **PowerShell**. FFmpeg must be on `PATH` (`winget install Gyan.FFmpeg`).

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Set DISCORD_TOKEN (and optional DISCORD_GUILD_ID) in .env
python -m cadence
```

More detail (start/stop, single-instance lock): [docs/setup.md](docs/setup.md).

## Tests

```powershell
pip install -r requirements-dev.txt
pytest          # or: make test
make check      # ruff + mypy + pytest
```

Oracle VM smoke checks (remote health / yt-dlp) are PowerShell entrypoints:

```powershell
.\tools\oracle\manage.ps1 test
.\tools\oracle\manage.ps1 test-ytdlp
```

## Docs

- [Slash commands](docs/commands.md)
- [Local setup](docs/setup.md)
- [Playback architecture](docs/playback-architecture.md)
- [Oracle VM deploy](docs/oracle-setup.md) (optional)

## License

MIT — see [LICENSE](LICENSE).
