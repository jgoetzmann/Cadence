#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/cadence"
ENV_FILE="${APP_DIR}/.env"
SERVICE_NAME="cadence"
FAILURES=0

ok() {
  echo "[healthcheck] OK: $*"
}

warn() {
  echo "[healthcheck] WARN: $*"
}

err() {
  echo "[healthcheck] ERROR: $*"
  FAILURES=$((FAILURES + 1))
}

check_cmd() {
  local name="$1"
  local cmd="$2"
  if eval "${cmd}" >/dev/null 2>&1; then
    ok "${name}"
  else
    err "${name}"
  fi
}

echo "[healthcheck] Starting Cadence VM checks"

check_cmd "Python venv exists" "[ -x '${APP_DIR}/.venv/bin/python' ]"
check_cmd "Python 3.11 available in venv" "'${APP_DIR}/.venv/bin/python' -c \"import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)\""
check_cmd "FFmpeg available" "command -v ffmpeg"
check_cmd "Service unit loaded" "systemctl list-unit-files '${SERVICE_NAME}.service' --no-legend | grep -q '${SERVICE_NAME}.service'"
check_cmd "Service active" "systemctl is-active --quiet '${SERVICE_NAME}.service'"

if [[ -f "${ENV_FILE}" ]]; then
  ok ".env file exists"
  perms="$(stat -c '%a' "${ENV_FILE}")"
  if [[ "${perms}" == "600" ]]; then
    ok ".env permissions are 600"
  else
    err ".env permissions are ${perms} (expected 600)"
  fi

  if grep -q $'\r' "${ENV_FILE}"; then
    err ".env has CRLF line endings; re-run push-env to normalize to LF"
  else
    ok ".env line endings are LF"
  fi
else
  err ".env file missing at ${ENV_FILE}"
fi

check_cmd "POT provider container running" "docker ps --filter name=bgutil-provider --filter status=running -q | grep -q ."
check_cmd "POT provider HTTP reachable" "curl -fsS -o /dev/null http://127.0.0.1:4416/ping"
check_cmd "WARP proxy container running" "docker ps --filter name=warp-proxy --filter status=running -q | grep -q ."
check_cmd "WARP proxy reachable" "curl -fsS --max-time 15 --proxy socks5h://127.0.0.1:1080 https://ifconfig.me -o /dev/null"
check_cmd "bgutil plugin installed" "'${APP_DIR}/.venv/bin/python' -c \"import yt_dlp_plugins.extractor.getpot_bgutil_http\""
check_cmd "Deno runtime available" "[ -x '/home/ubuntu/.deno/bin/deno' ]"

if [[ -x "${APP_DIR}/test_ytdlp_vm.py" ]]; then
  echo "[healthcheck] Running yt-dlp POT probe"
  if "${APP_DIR}/.venv/bin/python" "${APP_DIR}/test_ytdlp_vm.py" 2>&1 | tail -n 5; then
    ok "yt-dlp POT probe passed"
  else
    err "yt-dlp POT probe failed"
  fi
fi

echo "[healthcheck] Recent service logs:"
journalctl -u "${SERVICE_NAME}" -n 25 --no-pager || warn "Unable to read journal logs"

if [[ "${FAILURES}" -gt 0 ]]; then
  echo "[healthcheck] Completed with ${FAILURES} failure(s)"
  exit 1
fi

echo "[healthcheck] All checks passed"
