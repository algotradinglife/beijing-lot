#!/usr/bin/env python3
"""Analyze result-probability calibration by Beidan handicap for N3 work."""
from __future__ import annotations

import argparse
import csv
import math
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.walkforward_beidan_strategy_eval import default_db_path, md_table, write_csv


def fnum(value: object, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def hcp_bucket(hcp: float) -> str:
    if abs(hcp - round(hcp)) < 1e-9:
        return str(int(round(hcp)))
    return f"{hcp:g}"


def odds_bucket(sp: float) -> str:
    if sp < 2:
        return "sp_lt2"
    if sp < 3:
        return "sp_2_3"
    if sp < 5:
        return "sp_3_5"
    if sp < 8:
        return "sp_5_8"
    return "sp_ge8"


def p_bucket(p_hat: float) -> str:
    if p_hat < 0.25:
        return "p_lt25"
    if p_hat < 0.35:
        return "p_25_35"
    if p_hat < 0.45:
        return "p_35_45"
    if p_hat < 0.55:
        return "p_45_55"
    return "p_ge55"


def q_bucket(q: float) -> str:
    if q < 0.8:
        return "q_lt0p8"
    if q < 1.0:
        return "q_0p8_1"
    if q < 1.154:
        return "q_1_1p154"
    if q < 1.4:
        return "q_1p154_1p4"
    return "q_ge1p4"


def load_settlement(db_path: Path, min_year: int) -> dict[tuple[str, int, str], dict[str, float]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    sql = """
        SELECT issue, match_id, outcome_code, hit, winning_sp
        FROM outcome_features
        WHERE has_winning_sp = 1
          AND season_year >= ?
          AND outcome_code IN ('3', '1', '0')
    """
    out = {}
    for row in conn.execute(sql, [min_year]):
        out[(str(row["issue"]), int(row["match_id"]), str(row["outcome_code"]))] = {
            "hit": fnum(row["hit"]),
            "winning_sp": fnum(row["winning_sp"]),
        }
    conn.close()
    return out


def add_row(agg: dict[tuple[str, ...], dict[str, float]], key: tuple[str, ...], row: dict[str, float]) -> None:
    vals = agg.setdefault(
        key,
        {
            "n": 0.0,
            "hits": 0.0,
            "pred_p_sum": 0.0,
            "estimated_sp_sum": 0.0,
            "q_sum": 0.0,
            "sp_on_hits_sum": 0.0,
        },
    )
    vals["n"] += 1
    vals["hits"] += row["hit"]
    vals["pred_p_sum"] += row["p_hat"]
    vals["estimated_sp_sum"] += row["estimated_sp"]
    vals["q_sum"] += row["q"]
    if row["hit"] > 0:
        vals["sp_on_hits_sum"] += row["winning_sp"]


def summarize_agg(agg: dict[tuple[str, ...], dict[str, float]], min_n: int) -> list[dict[str, object]]:
    out = []
    for key, vals in agg.items():
        n = vals["n"]
        if n < min_n:
            continue
        hits = vals["hits"]
        pred_p = vals["pred_p_sum"] / n
        hit_rate = hits / n
        avg_sp_on_hits = vals["sp_on_hits_sum"] / hits if hits else 0.0
        realized_leg_ev = 0.65 * hit_rate * avg_sp_on_hits - 1.0 if hits else -1.0
        out.append(
            {
                "group_type": key[0],
                "outcome": key[1] if len(key) > 1 else "",
                "hcp": key[2] if len(key) > 2 else "",
                "bucket": "/".join(key[3:]) if len(key) > 3 else "",
                "n": int(n),
                "pred_p": pred_p,
                "hit_rate": hit_rate,
                "calibration_gap": hit_rate - pred_p,
                "calibration_ratio": hit_rate / pred_p if pred_p > 0 else math.nan,
                "avg_estimated_sp": vals["estimated_sp_sum"] / n,
                "avg_q": vals["q_sum"] / n,
                "avg_realized_sp_on_hits": avg_sp_on_hits,
                "realized_leg_ev_proxy": realized_leg_ev,
            }
        )
    out.sort(
        key=lambda row: (
            str(row["group_type"]),
            str(row["outcome"]),
            str(row["hcp"]),
            -abs(fnum(row["calibration_gap"])),
            -int(row["n"]),
        )
    )
    return out


def compact(rows: list[dict[str, object]], *, group_type: str, limit: int) -> list[dict[str, object]]:
    keep = [
        "group_type",
        "outcome",
        "hcp",
        "bucket",
        "n",
        "pred_p",
        "hit_rate",
        "calibration_gap",
        "calibration_ratio",
        "avg_estimated_sp",
        "avg_realized_sp_on_hits",
        "realized_leg_ev_proxy",
    ]
    filtered = [row for row in rows if row["group_type"] == group_type]
    filtered.sort(key=lambda row: (-abs(fnum(row["calibration_gap"])), -int(row["n"])))
    return [{key: row.get(key, "") for key in keep} for row in filtered[:limit]]


def run(args: argparse.Namespace) -> None:
    settlement = load_settlement(args.db_path, args.min_year)
    agg: dict[tuple[str, ...], dict[str, float]] = {}
    loaded = 0
    skipped = 0
    for row in read_csv(args.outcomes_path):
        if row.get("strategy") != args.strategy:
            continue
        issue = str(row["issue"])
        match_id = int(float(row["match_id"]))
        outcome = str(row["outcome"])
        st = settlement.get((issue, match_id, outcome))
        if st is None:
            skipped += 1
            continue
        hcp = fnum(row["hcp"])
        p_hat = fnum(row["p_hat"], math.nan)
        estimated_sp = fnum(row["estimated_sp"], math.nan)
        q = fnum(row["q"], math.nan)
        if not all(math.isfinite(v) for v in [p_hat, estimated_sp, q]):
            skipped += 1
            continue
        loaded += 1
        vals = {
            "hit": st["hit"],
            "winning_sp": st["winning_sp"],
            "p_hat": p_hat,
            "estimated_sp": estimated_sp,
            "q": q,
        }
        hb = hcp_bucket(hcp)
        add_row(agg, ("outcome_hcp", outcome, hb), vals)
        add_row(agg, ("outcome_hcp_sp", outcome, hb, odds_bucket(estimated_sp)), vals)
        add_row(agg, ("outcome_hcp_p", outcome, hb, p_bucket(p_hat)), vals)
        add_row(agg, ("outcome_hcp_q", outcome, hb, q_bucket(q)), vals)

    rows = summarize_agg(agg, args.min_n)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "n3_handicap_result_calibration.csv", rows)

    report = [
        "# N3 result calibration by Beidan handicap",
        "",
        f"- Source outcomes: `{args.outcomes_path}`",
        f"- Strategy: `{args.strategy}`",
        f"- Loaded outcome rows: `{loaded}`; skipped: `{skipped}`.",
        "- This analyzes all 3/1/0 outcome candidates, not only the N3-selected legs.",
        "- `realized_leg_ev_proxy = 0.65 * hit_rate * avg_realized_sp_on_hits - 1`.",
        "",
        "## Biggest Outcome + Handicap Calibration Gaps",
        "",
        md_table(compact(rows, group_type="outcome_hcp", limit=40)),
        "",
        "## With SP Buckets",
        "",
        md_table(compact(rows, group_type="outcome_hcp_sp", limit=60)),
        "",
        "## With P Buckets",
        "",
        md_table(compact(rows, group_type="outcome_hcp_p", limit=60)),
        "",
        "## With Q Buckets",
        "",
        md_table(compact(rows, group_type="outcome_hcp_q", limit=60)),
        "",
    ]
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.report_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--outcomes-path",
        type=Path,
        default=Path("results/n7_ev_framework_selector_2014_1h_minodds4_optional/ev_framework_outcomes.csv"),
    )
    parser.add_argument("--strategy", default="ev_m0p95_p0p8_full_opt")
    parser.add_argument("--db-path", type=Path, default=default_db_path())
    parser.add_argument("--min-year", type=int, default=2014)
    parser.add_argument("--min-n", type=int, default=120)
    parser.add_argument("--output-dir", type=Path, default=Path("results/n3_handicap_result_calibration_20260628"))
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("docs/research/n3_handicap_result_calibration_2026-06-28.md"),
    )
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
