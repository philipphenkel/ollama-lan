#!/usr/bin/env bash
if [ -z "${BASH_VERSION:-}" ]; then
  exec /usr/bin/env bash "$0" "$@"
fi
set -euo pipefail

if [ "$(uname -s)" != "Linux" ]; then
  echo "This uninstaller is for Linux only." >&2
  exit 1
fi

if [ "${EUID:-$(id -u)}" -ne 0 ]; then
  if command -v sudo >/dev/null 2>&1; then
    SUDO="sudo"
  else
    echo "This uninstaller needs root privileges (no sudo found)." >&2
    exit 1
  fi
else
  SUDO=""
fi

OLLAMA_LAN_DIR="${OLLAMA_LAN_DIR:-/opt/ollama-lan}"

if command -v systemctl >/dev/null 2>&1; then
  if systemctl list-unit-files | grep -q "^ollama-lan.service"; then
    $SUDO systemctl stop ollama-lan || true
    $SUDO systemctl disable ollama-lan || true
    $SUDO systemctl daemon-reload
  fi
fi

$SUDO rm -f /etc/systemd/system/ollama-lan.service
$SUDO rm -f /usr/local/bin/ollama-lan
$SUDO rm -rf "$OLLAMA_LAN_DIR"

echo "Uninstall complete."
