#!/usr/bin/env python3
"""Evaluate issue-level regime selectors over precomputed N=7 strategy candidates."""
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

from scripts.evaluate_n7_depth_draw_cover import compact_summary
from scripts.walkforward_beidan_strategy_eval import md_table, summarize_tickets, write_csv


CURRENT_MAIN = "confidence_depth_constrained_hybrid__draw_dynamic_model_draw_ratio_t0.55_k2"


@dataclass(frozen=True)
class RunSpec:
    train_window: str
    directory: Path


@dataclass(frozen=True)
class SelectorProfile:
    name: str
    window: int
    metric: str
    min_history_issues: int
    fallback: str
    min_best_roi: float | None = None
    margin_vs_current: float = 0.0
    risk_penalty: float = 0.0
    win_rate_bonus: float = 0.0


def read_csv(path: Path) -> list[dict[str, str]]:
    import csv

    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def parse_run_specs(raw: str) -> list[RunSpec]:
    out = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        label, directory = item.split("=", 1)
        out.append(RunSpec(label.strip(), Path(directory.strip())))
    return out


def candidate_allowed(strategy: str, candidate_set: str) -> bool:
    is_conf = strategy.startswith("confidence_depth_constrained_hybrid")
    is_dynamic = "__draw_dynamic_" in strategy
    is_k2 = "_k2" in strategy
    if candidate_set == "confidence_all":
        return is_conf
    if candidate_set == "confidence_k2":
        return is_conf and is_dynamic and is_k2
    if candidate_set == "confidence_stable":
        return strategy in {
            "confidence_depth_constrained_hybrid",
            "confidence_depth_constrained_hybrid__draw_cover_model_draw_ratio_k2",
            "confidence_depth_constrained_hybrid__draw_dynamic_model_draw_ratio_t0.55_k2",
            "confidence_depth_constrained_hybrid__draw_dynamic_model_draw_ratio_t0.65_k2",
            "confidence_depth_constrained_hybrid__draw_dynamic_model_draw_ratio_t0.75_k2",
        }
    if candidate_set == "confidence_pair75":
        return strategy in {
            "confidence_depth_constrained_hybrid__draw_dynamic_model_draw_ratio_t0.55_k2",
            "confidence_depth_constrained_hybrid__draw_dynamic_model_draw_ratio_t0.75_k2",
        }
    if candidate_set == "confidence_pair65_75":
        return strategy in {
            "confidence_depth_constrained_hybrid__draw_dynamic_model_draw_ratio_t0.55_k2",
            "confidence_depth_constrained_hybrid__draw_dynamic_model_draw_ratio_t0.65_k2",
            "confidence_depth_constrained_hybrid__draw_dynamic_model_draw_ratio_t0.75_k2",
        }
    if candidate_set == "all":
        return True
    raise ValueError(f"unsupported candidate set: {candidate_set}")


def strategy_stats(rows: list[dict[str, str]]) -> dict[str, float]:
    if not rows:
        return {
            "stake": 0.0,
            "profit": 0.0,
            "roi": float("-inf"),
            "mean_issue_roi": float("-inf"),
            "std_issue_roi": 0.0,
            "win_rate": 0.0,
        }
    stakes = np.asarray([float(r["stake_units"]) for r in rows], dtype=float)
    profits = np.asarray([float(r["profit_units"]) for r in rows], dtype=float)
    rois = np.divide(profits, np.maximum(stakes, 1e-9))
    stake = float(stakes.sum())
    profit = float(profits.sum())
    return {
        "stake": stake,
        "profit": profit,
        "roi": profit / stake if stake > 0 else float("-inf"),
        "mean_issue_roi": float(rois.mean()) if len(rois) else float("-inf"),
        "std_issue_roi": float(rois.std()) if len(rois) else 0.0,
        "win_rate": float((profits > 0).mean()) if len(profits) else 0.0,
    }


def score_stats(stats: dict[str, float], profile: SelectorProfile) -> float:
    if profile.metric == "roi":
        base = stats["roi"]
    elif profile.metric == "profit":
        base = stats["profit"]
    elif profile.metric == "mean_issue_roi":
        base = stats["mean_issue_roi"]
    elif profile.metric == "risk_adjusted_roi":
        base = stats["roi"] - profile.risk_penalty * stats["std_issue_roi"] + profile.win_rate_bonus * stats["win_rate"]
    else:
        raise ValueError(f"unsupported selector metric: {profile.metric}")
    return float(base)


def default_profiles() -> list[SelectorProfile]:
    return [
        SelectorProfile("roi_w4_current_fallback", window=4, metric="roi", min_history_issues=4, fallback="current"),
        SelectorProfile("roi_w6_current_fallback", window=6, metric="roi", min_history_issues=4, fallback="current"),
        SelectorProfile("roi_w8_current_fallback", window=8, metric="roi", min_history_issues=5, fallback="current"),
        SelectorProfile("roi_w6_margin10", window=6, metric="roi", min_history_issues=4, fallback="current", margin_vs_current=0.10),
        SelectorProfile("roi_w8_margin10", window=8, metric="roi", min_history_issues=5, fallback="current", margin_vs_current=0.10),
        SelectorProfile("roi_w8_margin25", window=8, metric="roi", min_history_issues=5, fallback="current", margin_vs_current=0.25),
        SelectorProfile("roi_w12_current_fallback", window=12, metric="roi", min_history_issues=6, fallback="current"),
        SelectorProfile("roi_w12_margin10", window=12, metric="roi", min_history_issues=6, fallback="current", margin_vs_current=0.10),
        SelectorProfile("roi_w6_skip_if_negative", window=6, metric="roi", min_history_issues=4, fallback="skip", min_best_roi=0.0),
        SelectorProfile("profit_w6_current_fallback", window=6, metric="profit", min_history_issues=4, fallback="current"),
        SelectorProfile(
            "riskadj_w8_current_fallback",
            window=8,
            metric="risk_adjusted_roi",
            min_history_issues=5,
            fallback="current",
            risk_penalty=0.35,
            win_rate_bonus=0.20,
        ),
        SelectorProfile(
            "riskadj_w8_skip_if_negative",
            window=8,
            metric="risk_adjusted_roi",
            min_history_issues=5,
            fallback="skip",
            min_best_roi=0.0,
            risk_penalty=0.35,
            win_rate_bonus=0.20,
        ),
    ]


def load_run(directory: Path, candidate_set: str):
    issue_rows = read_csv(directory / "dynamic_draw_issue_profit.csv")
    ticket_rows = read_csv(directory / "dynamic_draw_tickets.csv")
    candidates = sorted({r["strategy"] for r in issue_rows if candidate_allowed(r["strategy"], candidate_set)})
    issues = sorted({r["issue"] for r in issue_rows})
    issue_by_key: dict[tuple[str, str], dict[str, str]] = {}
    for row in issue_rows:
        if row["strategy"] in candidates:
            issue_by_key[(row["strategy"], row["issue"])] = row
    tickets_by_key: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in ticket_rows:
        if row["strategy"] in candidates:
            tickets_by_key[(row["strategy"], row["issue"])].append(row)
    return candidates, issues, issue_by_key, tickets_by_key


def select_strategy(
    *,
    issue_idx: int,
    issues: list[str],
    candidates: list[str],
    issue_by_key: dict[tuple[str, str], dict[str, str]],
    profile: SelectorProfile,
) -> tuple[str | None, dict[str, object]]:
    issue = issues[issue_idx]
    past_issues = issues[max(0, issue_idx - profile.window) : issue_idx]
    if len(past_issues) < profile.min_history_issues:
        fallback = CURRENT_MAIN if CURRENT_MAIN in candidates else (candidates[0] if candidates else None)
        return fallback, {
            "decision_reason": "insufficient_history_current_fallback",
            "past_issues": len(past_issues),
            "best_score": "",
            "best_trailing_roi": "",
            "current_trailing_roi": "",
        }

    scored = []
    stats_by_strategy = {}
    for strategy in candidates:
        rows = [issue_by_key[(strategy, past)] for past in past_issues if (strategy, past) in issue_by_key]
        stats = strategy_stats(rows)
        stats_by_strategy[strategy] = stats
        if len(rows) < profile.min_history_issues or stats["stake"] <= 0:
            continue
        scored.append((score_stats(stats, profile), strategy, stats))
    if not scored:
        fallback = CURRENT_MAIN if profile.fallback == "current" and CURRENT_MAIN in candidates else None
        return fallback, {
            "decision_reason": "no_scored_candidate",
            "past_issues": len(past_issues),
            "best_score": "",
            "best_trailing_roi": "",
            "current_trailing_roi": "",
        }
    scored.sort(key=lambda x: (x[0], x[2]["roi"], x[2]["profit"]), reverse=True)
    best_score, best_strategy, best_stats = scored[0]
    current_stats = stats_by_strategy.get(CURRENT_MAIN, strategy_stats([]))

    if profile.margin_vs_current > 0 and CURRENT_MAIN in candidates:
        current_score = score_stats(current_stats, profile)
        if best_score < current_score + profile.margin_vs_current:
            return CURRENT_MAIN, {
                "decision_reason": "current_margin_fallback",
                "past_issues": len(past_issues),
                "best_score": best_score,
                "best_trailing_roi": best_stats["roi"],
                "current_trailing_roi": current_stats["roi"],
            }

    if profile.min_best_roi is not None and best_stats["roi"] < profile.min_best_roi:
        if profile.fallback == "skip":
            return None, {
                "decision_reason": "skip_best_roi_below_floor",
                "past_issues": len(past_issues),
                "best_score": best_score,
                "best_trailing_roi": best_stats["roi"],
                "current_trailing_roi": current_stats["roi"],
            }
        if profile.fallback == "current" and CURRENT_MAIN in candidates:
            return CURRENT_MAIN, {
                "decision_reason": "current_best_roi_below_floor",
                "past_issues": len(past_issues),
                "best_score": best_score,
                "best_trailing_roi": best_stats["roi"],
                "current_trailing_roi": current_stats["roi"],
            }

    return best_strategy, {
        "decision_reason": "selected_best_trailing_score",
        "past_issues": len(past_issues),
        "best_score": best_score,
        "best_trailing_roi": best_stats["roi"],
        "current_trailing_roi": current_stats["roi"],
    }


def run_selector_for_spec(
    spec: RunSpec,
    *,
    candidate_set: str,
    profiles: list[SelectorProfile],
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    candidates, issues, issue_by_key, tickets_by_key = load_run(spec.directory, candidate_set)
    decision_rows: list[dict[str, object]] = []
    selected_ticket_rows: list[dict[str, object]] = []
    profile_summary_rows: list[dict[str, object]] = []

    for profile in profiles:
        selector_name = f"selector_{candidate_set}_{profile.name}"
        ticket_strategy_name = f"{selector_name}__tw_{spec.train_window}"
        source_counts: Counter[str] = Counter()
        skipped = 0
        for issue_idx, issue in enumerate(issues):
            chosen, meta = select_strategy(
                issue_idx=issue_idx,
                issues=issues,
                candidates=candidates,
                issue_by_key=issue_by_key,
                profile=profile,
            )
            if chosen is None:
                skipped += 1
                chosen_profit = chosen_stake = chosen_hits = chosen_tickets = 0.0
                source_counts["SKIP"] += 1
            else:
                source_counts[chosen] += 1
                issue_row = issue_by_key.get((chosen, issue))
                chosen_profit = float(issue_row["profit_units"]) if issue_row else 0.0
                chosen_stake = float(issue_row["stake_units"]) if issue_row else 0.0
                chosen_hits = float(issue_row["hits"]) if issue_row else 0.0
                chosen_tickets = float(issue_row["tickets"]) if issue_row else 0.0
                for ticket in tickets_by_key.get((chosen, issue), []):
                    copied = dict(ticket)
                    copied["selector"] = selector_name
                    copied["source_strategy"] = chosen
                    copied["strategy"] = ticket_strategy_name
                    selected_ticket_rows.append(copied)
            decision_rows.append(
                {
                    "train_window": spec.train_window,
                    "candidate_set": candidate_set,
                    "selector": selector_name,
                    "profile": profile.name,
                    "issue": issue,
                    "chosen_strategy": chosen or "SKIP",
                    "chosen_tickets": chosen_tickets,
                    "chosen_hits": chosen_hits,
                    "chosen_stake_units": chosen_stake,
                    "chosen_profit_units": chosen_profit,
                    "chosen_roi": chosen_profit / chosen_stake if chosen_stake else "",
                    **meta,
                }
            )
        profile_summary_rows.append(
            {
                "train_window": spec.train_window,
                "candidate_set": candidate_set,
                "selector": selector_name,
                "ticket_strategy": ticket_strategy_name,
                "decision_issues": len(issues),
                "skipped_issues": skipped,
                "unique_source_strategies": len([k for k in source_counts if k != "SKIP"]),
                "current_main_issues": source_counts.get(CURRENT_MAIN, 0),
                "top_source_strategy": source_counts.most_common(1)[0][0] if source_counts else "",
                "top_source_issues": source_counts.most_common(1)[0][1] if source_counts else 0,
                "source_mix": ";".join(f"{k}:{v}" for k, v in source_counts.most_common()),
            }
        )

    return decision_rows, selected_ticket_rows, profile_summary_rows


def selector_summary_rows(ticket_rows: list[dict[str, object]], profile_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    base_summary = summarize_tickets(ticket_rows)
    by_selector = {row["strategy"]: row for row in base_summary}
    out = []
    for profile_row in profile_rows:
        selector = str(profile_row["selector"])
        ticket_strategy = str(profile_row["ticket_strategy"])
        summary = by_selector.get(ticket_strategy)
        if summary is None:
            row = dict(profile_row)
            row.update(
                {
                    "n_tickets": 0,
                    "n_issues": 0,
                    "hit_rate": "",
                    "profitable_issues": 0,
                    "total_stake_units": 0.0,
                    "total_profit_units": 0.0,
                    "roi": "",
                    "best_issue_profit_share": "",
                    "max_ticket_loss_streak": "",
                    "avg_double_cover_per_ticket": "",
                    "verdict": "skip_all",
                }
            )
        else:
            row = dict(profile_row)
            row.update(
                {
                    "n_tickets": summary.get("n_tickets", ""),
                    "n_issues": summary.get("n_issues", ""),
                    "hit_rate": summary.get("hit_rate", ""),
                    "profitable_issues": summary.get("profitable_issues", ""),
                    "total_stake_units": summary.get("total_stake_units", ""),
                    "total_profit_units": summary.get("total_profit_units", ""),
                    "roi": summary.get("roi", ""),
                    "best_issue_profit_share": summary.get("best_issue_profit_share", ""),
                    "max_ticket_loss_streak": summary.get("max_ticket_loss_streak", ""),
                    "avg_double_cover_per_ticket": summary.get("avg_double_cover_per_ticket", ""),
                    "verdict": summary.get("verdict", ""),
                }
            )
        out.append(row)
    out.sort(key=lambda row: float(row["roi"]) if row["roi"] != "" and math.isfinite(float(row["roi"])) else -999, reverse=True)
    return out


def aggregate_summary(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["candidate_set"]), str(row["selector"]))].append(row)
    out = []
    for (candidate_set, selector), vals in grouped.items():
        rois = [float(v["roi"]) for v in vals if v["roi"] != ""]
        profits = [float(v["total_profit_units"]) for v in vals if v["total_profit_units"] != ""]
        streaks = [float(v["max_ticket_loss_streak"]) for v in vals if v["max_ticket_loss_streak"] != ""]
        hit_rates = [float(v["hit_rate"]) for v in vals if v["hit_rate"] != ""]
        passes = sum(1 for v in vals if v["verdict"] == "pass_watchlist")
        out.append(
            {
                "candidate_set": candidate_set,
                "selector": selector,
                "windows": len(vals),
                "avg_roi": sum(rois) / len(rois) if rois else "",
                "min_roi": min(rois) if rois else "",
                "total_profit_units": sum(profits) if profits else "",
                "avg_hit_rate": sum(hit_rates) / len(hit_rates) if hit_rates else "",
                "avg_max_ticket_loss_streak": sum(streaks) / len(streaks) if streaks else "",
                "pass_windows": passes,
                "avg_skipped_issues": sum(float(v["skipped_issues"]) for v in vals) / len(vals),
                "avg_current_main_issues": sum(float(v["current_main_issues"]) for v in vals) / len(vals),
            }
        )
    out.sort(key=lambda row: (float(row["avg_roi"]) if row["avg_roi"] != "" else -999, float(row["pass_windows"])), reverse=True)
    return out


def run(args: argparse.Namespace) -> None:
    specs = parse_run_specs(args.runs)
    candidate_sets = [x.strip() for x in args.candidate_sets.split(",") if x.strip()]
    profiles = default_profiles()

    all_decisions: list[dict[str, object]] = []
    all_tickets: list[dict[str, object]] = []
    all_profile_rows: list[dict[str, object]] = []
    for spec in specs:
        for candidate_set in candidate_sets:
            decision_rows, ticket_rows, profile_rows = run_selector_for_spec(spec, candidate_set=candidate_set, profiles=profiles)
            all_decisions.extend(decision_rows)
            all_tickets.extend(ticket_rows)
            all_profile_rows.extend(profile_rows)

    summary = selector_summary_rows(all_tickets, all_profile_rows)
    aggregate = aggregate_summary(summary)

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "regime_selector_decisions.csv", all_decisions)
    write_csv(out / "regime_selector_tickets.csv", all_tickets)
    write_csv(out / "regime_selector_summary.csv", summary)
    write_csv(out / "regime_selector_aggregate.csv", aggregate)

    report = [
        "# N=7 regime selector evaluation",
        "",
        f"- Runs: `{args.runs}`",
        f"- Candidate sets: `{args.candidate_sets}`",
        f"- Leakage guard: selector decisions use only prior issue-level realized performance.",
        "",
        "## Aggregate",
        md_table(aggregate[:40]),
        "",
        "## Summary",
        md_table(summary[:80]),
        "",
        "## Files",
        "",
        "- `regime_selector_aggregate.csv`",
        "- `regime_selector_summary.csv`",
        "- `regime_selector_decisions.csv`",
        "- `regime_selector_tickets.csv`",
        "",
    ]
    (out / "regime_selector_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'regime_selector_report.md'}")
    print(f"Wrote {len(all_decisions)} decisions and {len(all_tickets)} ticket rows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_regime_selector"))
    parser.add_argument(
        "--runs",
        default=(
            "t8=results/n7_dynamic_draw_cover_t8,"
            "t12=results/n7_dynamic_draw_cover,"
            "t16=results/n7_dynamic_draw_cover_t16,"
            "t20=results/n7_dynamic_draw_cover_t20"
        ),
    )
    parser.add_argument("--candidate-sets", default="confidence_stable,confidence_k2,confidence_all,all")
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
