#!/usr/bin/env pwsh
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("provision", "deploy", "push-env", "push-cookies", "status", "logs", "start", "stop", "restart", "enable", "disable", "ssh", "test", "test-ytdlp", "test-urls", "pot-status", "pot-restart", "warp-status", "warp-restart")]
    [string]$Command,
    [string]$RepoUrl = "",
    [int]$Lines = 200
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$TOOLS_DIR = $SCRIPT_DIR
$REPO_ROOT = Split-Path -Parent (Split-Path -Parent $SCRIPT_DIR)
$ENV_FILE = Join-Path $REPO_ROOT ".env"
$RUNTIME_ENV_KEYS = @("DISCORD_TOKEN", "DISCORD_GUILD_ID", "LOG_LEVEL", "CADENCE_DEFAULT_VOLUME")
$REMOTE_COOKIE_PATH = "/opt/cadence/youtube_cookies.txt"
$DEFAULT_LOCAL_COOKIE_PATH = Join-Path $REPO_ROOT "keys/youtube_cookies.txt"
$REMOTE_TMP_DIR = "/tmp/cadence-tools"
$REMOTE_APP_DIR = "/opt/cadence"
$REMOTE_SERVICE_PATH = "/etc/systemd/system/cadence.service"
$POT_CONTAINER_NAME = "bgutil-provider"
$POT_IMAGE = "brainicism/bgutil-ytdlp-pot-provider:1.3.1-deno"
$POT_PORT = "4416"
$WARP_CONTAINER_NAME = "warp-proxy"
$WARP_PORT = "1080"
$DEFAULT_YTDLP_PROXY = "socks5h://127.0.0.1:1080"
$DEFAULT_YTDLP_IMPERSONATE = "chrome"

function Fail([string]$Message) {
    throw $Message
}

function Info([string]$Message) {
    Write-Host "[oracle] $Message"
}

function Read-DotEnvFile([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        Fail "Missing .env at '$Path'. Run this command from the repository root or create .env first."
    }

    $values = @{}
    foreach ($line in [System.IO.File]::ReadAllLines($Path)) {
        $trimmed = $line.Trim()
        if ([string]::IsNullOrWhiteSpace($trimmed) -or $trimmed.StartsWith("#")) {
            continue
        }

        $eqIndex = $trimmed.IndexOf("=")
        if ($eqIndex -lt 1) {
            continue
        }

        $key = $trimmed.Substring(0, $eqIndex).Trim()
        $value = $trimmed.Substring($eqIndex + 1)
        $values[$key] = $value
    }
    return $values
}

function Get-EnvValue([hashtable]$EnvMap, [string]$Key, [bool]$Required = $true) {
    if ($EnvMap.ContainsKey($Key)) {
        $value = [string]$EnvMap[$Key]
        if (-not [string]::IsNullOrWhiteSpace($value)) {
            return $value
        }
    }
    if ($Required) {
        Fail "Missing required '$Key' in .env."
    }
    return ""
}

function New-SshArgs([string]$TargetHost, [string]$User, [string]$KeyPath, [string]$RemoteCommand) {
    $args = @(
        "-i", $KeyPath,
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "IdentitiesOnly=yes",
        "$User@$TargetHost"
    )
    if (-not [string]::IsNullOrWhiteSpace($RemoteCommand)) {
        $args += $RemoteCommand
    }
    return $args
}

function New-ScpArgs([string]$KeyPath, [string]$SourcePath, [string]$TargetSpec) {
    return @(
        "-i", $KeyPath,
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "IdentitiesOnly=yes",
        $SourcePath,
        $TargetSpec
    )
}

function Invoke-External([string]$Program, [string[]]$ProgramArgs, [string]$ErrorMessage) {
    & $Program @ProgramArgs
    if ($LASTEXITCODE -ne 0) {
        Fail "$ErrorMessage (exit code $LASTEXITCODE)"
    }
}

function Invoke-Remote([hashtable]$Conn, [string]$RemoteCommand) {
    $sshArgs = New-SshArgs -TargetHost $Conn.OracleHost -User $Conn.User -KeyPath $Conn.KeyPath -RemoteCommand $RemoteCommand
    Invoke-External -Program "ssh" -ProgramArgs $sshArgs -ErrorMessage "SSH command failed"
}

function Copy-TreeToRemote([hashtable]$Conn, [string]$LocalPath, [string]$RemoteDir) {
    if (-not (Test-Path -LiteralPath $LocalPath)) {
        Fail "Local path not found: '$LocalPath'"
    }
    $targetSpec = "$($Conn.User)@$($Conn.OracleHost):$RemoteDir"
    $scpArgs = @(
        "-i", $Conn.KeyPath,
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "IdentitiesOnly=yes",
        "-r",
        $LocalPath,
        $targetSpec
    )
    Invoke-External -Program "scp" -ProgramArgs $scpArgs -ErrorMessage "SCP upload failed for '$LocalPath'"
}

function Sync-ApplicationCode([hashtable]$Conn) {
    Info "Uploading application source to $REMOTE_APP_DIR"
    Copy-TreeToRemote -Conn $Conn -LocalPath (Join-Path $REPO_ROOT "cadence") -RemoteDir "$REMOTE_APP_DIR/"
    foreach ($file in @("requirements.txt", "pyproject.toml")) {
        $localFile = Join-Path $REPO_ROOT $file
        if (Test-Path -LiteralPath $localFile) {
            Copy-ToRemote -Conn $Conn -LocalPath $localFile -RemotePath "$REMOTE_APP_DIR/$file"
        }
    }
}

function Copy-ToRemote([hashtable]$Conn, [string]$LocalPath, [string]$RemotePath) {
    if (-not (Test-Path -LiteralPath $LocalPath)) {
        Fail "Local file missing: $LocalPath"
    }
    $targetSpec = "$($Conn.User)@$($Conn.OracleHost):$RemotePath"
    $scpArgs = New-ScpArgs -KeyPath $Conn.KeyPath -SourcePath $LocalPath -TargetSpec $targetSpec
    Invoke-External -Program "scp" -ProgramArgs $scpArgs -ErrorMessage "SCP upload failed for '$LocalPath'"
}

function Get-Connection([hashtable]$EnvMap) {
    $oracleHost = Get-EnvValue -EnvMap $EnvMap -Key "ORACLE_HOST"
    $user = Get-EnvValue -EnvMap $EnvMap -Key "ORACLE_USER"
    $keyPath = Get-EnvValue -EnvMap $EnvMap -Key "ORACLE_SSH_KEY"

    if (-not (Test-Path -LiteralPath $keyPath)) {
        Fail "ORACLE_SSH_KEY path does not exist: '$keyPath'"
    }

    return @{
        OracleHost = $oracleHost
        User = $user
        KeyPath = $keyPath
    }
}

function Assert-RuntimeEnvPresent([hashtable]$EnvMap) {
    foreach ($key in $RUNTIME_ENV_KEYS) {
        [void](Get-EnvValue -EnvMap $EnvMap -Key $key)
    }
}

function Resolve-LocalCookiePath([hashtable]$EnvMap) {
    $configured = Get-EnvValue -EnvMap $EnvMap -Key "YOUTUBE_COOKIES_FILE" -Required $false
    if (-not [string]::IsNullOrWhiteSpace($configured)) {
        return $configured
    }
    return $DEFAULT_LOCAL_COOKIE_PATH
}

function Get-RuntimeEnvEntries([hashtable]$EnvMap, [bool]$IncludeCookies) {
    Assert-RuntimeEnvPresent -EnvMap $EnvMap
    $entries = [ordered]@{}
    foreach ($key in $RUNTIME_ENV_KEYS) {
        $entries[$key] = [string]$EnvMap[$key]
    }
    if ($IncludeCookies) {
        $entries["YTDLP_COOKIE_FILE"] = $REMOTE_COOKIE_PATH
    }
    if ($EnvMap.ContainsKey("YTDLP_PROXY") -and -not [string]::IsNullOrWhiteSpace([string]$EnvMap["YTDLP_PROXY"])) {
        $entries["YTDLP_PROXY"] = [string]$EnvMap["YTDLP_PROXY"]
    }
    else {
        $entries["YTDLP_PROXY"] = $DEFAULT_YTDLP_PROXY
    }
    if ($EnvMap.ContainsKey("YTDLP_IMPERSONATE") -and -not [string]::IsNullOrWhiteSpace([string]$EnvMap["YTDLP_IMPERSONATE"])) {
        $entries["YTDLP_IMPERSONATE"] = [string]$EnvMap["YTDLP_IMPERSONATE"]
    }
    else {
        $entries["YTDLP_IMPERSONATE"] = $DEFAULT_YTDLP_IMPERSONATE
    }
    return $entries
}

function Write-TempRuntimeEnv([hashtable]$EnvMap, [bool]$IncludeCookies) {
    $entries = Get-RuntimeEnvEntries -EnvMap $EnvMap -IncludeCookies:$IncludeCookies

    $lines = @()
    foreach ($entry in $entries.GetEnumerator()) {
        $value = $entry.Value -replace "`r", "" -replace "`n", ""
        $lines += "$($entry.Key)=$value"
    }
    $content = ($lines -join "`n") + "`n"

    $tempFile = [System.IO.Path]::GetTempFileName()
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($tempFile, $content, $utf8NoBom)
    return $tempFile
}

function Should-IncludeCookies([hashtable]$EnvMap) {
    $cookiePath = Resolve-LocalCookiePath -EnvMap $EnvMap
    return Test-Path -LiteralPath $cookiePath
}

function Sync-ToolkitFiles([hashtable]$Conn) {
    Info "Uploading toolkit files to $REMOTE_TMP_DIR"
    Invoke-Remote -Conn $Conn -RemoteCommand "mkdir -p $REMOTE_TMP_DIR"

    Copy-ToRemote -Conn $Conn -LocalPath (Join-Path $TOOLS_DIR "bootstrap.sh") -RemotePath "$REMOTE_TMP_DIR/bootstrap.sh"
    Copy-ToRemote -Conn $Conn -LocalPath (Join-Path $TOOLS_DIR "cadence.service") -RemotePath "$REMOTE_TMP_DIR/cadence.service"
    Copy-ToRemote -Conn $Conn -LocalPath (Join-Path $TOOLS_DIR "healthcheck.sh") -RemotePath "$REMOTE_TMP_DIR/healthcheck.sh"
    Copy-ToRemote -Conn $Conn -LocalPath (Join-Path $TOOLS_DIR "test_ytdlp_vm.py") -RemotePath "$REMOTE_TMP_DIR/test_ytdlp_vm.py"
    Copy-ToRemote -Conn $Conn -LocalPath (Join-Path $TOOLS_DIR "test_urls_vm.py") -RemotePath "$REMOTE_TMP_DIR/test_urls_vm.py"

    Invoke-Remote -Conn $Conn -RemoteCommand "chmod +x $REMOTE_TMP_DIR/bootstrap.sh $REMOTE_TMP_DIR/healthcheck.sh $REMOTE_TMP_DIR/test_ytdlp_vm.py $REMOTE_TMP_DIR/test_urls_vm.py"
}

function Push-RuntimeEnv([hashtable]$Conn, [hashtable]$EnvMap) {
    $includeCookies = Should-IncludeCookies -EnvMap $EnvMap
    $tempFile = Write-TempRuntimeEnv -EnvMap $EnvMap -IncludeCookies:$includeCookies
    try {
        Info "Pushing runtime .env to $REMOTE_APP_DIR/.env"
        Copy-ToRemote -Conn $Conn -LocalPath $tempFile -RemotePath "/tmp/cadence.runtime.env"
        Invoke-Remote -Conn $Conn -RemoteCommand "sudo install -o $($Conn.User) -g $($Conn.User) -m 600 /tmp/cadence.runtime.env $REMOTE_APP_DIR/.env && rm -f /tmp/cadence.runtime.env"
    }
    finally {
        if (Test-Path -LiteralPath $tempFile) {
            Remove-Item -LiteralPath $tempFile -Force
        }
    }
}

function Push-Cookies([hashtable]$Conn, [hashtable]$EnvMap) {
    $localCookiePath = Resolve-LocalCookiePath -EnvMap $EnvMap
    if (-not (Test-Path -LiteralPath $localCookiePath)) {
        Fail "Cookie file not found at '$localCookiePath'. Export YouTube cookies to this path first."
    }

    Info "Uploading YouTube cookies to $REMOTE_COOKIE_PATH"
    Copy-ToRemote -Conn $Conn -LocalPath $localCookiePath -RemotePath "/tmp/youtube_cookies.txt"
    Invoke-Remote -Conn $Conn -RemoteCommand "sudo install -o $($Conn.User) -g $($Conn.User) -m 600 /tmp/youtube_cookies.txt $REMOTE_COOKIE_PATH && rm -f /tmp/youtube_cookies.txt"
    Push-RuntimeEnv -Conn $Conn -EnvMap $EnvMap
    Invoke-Remote -Conn $Conn -RemoteCommand "sudo systemctl restart cadence"
    Info "Cookies pushed and service restarted"
}

function Install-Service([hashtable]$Conn) {
    Info "Installing cadence systemd service"
    Invoke-Remote -Conn $Conn -RemoteCommand "sed 's/^User=.*/User=$($Conn.User)/; s/^Group=.*/Group=$($Conn.User)/' $REMOTE_TMP_DIR/cadence.service | sudo tee $REMOTE_SERVICE_PATH >/dev/null"
    Invoke-Remote -Conn $Conn -RemoteCommand "sudo install -m 755 $REMOTE_TMP_DIR/healthcheck.sh $REMOTE_APP_DIR/healthcheck.sh"
    Invoke-Remote -Conn $Conn -RemoteCommand "sudo systemctl daemon-reload"
    Invoke-Remote -Conn $Conn -RemoteCommand "sudo systemctl enable --now cadence"
}

function Invoke-Provision([hashtable]$Conn, [hashtable]$EnvMap, [string]$RepoUrl) {
    Sync-ToolkitFiles -Conn $Conn

    $repoEnv = if ([string]::IsNullOrWhiteSpace($RepoUrl)) { "" } else { "REPO_URL='$RepoUrl'" }
    $bootstrapCmd = "sudo $repoEnv APP_USER='$($Conn.User)' bash $REMOTE_TMP_DIR/bootstrap.sh"
    Info "Running remote bootstrap"
    Invoke-Remote -Conn $Conn -RemoteCommand $bootstrapCmd

    Push-RuntimeEnv -Conn $Conn -EnvMap $EnvMap
    Install-Service -Conn $Conn

    Info "Provision complete. Current service status:"
    Invoke-Remote -Conn $Conn -RemoteCommand "sudo systemctl --no-pager --full status cadence"
}

function Test-RemoteGitCheckout([hashtable]$Conn) {
    try {
        Invoke-Remote -Conn $Conn -RemoteCommand "test -d '$REMOTE_APP_DIR/.git'"
        return $true
    }
    catch {
        return $false
    }
}

function Invoke-Deploy([hashtable]$Conn, [hashtable]$EnvMap) {
    Sync-ToolkitFiles -Conn $Conn

    if (-not (Test-RemoteGitCheckout -Conn $Conn)) {
        Sync-ApplicationCode -Conn $Conn
    }

    $updateCmd = @(
        "set -euo pipefail",
        "if [ -d '$REMOTE_APP_DIR/.git' ]; then",
        "  echo '[oracle] Pulling latest code'",
        "  git -C '$REMOTE_APP_DIR' pull --ff-only",
        "else",
        "  echo '[oracle] No git checkout found, using uploaded source tree'",
        "fi",
        "if [ -f '$REMOTE_APP_DIR/requirements.txt' ]; then",
        "  '$REMOTE_APP_DIR/.venv/bin/pip' install -r '$REMOTE_APP_DIR/requirements.txt'",
        "else",
        "  echo '[oracle] WARNING: requirements.txt missing; skipping pip install'",
        "fi"
    ) -join "`n"

    Info "Applying code/dependency updates"
    Invoke-Remote -Conn $Conn -RemoteCommand "bash -lc ""$updateCmd"""

    Push-RuntimeEnv -Conn $Conn -EnvMap $EnvMap
    Install-Service -Conn $Conn

    Info "Restarting cadence service"
    Invoke-Remote -Conn $Conn -RemoteCommand "sudo systemctl restart cadence"
    Invoke-Remote -Conn $Conn -RemoteCommand "sudo systemctl --no-pager --full status cadence"
    Invoke-Remote -Conn $Conn -RemoteCommand "sudo journalctl -u cadence -n 40 --no-pager"
}

function Invoke-Logs([hashtable]$Conn, [int]$Lines) {
    Invoke-Remote -Conn $Conn -RemoteCommand "sudo journalctl -u cadence -n $Lines --no-pager"
}

function Invoke-Test([hashtable]$Conn) {
    Sync-ToolkitFiles -Conn $Conn
    Invoke-Remote -Conn $Conn -RemoteCommand "sudo install -m 755 $REMOTE_TMP_DIR/healthcheck.sh $REMOTE_APP_DIR/healthcheck.sh"
    Invoke-Remote -Conn $Conn -RemoteCommand "sudo install -m 755 $REMOTE_TMP_DIR/test_ytdlp_vm.py $REMOTE_APP_DIR/test_ytdlp_vm.py"
    Invoke-Remote -Conn $Conn -RemoteCommand "sudo $REMOTE_APP_DIR/healthcheck.sh"
}

function Invoke-TestYtDlp([hashtable]$Conn) {
    Sync-ToolkitFiles -Conn $Conn
    Invoke-Remote -Conn $Conn -RemoteCommand "sudo install -m 755 $REMOTE_TMP_DIR/test_ytdlp_vm.py $REMOTE_APP_DIR/test_ytdlp_vm.py"
    $runCmd = "cd $REMOTE_APP_DIR && set -a && source .env && set +a && export PATH=/home/ubuntu/.deno/bin:`$PATH && PYTHONUNBUFFERED=1 $REMOTE_APP_DIR/.venv/bin/python $REMOTE_APP_DIR/test_ytdlp_vm.py"
    Invoke-Remote -Conn $Conn -RemoteCommand $runCmd
}

function Invoke-TestUrls([hashtable]$Conn) {
    Sync-ToolkitFiles -Conn $Conn
    Invoke-Remote -Conn $Conn -RemoteCommand "sudo install -m 755 $REMOTE_TMP_DIR/test_urls_vm.py $REMOTE_APP_DIR/test_urls_vm.py"
    $runCmd = "cd $REMOTE_APP_DIR && set -a && source .env && set +a && export PATH=/home/ubuntu/.deno/bin:`$PATH && PYTHONUNBUFFERED=1 $REMOTE_APP_DIR/.venv/bin/python $REMOTE_APP_DIR/test_urls_vm.py"
    Invoke-Remote -Conn $Conn -RemoteCommand $runCmd
}

function Invoke-PotStatus([hashtable]$Conn) {
    Invoke-Remote -Conn $Conn -RemoteCommand "docker ps --filter name=$POT_CONTAINER_NAME --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"
    Invoke-Remote -Conn $Conn -RemoteCommand "curl -fsS -o /dev/null -w 'POT HTTP %{http_code}\n' http://127.0.0.1:$POT_PORT/ping || echo 'POT HTTP unreachable'"
}

function Invoke-PotRestart([hashtable]$Conn) {
    Invoke-Remote -Conn $Conn -RemoteCommand "docker restart $POT_CONTAINER_NAME"
    Invoke-PotStatus -Conn $Conn
}

function Invoke-WarpStatus([hashtable]$Conn) {
    Invoke-Remote -Conn $Conn -RemoteCommand "docker ps --filter name=$WARP_CONTAINER_NAME --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"
    Invoke-Remote -Conn $Conn -RemoteCommand "curl -fsS --max-time 15 --proxy socks5h://127.0.0.1:$WARP_PORT https://ifconfig.me -o /dev/null -w 'WARP egress IP check HTTP %{http_code}\n' || echo 'WARP proxy unreachable'"
}

function Invoke-WarpRestart([hashtable]$Conn) {
    Invoke-Remote -Conn $Conn -RemoteCommand "docker restart $WARP_CONTAINER_NAME"
    Invoke-WarpStatus -Conn $Conn
}

function Main {
    if ([string]::IsNullOrWhiteSpace($Command)) {
        Write-Host "Usage: .\tools\oracle\manage.ps1 <command> [-RepoUrl <url>] [-Lines <n>]"
        Write-Host "Commands: provision, deploy, push-env, push-cookies, status, logs, start, stop, restart, enable, disable, ssh, test, test-ytdlp, test-urls, pot-status, pot-restart, warp-status, warp-restart"
        exit 1
    }

    $envMap = Read-DotEnvFile -Path $ENV_FILE
    $conn = Get-Connection -EnvMap $envMap

    switch ($Command) {
        "provision" { Invoke-Provision -Conn $conn -EnvMap $envMap -RepoUrl $RepoUrl }
        "deploy" { Invoke-Deploy -Conn $conn -EnvMap $envMap }
        "push-env" { Push-RuntimeEnv -Conn $conn -EnvMap $envMap }
        "push-cookies" { Push-Cookies -Conn $conn -EnvMap $envMap }
        "status" { Invoke-Remote -Conn $conn -RemoteCommand "sudo systemctl --no-pager --full status cadence" }
        "logs" { Invoke-Logs -Conn $conn -Lines $Lines }
        "start" { Invoke-Remote -Conn $conn -RemoteCommand "sudo systemctl start cadence" }
        "stop" { Invoke-Remote -Conn $conn -RemoteCommand "sudo systemctl stop cadence" }
        "restart" { Invoke-Remote -Conn $conn -RemoteCommand "sudo systemctl restart cadence" }
        "enable" { Invoke-Remote -Conn $conn -RemoteCommand "sudo systemctl enable cadence" }
        "disable" { Invoke-Remote -Conn $conn -RemoteCommand "sudo systemctl disable cadence" }
        "ssh" {
            $sshArgs = New-SshArgs -TargetHost $conn.OracleHost -User $conn.User -KeyPath $conn.KeyPath -RemoteCommand ""
            Invoke-External -Program "ssh" -ProgramArgs $sshArgs -ErrorMessage "Failed to open SSH session"
        }
        "test" { Invoke-Test -Conn $conn }
        "test-ytdlp" { Invoke-TestYtDlp -Conn $conn }
        "test-urls" { Invoke-TestUrls -Conn $conn }
        "pot-status" { Invoke-PotStatus -Conn $conn }
        "pot-restart" { Invoke-PotRestart -Conn $conn }
        "warp-status" { Invoke-WarpStatus -Conn $conn }
        "warp-restart" { Invoke-WarpRestart -Conn $conn }
        default { Fail "Unknown command '$Command'" }
    }
}

Main
