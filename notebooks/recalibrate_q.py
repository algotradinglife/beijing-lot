"""Recalibrate q per (league, SP-bucket).

For each match, generate 3 candidate legs (sides 3/1/0, with their own SPs).
Bucket SP into bands. q = mean(hit) / mean(implied_p) where implied_p = 1/sp/0.65.
Save to data/raw/q_recalibrated.json keyed by f"{league}|{bucket}".
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "data" / "raw" / "beidan_full_3sp.csv"
OUT_PATH = ROOT / "data" / "raw" / "q_recalibrated.json"

BUCKETS = [
    (1.0, 1.5, "[1.0,1.5)"),
    (1.5, 2.0, "[1.5,2.0)"),
    (2.0, 3.0, "[2.0,3.0)"),
    (3.0, 5.0, "[3.0,5.0)"),
    (5.0, 8.0, "[5.0,8.0)"),
    (8.0, 15.0, "[8.0,15.0)"),
    (15.0, math.inf, "[15.0,inf)"),
]
MIN_N = 50


def bucket_of(sp: float) -> str | None:
    for lo, hi, name in BUCKETS:
        if lo <= sp < hi:
            return name
    return None


def main() -> None:
    # cell_stats[(league, bucket)] = [hit_sum, p_sum, n]
    cell = defaultdict(lambda: [0.0, 0.0, 0])
    overall = defaultdict(lambda: [0.0, 0.0, 0])  # by bucket only

    with CSV_PATH.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                rc = int(row["result_code"])
                sps = {3: float(row["sp_3"]), 1: float(row["sp_1"]), 0: float(row["sp_0"])}
            except (ValueError, KeyError):
                continue
            league = row["league"].strip()
            for side, sp in sps.items():
                if sp <= 1.0:
                    continue
                b = bucket_of(sp)
                if b is None:
                    continue
                hit = 1.0 if side == rc else 0.0
                p = 1.0 / sp / 0.65
                cell[(league, b)][0] += hit
                cell[(league, b)][1] += p
                cell[(league, b)][2] += 1
                overall[b][0] += hit
                overall[b][1] += p
                overall[b][2] += 1

    out: dict[str, dict] = {}
    overall_q: dict[str, float] = {}
    for b, (h, p, n) in overall.items():
        overall_q[b] = (h / n) / (p / n) if n > 0 and p > 0 else 1.0

    for (league, b), (h, p, n) in cell.items():
        key = f"{league}|{b}"
        if n >= MIN_N and p > 0:
            q = (h / n) / (p / n)
            out[key] = {"q": q, "n": n, "fallback": False}
        else:
            out[key] = {"q": overall_q.get(b, 1.0), "n": n, "fallback": True}

    # store overall fallback under special key
    out["__overall__"] = {b: {"q": q} for b, q in overall_q.items()}

    OUT_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"Wrote {OUT_PATH} with {len(out) - 1} (league, bucket) cells.")
    print("Overall bucket q:")
    for b, q in sorted(overall_q.items()):
        print(f"  {b:>14s}  q={q:.4f}  n={overall[b][2]}")
    # top 10 highest q cells with n>=50
    real = [(k, v["q"], v["n"]) for k, v in out.items() if k != "__overall__" and not v["fallback"]]
    real.sort(key=lambda x: -x[1])
    print("\nTop 15 (league|bucket) by q (n>=50):")
    for k, q, n in real[:15]:
        print(f"  {k:>40s}  q={q:.3f}  n={n}")


if __name__ == "__main__":
    main()
