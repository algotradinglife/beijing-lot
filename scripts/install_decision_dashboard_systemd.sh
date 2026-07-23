#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="$ROOT/ops/systemd/user"
TARGET_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

mkdir -p "$TARGET_DIR"
for unit in "$SOURCE_DIR"/*; do
  install -m 0644 "$unit" "$TARGET_DIR/$(basename "$unit")"
done

systemctl --user daemon-reload
systemctl --user enable beidanlot-decision-dashboard.target
systemctl --user enable beidanlot-decision-dashboard-health.timer
systemctl --user enable beidanlot-a9-coordinator.timer
systemctl --user restart beidanlot-decision-dashboard.target
