#!/usr/bin/env python3
"""Collect 500 BJDC non-SPF play settlements (总进球/上下单双/半全场/比分).

Each play page shares the same row pattern: `<tr class="vs_lines ...">` with
`fid`, `value="{index:...}"`, a score anchor (`title="析"` H:A), and option
labels (`label_br` / `label`) where the winning option has a non-empty
`sp_value`.  `play_type` is one of:

  * jq — 总进球 (project_fq_jq.php)     options 0/1/.../7+
  * ds — 上下单双 (project_fq_ds.php)   options 上+单/上+双/下+单/下+双
  * bq — 半全场 (project_fq_bq.php)     options 胜-胜/胜-平/...
  * bf — 比分 (project_fq_bf.php)       score-ratio options

Storage: `raw_settlement_play_row` keyed by (issue, slot, play_type); relies
on an existing `raw_settlement_capture` batch from the SPF collector (same
batch_id links the play rows to the issue receipt).
"""

from __future__ import annotations

import argparse
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.titan_clean.settlement import SettlementStore  # noqa: E402

PLAY_URLS = {
    "jq": "https://trade.500.com/bjdc/project_fq_jq.php?expect={issue}",
    "ds": "https://trade.500.com/bjdc/project_fq_ds.php?expect={issue}",
    "bq": "https://trade.500.com/bjdc/project_fq_bq.php?expect={issue}",
    "bf": "https://trade.500.com/bjdc/project_fq_bf.php?expect={issue}",
}
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
PARSER_VERSION = "500_historical_play_v1"
RATE_PER_MINUTE = 30
ROW_RE = re.compile(r'<tr[^>]*class="[^"]*vs_lines[^"]*"[^>]*>.*?</tr>', re.S)
VALUE_ATTR_RE = re.compile(r"value=\"\{index:'(\d+)'")
FID_ATTR_RE = re.compile(r'fid="(-?\d+)"')
SCORE_RE = re.compile(r'title="析" class="red eng">(\d+):(\d+)</a>')
HANDICAP_RE = re.compile(r"rangqiuNum:'(-?\d+)'")
# 通用选项：label 或 label_br，value + sp_value（有值=中奖）
OPTION_LABEL_RE = re.compile(r'<label class="(?:label_br|label_n|label)">(.*?)</label>', re.S)
OPTION_VALUE_RE = re.compile(r'value="([^"]*)"')
OPTION_SP_RE = re.compile(r'sp_value eng[^"]*"[^>]*>([\d.]*)</span>')


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch(url: str, timeout: float = 30) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def parse_play(issue: str, play_type: str, payload: bytes) -> list[tuple[int, int, int | None, int | None, str | None, float | None, str, int | None]]:
    """Parse one play page into (slot, fid, home, away, winning_option, winning_sp, state, handicap_line)."""
    text = payload.decode("gb18030", errors="replace")
    rows: list[tuple[int, int, int | None, int | None, str | None, float | None, str, int | None]] = []
    for match in ROW_RE.finditer(text):
        tr = match.group(0)
        slot_match = VALUE_ATTR_RE.search(tr)
        fid_match = FID_ATTR_RE.search(tr)
        if slot_match is None or fid_match is None:
            continue
        slot = int(slot_match.group(1))
        fid = int(fid_match.group(1))
        if fid <= 0:
            continue
        handicap_match = HANDICAP_RE.search(tr)
        handicap_line = int(handicap_match.group(1)) if handicap_match else None
        score = SCORE_RE.search(tr)
        home = away = None
        if score is not None:
            home, away = int(score.group(1)), int(score.group(2))
        postponed = "later.gif" in tr

        # 中奖选项 = 唯一有 sp_value 值的 label（jq/ds/bq）
        # bf 比分玩法：无 label 列表，开奖 SP 直接对应比分（<span class="eng red">）
        winning_option = None
        winning_sp = None
        state = "cancelled"
        if postponed:
            state = "postponed"
        elif play_type == "bf":
            bf_sp = re.search(r'<!-- 开奖SP -->\s*<span class="eng red">([\d.]+)</span>', tr)
            if score is not None and bf_sp is not None:
                winning_option = f"{home}:{away}"
                winning_sp = float(bf_sp.group(1))
                state = "settled"
            elif score is not None:
                state = "no_result"
        elif score is not None or play_type in ("ds", "jq"):
            filled: list[tuple[str, float]] = []
            for label in OPTION_LABEL_RE.findall(tr):
                value_m = OPTION_VALUE_RE.search(label)
                sp_m = OPTION_SP_RE.search(label)
                if value_m is not None and sp_m is not None and sp_m.group(1):
                    filled.append((value_m.group(1), float(sp_m.group(1))))
            if len(filled) == 1:
                winning_option, winning_sp = filled[0]
                state = "settled"
            elif score is not None or play_type == "ds":
                state = "no_result"
        rows.append((slot, fid, home, away, winning_option, winning_sp, state, handicap_line))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--play", choices=["jq", "ds", "bq", "bf"], required=True)
    parser.add_argument("--issues", help="comma-separated issue codes (trial)")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--rate-per-minute", type=int, default=RATE_PER_MINUTE)
    args = parser.parse_args()
    if args.rate_per_minute < 1 or args.rate_per_minute > 120:
        parser.error("--rate-per-minute must be between 1 and 120")

    discovery = args.data_root / "control" / "external_id_discovery" / "discovery.sqlite"
    store = SettlementStore.open(args.data_root)
    try:
        already = store.raw_play_issues(args.play)
        if args.issues:
            issues = [x for x in args.issues.split(",") if x]
        else:
            import sqlite3
            con = sqlite3.connect(discovery)
            try:
                issues = [r[0] for r in con.execute("SELECT DISTINCT issue_code FROM issue_slot_nowscore_map ORDER BY issue_code")]
            finally:
                con.close()
        pending = [x for x in issues if x not in already]
        if args.limit:
            pending = pending[: args.limit]
        print({"play": args.play, "pending": len(pending), "already": len(already)}, flush=True)

        url_template = PLAY_URLS[args.play]
        interval = 60.0 / args.rate_per_minute
        for i, issue in enumerate(pending, 1):
            try:
                payload = fetch(url_template.format(issue=issue))
                rows = parse_play(issue, args.play, payload)
                # 复用该期已有的 SPF capture batch；若无（SPF 未抓到该期），
                # 创建一个独立的 play batch（play 数据不依赖 SPF）。
                batch = store.connection.execute(
                    "SELECT batch_id FROM raw_settlement_capture WHERE issue_code=? ORDER BY trusted_received_at_utc DESC LIMIT 1",
                    (issue,),
                ).fetchone()
                if batch is None:
                    play_batch_id = f"settle-play:{now_utc()}:{issue}"
                    store.record_raw_settlement(
                        batch_id=play_batch_id, issue_code=issue,
                        source_url=url_template.format(issue=issue),
                        payload=payload, trusted_received_at_utc=now_utc(),
                        parser_version=PARSER_VERSION, rows=[],
                    )
                    batch = (play_batch_id,)
                store.record_raw_play_settlement(
                    batch_id=batch[0], issue_code=issue, play_type=args.play, rows=rows,
                )
                n_settled = sum(1 for r in rows if r[5] is not None)
                print({"issue": issue, "rows": len(rows), "settled": n_settled}, flush=True)
            except Exception as exc:
                print({"issue": issue, "error": type(exc).__name__, "detail": str(exc)[:200]}, flush=True)
            time.sleep(max(0.0, interval - 0.2))
        print({"status": "DONE", "processed": len(pending)})
    finally:
        store.close()


if __name__ == "__main__":
    main()
