#!/usr/bin/env python3
"""Investigate 2023-2025 low-q/low-confidence LL behavior for N=7 keyed tickets."""
from __future__ import annotations

import argparse
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.walkforward_beidan_strategy_eval import hcp_bucket, md_table


def issue_year(issue: object) -> int:
    text = str(issue)
    return 2000 + int(text[:2]) if len(text) >= 2 and text[:2].isdigit() else 0


def finite_mean(values: pd.Series) -> float:
    vals = pd.to_numeric(values, errors="coerce")
    vals = vals[np.isfinite(vals)]
    return float(vals.mean()) if len(vals) else float("nan")


def summarize_legs(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    rows = []
    for key, group in df.groupby(group_cols, dropna=False):
        if not isinstance(key, tuple):
            key = (key,)
        hits = group[group["hit"].astype(int) == 1]
        used = group[group["baseline_ticket_uses"].astype(int) > 0]
        used_hits = used[used["hit"].astype(int) == 1]
        hit_rate = len(hits) / len(group) if len(group) else float("nan")
        avg_snapshot_p = finite_mean(group["snapshot_p"])
        market_q_proxy = hit_rate / avg_snapshot_p if avg_snapshot_p and math.isfinite(avg_snapshot_p) else float("nan")
        avg_mult = finite_mean(hits["realized_sp_multiplier"])
        row = {col: value for col, value in zip(group_cols, key)}
        row.update(
            {
                "n_legs": len(group),
                "n_issues": group["issue"].nunique(),
                "n_years": group["year"].nunique(),
                "hit_rate": hit_rate,
                "avg_snapshot_p": avg_snapshot_p,
                "avg_snapshot_odds": finite_mean(group["snapshot_odds"]),
                "avg_pred_sp_multiplier": finite_mean(group["pred_sp_multiplier"]),
                "avg_realized_sp_multiplier_on_hits": avg_mult,
                "avg_winning_sp_on_hits": finite_mean(hits["winning_sp"]),
                "market_q_proxy": market_q_proxy,
                "drift_adjusted_ev_proxy": (
                    market_q_proxy * avg_mult
                    if math.isfinite(market_q_proxy) and math.isfinite(avg_mult)
                    else float("nan")
                ),
                "baseline_ticket_uses": int(group["baseline_ticket_uses"].sum()),
                "used_legs": len(used),
                "used_hit_rate": len(used_hits) / len(used) if len(used) else float("nan"),
                "used_avg_realized_sp_multiplier_on_hits": finite_mean(used_hits["realized_sp_multiplier"]),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def parse_ticket_legs(raw: str) -> list[str]:
    if not isinstance(raw, str) or not raw:
        return []
    out = []
    for item in raw.split(";"):
        token = item.split("@", 1)[0]
        if ":" in token:
            out.append(token)
    return out


def ticket_ll_rows(tickets: pd.DataFrame, leg: pd.DataFrame) -> pd.DataFrame:
    leg_info = leg.set_index("leg_id").to_dict("index")
    rows = []
    for row in tickets.itertuples(index=False):
        issue = str(row.issue)
        leg_ids = parse_ticket_legs(str(row.legs))
        infos = [leg_info.get(leg_id, {}) for leg_id in leg_ids]
        ll_infos = [info for info in infos if info.get("quad2") == "LL"]
        drift_counts = Counter(str(info.get("drift_bucket", "")) for info in ll_infos)
        pocket_counts = Counter(str(info.get("pocket", "")) for info in ll_infos)
        rows.append(
            {
                "strategy": row.strategy,
                "issue": issue,
                "year": issue_year(issue),
                "ticket_idx": int(row.ticket_idx),
                "stake_units": float(getattr(row, "stake_units", 1.0)),
                "hit": int(row.hit),
                "profit_units": float(row.profit_units),
                "payout_units": float(row.payout_units),
                "legs": row.legs,
                "ll_count": len(ll_infos),
                "ll_driftH_count": drift_counts.get("H", 0),
                "ll_driftM_count": drift_counts.get("M", 0),
                "ll_driftL_count": drift_counts.get("L", 0),
                "ll_pockets": ";".join(f"{k}:{v}" for k, v in sorted(pocket_counts.items()) if k),
                "ll_leg_ids": ";".join(str(info.get("leg_id_copy", "")) for info in ll_infos),
            }
        )
    return pd.DataFrame(rows)


def summarize_tickets(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    rows = []
    for key, group in df.groupby(group_cols, dropna=False):
        if not isinstance(key, tuple):
            key = (key,)
        hits = group[group["hit"] == 1]
        stake = float(group["stake_units"].sum()) if "stake_units" in group else float(len(group))
        hit_stake = float((group["hit"] * group.get("stake_units", 1.0)).sum()) if "stake_units" in group else float(group["hit"].sum())
        profit = float(group["profit_units"].sum())
        row = {col: value for col, value in zip(group_cols, key)}
        row.update(
            {
                "n_tickets": len(group),
                "n_issues": group["issue"].nunique(),
                "hits": int(group["hit"].sum()),
                "stake_units": stake,
                "hit_stake_units": hit_stake,
                "hit_rate": hit_stake / stake if stake > 0 else float("nan"),
                "profit_units": profit,
                "avg_profit_per_ticket": profit / len(group) if len(group) else float("nan"),
                "roi_per_stake": profit / stake if stake > 0 else float("nan"),
                "positive_profit_tickets": int((group["profit_units"] > 0).sum()),
                "best_ticket_profit": float(group["profit_units"].max()) if len(group) else float("nan"),
                "hit_profit_units": float(hits["profit_units"].sum()),
            }
        )
        rows.append(row)
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--joint-dir", type=Path, default=Path("results/n7_q_conf_drift_joint_2014_10h_trusted"))
    parser.add_argument("--matrix-dir", type=Path, default=Path("results/n7_q_pocket_conf_matrix_drift_ll_keyed_2014_10h_trusted"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_ll_2023_2025_investigation"))
    parser.add_argument("--start-year", type=int, default=2023)
    parser.add_argument("--end-year", type=int, default=2025)
    args = parser.parse_args()

    leg = pd.read_csv(args.joint_dir / "joint_leg_rows.csv")
    leg["q_med"] = leg.groupby("issue")["q_score"].transform("median")
    leg["conf_med"] = leg.groupby("issue")["conf_weight"].transform("median")
    leg["q_bin"] = np.where(leg["q_score"] >= leg["q_med"], "H", "L")
    leg["conf_bin"] = np.where(leg["conf_weight"] >= leg["conf_med"], "H", "L")
    leg["quad2"] = leg["q_bin"] + leg["conf_bin"]
    leg["hcp_bucket"] = leg["hcp"].map(hcp_bucket)
    leg["pocket"] = leg["action_code"].astype(str) + "@" + leg["hcp_bucket"].astype(str)
    leg["leg_id_copy"] = leg["leg_id"]
    recent_leg = leg[(leg["year"] >= args.start_year) & (leg["year"] <= args.end_year)].copy()
    recent_ll = recent_leg[recent_leg["quad2"] == "LL"].copy()

    tickets = pd.read_csv(args.joint_dir / "joint_replay_tickets.csv")
    base_tickets = tickets[tickets["strategy"] == "keyed_pockets__selector_all_keyed"].copy()
    recent_tickets = base_tickets[
        base_tickets["issue"].map(issue_year).between(args.start_year, args.end_year)
    ].copy()
    ticket_ll = ticket_ll_rows(recent_tickets, leg)
    budget_rows = pd.read_csv(args.joint_dir / "joint_replay_budget_rows.csv")
    base_budget_rows = budget_rows[
        budget_rows["strategy"] == "keyed_pockets__selector_all_keyed__budget20_whole"
    ].copy()
    recent_budget_rows = base_budget_rows[
        base_budget_rows["issue"].map(issue_year).between(args.start_year, args.end_year)
    ].copy()
    budget_ticket_ll = ticket_ll_rows(recent_budget_rows, leg)

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)

    period_quad = summarize_legs(
        leg.assign(period=np.where(leg["year"] >= args.start_year, "2023-2025", "2014-2022")),
        ["period", "quad2"],
    ).sort_values(["period", "quad2"])
    recent_ll_by_year = summarize_legs(recent_ll, ["year"]).sort_values("year")
    recent_ll_by_drift = summarize_legs(recent_ll, ["drift_bucket"]).sort_values("drift_bucket")
    recent_ll_by_pocket = summarize_legs(recent_ll, ["pocket"]).sort_values(
        ["baseline_ticket_uses", "n_legs"], ascending=False
    )
    recent_ll_by_league = summarize_legs(recent_ll, ["league"]).sort_values(
        ["baseline_ticket_uses", "n_legs"], ascending=False
    )
    recent_ll_by_year_drift = summarize_legs(recent_ll, ["year", "drift_bucket"]).sort_values(["year", "drift_bucket"])

    ticket_by_ll_count = summarize_tickets(ticket_ll, ["ll_count"]).sort_values("ll_count")
    ticket_by_year_ll_count = summarize_tickets(ticket_ll, ["year", "ll_count"]).sort_values(["year", "ll_count"])
    budget_ticket_by_ll_count = summarize_tickets(budget_ticket_ll, ["ll_count"]).sort_values("ll_count")
    budget_ticket_by_year_ll_count = summarize_tickets(budget_ticket_ll, ["year", "ll_count"]).sort_values(["year", "ll_count"])
    winning_tickets = ticket_ll[ticket_ll["hit"] == 1].sort_values(["year", "issue", "ticket_idx"])
    budget_winning_tickets = budget_ticket_ll[budget_ticket_ll["hit"] == 1].sort_values(["year", "issue", "ticket_idx"])
    winning_ticket_detail = []
    leg_info = leg.set_index("leg_id").to_dict("index")
    for row in winning_tickets.itertuples(index=False):
        for leg_id in parse_ticket_legs(str(row.legs)):
            info = leg_info.get(leg_id, {})
            winning_ticket_detail.append(
                {
                    "issue": row.issue,
                    "year": row.year,
                    "ticket_idx": row.ticket_idx,
                    "ticket_profit_units": row.profit_units,
                    "leg_id": leg_id,
                    "quad2": info.get("quad2", ""),
                    "drift_bucket": info.get("drift_bucket", ""),
                    "pocket": info.get("pocket", ""),
                    "league": info.get("league", ""),
                    "q_score": info.get("q_score", float("nan")),
                    "conf_weight": info.get("conf_weight", float("nan")),
                    "pred_sp_multiplier": info.get("pred_sp_multiplier", float("nan")),
                    "snapshot_odds": info.get("snapshot_odds", float("nan")),
                    "winning_sp": info.get("winning_sp", float("nan")),
                    "realized_sp_multiplier": info.get("realized_sp_multiplier", float("nan")),
                }
            )
    winning_ticket_detail_df = pd.DataFrame(winning_ticket_detail)

    arm_annual = pd.DataFrame()
    matrix_annual_path = args.matrix_dir / "q_pocket_conf_matrix_annual_summary.csv"
    if matrix_annual_path.exists():
        arm_annual = pd.read_csv(matrix_annual_path)
        arm_annual = arm_annual[arm_annual["year"].between(args.start_year, args.end_year)].copy()

    outputs = {
        "period_quad_summary.csv": period_quad,
        "recent_ll_by_year.csv": recent_ll_by_year,
        "recent_ll_by_drift.csv": recent_ll_by_drift,
        "recent_ll_by_pocket.csv": recent_ll_by_pocket,
        "recent_ll_by_league.csv": recent_ll_by_league,
        "recent_ll_by_year_drift.csv": recent_ll_by_year_drift,
        "base_ticket_by_ll_count_2023_2025.csv": ticket_by_ll_count,
        "base_ticket_by_year_ll_count_2023_2025.csv": ticket_by_year_ll_count,
        "base_budget_ticket_by_ll_count_2023_2025.csv": budget_ticket_by_ll_count,
        "base_budget_ticket_by_year_ll_count_2023_2025.csv": budget_ticket_by_year_ll_count,
        "base_winning_tickets_2023_2025.csv": winning_tickets,
        "base_budget_winning_tickets_2023_2025.csv": budget_winning_tickets,
        "base_winning_ticket_leg_detail_2023_2025.csv": winning_ticket_detail_df,
        "ll_arm_annual_2023_2025.csv": arm_annual,
    }
    for filename, df in outputs.items():
        df.to_csv(out / filename, index=False)

    key_cols = [
        "period",
        "quad2",
        "n_legs",
        "hit_rate",
        "avg_realized_sp_multiplier_on_hits",
        "drift_adjusted_ev_proxy",
        "baseline_ticket_uses",
        "used_hit_rate",
    ]
    recent_ll_cols = [
        "drift_bucket",
        "n_legs",
        "n_issues",
        "hit_rate",
        "avg_realized_sp_multiplier_on_hits",
        "drift_adjusted_ev_proxy",
        "baseline_ticket_uses",
        "used_hit_rate",
    ]
    report = [
        "# N=7 2023-2025 LL investigation",
        "",
        f"- Joint dir: `{args.joint_dir}`",
        f"- Reconstructed LL: issue-local median q_score = L and median conf_weight = L",
        f"- Period: `{args.start_year}-{args.end_year}`",
        "",
        "## Period x Quadrant",
        md_table(period_quad[key_cols].to_dict("records")),
        "## Recent LL by drift bucket",
        md_table(recent_ll_by_drift[recent_ll_cols].to_dict("records")),
        "## Base tickets by LL count, 2023-2025",
        md_table(ticket_by_ll_count.to_dict("records")),
        "## Base budgeted tickets by LL count, 2023-2025",
        md_table(budget_ticket_by_ll_count.to_dict("records")),
        "## Base winning tickets, 2023-2025",
        md_table(winning_tickets.to_dict("records")),
        "## Top LL pockets by base ticket use, 2023-2025",
        md_table(recent_ll_by_pocket.head(12).to_dict("records")),
        "## Files",
        "",
    ]
    report.extend(f"- `{filename}`" for filename in outputs)
    (out / "ll_2023_2025_investigation.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'll_2023_2025_investigation.md'}")


if __name__ == "__main__":
    main()
