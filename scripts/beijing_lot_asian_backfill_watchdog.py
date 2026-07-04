#!/usr/bin/env python3
"""No-agent watchdog for the Beidan Asian-line backfill Kanban card."""
from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import subprocess
import time
from pathlib import Path


BOARD = "beijing-lot"
TASK_ID = "t_c0c33d16"
HERMES = os.environ.get("HERMES_BIN", "/home/drwho1985/.local/bin/hermes")
ROOT = Path("/home/drwho1985/workspace/soccer/beijing-lot/.worktrees/feature-beijing-lot-codex")
DB_PATH = ROOT / "data/derived/beidan_xlsm/beidan_nowscore_2026.sqlite"
PID_PATH = ROOT / "results/asian_line_backfill_20260629/asian_backfill.pid"
LOG_PATH = ROOT / "results/asian_line_backfill_20260629/asian_backfill.log"
STATE_PATH = Path("/home/drwho1985/.hermes/cron/state/beijing_lot_asian_backfill_watchdog.json")
EXPECTED_MATCHES = 6001
EXPECTED_ROWS = EXPECTED_MATCHES * 18 * 4
COMMENT_MATCH_STEP = 500
COMMENT_MIN_SECONDS = 30 * 60


def run_cmd(args: list[str], timeout: int = 45) -> str:
    proc = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())
    return proc.stdout


def load_state() -> dict:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(STATE_PATH)


def read_pid() -> int | None:
    try:
        return int(PID_PATH.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def process_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def db_progress() -> dict[str, int]:
    conn = sqlite3.connect(DB_PATH)
    total_matches = int(conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0])
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS rows,
            COUNT(DISTINCT match_id) AS matches,
            COALESCE(SUM(v1 IS NOT NULL OR v2 IS NOT NULL OR v3 IS NOT NULL), 0) AS nonnull_rows
        FROM market_snapshots
        WHERE market='asian_handicap'
        """
    ).fetchone()
    conn.close()
    rows = int(row[0] or 0)
    matches = int(row[1] or 0)
    nonnull_rows = int(row[2] or 0)
    return {
        "total_matches": total_matches,
        "rows": rows,
        "matches": matches,
        "nonnull_rows": nonnull_rows,
        "pct": int(math.floor(10000 * rows / EXPECTED_ROWS)),
    }


def log_progress() -> dict[str, int | str]:
    text = LOG_PATH.read_text(encoding="utf-8", errors="replace") if LOG_PATH.exists() else ""
    progress_lines = [line for line in text.splitlines() if line.startswith("[progress]")]
    warn_count = sum(1 for line in text.splitlines() if line.startswith("[warn]"))
    latest = progress_lines[-1] if progress_lines else ""
    out: dict[str, int | str] = {"latest": latest, "warn_count": warn_count}
    m = re.search(r"attempted=(\d+)\s+skipped=(\d+)\s+rows=(\d+)\s+errors=(\d+)", latest)
    if m:
        out.update(
            {
                "attempted": int(m.group(1)),
                "skipped": int(m.group(2)),
                "inserted_rows": int(m.group(3)),
                "errors": int(m.group(4)),
            }
        )
    return out


def heartbeat(note: str) -> None:
    run_cmd([HERMES, "kanban", "--board", BOARD, "heartbeat", "--note", note, TASK_ID], timeout=60)


def comment(body: str) -> None:
    run_cmd([HERMES, "kanban", "--board", BOARD, "comment", TASK_ID, body], timeout=60)


def main() -> int:
    now = int(time.time())
    state = load_state()
    pid = read_pid()
    alive = process_alive(pid)
    db = db_progress()
    log = log_progress()
    percent = db["pct"] / 100.0
    errors = int(log.get("errors", 0) or 0)
    warn_count = int(log.get("warn_count", 0) or 0)

    note = (
        f"Asian backfill {'running' if alive else 'not-running'}; "
        f"rows={db['rows']}/{EXPECTED_ROWS} ({percent:.2f}%); "
        f"matches={db['matches']}/{db['total_matches']}; errors={errors}; warnings={warn_count}"
    )
    heartbeat(note[:500])

    should_comment = False
    reason = ""
    last_comment_matches = int(state.get("last_comment_matches", 0) or 0)
    last_comment_ts = int(state.get("last_comment_ts", 0) or 0)
    last_errors = int(state.get("last_errors", 0) or 0)
    last_alive = bool(state.get("last_alive", True))
    already_done = bool(state.get("done_comment_sent", False))

    if errors > last_errors or warn_count > int(state.get("last_warn_count", 0) or 0):
        should_comment = True
        reason = "errors/warnings changed"
    elif not alive and last_alive:
        should_comment = True
        reason = "process stopped"
    elif db["rows"] >= EXPECTED_ROWS and not already_done:
        should_comment = True
        reason = "expected coverage reached"
        state["done_comment_sent"] = True
    elif db["matches"] - last_comment_matches >= COMMENT_MATCH_STEP:
        should_comment = True
        reason = f"advanced {db['matches'] - last_comment_matches} matches"
    elif db["matches"] > last_comment_matches and now - last_comment_ts >= COMMENT_MIN_SECONDS:
        should_comment = True
        reason = "periodic progress"

    if should_comment:
        latest = str(log.get("latest", ""))
        body = (
            f"Asian line backfill watchdog update ({reason}): "
            f"pid={pid or 'none'}, alive={int(alive)}, "
            f"asian_rows={db['rows']}/{EXPECTED_ROWS} ({percent:.2f}%), "
            f"covered_matches={db['matches']}/{db['total_matches']}, "
            f"nonnull_rows={db['nonnull_rows']}, errors={errors}, warnings={warn_count}. "
            f"Latest progress: {latest or 'n/a'}"
        )
        comment(body[:1800])
        state["last_comment_matches"] = db["matches"]
        state["last_comment_ts"] = now

    state.update(
        {
            "last_alive": alive,
            "last_rows": db["rows"],
            "last_matches": db["matches"],
            "last_errors": errors,
            "last_warn_count": warn_count,
            "last_run_ts": now,
            "pid": pid,
        }
    )
    save_state(state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
