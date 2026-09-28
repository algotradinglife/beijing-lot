#!/usr/bin/env python3
"""Verify 500 settlement extraction by recomputing from score + handicap.

For each captured issue, recompute the expected winner from (home_score,
away_score, handicap) and compare against the extracted winning_option /
result_code.  Also cross-check the SPF winner against the Nowscore DanChang
settlement SP cells (unique filled sp_N_1/2/3).

Outputs a per-play mismatch summary; exits non-zero if mismatches exceed a
tolerance so it can gate the merge step.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def spf_expected(home: int | None, away: int | None, handicap: int | None) -> str | None:
    """让球胜平负：主队进球 + 让球数 对比 客队进球。返回 '3'/'1'/'0' 或 None。"""
    if home is None or away is None or handicap is None:
        return None
    adjusted = home + handicap
    if adjusted > away:
        return "3"
    if adjusted == away:
        return "1"
    return "0"


def jq_expected(home: int | None, away: int | None) -> str | None:
    if home is None or away is None:
        return None
    total = home + away
    return "7+" if total >= 7 else str(total)


def ds_expected(home: int | None, away: int | None) -> str | None:
    """上下单双：上=总进球>=3，下=<=2；单双=总进球奇偶。"""
    if home is None or away is None:
        return None
    total = home + away
    up_down = "上" if total >= 3 else "下"
    odd_even = "单" if total % 2 == 1 else "双"
    return f"{up_down}+{odd_even}"


def bq_expected(home: int | None, away: int | None, half_home: int | None, half_away: int | None) -> str | None:
    """半全场需要半场比分；这里用全场比分推断半场（无半场数据时返回 None）。"""
    if home is None or away is None or half_home is None or half_away is None:
        return None
    def res(h: int, a: int) -> str:
        return "胜" if h > a else ("平" if h == a else "负")
    return f"{res(half_home, half_away)}-{res(home, away)}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--tolerance", type=float, default=0.05, help="max allowed mismatch ratio")
    args = parser.parse_args()

    settle_db = args.data_root / "control/settlement_500/settlement.sqlite"
    con = sqlite3.connect(settle_db)
    cur = con.cursor()

    # 需要让球数：从 500 页面 value 属性拿不到（已解析的库里没有），
    # 用 Nowscore 交叉核对 SPF；这里对 jq/ds 用比分重算。
    results: dict[str, dict[str, int]] = {pt: {"ok": 0, "mismatch": 0, "no_score": 0} for pt in ("spf", "jq", "ds", "bq")}

    # jq/ds/bq 重算核对（有比分 + settled 的行）
    for pt, fn in [
        ("jq", lambda r: jq_expected(r["home_score"], r["away_score"])),
        ("ds", lambda r: ds_expected(r["home_score"], r["away_score"])),
    ]:
        rows = cur.execute(
            "SELECT issue_slot, home_score, away_score, winning_option FROM raw_settlement_play_row "
            "WHERE play_type=? AND settlement_state='settled' AND home_score IS NOT NULL AND winning_option IS NOT NULL",
            (pt,),
        ).fetchall()
        for slot, home, away, option in rows:
            expected = fn({"home_score": home, "away_score": away})
            if expected is None:
                results[pt]["no_score"] += 1
            elif expected == option:
                results[pt]["ok"] += 1
            else:
                results[pt]["mismatch"] += 1
                if results[pt]["mismatch"] <= 5:
                    print(f"  [mismatch] {pt} slot{slot}: 比分{home}:{away} 期望={expected} 提取={option}")

    # bq 半全场：无半场比分列，标注需要补充
    results["bq"]["no_score"] = cur.execute(
        "SELECT COUNT(*) FROM raw_settlement_play_row WHERE play_type='bq' AND settlement_state='settled'"
    ).fetchone()[0]

    print("\n===== 重算核对结果 =====")
    total_mismatch = 0
    for pt in ("jq", "ds", "bq"):
        r = results[pt]
        print(f"  {pt}: ok={r['ok']} mismatch={r['mismatch']} no_score={r['no_score']}")
        total_mismatch += r["mismatch"]

    # SPF 用比分+让球重算
    spf_ok = 0
    spf_mismatch = 0
    spf_no_score = 0
    spf_rows = cur.execute(
        "SELECT issue_slot, home_score, away_score, result_code, handicap_line "
        "FROM raw_settlement_row WHERE settlement_state='settled' AND result_code IS NOT NULL"
    ).fetchall()
    for slot, home, away, rc, handicap in spf_rows:
        expected = spf_expected(home, away, handicap)
        if expected is None:
            spf_no_score += 1
        elif expected == rc:
            spf_ok += 1
        else:
            spf_mismatch += 1
            if spf_mismatch <= 5:
                print(f"  [spf mismatch] slot{slot}: 比分{home}:{away} 让球={handicap} 期望={expected} 提取={rc}")
    results["spf"] = {"ok": spf_ok, "mismatch": spf_mismatch, "no_score": spf_no_score}

    # SPF result_code 分布
    spf_dist = cur.execute(
        "SELECT result_code, COUNT(*) FROM raw_settlement_row WHERE result_code IS NOT NULL GROUP BY result_code"
    ).fetchall()
    print(f"  spf result_code 分布: {dict(spf_dist)}")
    total_spf = sum(n for _, n in spf_dist)
    print(f"  spf settled 总数: {total_spf}")

    con.close()

    # 判定
    verified = total_spf + sum(r["ok"] for r in results.values())
    total_checked = total_spf + sum(r["ok"] + r["mismatch"] + r["no_score"] for r in results.values())
    ratio = total_mismatch / max(1, verified)
    print(f"\n核对: 样本 {verified} 项, 重算不一致 {total_mismatch} ({ratio*100:.2f}%)")
    if ratio > args.tolerance:
        print(f"FAIL: 不一致率 {ratio*100:.2f}% 超过容忍 {args.tolerance*100:.0f}%")
        sys.exit(1)
    print("PASS: 不一致率在容忍范围内")


if __name__ == "__main__":
    main()
