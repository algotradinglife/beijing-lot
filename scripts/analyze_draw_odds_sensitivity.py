#!/usr/bin/env python3
"""Analyze whether draw odds are more sensitive to odds movement.

This is a research diagnostic, not a selector. It uses outcome_features single
outcomes (3/1/0) and compares movement windows:

* 10h -> 1h: observable before a 1h decision.
* 1h -> final: closing drift, not observable at 1h.
* 10h -> final: total pre-close drift.

Caveat: euro_* odds are European 1X2 proxy odds. For non-zero Beidan handicap,
the Beidan "draw" means handicap draw, so this first pass is a proxy analysis.
"""
from __future__ import annotations

import argparse
import csv
import math
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.walkforward_beidan_strategy_eval import default_db_path, md_table, write_csv


OUTCOMES = ("3", "1", "0")
ACTION_LABEL = {"3": "home_win", "1": "draw", "0": "away_win"}
WINDOWS = {
    "10h_to_1h": ("euro_10h_odds", "euro_10h_p", "euro_1h_odds", "euro_1h_p"),
    "1h_to_final": ("euro_1h_odds", "euro_1h_p", "euro_final_odds", "euro_final_p"),
    "10h_to_final": ("euro_10h_odds", "euro_10h_p", "euro_final_odds", "euro_final_p"),
}


def as_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return out


def quantile(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    vals = sorted(values)
    pos = (len(vals) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return vals[lo]
    return vals[lo] * (hi - pos) + vals[hi] * (pos - lo)


def odds_bucket(odds: float) -> str:
    if odds < 2.0:
        return "<2"
    if odds < 3.0:
        return "2-3"
    if odds < 4.0:
        return "3-4"
    if odds < 6.0:
        return "4-6"
    if odds < 8.0:
        return "6-8"
    return ">=8"


def move_bucket(move_log: float) -> str:
    if move_log <= -math.log(1.15):
        return "odds_down_ge15"
    if move_log <= -math.log(1.05):
        return "odds_down_5_15"
    if move_log < math.log(1.05):
        return "flat_pm5"
    if move_log < math.log(1.15):
        return "odds_up_5_15"
    return "odds_up_ge15"


def segment_for_year(year: int) -> list[str]:
    segments = ["all"]
    if 2023 <= year <= 2025:
        segments.append("recent_2023_2025")
    return segments


def summarize_rows(rows: list[dict[str, float | str]]) -> dict[str, object]:
    n = len(rows)
    if n == 0:
        return {}
    hit_rows = [row for row in rows if int(row["hit"]) == 1]
    moves = [float(row["move_log"]) for row in rows]
    abs_moves = [abs(value) for value in moves]
    base_ps = [float(row["base_p"]) for row in rows if math.isfinite(float(row["base_p"])) and float(row["base_p"]) > 0]
    current_ps = [
        float(row["current_p"])
        for row in rows
        if math.isfinite(float(row["current_p"])) and float(row["current_p"]) > 0
    ]
    hit_rate = len(hit_rows) / n
    avg_base_p = mean(base_ps) if base_ps else float("nan")
    avg_current_p = mean(current_ps) if current_ps else float("nan")
    winning_sps = [float(row["winning_sp"]) for row in hit_rows if float(row["winning_sp"]) > 0]
    realized_multipliers = [
        float(row["winning_sp"]) / float(row["current_odds"])
        for row in hit_rows
        if float(row["winning_sp"]) > 0 and float(row["current_odds"]) > 1
    ]
    avg_winning_sp = mean(winning_sps) if winning_sps else float("nan")
    avg_realized_multiplier = mean(realized_multipliers) if realized_multipliers else float("nan")
    ev_after_65 = 0.65 * hit_rate * avg_winning_sp - 1.0 if math.isfinite(avg_winning_sp) else float("nan")
    q_vs_base = hit_rate / avg_base_p if avg_base_p and math.isfinite(avg_base_p) else float("nan")
    q_vs_current = hit_rate / avg_current_p if avg_current_p and math.isfinite(avg_current_p) else float("nan")
    return {
        "n": n,
        "hit_rate": hit_rate,
        "avg_base_p": avg_base_p,
        "avg_current_p": avg_current_p,
        "q_vs_base_p": q_vs_base,
        "q_vs_current_p": q_vs_current,
        "avg_winning_sp_on_hits": avg_winning_sp,
        "avg_realized_sp_multiplier_on_hits": avg_realized_multiplier,
        "ev_after_65": ev_after_65,
        "mean_move_log": mean(moves),
        "mean_abs_move_log": mean(abs_moves),
        "median_abs_move_log": quantile(abs_moves, 0.50),
        "p90_abs_move_log": quantile(abs_moves, 0.90),
        "p95_abs_move_log": quantile(abs_moves, 0.95),
        "share_abs_gt_5pct": sum(1 for value in abs_moves if value > math.log(1.05)) / n,
        "share_abs_gt_10pct": sum(1 for value in abs_moves if value > math.log(1.10)) / n,
        "share_abs_gt_20pct": sum(1 for value in abs_moves if value > math.log(1.20)) / n,
        "share_odds_up_gt_5pct": sum(1 for value in moves if value > math.log(1.05)) / n,
        "share_odds_down_gt_5pct": sum(1 for value in moves if value < -math.log(1.05)) / n,
    }


def fmt_pct(value: object) -> str:
    try:
        val = float(value)
    except (TypeError, ValueError):
        return ""
    if not math.isfinite(val):
        return ""
    return f"{val:.2%}"


def fmt_num(value: object) -> str:
    try:
        val = float(value)
    except (TypeError, ValueError):
        return ""
    if not math.isfinite(val):
        return ""
    return f"{val:.4f}"


def load_rows(db: Path, min_year: int) -> list[sqlite3.Row]:
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    rows = list(
        conn.execute(
            """
            SELECT
                match_id,
                issue,
                season_year,
                league,
                handicap_line_norm,
                outcome_code,
                hit,
                winning_sp,
                euro_10h_odds,
                euro_10h_p,
                euro_1h_odds,
                euro_1h_p,
                euro_final_odds,
                euro_final_p
            FROM outcome_features
            WHERE season_year >= ?
              AND has_winning_sp = 1
              AND has_trusted_settlement = 1
              AND outcome_code IN ('3', '1', '0')
            """,
            (min_year,),
        )
    )
    conn.close()
    return rows


def expand_analysis_rows(rows: list[sqlite3.Row]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for row in rows:
        action = str(row["outcome_code"])
        year = int(row["season_year"])
        for window, (base_odds_col, base_p_col, current_odds_col, current_p_col) in WINDOWS.items():
            base_odds = as_float(row[base_odds_col])
            current_odds = as_float(row[current_odds_col])
            if base_odds is None or current_odds is None or base_odds <= 1.0 or current_odds <= 1.0:
                continue
            base_p = as_float(row[base_p_col])
            current_p = as_float(row[current_p_col])
            if base_p is None or base_p <= 0:
                base_p = 1.0 / base_odds
            if current_p is None or current_p <= 0:
                current_p = 1.0 / current_odds
            move = math.log(current_odds / base_odds)
            for segment in segment_for_year(year):
                out.append(
                    {
                        "segment": segment,
                        "window": window,
                        "year": year,
                        "match_id": int(row["match_id"]),
                        "issue": str(row["issue"]),
                        "league": str(row["league"] or ""),
                        "hcp": float(row["handicap_line_norm"])
                        if row["handicap_line_norm"] is not None
                        else float("nan"),
                        "action_code": action,
                        "action_label": ACTION_LABEL[action],
                        "hit": int(row["hit"]),
                        "winning_sp": float(row["winning_sp"]),
                        "base_odds": base_odds,
                        "current_odds": current_odds,
                        "base_p": base_p,
                        "current_p": current_p,
                        "base_odds_bucket": odds_bucket(base_odds),
                        "current_odds_bucket": odds_bucket(current_odds),
                        "move_log": move,
                        "move_bucket": move_bucket(move),
                    }
                )
    return out


def group_summary(analysis_rows: list[dict[str, object]], keys: list[str]) -> list[dict[str, object]]:
    grouped: dict[tuple[object, ...], list[dict[str, object]]] = defaultdict(list)
    for row in analysis_rows:
        grouped[tuple(row[key] for key in keys)].append(row)
    out: list[dict[str, object]] = []
    for key, rows in sorted(grouped.items()):
        summary = summarize_rows(rows)  # type: ignore[arg-type]
        if not summary:
            continue
        out.append({keys[i]: key[i] for i in range(len(keys))} | summary)
    return out


def contrast_rows(action_summary: list[dict[str, object]]) -> list[dict[str, object]]:
    by_key: dict[tuple[str, str], dict[str, dict[str, object]]] = defaultdict(dict)
    for row in action_summary:
        by_key[(str(row["segment"]), str(row["window"]))][str(row["action_code"])] = row
    out: list[dict[str, object]] = []
    for (segment, window), by_action in sorted(by_key.items()):
        draw = by_action.get("1")
        sides = [by_action.get("3"), by_action.get("0")]
        sides = [row for row in sides if row]
        if draw is None or len(sides) != 2:
            continue

        def avg(field: str) -> float:
            vals = [float(row[field]) for row in sides if math.isfinite(float(row[field]))]
            return mean(vals) if vals else float("nan")

        side_mean_abs = avg("mean_abs_move_log")
        side_p90_abs = avg("p90_abs_move_log")
        side_q_current = avg("q_vs_current_p")
        side_mult = avg("avg_realized_sp_multiplier_on_hits")
        out.append(
            {
                "segment": segment,
                "window": window,
                "draw_n": draw["n"],
                "side_avg_n": avg("n"),
                "draw_mean_abs_move_log": draw["mean_abs_move_log"],
                "side_mean_abs_move_log": side_mean_abs,
                "draw_vs_side_mean_abs_ratio": (
                    float(draw["mean_abs_move_log"]) / side_mean_abs if side_mean_abs else float("nan")
                ),
                "draw_p90_abs_move_log": draw["p90_abs_move_log"],
                "side_p90_abs_move_log": side_p90_abs,
                "draw_vs_side_p90_abs_ratio": (
                    float(draw["p90_abs_move_log"]) / side_p90_abs if side_p90_abs else float("nan")
                ),
                "draw_q_vs_current_p": draw["q_vs_current_p"],
                "side_q_vs_current_p": side_q_current,
                "draw_multiplier_on_hits": draw["avg_realized_sp_multiplier_on_hits"],
                "side_multiplier_on_hits": side_mult,
                "draw_ev_after_65": draw["ev_after_65"],
                "side_ev_after_65": avg("ev_after_65"),
            }
        )
    return out


def compact_action_summary(rows: list[dict[str, object]], *, segment: str, window: str) -> list[dict[str, object]]:
    selected = [row for row in rows if row["segment"] == segment and row["window"] == window]
    order = {"3": 0, "1": 1, "0": 2}
    selected.sort(key=lambda row: order[str(row["action_code"])])
    out = []
    for row in selected:
        out.append(
            {
                "action": f"{row['action_code']} {row['action_label']}",
                "n": row["n"],
                "hit": fmt_pct(row["hit_rate"]),
                "mean_abs_move": fmt_pct(row["mean_abs_move_log"]),
                "p90_abs_move": fmt_pct(row["p90_abs_move_log"]),
                "abs_gt_10": fmt_pct(row["share_abs_gt_10pct"]),
                "q_vs_current": fmt_num(row["q_vs_current_p"]),
                "sp_mult_hits": fmt_num(row["avg_realized_sp_multiplier_on_hits"]),
                "ev_after_65": fmt_pct(row["ev_after_65"]),
            }
        )
    return out


def compact_contrast(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    out = []
    for row in rows:
        if row["segment"] not in {"all", "recent_2023_2025"}:
            continue
        out.append(
            {
                "segment": row["segment"],
                "window": row["window"],
                "mean_abs_ratio": fmt_num(row["draw_vs_side_mean_abs_ratio"]),
                "p90_abs_ratio": fmt_num(row["draw_vs_side_p90_abs_ratio"]),
                "draw_q": fmt_num(row["draw_q_vs_current_p"]),
                "side_q": fmt_num(row["side_q_vs_current_p"]),
                "draw_mult": fmt_num(row["draw_multiplier_on_hits"]),
                "side_mult": fmt_num(row["side_multiplier_on_hits"]),
            }
        )
    return out


def run(args: argparse.Namespace) -> None:
    rows = load_rows(args.db, args.min_year)
    if not rows:
        raise SystemExit("no rows loaded")
    analysis_rows = expand_analysis_rows(rows)

    action_summary = group_summary(analysis_rows, ["segment", "window", "action_code", "action_label"])
    move_bucket_summary = group_summary(
        analysis_rows,
        ["segment", "window", "action_code", "action_label", "move_bucket"],
    )
    odds_move_summary = group_summary(
        analysis_rows,
        ["segment", "window", "action_code", "action_label", "base_odds_bucket", "move_bucket"],
    )
    annual_summary = group_summary(analysis_rows, ["year", "window", "action_code", "action_label"])
    contrast = contrast_rows(action_summary)

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "odds_sensitivity_action_summary.csv", action_summary)
    write_csv(out / "odds_sensitivity_move_bucket.csv", move_bucket_summary)
    write_csv(out / "odds_sensitivity_odds_move_bucket.csv", odds_move_summary)
    write_csv(out / "odds_sensitivity_annual_summary.csv", annual_summary)
    write_csv(out / "odds_sensitivity_draw_vs_side_contrast.csv", contrast)

    report = [
        "# Draw odds sensitivity analysis",
        "",
        f"- DB: `{args.db}`",
        f"- Min year: `{args.min_year}`",
        f"- Loaded outcome rows: `{len(rows)}`",
        f"- Expanded segment/window rows: `{len(analysis_rows)}`",
        "",
        "Caveat: `euro_*_odds` are European 1X2 proxy odds. For non-zero Beidan handicap, Beidan draw is handicap draw, so this is a proxy-level sensitivity study.",
        "",
        "## Draw Vs Side Contrast",
        "",
        md_table(compact_contrast(contrast)),
        "## All 10h->1h",
        "",
        md_table(compact_action_summary(action_summary, segment="all", window="10h_to_1h")),
        "## All 1h->final",
        "",
        md_table(compact_action_summary(action_summary, segment="all", window="1h_to_final")),
        "## Recent 2023-2025 10h->1h",
        "",
        md_table(compact_action_summary(action_summary, segment="recent_2023_2025", window="10h_to_1h")),
        "## Recent 2023-2025 1h->final",
        "",
        md_table(compact_action_summary(action_summary, segment="recent_2023_2025", window="1h_to_final")),
        "## Files",
        "",
        "- `odds_sensitivity_action_summary.csv`",
        "- `odds_sensitivity_draw_vs_side_contrast.csv`",
        "- `odds_sensitivity_move_bucket.csv`",
        "- `odds_sensitivity_odds_move_bucket.csv`",
        "- `odds_sensitivity_annual_summary.csv`",
        "",
    ]
    (out / "draw_odds_sensitivity_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'draw_odds_sensitivity_report.md'}")
    print(f"Wrote {len(action_summary)} action summary rows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--min-year", type=int, default=2014)
    parser.add_argument("--output-dir", type=Path, default=Path("results/draw_odds_sensitivity_2014"))
    args = parser.parse_args()
    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")
    run(args)


if __name__ == "__main__":
    main()
