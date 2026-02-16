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
OLLAMA_LAN_USER="${OLLAMA_LAN_USER:-${SUDO_USER:-$(id -un)}}"

if command -v systemctl >/dev/null 2>&1; then
  $SUDO systemctl stop ollama-lan || true
  $SUDO systemctl disable ollama-lan || true
  $SUDO systemctl daemon-reload || true

  if [ "$OLLAMA_LAN_USER" != "root" ]; then
    if command -v su >/dev/null 2>&1; then
      su -s /bin/bash -c "systemctl --user stop ollama-lan || true" "$OLLAMA_LAN_USER" || true
      su -s /bin/bash -c "systemctl --user disable ollama-lan || true" "$OLLAMA_LAN_USER" || true
      su -s /bin/bash -c "systemctl --user daemon-reload || true" "$OLLAMA_LAN_USER" || true
    fi
  fi
fi

if command -v pgrep >/dev/null 2>&1; then
  pids="$(pgrep -f "${OLLAMA_LAN_DIR}/ollama-lan.py" || true)"
  if [ -n "$pids" ]; then
    $SUDO kill $pids || true
  fi
fi

$SUDO rm -f /etc/systemd/system/ollama-lan.service
$SUDO rm -f /usr/local/bin/ollama-lan
$SUDO rm -rf "$OLLAMA_LAN_DIR"

echo "Uninstall complete."
