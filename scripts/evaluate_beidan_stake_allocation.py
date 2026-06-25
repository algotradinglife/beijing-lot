#!/usr/bin/env python3
"""Backtest single-match stake allocation from result probabilities.

The purpose is to test whether capital should follow the predicted 3/1/0
probability distribution, or whether it should follow odds-adjusted edge. This
is a single-match accounting layer; it does not model N-leg parlay covariance.
"""
from __future__ import annotations

import argparse
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

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
    default_db_path,
    load_action_rows,
    md_table,
    write_csv,
)


def parse_csv_floats(raw: str) -> list[float]:
    return [float(x) for x in raw.split(",") if x.strip()]


def group_samples_by_issue(samples):
    out = defaultdict(list)
    for sample in samples:
        out[sample.issue].append(sample)
    return dict(out)


def positive_kelly_fraction(p: float, gross_return: float) -> float:
    if gross_return <= 1.0:
        return 0.0
    edge = p * gross_return - 1.0
    if edge <= 0:
        return 0.0
    return edge / (gross_return - 1.0)


def normalized(values: np.ndarray) -> np.ndarray:
    total = float(values.sum())
    if total <= 0 or not math.isfinite(total):
        return np.zeros_like(values)
    return values / total


def stake_vector(
    strategy: str,
    probs: np.ndarray,
    proxy_gross: np.ndarray,
    *,
    kelly_fraction: float,
    max_match_stake: float,
) -> np.ndarray:
    if strategy == "flat_all":
        return np.ones(3, dtype=float) / 3.0
    if strategy == "prob_all":
        return normalized(probs)
    if strategy == "top_prob":
        stakes = np.zeros(3, dtype=float)
        stakes[int(np.argmax(probs))] = 1.0
        return stakes

    edge = probs * proxy_gross - 1.0
    edge_pos = np.maximum(edge, 0.0)
    if strategy == "ev_prop_budget":
        return normalized(edge_pos)
    if strategy == "top_ev":
        stakes = np.zeros(3, dtype=float)
        if float(edge_pos.max()) > 0:
            stakes[int(np.argmax(edge_pos))] = 1.0
        return stakes

    kelly = np.asarray(
        [positive_kelly_fraction(float(p), float(g)) for p, g in zip(probs, proxy_gross)],
        dtype=float,
    )
    if strategy == "kelly_norm_budget":
        return normalized(kelly)
    if strategy == "kelly_fractional":
        stakes = kelly_fraction * kelly
        total = float(stakes.sum())
        if total > max_match_stake > 0:
            stakes *= max_match_stake / total
        return stakes

    raise ValueError(f"unsupported allocation strategy: {strategy}")


def settle_sample(sample, probs: np.ndarray, strategy: str, *, kelly_fraction: float, max_match_stake: float) -> dict[str, object]:
    raise RuntimeError("settle_sample requires draw_tilt; use settle_sample_with_tilt")


def settle_sample_with_tilt(
    sample,
    probs: np.ndarray,
    strategy: str,
    *,
    draw_tilt: float,
    kelly_fraction: float,
    max_match_stake: float,
) -> dict[str, object]:
    raw_probs = np.asarray(probs, dtype=float)
    probs = raw_probs.copy()
    probs[1] *= draw_tilt
    probs = normalized(probs)
    proxy_gross = np.asarray([RETURN_RATE * float(sample.rows[code].euro_final_odds) for code in OUTCOMES], dtype=float)
    stakes = stake_vector(
        strategy,
        probs,
        proxy_gross,
        kelly_fraction=kelly_fraction,
        max_match_stake=max_match_stake,
    )
    actual_idx = int(sample.y)
    actual_code = OUTCOMES[actual_idx]
    stake = float(stakes.sum())
    actual_stake = float(stakes[actual_idx])
    official_gross = RETURN_RATE * float(sample.rows[actual_code].winning_sp)
    proxy_payout = actual_stake * float(proxy_gross[actual_idx])
    official_payout = actual_stake * official_gross
    n_outcomes_bet = int(sum(1 for x in stakes if x > 1e-12))
    edge = probs * proxy_gross - 1.0
    strategy_name = f"{strategy}_drawtilt{draw_tilt:g}"
    return {
        "strategy": strategy_name,
        "allocation_strategy": strategy,
        "draw_tilt": draw_tilt,
        "issue": sample.issue,
        "match_id": sample.match_id,
        "match_idx": sample.rows["3"].match_idx,
        "league": sample.rows["3"].league,
        "hcp": sample.rows["3"].hcp,
        "actual": actual_code,
        "stake_units": stake,
        "actual_stake_units": actual_stake,
        "actual_stake_share": actual_stake / stake if stake > 0 else "",
        "n_outcomes_bet": n_outcomes_bet,
        "raw_p_3": float(raw_probs[0]),
        "raw_p_1": float(raw_probs[1]),
        "raw_p_0": float(raw_probs[2]),
        "p_3": float(probs[0]),
        "p_1": float(probs[1]),
        "p_0": float(probs[2]),
        "proxy_gross_3": float(proxy_gross[0]),
        "proxy_gross_1": float(proxy_gross[1]),
        "proxy_gross_0": float(proxy_gross[2]),
        "edge_3": float(edge[0]),
        "edge_1": float(edge[1]),
        "edge_0": float(edge[2]),
        "stake_3": float(stakes[0]),
        "stake_1": float(stakes[1]),
        "stake_0": float(stakes[2]),
        "official_gross_actual": official_gross,
        "proxy_payout_units": proxy_payout,
        "official_payout_units": official_payout,
        "proxy_profit_units": proxy_payout - stake,
        "official_profit_units": official_payout - stake,
        "hit_any_stake": int(actual_stake > 1e-12),
    }


def summarize(rows: list[dict[str, object]], profit_key: str) -> list[dict[str, object]]:
    by_strategy = defaultdict(list)
    for row in rows:
        by_strategy[str(row["strategy"])].append(row)

    out = []
    for strategy, rs in sorted(by_strategy.items()):
        n_matches = len(rs)
        bet_rows = [r for r in rs if float(r["stake_units"]) > 0]
        stake = sum(float(r["stake_units"]) for r in rs)
        profit = sum(float(r[profit_key]) for r in rs)
        payout_key = profit_key.replace("profit", "payout")
        payout = sum(float(r[payout_key]) for r in rs)
        by_issue = defaultdict(lambda: [0.0, 0.0])
        equity = 10_000.0
        peak = equity
        max_dd = 0.0
        for r in sorted(rs, key=lambda x: (str(x["issue"]), int(x["match_idx"]), int(x["match_id"]))):
            by_issue[str(r["issue"])][0] += float(r["stake_units"])
            by_issue[str(r["issue"])][1] += float(r[profit_key])
            equity += float(r[profit_key])
            peak = max(peak, equity)
            if peak > 0:
                max_dd = min(max_dd, (equity - peak) / peak)
        issue_profits = [v[1] for v in by_issue.values()]
        best_issue_profit = max(issue_profits) if issue_profits else 0.0
        avg_actual_stake_share = [
            float(r["actual_stake_share"]) for r in bet_rows if r["actual_stake_share"] != ""
        ]
        n_outcomes = [int(r["n_outcomes_bet"]) for r in bet_rows]
        out.append(
            {
                "strategy": strategy,
                "settlement": profit_key.replace("_profit_units", ""),
                "n_matches": n_matches,
                "n_bet_matches": len(bet_rows),
                "coverage": len(bet_rows) / n_matches if n_matches else float("nan"),
                "hit_any_stake_rate": sum(int(r["hit_any_stake"]) for r in bet_rows) / len(bet_rows) if bet_rows else float("nan"),
                "avg_actual_stake_share": sum(avg_actual_stake_share) / len(avg_actual_stake_share) if avg_actual_stake_share else float("nan"),
                "avg_outcomes_bet": sum(n_outcomes) / len(n_outcomes) if n_outcomes else float("nan"),
                "total_stake_units": stake,
                "total_payout_units": payout,
                "total_profit_units": profit,
                "roi": profit / stake if stake > 0 else float("nan"),
                "profit_per_match": profit / n_matches if n_matches else float("nan"),
                "profitable_issues": sum(1 for p in issue_profits if p > 0),
                "best_issue_profit_units": best_issue_profit,
                "best_issue_profit_share": best_issue_profit / profit if profit > 0 and best_issue_profit > 0 else "",
                "max_drawdown_pct_on_10000": max_dd,
            }
        )
    return out


def run(args: argparse.Namespace) -> None:
    action_rows = load_action_rows(args.db, args.min_year)
    extras = load_match_extras(args.db, args.min_year)
    samples = build_samples(action_rows, extras)
    by_issue = group_samples_by_issue(samples)
    issues = sorted(by_issue)
    if len(issues) <= args.train_issues:
        raise SystemExit("not enough issues for train window")

    strategies = [x.strip() for x in args.strategies.split(",") if x.strip()]
    draw_tilts = parse_csv_floats(args.draw_tilts)
    allocation_rows: list[dict[str, object]] = []
    window_rows: list[dict[str, object]] = []

    for issue_idx in range(args.train_issues, len(issues)):
        test_issue = issues[issue_idx]
        train_issues = issues[issue_idx - args.train_issues:issue_idx]
        train_samples = [s for issue in train_issues for s in by_issue[issue]]
        test_samples = by_issue[test_issue]
        if len(train_samples) < args.min_train_matches:
            continue

        model = fit_model(train_samples, l2=args.l2, maxiter=args.maxiter, feature_set=args.feature_set)
        probs = predict_proba(test_samples, model)
        market = market_probs(test_samples)
        if args.blend_market_weight:
            probs = (1.0 - args.blend_market_weight) * probs + args.blend_market_weight * market
            probs = probs / probs.sum(axis=1, keepdims=True)
        _, y_test = feature_tensor(test_samples, model.ctx, model.feature_set)
        window_rows.append(
            {
                "test_issue": test_issue,
                "train_start_issue": train_issues[0],
                "train_end_issue": train_issues[-1],
                "n_train_matches": len(train_samples),
                "n_test_matches": len(test_samples),
                "model_logloss": logloss(probs, y_test),
            }
        )
        for sample, p_row in zip(test_samples, probs):
            for draw_tilt in draw_tilts:
                for strategy in strategies:
                    allocation_rows.append(
                        settle_sample_with_tilt(
                            sample,
                            p_row,
                            strategy,
                            draw_tilt=draw_tilt,
                            kelly_fraction=args.kelly_fraction,
                            max_match_stake=args.max_match_stake,
                        )
                    )

    official_summary = summarize(allocation_rows, "official_profit_units")
    proxy_summary = summarize(allocation_rows, "proxy_profit_units")

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "allocation_rows.csv", allocation_rows)
    write_csv(out / "allocation_summary_official.csv", official_summary)
    write_csv(out / "allocation_summary_proxy.csv", proxy_summary)
    write_csv(out / "window_metrics.csv", window_rows)

    report = [
        "# Beidan single-match stake allocation",
        "",
        f"- DB: `{args.db}`",
        f"- Train issues: `{args.train_issues}`",
        f"- Feature set: `{args.feature_set}`",
        f"- L2: `{args.l2}`",
        f"- Blend market weight: `{args.blend_market_weight}`",
        f"- Draw tilts: `{args.draw_tilts}`",
        f"- Kelly fraction: `{args.kelly_fraction}`",
        f"- Max match stake: `{args.max_match_stake}`",
        "",
        "## Official Winning SP Settlement",
        md_table(official_summary),
        "## Proxy Odds Settlement",
        md_table(proxy_summary),
        "",
        "## Files",
        "",
        "- `allocation_summary_official.csv`",
        "- `allocation_summary_proxy.csv`",
        "- `allocation_rows.csv`",
        "- `window_metrics.csv`",
        "",
    ]
    (out / "allocation_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'allocation_report.md'}")
    print(f"Wrote {len(allocation_rows)} allocation rows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--output-dir", type=Path, default=Path("results/beidan_stake_allocation"))
    parser.add_argument("--min-year", type=int, default=2024)
    parser.add_argument("--train-issues", type=int, default=12)
    parser.add_argument("--min-train-matches", type=int, default=300)
    parser.add_argument("--feature-set", choices=("base", "kelly", "priors", "extras", "rich"), default="base")
    parser.add_argument("--l2", type=float, default=0.01)
    parser.add_argument("--blend-market-weight", type=float, default=0.0)
    parser.add_argument("--draw-tilts", default="1.0")
    parser.add_argument("--maxiter", type=int, default=120)
    parser.add_argument("--kelly-fraction", type=float, default=0.25)
    parser.add_argument("--max-match-stake", type=float, default=1.0)
    parser.add_argument(
        "--strategies",
        default="flat_all,prob_all,top_prob,ev_prop_budget,top_ev,kelly_norm_budget,kelly_fractional",
    )
    args = parser.parse_args()
    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")
    run(args)


if __name__ == "__main__":
    main()
