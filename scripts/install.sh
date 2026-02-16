#!/usr/bin/env bash
if [ -z "${BASH_VERSION:-}" ]; then
  exec /usr/bin/env bash "$0" "$@"
fi
set -euo pipefail

if [ "$(uname -s)" != "Linux" ]; then
  echo "This installer is for Linux only." >&2
  exit 1
fi

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require_cmd python3
require_cmd tar

if command -v curl >/dev/null 2>&1; then
  FETCH="curl -fsSL"
elif command -v wget >/dev/null 2>&1; then
  FETCH="wget -qO-"
else
  echo "Missing required command: curl or wget" >&2
  exit 1
fi

if [ "${EUID:-$(id -u)}" -ne 0 ]; then
  if command -v sudo >/dev/null 2>&1; then
    SUDO="sudo"
  else
    echo "This installer needs root privileges (no sudo found)." >&2
    exit 1
  fi
else
  SUDO=""
fi

OLLAMA_LAN_REPO="${OLLAMA_LAN_REPO:-https://github.com/philipphenkel/ollama-lan}"
OLLAMA_LAN_REF="${OLLAMA_LAN_REF:-main}"
OLLAMA_LAN_DIR="${OLLAMA_LAN_DIR:-/opt/ollama-lan}"
OLLAMA_LAN_USER="${OLLAMA_LAN_USER:-${SUDO_USER:-$(id -un)}}"
OLLAMA_LAN_GROUP="${OLLAMA_LAN_GROUP:-$OLLAMA_LAN_USER}"
OLLAMA_LAN_HOST="${OLLAMA_LAN_HOST:-0.0.0.0}"
OLLAMA_LAN_PORT="${OLLAMA_LAN_PORT:-11440}"
OLLAMA_LAN_BASE_URL="${OLLAMA_LAN_BASE_URL:-http://localhost:11434}"
OLLAMA_LAN_MODEL="${OLLAMA_LAN_MODEL:-}"
OLLAMA_LAN_SHARE="${OLLAMA_LAN_SHARE:-false}"

TMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

ARCHIVE_URL="${OLLAMA_LAN_REPO}/archive/refs/heads/${OLLAMA_LAN_REF}.tar.gz"
echo "Downloading $ARCHIVE_URL"
$FETCH "$ARCHIVE_URL" | tar -xz -C "$TMP_DIR"

SRC_DIR="$TMP_DIR/ollama-lan-${OLLAMA_LAN_REF}"
if [ ! -f "$SRC_DIR/ollama-lan.py" ]; then
  echo "Install source missing ollama-lan.py. Check OLLAMA_LAN_REPO/REF." >&2
  exit 1
fi

$SUDO mkdir -p "$OLLAMA_LAN_DIR"
$SUDO cp "$SRC_DIR/ollama-lan.py" "$OLLAMA_LAN_DIR/ollama-lan.py"
$SUDO cp "$SRC_DIR/requirements.txt" "$OLLAMA_LAN_DIR/requirements.txt"
$SUDO chown -R "$OLLAMA_LAN_USER:$OLLAMA_LAN_GROUP" "$OLLAMA_LAN_DIR"

run_as_user() {
  local cmd="$*"
  if [ "${EUID:-$(id -u)}" -eq 0 ] && [ "$OLLAMA_LAN_USER" != "root" ]; then
    su -s /bin/bash -c "$cmd" "$OLLAMA_LAN_USER"
  else
    bash -lc "$cmd"
  fi
}

if [ ! -d "$OLLAMA_LAN_DIR/.venv" ]; then
  run_as_user "python3 -m venv \"$OLLAMA_LAN_DIR/.venv\""
fi
run_as_user "\"$OLLAMA_LAN_DIR/.venv/bin/pip\" install -r \"$OLLAMA_LAN_DIR/requirements.txt\""

if command -v systemctl >/dev/null 2>&1; then
  sd_quote() {
    local value="$1"
    value="${value//\\/\\\\}"
    value="${value//\"/\\\"}"
    printf '"%s"' "$value"
  }

  exec_line="ExecStart=${OLLAMA_LAN_DIR}/.venv/bin/python ${OLLAMA_LAN_DIR}/ollama-lan.py"
  exec_line="${exec_line} --host $(sd_quote "${OLLAMA_LAN_HOST}")"
  exec_line="${exec_line} --port $(sd_quote "${OLLAMA_LAN_PORT}")"
  exec_line="${exec_line} --ollama-base-url $(sd_quote "${OLLAMA_LAN_BASE_URL}")"
  if [ -n "${OLLAMA_LAN_MODEL:-}" ]; then
    exec_line="${exec_line} --model $(sd_quote "${OLLAMA_LAN_MODEL}")"
  fi
  case "${OLLAMA_LAN_SHARE:-false}" in
    1|true|TRUE|yes|YES) exec_line="${exec_line} --share" ;;
  esac

  cat <<EOF | $SUDO tee /etc/systemd/system/ollama-lan.service >/dev/null
[Unit]
Description=ollama-lan
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${OLLAMA_LAN_USER}
Group=${OLLAMA_LAN_GROUP}
WorkingDirectory=${OLLAMA_LAN_DIR}
${exec_line}
Restart=on-failure
RestartSec=2

[Install]
WantedBy=multi-user.target
EOF

  $SUDO systemctl daemon-reload
  $SUDO systemctl enable --now ollama-lan
  echo "Installed and started systemd service: ollama-lan"
else
  echo "systemd not found. Run manually: /usr/local/bin/ollama-lan"
fi

echo "Install complete."
