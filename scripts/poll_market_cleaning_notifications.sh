#!/usr/bin/env bash
set -euo pipefail
export PATH=/home/linuxbrew/.linuxbrew/bin:/home/drwho1985/.local/bin:/usr/local/bin:/usr/bin:/bin
export TMPDIR=/dev/shm
export PYTHONDONTWRITEBYTECODE=1
cd /home/drwho1985/.codex/worktrees/0aac/beijing-lot
exec /home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python scripts/notify_market_cleaning.py --contract config/persistent_data_layout.json --config config/market_cleaning_notifications.json
