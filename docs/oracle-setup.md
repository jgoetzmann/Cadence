# Oracle VM deployment

Deploys Cadence on an Oracle Cloud **Always-Free ARM** instance (Ampere A1, Ubuntu 24.04). Local Windows setup is in [`setup.md`](setup.md). Playback details: [`playback-architecture.md`](playback-architecture.md).

All remote actions go through PowerShell:

```powershell
.\tools\oracle\manage.ps1 <command>
```

---

## 0. What runs where

Cadence is a Discord bot: it makes **outbound** connections to Discord and to
YouTube (via yt-dlp) and never listens for inbound traffic. So the VM needs
outbound internet (open by default) and exactly **one** inbound port — SSH (22)
— for you to manage it. No web server, no ports 80/443.

For the full YouTube → Discord voice pipeline (two-phase lookup + piped playback,
WARP, POT, diagrams), see **`playback-architecture.md`**.

- **Your Windows machine (operator):** runs `manage.ps1`. Holds the SSH keys and
  the master `.env`. Never runs the bot at the same time as the VM (single
  instance lock — `setup.md`).
- **The Oracle VM:** runs the bot under **systemd** as the service `cadence`,
  restarts on failure, and starts on boot.

---

## 1. Prerequisites

- A running A1.Flex instance (e.g. `203.0.113.10`, 1 OCPU / 6 GB, Ubuntu 24.04).
  Free-tier safe: 1 OCPU / 6 GB is inside the current 2 OCPU / 12 GB Always-Free
  Ampere allowance.
- Port **22** open in the VCN Security List for `0.0.0.0/0` (default on a new VCN).
- The SSH key pair you generated at instance creation, saved locally.
- Windows OpenSSH client (`ssh`, `scp`) — built into Windows 10/11.
- The repo pushed to a Git host (recommended) **or** the working tree ready to
  copy up (see §5, fallback).

---

## 2. Connection config in `.env`

The toolkit reads connection details — including the **paths** to your SSH keys
— from the same local `.env` you already use for the bot. Add these four keys:

| Name | Example | Purpose |
|---|---|---|
| `ORACLE_HOST` | `203.0.113.10` | VM public IPv4 |
| `ORACLE_USER` | `ubuntu` | Default user on the Ubuntu image |
| `ORACLE_SSH_KEY` | `C:\path\to\cadence\keys\oracle-vm-ssh-priv-key.key` | **Path** to the PRIVATE key (local only) |
| `ORACLE_SSH_PUB` | `C:\path\to\cadence\keys\oracle-vm-ssh-pub-key.pub` | **Path** to the public key (optional) |

These `ORACLE_*` vars are consumed **only by the toolkit** — `cadence/config.py`
does not read them, so they don't affect `remember.md §2` / `overview.md §10`.

> **The key path, not the key.** `.env` stores the *path* to the private key.
> The private key file itself is used locally to authenticate SSH and is **never
> copied to the VM**. The toolkit only ever pushes the four bot runtime vars up
> (see §4). Keep honoring `G-001` (never commit `.env*`) and `G-002` (secrets via
> environment only).

Full local `.env` example:

```dotenv
# --- Bot runtime (pushed to the VM) ---
DISCORD_TOKEN=your-token-here
DISCORD_GUILD_ID=123456789012345678
LOG_LEVEL=INFO
CADENCE_DEFAULT_VOLUME=50

# --- Oracle deploy (toolkit only, NOT pushed) ---
ORACLE_HOST=203.0.113.10
ORACLE_USER=ubuntu
ORACLE_SSH_KEY=C:\path\to\cadence\keys\oracle-vm-ssh-priv-key.key
ORACLE_SSH_PUB=C:\path\to\cadence\keys\oracle-vm-ssh-pub-key.pub
```

If Windows OpenSSH refuses the key with *"UNPROTECTED PRIVATE KEY FILE"*, tighten
its ACL once:

```powershell
icacls "C:\path\to\cadence\keys\oracle-vm-ssh-priv-key.key" /inheritance:r /grant:r "$env:USERNAME:R"
```

---

## 3. Toolkit layout

Put these in the repo under `tools/oracle/` (the PowerShell script expects the
three VM files to sit next to it):

```
tools/oracle/
  manage.ps1        # operator entrypoint (Windows PowerShell)
  bootstrap.sh      # runs ON the VM: installs deps, swap, venv (idempotent)
  cadence.service   # systemd unit
  healthcheck.sh    # runs ON the VM: read-only diagnostics
```

Everything below is driven through `manage.ps1`. Run it from the repo root so it
finds `.env`:

```powershell
cd path\to\cadence
.\tools\oracle\manage.ps1 <command>
```

---

## 4. First-time provision (one command)

With the repo pushed to Git, provisioning is a single call. It uploads the three
VM files, runs `bootstrap.sh`, pushes `.env`, installs the systemd service, and
enables start-on-boot:

```powershell
.\tools\oracle\manage.ps1 provision -RepoUrl https://github.com/you/cadence.git
```

`bootstrap.sh` does, idempotently:

1. `apt` install **FFmpeg**, git, and build deps (`build-essential`, `libffi-dev`,
   `libsodium-dev`) so any native wheels build cleanly on ARM.
2. Create a **2 GB swapfile** (safety net for yt-dlp/ffmpeg spikes on 6 GB).
3. Ensure inbound **SSH** is allowed in the local `iptables` chain (usually
   already true — you're connected over it).
4. Install **uv**, then a pinned, prebuilt **Python 3.11** for aarch64
   (`uv python install 3.11`). This matches the tested target (`remember.md §1`)
   without depending on deadsnakes having an ARM build.
5. Clone/update the repo into `/opt/cadence` and build `.venv` from Python 3.11,
   installing `requirements.txt` with the venv's own `pip` (identical resolution
   to local — `setup.md`).

Then the toolkit installs `cadence.service` and does `systemctl enable --now cadence`.

> **Private repos:** either make the repo public, add a read-only **deploy key**
> to the VM (`ssh-keygen` on the VM, add the pub key to the repo's deploy keys),
> or use an HTTPS URL with a PAT. Or skip Git entirely — see §5.

Verify:

```powershell
.\tools\oracle\manage.ps1 test
```

---

## 5. Deploying updates

Normal update loop after a code change (commit + push locally first):

```powershell
git push                                   # push your changes to the Git host
.\tools\oracle\manage.ps1 deploy           # git pull on VM + push .env + pip install + restart
```

`deploy` restarts the service and prints a short status tail.

**Fallback without Git** (initial push, or if you're not using a Git host yet):
copy the tree up with `scp`, excluding local junk, then provision without a repo
URL:

```powershell
# from the repo root — copy source, requirements, and the cadence package
scp -i $SshKeyPath -r cadence requirements.txt pyproject.toml ubuntu@203.0.113.10:/opt/cadence/
.\tools\oracle\manage.ps1 provision        # no -RepoUrl: rebuilds venv from the copied tree
```

(Do **not** copy `.venv`, `.git`, or `.env` this way — `.env` goes up only via
the filtered `push-env` path in §4/§6.)

---

## 6. Day-to-day operations

| Task | Command |
|---|---|
| Live logs (follow) | `.\tools\oracle\manage.ps1 logs` |
| Last N log lines | `.\tools\oracle\manage.ps1 logs -Lines 200` |
| Service status | `.\tools\oracle\manage.ps1 status` |
| Start / stop / restart | `.\tools\oracle\manage.ps1 start` \| `stop` \| `restart` |
| Toggle start-on-boot | `.\tools\oracle\manage.ps1 enable` \| `disable` |
| Push only `.env` (after editing token/volume) | `.\tools\oracle\manage.ps1 push-env` |
| Full health probe | `.\tools\oracle\manage.ps1 test` |
| yt-dlp extraction matrix (diagnostics) | `.\tools\oracle\manage.ps1 test-ytdlp` |
| POT provider status | `.\tools\oracle\manage.ps1 pot-status` |
| Restart POT provider | `.\tools\oracle\manage.ps1 pot-restart` |
| WARP proxy status | `.\tools\oracle\manage.ps1 warp-status` |
| Restart WARP proxy | `.\tools\oracle\manage.ps1 warp-restart` |
| Interactive shell | `.\tools\oracle\manage.ps1 ssh` |

`push-env` writes the bot runtime vars (`DISCORD_TOKEN`,
`DISCORD_GUILD_ID`, `LOG_LEVEL`, `CADENCE_DEFAULT_VOLUME`) plus VM yt-dlp
tuning (`YTDLP_PROXY`, `YTDLP_IMPERSONATE`, and `YTDLP_COOKIE_FILE` when local
cookies exist) to `/opt/cadence/.env`
with **LF** line endings and `chmod 600`. It refuses to push if `DISCORD_TOKEN`
is absent. `YTDLP_PROXY` defaults to `socks5h://127.0.0.1:1080` and
`YTDLP_IMPERSONATE` defaults to `chrome` unless overridden in your local `.env`.

---

## 7. How the pieces map to the guardrails

- **`G-001` / `G-002`** — `.env` is never committed and never fully copied to the
  VM; only the four runtime vars go up, and the SSH private key stays local.
- **`G-003` / `G-004` / `G-006`** — pure runtime concerns in the bot code; the
  deployment doesn't touch them. FFmpeg on `PATH` (systemd `Environment=PATH=...`)
  keeps voice working.
- **`G-005`** — state stays in-memory; there is deliberately **no** database or
  on-disk persistence added here. A `systemctl restart` clears all guild state by
  design.

---

## 8. Gotchas (append to `remember.md §6` as you hit them)

- **Token works locally but the VM bot fails to log in** → CRLF line endings in
  `/opt/cadence/.env`. systemd's `EnvironmentFile` keeps the trailing `\r`, so the
  token becomes invalid. The toolkit writes LF; if you edit `.env` on the VM with
  a Windows editor, re-run `push-env`. `healthcheck.sh` flags CRLF.
- **`ffmpeg not found` / immediate silence** → FFmpeg is a system binary, not a
  pip package; `bootstrap.sh` installs it. Confirm with `manage.ps1 test`.
- **`UNPROTECTED PRIVATE KEY FILE` on connect** → tighten the key's Windows ACL
  (see §2).
- **`sudo` prompts for a password during provision** → the default `ubuntu` user
  has passwordless sudo on Oracle images; if you changed that, provisioning needs
  an interactive session (the toolkit already allocates a TTY for bootstrap).
- **Service won't start after reboot, "out of host capacity" on resize** →
  resizing an A1 shape behaves like a fresh launch and can fail on busy regions.
  Don't resize casually; if you must, stop the instance first, then edit, then
  start, and try a different fault domain.
- **Bot reclaimed / instance stopped** → the halved Always-Free Ampere limit
  (2 OCPU / 12 GB, June 2026) is enforced by shutdown on pure free-tier accounts.
  Keeping to 1 OCPU / 6 GB stays well under it. A long-lived Discord websocket
  generates steady traffic, so genuine idle-reclamation is unlikely; monitor via
  **Billing → Cost Management** rather than adding artificial CPU load.
- **`/play` returns "Couldn't find anything for that" on VM but works locally** →
  YouTube blocks many datacenter IPs (Oracle included). VM logs show
  `Sign in to confirm you're not a bot`. `bootstrap.sh` installs the
  `bgutil-provider` Docker container (PO tokens on `127.0.0.1:4416`), a
  **WARP SOCKS sidecar** (`warp-proxy` on `127.0.0.1:1080`), and
  `bgutil-ytdlp-pot-provider` + `curl-cffi` in the venv. Verify with
  `manage.ps1 pot-status`, `manage.ps1 warp-status`, and
  `manage.ps1 test-ytdlp` (look for `with_pot_plugin` → OK).
- **`Now playing` but no audio / song ends in seconds** → see
  `playback-architecture.md §9`. Playback pipes **yt-dlp → FFmpeg** (not a raw
  `googlevideo.com` URL). Logs showing `HTTP error 403 Forbidden` on
  `googlevideo.com` mean an old build — redeploy with `manage.ps1 deploy`.
- **First couple of seconds of each song missing** → yt-dlp subprocess cold start;
  current code prerolls ~16 KiB before FFmpeg decodes (`playback-architecture.md §5`).
- **WARP + POT on ARM** — `ghcr.io/kingcc/warproxy` has no `linux/arm64` image;
  bootstrap falls back to `ghcr.io/mon-ius/docker-warp-socks` with `NET_PORT=1080`.
  POT container uses `--network host` so BotGuard fetches can reach `127.0.0.1:1080`.

**Baseline probe (2026-07-08, before POT):** local `default` → OK (residential IP);
VM `default` / `android_ios_tv` / `tv_embedded` / `web_safari` → all FAIL with
`Sign in to confirm you're not a bot`; `pot_provider_reachable` → FAIL (not yet
installed); `with_pot_plugin` → SKIP (plugin not installed).

**Post-POT probe (2026-07-08):** `pot_provider_reachable` → OK (`/ping` 200);
`with_pot_plugin` → OK on acceptance URL (`dQw4w9WgXcQ`); probe URL still fails
(datacenter IP). Major-label music (e.g. Taylor Swift) may still fail even with
POT; use `/play never gonna give you up` for smoke tests. Deno must be on
`PATH` (bootstrap installs to `~/.deno/bin`; `cadence.service` includes it).

**Post-WARP probe:** `warp_proxy_reachable` → OK; `with_pot_plugin` uses
production opts (WARP proxy + `impersonate=chrome` + `tv` client rotation).
`hard_acceptance` (Love Story) is informational — may still fail on WARP egress.

---

## 9. Teardown

```powershell
.\tools\oracle\manage.ps1 stop
.\tools\oracle\manage.ps1 disable
```

To remove entirely, terminate the instance from the Oracle console
(**Compute → Instances → … → Terminate**). Because all state is in-memory
(`G-005`), there is nothing to back up on the bot side.
