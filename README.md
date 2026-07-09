# Cadence

Cadence is a self-hosted Discord music bot built for personal and small-community use. It streams audio from YouTube into voice channels through slash commands — join a channel, run `/play`, and the bot handles search, queueing, and playback. The project grew out of a working single-file prototype ([`bot.py`](bot.py)) and was restructured into a small, testable Python package so behavior stays predictable while the codebase stays easy to extend.

The stack is Python 3.11, discord.py 2.x, yt-dlp, and FFmpeg (a system binary, not a pip package). Voice encryption uses PyNaCl. All guild state — queues, volume, loop mode — lives in memory with no database; a restart clears everything by design. Configuration is env-based via `python-dotenv` (`DISCORD_TOKEN`, optional guild ID for fast command sync, log level, default volume).

Architecturally, [`cadence/app.py`](cadence/app.py) is the composition root: it wires the Discord client, slash commands, the playback [`Player`](cadence/player.py), and the [`YouTubeSource`](cadence/sources/youtube.py). YouTube uses a two-phase pipeline — in-process lookup to resolve a query into a canonical watch URL, then piped yt-dlp → FFmpeg → Discord voice PCM for streaming (never saving audio to disk). For deployment on Oracle Cloud Always-Free ARM, [`tools/oracle/manage.ps1`](tools/oracle/manage.ps1) provisions a VM with systemd, WARP, and a POT sidecar; see [`docs/playback-architecture.md`](docs/playback-architecture.md) for the full playback diagram.

## Documentation

- [Local setup](docs/setup.md)
- [Oracle VM deployment](docs/oracle-setup.md)
- [Playback architecture](docs/playback-architecture.md)
- [Full specification](docs/overview.md)

## License

MIT — see [LICENSE](LICENSE).
