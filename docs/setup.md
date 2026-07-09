# Local setup (PowerShell)

From the project root (`Cadence`).

## One-time

```powershell
cd path\to\cadence

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -r requirements-dev.txt

Copy-Item .env.example .env
# Edit .env — set DISCORD_TOKEN and DISCORD_GUILD_ID
```

FFmpeg must be on `PATH` (`winget install Gyan.FFmpeg` if needed).

## Start the bot

```powershell
cd path\to\cadence
$env:Path = [System.Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path','User')
.\.venv\Scripts\python.exe -m cadence
```

Only one instance can run at a time. If you see *"Another Cadence instance is already running"*, stop it first (below).

## Stop the bot

```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*cadence*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
```

## Restart (stop + start)

```powershell
cd path\to\cadence

Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -like '*cadence*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Start-Sleep -Seconds 1

$env:Path = [System.Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path','User')
.\.venv\Scripts\python.exe -m cadence
```
