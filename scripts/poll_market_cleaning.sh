#!/usr/bin/env bash
# Host scheduler entry: coordinate locally, persist all results on Sandisk.
set -euo pipefail
export PATH=/home/linuxbrew/.linuxbrew/bin:/home/drwho1985/.local/bin:/usr/local/bin:/usr/bin:/bin
export TMPDIR=/dev/shm
export PYTHONDONTWRITEBYTECODE=1
export R_LIBS_USER=/home/drwho1985/workspace/algotradinglife/beijing-lot/r_lib
data_root=/run/media/drwho1985/Sandisk/data/beijing-lot
/usr/bin/mountpoint -q /run/media/drwho1985/Sandisk
/home/drwho1985/workspace/algotradinglife/beijing-lot/.venv/bin/python /home/drwho1985/.codex/worktrees/0aac/beijing-lot/scripts/check_persistent_data_layout.py --contract /home/drwho1985/.codex/worktrees/0aac/beijing-lot/config/persistent_data_layout.json >/dev/null
[[ -f "$data_root/registry/markets-current.json" ]] || exit 0
# Preserve the existing coordination inode while a prior run/migration holds it.
lock_dir=/home/drwho1985/.local/state/beijing-lot-market-cleaning
mkdir -p "$lock_dir"
exec 9>"$lock_dir/run.lock"
/usr/bin/flock -n 9 || exit 0
state="$data_root/runtime/state/market-cleaning"
logs="$data_root/runtime/logs/market-cleaning"
mkdir -p "$state" "$logs"
cd /home/drwho1985/.codex/worktrees/0aac/beijing-lot
log="$logs/$(date -u +%Y%m%dT%H%M%SZ).log"
exec /home/linuxbrew/.linuxbrew/bin/codex exec -C "$PWD" -s danger-full-access -c 'approval_policy="never"' -o "$state/last-result.txt" - < ops/market_cleaning_poll.prompt >> "$log" 2>&1
