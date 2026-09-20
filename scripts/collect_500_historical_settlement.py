#!/usr/bin/env python3
"""Collect historical 500 BJDC settlement pages into the isolated 500 lane.

This lane is independent of Titan: rows are keyed by 500-native
(issue_code, issue_slot, local_500_fid) and matching to canonical Titan
fixtures happens later via the mapping library.  It runs in parallel with
the Titan historical collector without sharing its 120/min rate budget
(500.com is not in the Titan risk-ack allowed origins).

Dual-source settlement:
  * 500 page (trade.500.com/bjdc) provides the official score (H:A) and
    the SP value (unique `sp_value eng red` on settled rows).
  * Nowscore DanChang page (cp.nowscore.com, TypeID=5 = 单场让球胜平负)
    provides the authoritative winner: the unique filled `sp_N_1/2/3` cell
    (主胜/平/客胜) together with polygoal (让球数) and score.  This covers
    legacy 500 rows where all three options are rendered red (cannot
    determine the winner from 500 alone).
  * result_code mapping: 主胜 -> 3, 平 -> 1, 客胜 -> 0 (让球胜平负).

Nowscore issue numbers match 500 issue codes directly (verified).
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

TRADE_URL = "https://trade.500.com/bjdc/?expect={issue}"
NOWSCORE_URL = "https://cp.nowscore.com/buy/DanChang.aspx?TypeID=5&issueNum={issue}"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126 Safari/537.36"
PARSER_VERSION = "500_historical_settlement_v1"
RATE_PER_MINUTE = 30
ROW_RE = re.compile(r'<tr[^>]*class="[^"]*vs_lines[^"]*"[^>]*>.*?</tr>', re.S)
VALUE_ATTR_RE = re.compile(r"value=\"\{index:'(\d+)'")
FID_ATTR_RE = re.compile(r'fid="(-?\d+)"')
HANDICAP_RE = re.compile(r"rangqiuNum:'(-?\d+)'")
SCORE_RE = re.compile(r'title="析" class="red eng">(\d+):(\d+)</a>')
OPTION_RE = re.compile(r'value="(胜|平|负)"[^>]*>.*?(?:<span class="sp_value eng red">([\d.]+)</span>|--)', re.S)
NS_ROW_RE = re.compile(r'(?s)<tr id="row_\d+"[^>]*matchid="\d+"[^>]*>.*?</tr>')
NS_SCORE_RE = re.compile(r'style="font-weight:bold;color:Red;">(\d+)-(\d+)</td>')
NS_POLY_RE = re.compile(r'polygoal="(-?\d+)"')
NS_SP_RE = re.compile(r'id="sp_\d+_\d+"[^>]*>(.*?)</span>', re.S)


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch(url: str, timeout: float = 30) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def parse_nowscore_settlement(issue: str, payload: bytes) -> dict[int, tuple[int | None, int | None, str | None, float | None, str]]:
    """Parse Nowscore DanChang (TypeID=5 让球胜平负) page.

    Returns {slot: (home, away, result_code, winning_sp, state)}.
    The unique filled `sp_N_1/2/3` cell (主胜/平/客胜) is the settlement winner;
    status 完场/完赛 = settled, 推迟 = postponed, 取消 = cancelled.
    """
    text = payload.decode("utf-8", errors="replace")
    rows: dict[int, tuple[int | None, int | None, str | None, float | None, str]] = {}
    for match in NS_ROW_RE.finditer(text):
        tr = match.group(0)
        m = re.search(r'matchid="(\d+)"', tr)
        if not m:
            continue
        slot = int(m.group(1))
        seg = re.sub(r"\s+", " ", tr)
        stm = re.search(r'<td[^>]*title="截止时间：[^"]*"[^>]*>(.*?)</td>', seg)
        status = re.sub(r"<[^>]+>", "", stm.group(1)).strip() if stm else ""
        score = NS_SCORE_RE.search(seg)
        home = away = None
        if score is not None:
            home, away = int(score.group(1)), int(score.group(2))
        cells = re.findall(NS_SP_RE, tr)
        vals = [re.sub(r"<[^>]+>", "", c).strip() for c in cells]
        filled = [(i, v) for i, v in enumerate(vals) if v]
        result = None
        sp = None
        state = "no_result"
        if status in ("完场", "完赛"):
            if len(filled) == 1:
                idx, sp_raw = filled[0]
                try:
                    sp = float(sp_raw)
                except ValueError:
                    sp = None
                result = {0: "3", 1: "1", 2: "0"}[idx]
                state = "settled"
            elif score is not None:
                state = "no_result"
            else:
                state = "cancelled"
        elif "推迟" in status:
            state = "postponed"
        elif status in ("取消", "中断", "腰斩"):
            state = "cancelled"
        rows[slot] = (home, away, result, sp, state)
    return rows


def parse_settlement(issue: str, payload: bytes) -> list[tuple[int, int, int | None, int | None, str | None, float | None, str, int | None]]:
    """Parse one 500 issue page.

    Returns ``(slot, fid, home_score, away_score, result_code, winning_sp,
    settlement_state, handicap_line)`` where handicap_line is the 让球数 from
    the page (positive=home concedes, negative=away concedes).
    """
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
        # 让球数：rangqiuNum:'X'
        handicap_match = HANDICAP_RE.search(tr)
        handicap_line = int(handicap_match.group(1)) if handicap_match else None
        score = SCORE_RE.search(tr)
        home = away = None
        if score is not None:
            home, away = int(score.group(1)), int(score.group(2))

        # 延期警告：later.gif 图片（alt="本场比赛可能延期..."）
        postponed = "later.gif" in tr

        result_code = None
        winning_sp = None
        state = "cancelled"

        if postponed:
            state = "postponed"
        elif score is not None:
            # 结算 SP：恰好一个 sp_value eng red 且非 1.00
            red_spans = re.findall(r'sp_value eng red">([\d.]+)</span>', tr)
            if len(red_spans) == 1 and not (0.999 < float(red_spans[0]) < 1.001):
                for label in re.findall(r'<label class="label_n">(.*?)</label>', tr, flags=re.S):
                    option = re.search(r'value="(胜|平|负)"', label)
                    sp = re.search(r'sp_value eng red">([\d.]+)</span>', label)
                    if option is not None and sp is not None:
                        result_code = {"胜": "3", "平": "1", "负": "0"}[option.group(1)]
                        winning_sp = float(sp.group(1))
                        break
                state = "settled" if result_code is not None else "no_result"
            else:
                # 多个红（legacy 渲染）或单红 1.00 -> 无法判定
                state = "no_result"
        rows.append((slot, fid, home, away, result_code, winning_sp, state, handicap_line))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--issues", help="comma-separated issue codes (trial)")
    parser.add_argument("--limit", type=int, default=0, help="max issues to process (0 = all mapped issues)")
    parser.add_argument("--rate-per-minute", type=int, default=RATE_PER_MINUTE)
    parser.add_argument("--delay", type=float, default=0.0, help="extra sleep seconds between requests")
    args = parser.parse_args()
    if args.rate_per_minute < 1 or args.rate_per_minute > 120:
        parser.error("--rate-per-minute must be between 1 and 120")
    if args.limit < 0:
        parser.error("--limit must be >= 0")

    # 待抓期次：映射库中已映射的期次（排除已抓的）
    discovery = args.data_root / "control" / "external_id_discovery" / "discovery.sqlite"
    store = SettlementStore.open(args.data_root)
    try:
        already = store.raw_settlement_issues()
        if args.issues:
            issues = [x for x in args.issues.split(",") if x]
        else:
            import sqlite3
            con = sqlite3.connect(discovery)
            try:
                rows = con.execute("SELECT DISTINCT issue_code FROM issue_slot_nowscore_map ORDER BY issue_code").fetchall()
            finally:
                con.close()
            issues = [r[0] for r in rows]
        pending = [x for x in issues if x not in already]
        if args.limit:
            pending = pending[: args.limit]
        print({"pending": len(pending), "already_captured": len(already)}, flush=True)

        interval = 60.0 / args.rate_per_minute
        for i, issue in enumerate(pending, 1):
            try:
                payload_500 = fetch(TRADE_URL.format(issue=issue))
                payload_ns = fetch(NOWSCORE_URL.format(issue=issue))
                rows_500 = parse_settlement(issue, payload_500)
                ns_rows = parse_nowscore_settlement(issue, payload_ns)

                # 合并：Nowscore 优先定中奖/SP；500 提供 fid 和比分交叉验证。
                # 500 的 no_result（三选全红 legacy）用 Nowscore 补全。
                # ns 元组: (home, away, result_code, winning_sp, state)
                merged: list[tuple[int, int, int | None, int | None, str | None, float | None, str, int | None]] = []
                ns_by_slot = {slot: (h, a, rc, sp, st) for slot, (h, a, rc, sp, st) in ns_rows.items()}
                for slot, fid, h500, a500, rc500, sp500, st500, hc500 in rows_500:
                    ns = ns_by_slot.get(slot)
                    if ns is not None:
                        _, _, rc_ns, sp_ns, st_ns = ns
                        # Nowscore 结果仅在 500 无确定结果时用
                        if st_ns == "settled" and rc_ns is not None and rc500 is None:
                            merged.append((slot, fid, h500, a500, rc_ns, sp_ns, "settled", hc500))
                        elif st_ns in ("postponed", "cancelled"):
                            merged.append((slot, fid, h500, a500, None, None, st_ns, hc500))
                        else:
                            # Nowscore 无唯一中奖：回退 500 的判定
                            merged.append((slot, fid, h500, a500, rc500, sp500, st500, hc500))
                    else:
                        merged.append((slot, fid, h500, a500, rc500, sp500, st500, hc500))

                batch_id = f"settle:{now_utc()}:{issue}"
                store.record_raw_settlement(
                    batch_id=batch_id, issue_code=issue,
                    source_url=TRADE_URL.format(issue=issue),
                    payload=payload_500, trusted_received_at_utc=now_utc(),
                    parser_version=PARSER_VERSION, rows=merged,
                )
                n_settled = sum(1 for r in merged if r[4] is not None)
                print({"issue": issue, "rows": len(merged), "settled": n_settled}, flush=True)
            except Exception as exc:
                print({"issue": issue, "error": type(exc).__name__, "detail": str(exc)[:200]}, flush=True)
            time.sleep(max(0.0, interval - 0.2) + args.delay)
        print({"status": "DONE", "processed": len(pending)})
    finally:
        store.close()


if __name__ == "__main__":
    main()
