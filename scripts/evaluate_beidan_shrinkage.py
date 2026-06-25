#!/usr/bin/env python3
"""Evaluate probability-based N=7 combo shrinkage for Beidan tickets.

The experiment starts from the same rolling q-baseline N=7 ticket groups used
by the existing walk-forward evaluator. For each ticket group it allocates
1/2/3 options per match from predicted result probabilities, expands the base
cartesian product, then keeps only combinations whose total 3/1/0 counts are
close to the group's predicted count vector.
"""
from __future__ import annotations

import argparse
import itertools
import math
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import mean

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.walkforward_beidan_result_model_eval import (
    OUTCOMES,
    build_samples,
    feature_tensor,
    fit_model,
    load_match_extras,
    logloss,
    market_probs,
    predict_proba,
)
from scripts.walkforward_beidan_strategy_eval import (
    RETURN_RATE,
    break_even_factor,
    build_q_baseline_legs,
    default_db_path,
    full_cover_lookup,
    group_by_issue as group_action_rows_by_issue,
    load_action_rows,
    make_tickets,
    md_table,
    settle_ticket,
    summarize_tickets,
    train_q_model,
    write_csv,
)


@dataclass(frozen=True)
class ShrinkConfig:
    name: str
    mode: str
    coverage_threshold: float
    top_k: int
    count_tolerance: int
    count_target_ratio: float = 0.0


def parse_floats(raw: str) -> list[float]:
    return [float(x) for x in raw.split(",") if x.strip()]


def parse_ints(raw: str) -> list[int]:
    return [int(x) for x in raw.split(",") if x.strip()]


def group_samples_by_issue(samples):
    out = defaultdict(list)
    for sample in samples:
        out[sample.issue].append(sample)
    return dict(out)


def option_codes(probs: np.ndarray, config: ShrinkConfig) -> tuple[str, ...]:
    ranked = sorted(range(len(OUTCOMES)), key=lambda i: float(probs[i]), reverse=True)
    if config.mode == "topk":
        keep = ranked[: max(1, min(config.top_k, len(OUTCOMES)))]
    elif config.mode == "cum":
        keep = []
        total = 0.0
        for idx in ranked:
            keep.append(idx)
            total += float(probs[idx])
            if total >= config.coverage_threshold or len(keep) >= len(OUTCOMES):
                break
    else:
        raise ValueError(f"unsupported option mode: {config.mode}")
    return tuple(OUTCOMES[i] for i in keep)


def rounded_expected_counts(prob_rows: list[np.ndarray]) -> dict[str, int]:
    expected = np.sum(np.asarray(prob_rows, dtype=float), axis=0)
    floors = np.floor(expected).astype(int)
    remainder = int(len(prob_rows) - floors.sum())
    order = sorted(range(len(OUTCOMES)), key=lambda i: float(expected[i] - floors[i]), reverse=True)
    centers = floors.copy()
    for idx in order[:remainder]:
        centers[idx] += 1
    return {code: int(centers[i]) for i, code in enumerate(OUTCOMES)}


def count_bounds(prob_rows: list[np.ndarray], tolerance: int) -> dict[str, tuple[int, int]]:
    centers = rounded_expected_counts(prob_rows)
    n_legs = len(prob_rows)
    return {
        code: (max(0, center - tolerance), min(n_legs, center + tolerance))
        for code, center in centers.items()
    }


def count_tuple(combo: tuple[str, ...]) -> tuple[int, int, int]:
    counts = Counter(combo)
    return tuple(counts.get(code, 0) for code in OUTCOMES)


def combo_probability(combo: tuple[str, ...], prob_rows: list[np.ndarray]) -> float:
    prob = 1.0
    outcome_index = {code: i for i, code in enumerate(OUTCOMES)}
    for i, code in enumerate(combo):
        prob *= float(prob_rows[i][outcome_index[code]])
    return prob


def within_bounds(combo: tuple[str, ...], bounds: dict[str, tuple[int, int]]) -> bool:
    counts = Counter(combo)
    for code in OUTCOMES:
        lo, hi = bounds[code]
        if counts.get(code, 0) < lo or counts.get(code, 0) > hi:
            return False
    return True


def option_shape(options: list[tuple[str, ...]]) -> str:
    return "x".join(str(len(x)) for x in options)


def outcome_counts_label(combo: tuple[str, ...]) -> str:
    counts = Counter(combo)
    return ",".join(f"{code}:{counts.get(code, 0)}" for code in OUTCOMES)


def bounds_label(bounds: dict[str, tuple[int, int]]) -> str:
    return ",".join(f"{code}:{bounds[code][0]}-{bounds[code][1]}" for code in OUTCOMES)


def evaluate_group(ticket, samples_by_match, probs_by_match, config: ShrinkConfig) -> dict[str, object] | None:
    samples = []
    prob_rows = []
    for leg in ticket.legs:
        sample = samples_by_match.get(leg.row.match_id)
        probs = probs_by_match.get(leg.row.match_id)
        if sample is None or probs is None:
            return None
        samples.append(sample)
        prob_rows.append(np.asarray(probs, dtype=float))

    options = [option_codes(probs, config) for probs in prob_rows]
    base_count = math.prod(len(x) for x in options)
    kept_count = 0
    actual_combo = tuple(sample.rows["3"].result_code for sample in samples)
    actual_in_base = all(actual_combo[i] in options[i] for i in range(len(options)))
    actual_kept = False
    if config.count_tolerance >= 0:
        bounds = count_bounds(prob_rows, config.count_tolerance)
        count_filter_label = bounds_label(bounds)
        for combo in itertools.product(*options):
            if within_bounds(combo, bounds):
                kept_count += 1
                if combo == actual_combo:
                    actual_kept = True
    else:
        bucket_stats: dict[tuple[int, int, int], dict[str, float]] = defaultdict(lambda: {"n": 0.0, "mass": 0.0})
        for combo in itertools.product(*options):
            key = count_tuple(combo)
            bucket_stats[key]["n"] += 1.0
            bucket_stats[key]["mass"] += combo_probability(combo, prob_rows)
        cap = max(1, int(math.floor(base_count * config.count_target_ratio)))
        ranked_buckets = sorted(
            bucket_stats.items(),
            key=lambda item: (
                item[1]["mass"] / item[1]["n"] if item[1]["n"] else 0.0,
                item[1]["mass"],
            ),
            reverse=True,
        )
        kept_buckets: set[tuple[int, int, int]] = set()
        for key, stats in ranked_buckets:
            bucket_n = int(stats["n"])
            if kept_count + bucket_n <= cap or kept_count == 0:
                kept_buckets.add(key)
                kept_count += bucket_n
        actual_kept = actual_in_base and count_tuple(actual_combo) in kept_buckets
        count_filter_label = f"target_ratio={config.count_target_ratio:g};count_buckets={len(kept_buckets)}"

    sp_product = 1.0
    for sample in samples:
        actual_code = sample.rows["3"].result_code
        sp_product *= sample.rows[actual_code].winning_sp

    base_payout = RETURN_RATE * sp_product if actual_in_base else 0.0
    shrink_payout = RETURN_RATE * sp_product if actual_kept else 0.0
    base_profit = base_payout - base_count
    shrink_profit = shrink_payout - kept_count

    return {
        "config": config.name,
        "mode": config.mode,
        "coverage_threshold": config.coverage_threshold,
        "top_k": config.top_k,
        "count_tolerance": config.count_tolerance,
        "count_target_ratio": config.count_target_ratio,
        "issue": ticket.issue,
        "ticket_idx": ticket.ticket_idx,
        "base_count": base_count,
        "kept_count": kept_count,
        "shrink_ratio": kept_count / base_count if base_count else 0.0,
        "base_hit": int(actual_in_base),
        "shrink_hit": int(actual_kept),
        "base_payout_units": base_payout,
        "shrink_payout_units": shrink_payout,
        "base_profit_units": base_profit,
        "shrink_profit_units": shrink_profit,
        "option_shape": option_shape(options),
        "count_bounds": count_filter_label,
        "actual_counts": outcome_counts_label(actual_combo),
        "sp_product": sp_product,
        "legs": ";".join(f"{leg.row.match_id}:{leg.row.action_code}@{leg.row.hcp:g}" for leg in ticket.legs),
    }


def issue_profit_stats(rows: list[dict[str, object]], profit_key: str) -> tuple[float, int, float]:
    by_issue = defaultdict(float)
    for row in rows:
        by_issue[str(row["issue"])] += float(row[profit_key])
    if not by_issue:
        return 0.0, 0, 0.0
    profitable_issues = sum(1 for value in by_issue.values() if value > 0)
    best_issue_profit = max(by_issue.values())
    return best_issue_profit, profitable_issues, len(by_issue)


def summarize_config(rows: list[dict[str, object]], q_summary: dict[str, object]) -> dict[str, object]:
    first = rows[0]
    base_stake = sum(float(r["base_count"]) for r in rows)
    shrink_stake = sum(float(r["kept_count"]) for r in rows)
    base_profit = sum(float(r["base_profit_units"]) for r in rows)
    shrink_profit = sum(float(r["shrink_profit_units"]) for r in rows)
    base_hits = sum(int(r["base_hit"]) for r in rows)
    shrink_hits = sum(int(r["shrink_hit"]) for r in rows)
    zero_kept_groups = sum(1 for r in rows if int(r["kept_count"]) == 0)
    active_groups = len(rows) - zero_kept_groups
    base_best, base_profitable_issues, n_issues = issue_profit_stats(rows, "base_profit_units")
    shrink_best, shrink_profitable_issues, _ = issue_profit_stats(rows, "shrink_profit_units")
    shrink_roi = shrink_profit / shrink_stake if shrink_stake else float("nan")
    base_roi = base_profit / base_stake if base_stake else float("nan")
    return {
        "config": first["config"],
        "mode": first["mode"],
        "coverage_threshold": first["coverage_threshold"],
        "top_k": first["top_k"],
        "count_tolerance": first["count_tolerance"],
        "count_target_ratio": first.get("count_target_ratio", 0.0),
        "n_groups": len(rows),
        "active_groups": active_groups,
        "zero_kept_groups": zero_kept_groups,
        "n_issues": n_issues,
        "avg_base_count": mean(float(r["base_count"]) for r in rows),
        "avg_kept_count": mean(float(r["kept_count"]) for r in rows),
        "stake_shrink_ratio": shrink_stake / base_stake if base_stake else float("nan"),
        "avg_group_shrink_ratio": mean(float(r["shrink_ratio"]) for r in rows),
        "base_hit_rate": base_hits / len(rows) if rows else float("nan"),
        "shrink_hit_rate": shrink_hits / len(rows) if rows else float("nan"),
        "active_shrink_hit_rate": shrink_hits / active_groups if active_groups else float("nan"),
        "hit_retention": shrink_hits / base_hits if base_hits else float("nan"),
        "base_stake_units": base_stake,
        "shrink_stake_units": shrink_stake,
        "base_profit_units": base_profit,
        "shrink_profit_units": shrink_profit,
        "base_roi": base_roi,
        "shrink_roi": shrink_roi,
        "base_profitable_issues": base_profitable_issues,
        "shrink_profitable_issues": shrink_profitable_issues,
        "base_best_issue_share": base_best / base_profit if base_profit > 0 and base_best > 0 else "",
        "shrink_best_issue_share": shrink_best / shrink_profit if shrink_profit > 0 and shrink_best > 0 else "",
        "q_ticket_roi": q_summary.get("roi", ""),
        "q_ticket_profit_units": q_summary.get("total_profit_units", ""),
        "q_ticket_stake_units": q_summary.get("total_stake_units", ""),
    }


def build_configs(args: argparse.Namespace) -> list[ShrinkConfig]:
    configs: list[ShrinkConfig] = []
    tolerances = parse_ints(args.count_tolerances)
    if "topk" in args.modes.split(","):
        for top_k in parse_ints(args.top_k_values):
            for tol in tolerances:
                configs.append(
                    ShrinkConfig(
                        name=f"top{top_k}_tol{tol}",
                        mode="topk",
                        coverage_threshold=0.0,
                        top_k=top_k,
                        count_tolerance=tol,
                    )
                )
            if args.include_target_count_filter:
                configs.append(
                    ShrinkConfig(
                        name=f"top{top_k}_target{args.target_shrink_ratio:g}",
                        mode="topk",
                        coverage_threshold=0.0,
                        top_k=top_k,
                        count_tolerance=-1,
                        count_target_ratio=args.target_shrink_ratio,
                    )
                )
    if "cum" in args.modes.split(","):
        for threshold in parse_floats(args.coverage_thresholds):
            for tol in tolerances:
                configs.append(
                    ShrinkConfig(
                        name=f"cum{threshold:g}_tol{tol}",
                        mode="cum",
                        coverage_threshold=threshold,
                        top_k=0,
                        count_tolerance=tol,
                    )
                )
            if args.include_target_count_filter:
                configs.append(
                    ShrinkConfig(
                        name=f"cum{threshold:g}_target{args.target_shrink_ratio:g}",
                        mode="cum",
                        coverage_threshold=threshold,
                        top_k=0,
                        count_tolerance=-1,
                        count_target_ratio=args.target_shrink_ratio,
                    )
                )
    return configs


def compact_q_summary(q_rows: list[dict[str, object]]) -> dict[str, object]:
    summary = summarize_tickets(q_rows)
    for row in summary:
        if row.get("strategy") == "baseline_q_high_sp" and int(row.get("n_legs", 0)) == 7:
            return row
    return {}


def run(args: argparse.Namespace) -> None:
    action_rows = load_action_rows(args.db, args.min_year)
    extras = load_match_extras(args.db, args.min_year)
    samples = build_samples(action_rows, extras)
    action_by_issue = group_action_rows_by_issue(action_rows)
    samples_by_issue = group_samples_by_issue(samples)
    issues = sorted(samples_by_issue)
    configs = build_configs(args)
    if not configs:
        raise SystemExit("no shrink configs selected")
    if len(issues) <= args.train_issues:
        raise SystemExit("not enough issues for train window")

    threshold = break_even_factor(args.n_legs) + args.min_factor_margin
    q_ticket_rows: list[dict[str, object]] = []
    group_rows: list[dict[str, object]] = []
    prediction_rows: list[dict[str, object]] = []
    window_rows: list[dict[str, object]] = []
    skipped_groups = 0

    for issue_idx in range(args.train_issues, len(issues)):
        test_issue = issues[issue_idx]
        train_issues = issues[issue_idx - args.train_issues:issue_idx]
        train_action_rows = [row for issue in train_issues for row in action_by_issue.get(issue, [])]
        test_action_rows = action_by_issue.get(test_issue, [])
        train_samples = [sample for issue in train_issues for sample in samples_by_issue.get(issue, [])]
        test_samples = samples_by_issue.get(test_issue, [])
        if len(train_samples) < args.min_train_matches or not test_samples:
            continue

        q_model, global_q = train_q_model(train_action_rows, snapshot=args.snapshot, prior_n=args.q_prior_n)
        q_legs = build_q_baseline_legs(
            test_action_rows,
            q_model,
            global_q,
            snapshot=args.snapshot,
            min_proxy_odds=args.baseline_min_proxy_odds,
            max_proxy_odds=args.baseline_max_proxy_odds,
            min_score_factor=threshold,
        )
        tickets = make_tickets(
            q_legs,
            strategy="baseline_q_high_sp",
            issue=test_issue,
            n_legs=args.n_legs,
            max_tickets=args.max_tickets_per_issue,
            overlap_penalty=args.overlap_penalty,
            train_start_issue=train_issues[0],
            train_end_issue=train_issues[-1],
            full_rows=full_cover_lookup(test_action_rows),
            action_model={},
            protect_full_count=0,
        )
        q_ticket_rows.extend(settle_ticket(ticket) for ticket in tickets)
        if not tickets:
            continue

        model = fit_model(train_samples, l2=args.l2, maxiter=args.maxiter)
        probs = predict_proba(test_samples, model)
        market = market_probs(test_samples)
        _, y_test = feature_tensor(test_samples, model.ctx)
        prediction_rows.append(
            {
                "test_issue": test_issue,
                "train_start_issue": train_issues[0],
                "train_end_issue": train_issues[-1],
                "n_train_matches": len(train_samples),
                "n_test_matches": len(test_samples),
                "model_logloss": logloss(probs, y_test),
                "market_logloss": logloss(market, y_test),
            }
        )
        samples_by_match = {sample.match_id: sample for sample in test_samples}
        probs_by_match = {sample.match_id: probs[i] for i, sample in enumerate(test_samples)}
        for ticket in tickets:
            for config in configs:
                row = evaluate_group(ticket, samples_by_match, probs_by_match, config)
                if row is None:
                    skipped_groups += 1
                    continue
                group_rows.append(row)

        window_rows.append(
            {
                "test_issue": test_issue,
                "train_start_issue": train_issues[0],
                "train_end_issue": train_issues[-1],
                "n_q_candidate_legs": len(q_legs),
                "n_q_tickets": len(tickets),
                "global_q": global_q,
                "threshold_factor": threshold,
            }
        )

    q_summary = compact_q_summary(q_ticket_rows)
    by_config: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in group_rows:
        by_config[str(row["config"])].append(row)
    summary_rows = [summarize_config(rows, q_summary) for _, rows in sorted(by_config.items()) if rows]
    summary_rows.sort(
        key=lambda r: (
            abs(float(r["stake_shrink_ratio"]) - args.target_shrink_ratio),
            -float(r["hit_retention"]) if math.isfinite(float(r["hit_retention"])) else 0.0,
            -float(r["shrink_roi"]) if math.isfinite(float(r["shrink_roi"])) else 0.0,
        )
    )

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "shrinkage_group_rows.csv", group_rows)
    write_csv(out / "shrinkage_summary.csv", summary_rows)
    write_csv(out / "q_baseline_tickets.csv", q_ticket_rows)
    write_csv(out / "prediction_windows.csv", prediction_rows)
    write_csv(out / "walkforward_windows.csv", window_rows)

    report = [
        "# Beidan N=7 combo shrinkage evaluation",
        "",
        f"- DB: `{args.db}`",
        f"- Train issues: `{args.train_issues}`",
        f"- N legs: `{args.n_legs}`",
        f"- Max q ticket groups per issue: `{args.max_tickets_per_issue}`",
        f"- Proxy odds band: `{args.baseline_min_proxy_odds}` to `{args.baseline_max_proxy_odds}`",
        f"- Result model L2: `{args.l2}`",
        f"- Target stake shrink ratio: `{args.target_shrink_ratio}`",
        f"- Skipped group/config rows: `{skipped_groups}`",
        "",
        "## Q Baseline",
        md_table([q_summary] if q_summary else []),
        "## Shrinkage Summary",
        md_table(summary_rows),
        "## Prediction Windows",
        md_table(prediction_rows[:40]),
        "",
        "## Files",
        "",
        "- `shrinkage_summary.csv`",
        "- `shrinkage_group_rows.csv`",
        "- `q_baseline_tickets.csv`",
        "- `prediction_windows.csv`",
        "- `walkforward_windows.csv`",
        "",
    ]
    (out / "shrinkage_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'shrinkage_report.md'}")
    print(f"Wrote {len(group_rows)} group/config rows, {len(q_ticket_rows)} q ticket rows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--output-dir", type=Path, default=Path("results/beidan_shrinkage_n7"))
    parser.add_argument("--min-year", type=int, default=2024)
    parser.add_argument("--train-issues", type=int, default=12)
    parser.add_argument("--n-legs", type=int, default=7)
    parser.add_argument("--max-tickets-per-issue", type=int, default=20)
    parser.add_argument("--overlap-penalty", type=float, default=0.25)
    parser.add_argument("--baseline-min-proxy-odds", type=float, default=3.0)
    parser.add_argument("--baseline-max-proxy-odds", type=float, default=8.0)
    parser.add_argument("--snapshot", choices=("final", "1h", "10h"), default="final")
    parser.add_argument("--q-prior-n", type=int, default=80)
    parser.add_argument("--min-factor-margin", type=float, default=0.0)
    parser.add_argument("--l2", type=float, default=0.03)
    parser.add_argument("--maxiter", type=int, default=120)
    parser.add_argument("--min-train-matches", type=int, default=300)
    parser.add_argument("--modes", default="topk,cum")
    parser.add_argument("--top-k-values", default="2")
    parser.add_argument("--coverage-thresholds", default="0.7,0.8,0.9")
    parser.add_argument("--count-tolerances", default="0,1,2")
    parser.add_argument("--target-shrink-ratio", type=float, default=0.2)
    parser.add_argument("--include-target-count-filter", action="store_true")
    args = parser.parse_args()
    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")
    run(args)


if __name__ == "__main__":
    main()
