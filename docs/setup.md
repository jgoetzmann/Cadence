# Local setup

PowerShell from the repo root. Requires **Python 3.11+** and **FFmpeg** on `PATH` (`winget install Gyan.FFmpeg`).

## Install

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -r requirements-dev.txt   # for pytest / lint

Copy-Item .env.example .env
# Edit .env — set DISCORD_TOKEN (optional: DISCORD_GUILD_ID, LOG_LEVEL, volume)
```

## Run

```powershell
.\.venv\Scripts\python.exe -m cadence
```

Only one instance can run at a time. To stop:

```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*cadence*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
```

## Tests

```powershell
pytest          # unit + integration
make check      # ruff + mypy + pytest
```
