#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/cadence"
APP_USER="${APP_USER:-ubuntu}"
REPO_URL="${REPO_URL:-}"
SWAPFILE="/swapfile"

log() {
  echo "[oracle-bootstrap] $*"
}

fail() {
  echo "[oracle-bootstrap] ERROR: $*" >&2
  exit 1
}

require_root() {
  if [[ "${EUID}" -ne 0 ]]; then
    fail "Run as root (use sudo)."
  fi
}

run_as_user() {
  local cmd="$1"
  su -s /bin/bash - "${APP_USER}" -c "${cmd}"
}

ensure_packages() {
  log "Installing apt dependencies"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y \
    ffmpeg \
    git \
    curl \
    ca-certificates \
    build-essential \
    libffi-dev \
    libsodium-dev
}

ensure_swap() {
  if swapon --show | awk '{print $1}' | grep -qx "${SWAPFILE}"; then
    log "Swapfile already active"
    return
  fi

  if [[ ! -f "${SWAPFILE}" ]]; then
    log "Creating 2GB swapfile"
    fallocate -l 2G "${SWAPFILE}" || dd if=/dev/zero of="${SWAPFILE}" bs=1M count=2048 status=progress
    chmod 600 "${SWAPFILE}"
    mkswap "${SWAPFILE}"
  fi

  swapon "${SWAPFILE}"
  if ! grep -qE "^${SWAPFILE}[[:space:]]+none[[:space:]]+swap" /etc/fstab; then
    echo "${SWAPFILE} none swap sw 0 0" >> /etc/fstab
  fi
  log "Swapfile enabled"
}

ensure_ssh_rule() {
  if command -v iptables >/dev/null 2>&1; then
    if ! iptables -C INPUT -p tcp --dport 22 -j ACCEPT >/dev/null 2>&1; then
      log "Adding iptables INPUT rule for SSH (22)"
      iptables -I INPUT -p tcp --dport 22 -j ACCEPT
    fi
  fi
}

ensure_uv() {
  if run_as_user "command -v uv >/dev/null 2>&1"; then
    log "uv already installed"
    return
  fi

  log "Installing uv for ${APP_USER}"
  run_as_user "curl -LsSf https://astral.sh/uv/install.sh | sh"
}

ensure_python() {
  log "Ensuring Python 3.11 via uv"
  run_as_user "export PATH=\$HOME/.local/bin:\$PATH; uv python install 3.11"
}

ensure_app_dir() {
  mkdir -p "${APP_DIR}"
  chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"
}

sync_repo_if_configured() {
  if [[ -z "${REPO_URL}" ]]; then
    log "REPO_URL not set, using existing tree in ${APP_DIR}"
    return
  fi

  if [[ -d "${APP_DIR}/.git" ]]; then
    log "Git checkout detected, pulling latest"
    run_as_user "git -C '${APP_DIR}' fetch --all --tags --prune"
    run_as_user "git -C '${APP_DIR}' pull --ff-only"
    return
  fi

  if [[ -z "$(ls -A "${APP_DIR}")" ]]; then
    log "Cloning repository into ${APP_DIR}"
    run_as_user "git clone '${REPO_URL}' '${APP_DIR}'"
  else
    log "Non-empty ${APP_DIR} without .git; preserving existing files (fallback copy mode)"
  fi
}

ensure_venv_and_deps() {
  if [[ ! -f "${APP_DIR}/requirements.txt" ]]; then
    fail "Missing ${APP_DIR}/requirements.txt. Copy source tree or set REPO_URL."
  fi

  log "Creating/updating virtual environment"
  run_as_user "export PATH=\$HOME/.local/bin:\$PATH; cd '${APP_DIR}'; if [[ ! -d .venv ]]; then uv venv --python 3.11 .venv; fi"
  run_as_user "cd '${APP_DIR}'; .venv/bin/python -m ensurepip --upgrade"
  run_as_user "cd '${APP_DIR}'; .venv/bin/python -m pip install --upgrade pip"
  run_as_user "cd '${APP_DIR}'; .venv/bin/python -m pip install -r requirements.txt"
}

ensure_docker() {
  if command -v docker >/dev/null 2>&1; then
    log "Docker already installed"
  else
    log "Installing Docker"
    apt-get install -y docker.io
    systemctl enable --now docker
  fi
  if ! id -nG "${APP_USER}" | tr ' ' '\n' | grep -qx docker; then
    usermod -aG docker "${APP_USER}" || true
  fi
}

ensure_deno() {
  local deno_bin="/home/${APP_USER}/.deno/bin/deno"
  if [[ -x "${deno_bin}" ]]; then
    log "Deno already installed"
    return
  fi

  log "Installing Deno (yt-dlp JS runtime)"
  apt-get install -y unzip
  run_as_user "curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/home/${APP_USER}/.deno sh"
}

ensure_warp_proxy() {
  local image="ghcr.io/kingcc/warproxy:latest"
  local name="warp-proxy"

  if docker ps --filter "name=${name}" --filter "status=running" -q | grep -q .; then
    log "WARP proxy container already running"
    return
  fi

  if docker ps -a --filter "name=${name}" -q | grep -q .; then
    log "Starting existing WARP proxy container"
    docker start "${name}"
    return
  fi

  log "Pulling and starting WARP proxy container (${image})"
  if ! docker pull "${image}"; then
    log "WARN: ${image} pull failed; trying ARM fallback image"
    image="ghcr.io/mon-ius/docker-warp-socks:latest"
    docker pull "${image}"
    docker run --name "${name}" -d --restart unless-stopped \
      -e NET_PORT=1080 \
      -p 127.0.0.1:1080:1080 "${image}"
    log "WARP proxy listening on 127.0.0.1:1080 (mon-ius fallback)"
    return
  fi
  docker run --name "${name}" -d --restart unless-stopped \
    -p 127.0.0.1:1080:1080 "${image}"
  log "WARP proxy listening on 127.0.0.1:1080"
}

ensure_pot_provider() {
  local image="brainicism/bgutil-ytdlp-pot-provider:1.3.1-deno"
  local name="bgutil-provider"

  if docker ps --filter "name=${name}" --filter "status=running" -q | grep -q .; then
    log "POT provider container already running"
    return
  fi

  if docker ps -a --filter "name=${name}" -q | grep -q .; then
    log "Starting existing POT provider container"
    docker start "${name}"
    return
  fi

  log "Pulling and starting POT provider container"
  docker pull "${image}"
  # Host network lets POT reach the WARP SOCKS proxy on 127.0.0.1:1080 when yt-dlp
  # forwards its proxy for BotGuard (PO tokens must match the download egress IP).
  docker run --name "${name}" -d --restart unless-stopped --init \
    --network host "${image}"
  log "POT provider listening on 127.0.0.1:4416 (host network)"
}

main() {
  require_root
  ensure_packages
  ensure_swap
  ensure_ssh_rule
  ensure_app_dir
  ensure_uv
  ensure_python
  sync_repo_if_configured
  ensure_venv_and_deps
  ensure_deno
  ensure_docker
  ensure_warp_proxy
  ensure_pot_provider
  log "Bootstrap complete"
}

main "$@"
