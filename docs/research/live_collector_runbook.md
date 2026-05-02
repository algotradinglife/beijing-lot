# 北单 Live Collector — Runbook

**Status:** v0.1 — running and verified end-to-end against live 500.com + cp.zgzcw.com.
**Owner:** quant-data
**Critical-path:** YES. Every week without it running = a permanently lost week of pre-kickoff 3-SP + 销量比 data.

---

## 1. What it does

Polls two live pages every 5–15 minutes:

| Source | URL | Provides |
|---|---|---|
| 500.com `bjdc` | `https://trade.500.com/bjdc/?expect=<ISSUE>` | meta (kickoff, league, teams, handicap), avg European odds, 3-SP per W/D/L, **`tzbl` (vol-pct) spans** — empty post-settle |
| cp.zgzcw.com `bdplayvsforJsp` | `https://cp.zgzcw.com/lottery/bdplayvsforJsp.action?lotteryId=200` | `<input class="spArr" value="W D L">` — pre-kickoff has all-positive 3-SP, post-settle has only the paid leg with a `-` sign |

After each poll the two row-sets are merged on `match_idx` and one snapshot row per match is appended to SQLite.

In addition, every 4th poll runs the kaijiang settlement fetch (`zx.500.com/zqdc/kaijiang.php?playid=1&expect=<ISSUE>`) to backfill final score, result code, and winning-side SP for any issue with no `settlements` row yet.

---

## 2. How to run

```bash
# one-shot (manual / CI smoke):
PYTHONPATH=src python -m live_collector --once

# foreground long-running (recommended via tmux/systemd):
PYTHONPATH=src python -m live_collector \
    --interval-min 300 --interval-max 900     # 5–15 min jitter

# bounded run (e.g. 5-minute smoke):
PYTHONPATH=src python -m live_collector --duration 300 --interval-min 120 --interval-max 180

# alternative entry point:
PYTHONPATH=src python src/live_collector/main.py
```

CLI flags:

- `--db PATH` (default `data/beidan_live.db`)
- `--log PATH` (default `data/logs/live_collector.log`, rotates at 10 MB × 5)
- `--once` — single poll then exit
- `--duration N` — exit after N seconds
- `--no-settle` — skip kaijiang fetch
- `-v` — debug logging

The process catches **SIGINT / SIGTERM** and shuts down cleanly after the in-flight poll.

---

## 3. Production deployment

Recommended: a `tmux` session or a `launchd` (macOS) / `systemd` (Linux) unit with **Restart=on-failure**.

Sample systemd unit:

```ini
[Unit]
Description=Beidan Live Collector
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/beijing-lot
Environment=PYTHONPATH=/opt/beijing-lot/src
ExecStart=/usr/bin/python3 -m live_collector --interval-min 300 --interval-max 900
Restart=on-failure
RestartSec=30
KillSignal=SIGTERM
TimeoutStopSec=60

[Install]
WantedBy=multi-user.target
```

---

## 4. Monitoring

```bash
# tail logs
tail -f data/logs/live_collector.log

# check health (snapshots in last hour):
sqlite3 data/beidan_live.db \
  "SELECT COUNT(*) FROM snapshots WHERE snapshot_ts > datetime('now','-1 hour');"

# per-poll counts:
sqlite3 data/beidan_live.db \
  "SELECT snapshot_ts, COUNT(*) FROM snapshots GROUP BY snapshot_ts ORDER BY snapshot_ts DESC LIMIT 10;"

# matches with full pre-kickoff 3-SP captured:
sqlite3 data/beidan_live.db \
  "SELECT COUNT(DISTINCT match_id) FROM snapshots
   WHERE sp_3 IS NOT NULL AND sp_1 IS NOT NULL AND sp_0 IS NOT NULL;"

# matches missing settlement after kickoff:
sqlite3 data/beidan_live.db \
  "SELECT m.match_id, m.kickoff_ts FROM matches m
   LEFT JOIN settlements s ON s.match_id=m.match_id
   WHERE s.match_id IS NULL AND m.kickoff_ts < datetime('now','-6 hours')
   ORDER BY m.kickoff_ts DESC LIMIT 20;"
```

---

## 5. Sample log output (real, 2026-05-02 smoke run)

```
2026-05-02 08:57:41 INFO live_collector.scheduler | poll start issue=26051 ts=2026-05-02T00:57:41Z
2026-05-02 08:57:42 INFO live_collector.scheduler |   500.com bjdc: 382 rows
2026-05-02 08:57:44 INFO live_collector.scheduler |   zgzcw bdplay: 382 rows
2026-05-02 08:57:44 INFO live_collector.scheduler |   merged: 382 unique matches
2026-05-02 08:57:44 INFO live_collector.scheduler | poll done: inserted 382 snapshot rows
2026-05-02 08:57:45 INFO live_collector.scheduler | settle issue=26051 wrote 14 settlement rows
2026-05-02 08:57:45 INFO live_collector | sleeping 159s
```

---

## 6. Smoke-test findings (2026-05-02)

- **No anti-bot triggered** at ~1 req/s with rotating UA. Both sites return clean HTML.
- 500.com bjdc HTML is **gb18030-decodable** (declared gb2312); cp.zgzcw.com is UTF-8.
- A single bjdc fetch returns **382 matches** spanning multiple upcoming days/issues (the dropdown has all near-term expects). The `expect=26051` URL parameter does not strictly partition the response — all *near-term selectable* matches are listed with continuous match_idx 1..N.
- **Issue 26051** (the most recently closed issue at fetch time) had 14 settled rows in kaijiang — these were correctly written to `settlements` with full FT score, result code (`3/1/0`), winning SP, and avg European odds.
- **3-SP vector**: populated for upcoming matches (e.g. match 15: SP 2.70 / 3.09 / 3.25); blanked-with-only-winner for already-settled matches (match 1: SP 1.76 / null / null).

### Known gap

`tzbl` (销量比 / vol-pct) spans on the bjdc page were `--` for **every match** during the smoke run, including upcoming ones. The research doc reports tzbl is populated pre-kickoff, but at fetch time (mid-afternoon Beijing time) the data display page returned blanks. Hypotheses:

1. tzbl on the data page (`trade.500.com/bjdc/`) is updated only inside a narrow window — possibly only after sales open and before a few hours pre-kickoff. Need to poll across a full day to confirm.
2. tzbl might be exposed only on the actual betting page (`trade.500.com/bjdc/betting/...`) which requires login.
3. The research note's `<span class="tzbl">` was discovered on a settled-page mock-up and may have been historically populated but no longer is. The cp.zgzcw bet page does **not** expose tzbl at all.

**Action:** keep collector running across a full day, then sample `vol_pct_3` distribution. If still always-null, escalate — locate an alternative endpoint (mobile page? API endpoint behind login?) before strategy Phase 4.

---

## 7. Schema cheat-sheet (`data/beidan_live.db`)

```text
matches(match_id PK, issue, match_idx, league, kickoff_ts, home, away, handicap_line, status)
snapshots(id PK, match_id FK, snapshot_ts, sp_3, sp_1, sp_0, vol_pct_3, vol_pct_1, vol_pct_0,
          pool_total, eu_h, eu_d, eu_a, source, UNIQUE(match_id, snapshot_ts, source))
settlements(match_id PK, issue, match_idx, fthg, ftag, result_code, winning_sp,
            avg_eu_h, avg_eu_d, avg_eu_a, settled_ts)
```

Natural keys:

- `matches`: `(issue, match_idx)` — UNIQUE.
- `snapshots`: `(match_id, snapshot_ts, source)` — UNIQUE (idempotent re-runs).
- `settlements`: `match_id` — PK with INSERT OR REPLACE semantics (idempotent re-fetch).

---

## 8. Recovery

- **Process killed mid-poll:** safe. No partial-row writes; each `insert_snapshot` is its own tx.
- **DB corruption:** WAL mode is on. Run `sqlite3 data/beidan_live.db "PRAGMA integrity_check;"`. If broken, archive the file and restart — the collector will repopulate on next poll (you lose only the historical snapshots, which are append-only forward-going anyway).
- **500.com or zgzcw blocked:** the merge is tolerant — if either source fails, the other still produces snapshots. If both fail, `poll_once` returns 0 and logs the HTTP errors; the loop continues.
- **Cloudflare challenge / rate-limit:** the scraper retries with exponential backoff on 429/5xx. If it persists, lower `min_interval` won't help — slow down and consider rotating IP.

---

## 9. Tests

```bash
cd /path/to/beijing-lot
python -m pytest tests/live_collector/ -v
```

Should print 18 passes. The fixture HTMLs in `tests/fixtures/live_collector/` are real captures from 2026-05-02 — refresh them when the upstream layout changes.

---

## 10. Open issues / TODO

- [ ] Resolve the **tzbl always-null** mystery. Sample across a full day of polls; if still null, find alternative source (cp.zgzcw doesn't have it either).
- [ ] Per-row issue assignment: currently every row in a poll is tagged with the URL's `expect` value. Multi-day mode isn't strictly correct — match #200 in a poll likely belongs to expect=26053, not 26051. Workaround: re-bucket downstream by `kickoff_ts`. Long-term: fetch each upcoming issue separately.
- [ ] Pool total (`pool_total`) field exists in schema but neither source page exposes it cleanly. Investigate `投注金额` endpoint.
- [ ] Add a one-shot integrity-check job: for each `matches` row past kickoff + 6h, ensure a `settlements` row exists; alert if missing for >24h.
