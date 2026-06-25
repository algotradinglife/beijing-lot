#!/usr/bin/env python3
"""Evaluate dynamic N selection over precomputed N=5/6/7/8 strategy runs."""
from __future__ import annotations

import argparse
import math
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.walkforward_beidan_strategy_eval import md_table, strategy_verdict, write_csv


MAIN_STRATEGY = "confidence_depth_constrained_hybrid__draw_dynamic_model_draw_ratio_t0.55_k2"
DEFAULT_RUNS = {
    "t8": {
        5: Path("results/n5_dynamic_draw_cover_t8"),
        6: Path("results/n6_dynamic_draw_cover_t8"),
        7: Path("results/n7_dynamic_draw_cover_t8"),
        8: Path("results/n8_dynamic_draw_cover_t8"),
    },
    "t12": {
        5: Path("results/n5_dynamic_draw_cover_t12"),
        6: Path("results/n6_dynamic_draw_cover_t12"),
        7: Path("results/n7_dynamic_draw_cover"),
        8: Path("results/n8_dynamic_draw_cover_t12"),
    },
    "t16": {
        5: Path("results/n5_dynamic_draw_cover_t16"),
        6: Path("results/n6_dynamic_draw_cover_t16"),
        7: Path("results/n7_dynamic_draw_cover_t16"),
        8: Path("results/n8_dynamic_draw_cover_t16"),
    },
    "t20": {
        5: Path("results/n5_dynamic_draw_cover_t20"),
        6: Path("results/n6_dynamic_draw_cover_t20"),
        7: Path("results/n7_dynamic_draw_cover_t20"),
        8: Path("results/n8_dynamic_draw_cover_t20"),
    },
}


@dataclass(frozen=True)
class SelectorProfile:
    name: str
    window: int
    metric: str
    min_history_issues: int
    fallback_n: int = 7
    min_best_roi: float | None = None
    margin_vs_fallback: float = 0.0
    risk_penalty: float = 0.0
    win_rate_bonus: float = 0.0


def read_csv(path: Path) -> list[dict[str, str]]:
    import csv

    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def default_profiles() -> list[SelectorProfile]:
    return [
        SelectorProfile("roi_w4_fallback7", window=4, metric="roi", min_history_issues=4),
        SelectorProfile("roi_w6_fallback7", window=6, metric="roi", min_history_issues=4),
        SelectorProfile("roi_w8_fallback7", window=8, metric="roi", min_history_issues=5),
        SelectorProfile("roi_w12_fallback7", window=12, metric="roi", min_history_issues=6),
        SelectorProfile("roi_w8_margin10", window=8, metric="roi", min_history_issues=5, margin_vs_fallback=0.10),
        SelectorProfile("roi_w8_margin25", window=8, metric="roi", min_history_issues=5, margin_vs_fallback=0.25),
        SelectorProfile("roi_w12_margin10", window=12, metric="roi", min_history_issues=6, margin_vs_fallback=0.10),
        SelectorProfile("roi_w6_skip_if_negative", window=6, metric="roi", min_history_issues=4, min_best_roi=0.0),
        SelectorProfile("profit_w6_fallback7", window=6, metric="profit", min_history_issues=4),
        SelectorProfile(
            "riskadj_w8_fallback7",
            window=8,
            metric="risk_adjusted_roi",
            min_history_issues=5,
            risk_penalty=0.35,
            win_rate_bonus=0.20,
        ),
        SelectorProfile(
            "riskadj_w8_skip_if_negative",
            window=8,
            metric="risk_adjusted_roi",
            min_history_issues=5,
            min_best_roi=0.0,
            risk_penalty=0.35,
            win_rate_bonus=0.20,
        ),
    ]


def n_sets(raw: str) -> dict[str, list[int]]:
    out = {}
    for part in raw.split(";"):
        part = part.strip()
        if not part:
            continue
        name, values = part.split("=", 1)
        out[name.strip()] = [int(x) for x in values.split(",") if x.strip()]
    return out


def load_runs(run_dirs: dict[str, dict[int, Path]], allowed_ns: list[int]):
    issue_rows: dict[tuple[int, str], dict[str, str]] = {}
    ticket_rows: dict[tuple[int, str], list[dict[str, str]]] = defaultdict(list)
    issues: set[str] = set()
    for n in allowed_ns:
        directory = run_dirs[n]
        for row in read_csv(directory / "dynamic_draw_issue_profit.csv"):
            if row["strategy"] != MAIN_STRATEGY:
                continue
            issue = row["issue"]
            issues.add(issue)
            issue_rows[(n, issue)] = row
        for row in read_csv(directory / "dynamic_draw_tickets.csv"):
            if row["strategy"] != MAIN_STRATEGY:
                continue
            ticket_rows[(n, row["issue"])].append(row)
    return sorted(issues), issue_rows, ticket_rows


def stats(rows: list[dict[str, str]]) -> dict[str, float]:
    if not rows:
        return {"stake": 0.0, "profit": 0.0, "roi": float("-inf"), "std_roi": 0.0, "win_rate": 0.0}
    stakes = np.asarray([float(r["stake_units"]) for r in rows], dtype=float)
    profits = np.asarray([float(r["profit_units"]) for r in rows], dtype=float)
    rois = profits / np.maximum(stakes, 1e-9)
    stake = float(stakes.sum())
    profit = float(profits.sum())
    return {
        "stake": stake,
        "profit": profit,
        "roi": profit / stake if stake > 0 else float("-inf"),
        "std_roi": float(rois.std()) if len(rois) else 0.0,
        "win_rate": float((profits > 0).mean()) if len(profits) else 0.0,
    }


def score(st: dict[str, float], profile: SelectorProfile) -> float:
    if profile.metric == "roi":
        return st["roi"]
    if profile.metric == "profit":
        return st["profit"]
    if profile.metric == "risk_adjusted_roi":
        return st["roi"] - profile.risk_penalty * st["std_roi"] + profile.win_rate_bonus * st["win_rate"]
    raise ValueError(f"unsupported metric: {profile.metric}")


def choose_n(
    issue_idx: int,
    issues: list[str],
    allowed_ns: list[int],
    issue_rows: dict[tuple[int, str], dict[str, str]],
    profile: SelectorProfile,
) -> tuple[int | None, dict[str, object]]:
    past = issues[max(0, issue_idx - profile.window) : issue_idx]
    if len(past) < profile.min_history_issues:
        return profile.fallback_n, {
            "decision_reason": "insufficient_history_fallback7",
            "past_issues": len(past),
            "best_score": "",
            "best_trailing_roi": "",
            "fallback_trailing_roi": "",
        }

    scored = []
    by_n = {}
    for n in allowed_ns:
        rows = [issue_rows[(n, issue)] for issue in past if (n, issue) in issue_rows]
        st = stats(rows)
        by_n[n] = st
        if len(rows) >= profile.min_history_issues and st["stake"] > 0:
            scored.append((score(st, profile), n, st))
    if not scored:
        return profile.fallback_n, {
            "decision_reason": "no_scored_n_fallback7",
            "past_issues": len(past),
            "best_score": "",
            "best_trailing_roi": "",
            "fallback_trailing_roi": "",
        }
    scored.sort(key=lambda x: (x[0], x[2]["roi"], x[2]["profit"]), reverse=True)
    best_score, best_n, best_stats = scored[0]
    fallback_stats = by_n.get(profile.fallback_n, stats([]))

    if profile.margin_vs_fallback > 0 and profile.fallback_n in allowed_ns:
        fallback_score = score(fallback_stats, profile)
        if best_score < fallback_score + profile.margin_vs_fallback:
            return profile.fallback_n, {
                "decision_reason": "fallback7_margin",
                "past_issues": len(past),
                "best_score": best_score,
                "best_trailing_roi": best_stats["roi"],
                "fallback_trailing_roi": fallback_stats["roi"],
            }

    if profile.min_best_roi is not None and best_stats["roi"] < profile.min_best_roi:
        return None, {
            "decision_reason": "skip_best_roi_below_floor",
            "past_issues": len(past),
            "best_score": best_score,
            "best_trailing_roi": best_stats["roi"],
            "fallback_trailing_roi": fallback_stats["roi"],
        }

    return best_n, {
        "decision_reason": "selected_best_trailing_score",
        "past_issues": len(past),
        "best_score": best_score,
        "best_trailing_roi": best_stats["roi"],
        "fallback_trailing_roi": fallback_stats["roi"],
    }


def summarize_mixed(selector: str, rows: list[dict[str, str]]) -> dict[str, object]:
    rows = sorted(rows, key=lambda r: (str(r["issue"]), int(r["ticket_idx"])))
    stake = sum(float(r["stake_units"]) for r in rows)
    profit = sum(float(r["profit_units"]) for r in rows)
    hits = sum(int(r["hit"]) for r in rows)
    issue_profit: dict[str, float] = defaultdict(float)
    issue_stake: dict[str, float] = defaultdict(float)
    cur_loss = 0
    max_loss = 0
    for row in rows:
        issue_profit[str(row["issue"])] += float(row["profit_units"])
        issue_stake[str(row["issue"])] += float(row["stake_units"])
        if int(row["hit"]) == 1:
            cur_loss = 0
        else:
            cur_loss += 1
            max_loss = max(max_loss, cur_loss)
    best_issue_profit = max(issue_profit.values()) if issue_profit else 0.0
    roi = profit / stake if stake > 0 else float("nan")
    hit_rate = hits / len(rows) if rows else 0.0
    best_share = best_issue_profit / profit if profit > 0 and best_issue_profit > 0 else None
    verdict, reason = strategy_verdict(
        n_tickets=len(rows),
        roi=roi,
        profitable_issues=sum(1 for v in issue_profit.values() if v > 0),
        best_issue_profit_share=best_share,
        hit_rate=hit_rate,
    )
    n_counts = Counter(int(r["n_legs"]) for r in rows)
    return {
        "selector": selector,
        "n_tickets": len(rows),
        "n_issues": len(issue_profit),
        "hit_rate": hit_rate,
        "profitable_issues": sum(1 for v in issue_profit.values() if v > 0),
        "total_stake_units": stake,
        "total_profit_units": profit,
        "roi": roi,
        "best_issue_profit_share": best_share if best_share is not None else "",
        "max_ticket_loss_streak": max_loss,
        "avg_double_cover_per_ticket": sum(float(r["n_double_cover"]) for r in rows) / len(rows) if rows else 0.0,
        "avg_n_legs": sum(int(r["n_legs"]) for r in rows) / len(rows) if rows else 0.0,
        "n_mix": ";".join(f"N{k}:{v}" for k, v in sorted(n_counts.items())),
        "verdict": verdict,
        "verdict_reason": reason,
    }


def run_selector_for_window(train_window: str, run_dirs: dict[int, Path], set_name: str, allowed_ns: list[int], profiles):
    issues, issue_rows, tickets_by_key = load_runs(run_dirs, allowed_ns)
    decisions = []
    tickets = []
    summaries = []
    for profile in profiles:
        selector = f"selector_{set_name}_{profile.name}"
        ticket_strategy = f"{selector}__tw_{train_window}"
        n_counts: Counter[str] = Counter()
        skipped = 0
        selected_rows = []
        for issue_idx, issue in enumerate(issues):
            chosen_n, meta = choose_n(issue_idx, issues, allowed_ns, issue_rows, profile)
            if chosen_n is None:
                skipped += 1
                n_counts["SKIP"] += 1
                issue_profit = issue_stake = issue_hits = issue_tickets = 0.0
            else:
                n_counts[f"N{chosen_n}"] += 1
                issue_row = issue_rows.get((chosen_n, issue))
                issue_profit = float(issue_row["profit_units"]) if issue_row else 0.0
                issue_stake = float(issue_row["stake_units"]) if issue_row else 0.0
                issue_hits = float(issue_row["hits"]) if issue_row else 0.0
                issue_tickets = float(issue_row["tickets"]) if issue_row else 0.0
                for row in tickets_by_key.get((chosen_n, issue), []):
                    copied = dict(row)
                    copied["strategy"] = ticket_strategy
                    copied["selector"] = selector
                    copied["source_n"] = chosen_n
                    selected_rows.append(copied)
                    tickets.append(copied)
            decisions.append(
                {
                    "train_window": train_window,
                    "n_set": set_name,
                    "selector": selector,
                    "issue": issue,
                    "chosen_n": chosen_n or "SKIP",
                    "issue_tickets": issue_tickets,
                    "issue_hits": issue_hits,
                    "issue_stake_units": issue_stake,
                    "issue_profit_units": issue_profit,
                    "issue_roi": issue_profit / issue_stake if issue_stake else "",
                    **meta,
                }
            )
        summary = summarize_mixed(ticket_strategy, selected_rows)
        summary.update(
            {
                "train_window": train_window,
                "n_set": set_name,
                "selector": selector,
                "ticket_strategy": ticket_strategy,
                "decision_issues": len(issues),
                "skipped_issues": skipped,
                "decision_mix": ";".join(f"{k}:{v}" for k, v in n_counts.most_common()),
            }
        )
        summaries.append(summary)
    return decisions, tickets, summaries


def aggregate(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["n_set"]), str(row["selector"]))].append(row)
    out = []
    for (set_name, selector), vals in grouped.items():
        rois = [float(v["roi"]) for v in vals]
        profits = [float(v["total_profit_units"]) for v in vals]
        hit_rates = [float(v["hit_rate"]) for v in vals]
        streaks = [float(v["max_ticket_loss_streak"]) for v in vals]
        out.append(
            {
                "n_set": set_name,
                "selector": selector,
                "windows": len(vals),
                "avg_roi": sum(rois) / len(rois),
                "min_roi": min(rois),
                "total_profit_units": sum(profits),
                "avg_hit_rate": sum(hit_rates) / len(hit_rates),
                "avg_max_ticket_loss_streak": sum(streaks) / len(streaks),
                "pass_windows": sum(1 for v in vals if v["verdict"] == "pass_watchlist"),
                "avg_n_legs": sum(float(v["avg_n_legs"]) for v in vals) / len(vals),
                "avg_skipped_issues": sum(float(v["skipped_issues"]) for v in vals) / len(vals),
            }
        )
    out.sort(key=lambda r: (float(r["pass_windows"]), float(r["avg_roi"]), float(r["total_profit_units"])), reverse=True)
    return out


def run(args: argparse.Namespace) -> None:
    sets = n_sets(args.n_sets)
    profiles = default_profiles()
    decisions = []
    tickets = []
    summaries = []
    for train_window, run_dirs in DEFAULT_RUNS.items():
        for set_name, allowed_ns in sets.items():
            d, t, s = run_selector_for_window(train_window, run_dirs, set_name, allowed_ns, profiles)
            decisions.extend(d)
            tickets.extend(t)
            summaries.extend(s)
    agg = aggregate(summaries)
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "n_dynamic_selector_decisions.csv", decisions)
    write_csv(out / "n_dynamic_selector_tickets.csv", tickets)
    write_csv(out / "n_dynamic_selector_summary.csv", summaries)
    write_csv(out / "n_dynamic_selector_aggregate.csv", agg)
    report = [
        "# Dynamic N selector evaluation",
        "",
        f"- Strategy: `{MAIN_STRATEGY}`",
        f"- N sets: `{args.n_sets}`",
        "- Leakage guard: each issue selects N from prior issue-level performance only.",
        "",
        "## Aggregate",
        md_table(agg[:60]),
        "",
        "## Summary",
        md_table(summaries[:80]),
        "",
        "## Files",
        "",
        "- `n_dynamic_selector_aggregate.csv`",
        "- `n_dynamic_selector_summary.csv`",
        "- `n_dynamic_selector_decisions.csv`",
        "- `n_dynamic_selector_tickets.csv`",
        "",
    ]
    (out / "n_dynamic_selector_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'n_dynamic_selector_report.md'}")
    print(f"Wrote {len(decisions)} decisions and {len(tickets)} ticket rows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("results/n_dynamic_selector"))
    parser.add_argument("--n-sets", default="n5678=5,6,7,8;n67=6,7;n678=6,7,8")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
