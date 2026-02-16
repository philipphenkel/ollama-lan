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
UNIT="ollama-lan.service"

if command -v systemctl >/dev/null 2>&1; then
  # Stop + disable (works even if already stopped/disabled)
  $SUDO systemctl disable --now "$UNIT" 2>/dev/null || true

  # Ensure no processes remain in the unit's cgroup (important with Restart=on-failure)
  $SUDO systemctl kill --kill-who=all "$UNIT" 2>/dev/null || true
  $SUDO systemctl reset-failed "$UNIT" 2>/dev/null || true
fi

# Remove unit + binaries
$SUDO rm -f /etc/systemd/system/"$UNIT"
$SUDO rm -f /usr/local/bin/ollama-lan
$SUDO rm -rf "$OLLAMA_LAN_DIR"

# Now reload so systemd forgets the removed unit file
if command -v systemctl >/dev/null 2>&1; then
  $SUDO systemctl daemon-reload 2>/dev/null || true
fi

echo "Uninstall complete."
