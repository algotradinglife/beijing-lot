"""Track B P0+P1 — build the feature DB from beidan.xlsm and validate it.

P0: parse the collector xlsm -> data/beidan_features.db (table `matches`).
P1: validation report (row count / season span / result dist / non-null rates) +
    benchmark calibration of the consensus closing prob on handicap_line=0
    (the O5-comparable subset). If the benchmark isn't calibrated there, the
    'beat the closing line' question is ill-posed.

Run (smoke):  PYTHONPATH=".:src" .venv/bin/python scripts/build_track_b_features.py --limit 3000
Run (full) :  PYTHONPATH=".:src" .venv/bin/python scripts/build_track_b_features.py
"""
from __future__ import annotations

import argparse
import sqlite3
import sys

from src.track_b import etl
from src.track_b.benchmark import calibration_table, max_calibration_gap, brier

XLSM = "/mnt/c/Users/hhusl/Downloads/soccer lot/北单采集器/北单采集器/beidan.xlsm"
DB = "data/beidan_features.db"
EDGES = [0.0, 0.15, 0.3, 0.45, 0.6, 0.8, 1.0]


def build(limit):
    if limit:
        # smoke build: stream only `limit` parsed rows into the db
        con = sqlite3.connect(DB)
        con.execute("DROP TABLE IF EXISTS matches")
        con.execute(f"CREATE TABLE matches ({', '.join(c + ' ' + etl._coltype(c) for c in etl.COLUMNS)})")
        n = 0
        for rec in etl.iter_matches(XLSM):
            con.execute(f"INSERT INTO matches VALUES ({','.join('?' * len(etl.COLUMNS))})",
                        tuple(rec[c] for c in etl.COLUMNS))
            n += 1
            if n >= limit:
                break
        con.commit(); con.close()
        return n
    return etl.build_sqlite(XLSM, DB)


def validate():
    con = sqlite3.connect(DB)
    c = con.cursor()
    n = c.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    smin, smax = c.execute("SELECT MIN(season), MAX(season) FROM matches").fetchone()
    print(f"\n== 校验 ==\nrows={n}  season {smin}..{smax}")
    print("result_code 分布:", dict(c.execute(
        "SELECT result_code, COUNT(*) FROM matches GROUP BY result_code").fetchall()))
    print("非空率(关键列):")
    for col in ("p_close_3", "p_open_3", "crown_close_3", "pinn_close_3",
                "asian_p_home_close", "asian_line", "beidan_hcap", "rank_home"):
        nn = c.execute(f"SELECT COUNT({col}) FROM matches").fetchone()[0]
        print(f"  {col:22} {nn/n*100:5.1f}%")

    # P1 benchmark calibration on handicap_line=0 (straight ↔ 让球 result)
    rows = c.execute(
        "SELECT p_close_3, p_close_1, p_close_0, result_code FROM matches "
        "WHERE beidan_hcap=0 AND p_close_3 IS NOT NULL").fetchall()
    print(f"\n== P1 基准校准（beidan_hcap=0, n={len(rows)}）：consensus 收盘 p vs realized ==")
    for code, idx, label in [("3", 0, "home"), ("1", 1, "draw"), ("0", 2, "away")]:
        pairs = [(r[idx], r[3] == code) for r in rows]
        tab = calibration_table(pairs, EDGES)
        gap = max_calibration_gap(tab)
        print(f"  {label}: Brier={brier(pairs):.4f}  最大校准缺口(n≥30)={gap:.3f}"
              + ("  ✓校准" if gap == gap and gap < 0.05 else "  ⚠看下表"))
        for b in tab:
            if b["n"] >= 30:
                print(f"     p[{b['lo']:.2f},{b['hi']:.2f}) n={b['n']:5} "
                      f"meanP={b['mean_p']:.3f} realized={b['hit_rate']:.3f}")
    con.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="smoke-build only N rows")
    a = ap.parse_args()
    print(f"building {DB} from collector xlsm" + (f" (limit {a.limit})" if a.limit else " (FULL)"))
    n = build(a.limit)
    print(f"wrote {n} matches")
    validate()


if __name__ == "__main__":
    main()
