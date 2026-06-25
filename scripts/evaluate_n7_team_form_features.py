#!/usr/bin/env python3
"""Evaluate rolling team-form/Poisson features inside the current N=7 model."""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_n7_confidence_coverage import make_depth_weighted_tickets, transform_legs_for_depth
from scripts.evaluate_n7_depth_draw_cover import compact_summary, coverage_snapshot, group_samples_by_issue, issue_profit_rows
from scripts.evaluate_n7_dynamic_draw_cover import dynamic_draw_cover_ticket
from scripts.evaluate_n7_matchpredict_integration import (
    MatchInfo,
    append_prediction_rows,
    handicap_result,
    load_match_info,
    poisson_pmf,
    probability_summary,
)
from scripts.walkforward_beidan_result_model_eval import (
    OUTCOMES,
    build_samples,
    fit_model,
    market_probs,
    predict_proba,
)
from scripts.walkforward_beidan_strategy_eval import (
    break_even_factor,
    build_q_baseline_legs,
    default_db_path,
    group_by_issue as group_action_rows_by_issue,
    load_action_rows,
    md_table,
    settle_ticket,
    summarize_tickets,
    train_q_model,
    write_csv,
)


def parse_strings(raw: str) -> list[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


def safe_rate(hits: float, total: float, prior: float, prior_n: float) -> float:
    return (hits + prior * prior_n) / (total + prior_n) if total > 0 or prior_n > 0 else prior


def raw_result(fthg: int, ftag: int) -> int:
    if fthg > ftag:
        return 0
    if fthg == ftag:
        return 1
    return 2


@dataclass
class RollingTeamForm:
    lookback_matches: int
    prior_matches: float
    max_goals: int
    home_advantage: float
    away_discount: float

    def __post_init__(self) -> None:
        self.by_team_role: dict[tuple[str, str, str], list[tuple[float, float, int]]] = defaultdict(list)
        self.league_role_goals: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
        self.global_role_goals: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
        self.league_role_results: dict[tuple[str, str], Counter[int]] = defaultdict(Counter)
        self.global_role_results: dict[str, Counter[int]] = defaultdict(Counter)

    def update(self, info: MatchInfo) -> None:
        home_result = raw_result(info.fthg, info.ftag)
        away_result = raw_result(info.ftag, info.fthg)
        updates = (
            ("home", info.home, float(info.fthg), float(info.ftag), home_result),
            ("away", info.away, float(info.ftag), float(info.fthg), away_result),
        )
        for role, team, gf, ga, result in updates:
            self.by_team_role[(info.league, team, role)].append((gf, ga, result))
            self.league_role_goals[(info.league, role)][0] += gf
            self.league_role_goals[(info.league, role)][1] += ga
            self.league_role_goals[(info.league, role)][2] += 1.0
            self.global_role_goals[role][0] += gf
            self.global_role_goals[role][1] += ga
            self.global_role_goals[role][2] += 1.0
            self.league_role_results[(info.league, role)][result] += 1
            self.global_role_results[role][result] += 1

    def role_goal_prior(self, league: str, role: str, field: str) -> float:
        idx = 0 if field == "gf" else 1
        vals = self.league_role_goals.get((league, role))
        if vals and vals[2] > 0:
            return vals[idx] / vals[2]
        vals = self.global_role_goals.get(role)
        if vals and vals[2] > 0:
            return vals[idx] / vals[2]
        return 1.25

    def role_result_prior(self, league: str, role: str, result: int) -> float:
        counts = self.league_role_results.get((league, role))
        if counts and sum(counts.values()) > 0:
            total = sum(counts.values())
            return counts[result] / total
        counts = self.global_role_results.get(role)
        if counts and sum(counts.values()) > 0:
            total = sum(counts.values())
            return counts[result] / total
        return 0.28 if result == 1 else 0.36

    def history(self, league: str, team: str, role: str) -> list[tuple[float, float, int]]:
        return self.by_team_role.get((league, team, role), [])[-self.lookback_matches :]

    def team_role_goal_avg(self, league: str, team: str, role: str, field: str) -> float:
        idx = 0 if field == "gf" else 1
        prior = self.role_goal_prior(league, role, field)
        history = self.history(league, team, role)
        if not history:
            return prior
        raw = sum(row[idx] for row in history) / len(history)
        n = float(len(history))
        return (raw * n + prior * self.prior_matches) / (n + self.prior_matches)

    def team_result_rate(self, league: str, team: str, role: str, result: int) -> float:
        history = self.history(league, team, role)
        prior = self.role_result_prior(league, role, result)
        if not history:
            return prior
        return safe_rate(sum(1 for row in history if row[2] == result), float(len(history)), prior, self.prior_matches)

    def team_form_points(self, league: str, team: str, role: str) -> float:
        history = self.history(league, team, role)
        win_prior = self.role_result_prior(league, role, 0)
        draw_prior = self.role_result_prior(league, role, 1)
        prior_points = (3.0 * win_prior + draw_prior) / 3.0
        if not history:
            return prior_points
        points = sum(3.0 if row[2] == 0 else 1.0 if row[2] == 1 else 0.0 for row in history)
        return safe_rate(points / 3.0, float(len(history)), prior_points, self.prior_matches)

    def features_for(self, info: MatchInfo) -> dict[str, float]:
        home_attack = self.team_role_goal_avg(info.league, info.home, "home", "gf")
        home_defense = self.team_role_goal_avg(info.league, info.home, "home", "ga")
        away_attack = self.team_role_goal_avg(info.league, info.away, "away", "gf")
        away_defense = self.team_role_goal_avg(info.league, info.away, "away", "ga")
        xg_home = (0.70 * home_attack + 0.30 * away_defense) * self.home_advantage
        xg_away = (0.70 * away_attack + 0.30 * home_defense) * self.away_discount

        probs = np.zeros(3, dtype=float)
        total_mass = 0.0
        for h, hp in enumerate(poisson_pmf(xg_home, self.max_goals)):
            for a, ap in enumerate(poisson_pmf(xg_away, self.max_goals)):
                mass = hp * ap
                probs[handicap_result(h, a, info.hcp)] += mass
                total_mass += mass
        if total_mass > 0:
            probs /= total_mass
        else:
            probs[:] = 1 / 3

        home_history = self.history(info.league, info.home, "home")
        away_history = self.history(info.league, info.away, "away")
        return {
            "team_home_attack": home_attack,
            "team_home_defense": home_defense,
            "team_away_attack": away_attack,
            "team_away_defense": away_defense,
            "team_xg_home": float(xg_home),
            "team_xg_away": float(xg_away),
            "team_xg_diff": float(xg_home - xg_away),
            "team_abs_xg_diff": float(abs(xg_home - xg_away)),
            "team_xg_total": float(xg_home + xg_away),
            "team_poisson_p3": float(probs[0]),
            "team_poisson_p1": float(probs[1]),
            "team_poisson_p0": float(probs[2]),
            "team_home_draw_rate": self.team_result_rate(info.league, info.home, "home", 1),
            "team_away_draw_rate": self.team_result_rate(info.league, info.away, "away", 1),
            "team_home_form_points": self.team_form_points(info.league, info.home, "home"),
            "team_away_form_points": self.team_form_points(info.league, info.away, "away"),
            "team_home_role_n": float(len(home_history)),
            "team_away_role_n": float(len(away_history)),
        }


def sample_sort_key(sample) -> tuple[str, int, int]:
    return (sample.issue, sample.rows["3"].match_idx, sample.match_id)


def with_extras(samples, extras_by_match: dict[int, dict[str, float]]):
    out = []
    for sample in samples:
        merged = dict(sample.extras)
        merged.update(extras_by_match.get(sample.match_id, {}))
        out.append(replace(sample, extras=merged))
    return out


def team_form_train_test_samples(args, train_samples, test_samples, match_info: dict[int, MatchInfo]):
    builder = RollingTeamForm(
        lookback_matches=args.team_lookback_matches,
        prior_matches=args.team_prior_matches,
        max_goals=args.team_max_goals,
        home_advantage=args.team_home_advantage,
        away_discount=args.team_away_discount,
    )
    train_extras: dict[int, dict[str, float]] = {}
    for sample in sorted(train_samples, key=sample_sort_key):
        info = match_info.get(sample.match_id)
        if info is None:
            continue
        train_extras[sample.match_id] = builder.features_for(info)
        builder.update(info)

    test_extras: dict[int, dict[str, float]] = {}
    for sample in test_samples:
        info = match_info.get(sample.match_id)
        if info is not None:
            test_extras[sample.match_id] = builder.features_for(info)

    return with_extras(train_samples, train_extras), with_extras(test_samples, test_extras)


def fit_predict(train_samples, test_samples, *, feature_set: str, l2: float, maxiter: int) -> np.ndarray:
    model = fit_model(train_samples, l2=l2, maxiter=maxiter, feature_set=feature_set)
    return predict_proba(test_samples, model)


def run(args: argparse.Namespace) -> None:
    action_rows = load_action_rows(args.db, args.min_year)
    samples = build_samples(action_rows, {})
    match_info = load_match_info(args.db, args.min_year)
    action_by_issue = group_action_rows_by_issue(action_rows)
    samples_by_issue = group_samples_by_issue(samples)
    issues = sorted(samples_by_issue)
    sources = parse_strings(args.sources)
    dynamic_policies = parse_strings(args.dynamic_policies)
    threshold = break_even_factor(args.n_legs) + args.min_factor_margin

    ticket_rows: list[dict[str, object]] = []
    prediction_rows: list[dict[str, object]] = []
    coverage_rows: list[dict[str, object]] = []
    window_rows: list[dict[str, object]] = []

    for issue_idx in range(args.train_issues, len(issues)):
        test_issue = issues[issue_idx]
        train_issues = issues[issue_idx - args.train_issues : issue_idx]
        if any(issue >= test_issue for issue in train_issues):
            raise RuntimeError(f"leakage guard failed: train_issues={train_issues}, test_issue={test_issue}")

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
        if len(q_legs) < args.n_legs:
            continue

        team_train_samples, team_test_samples = team_form_train_test_samples(args, train_samples, test_samples, match_info)
        probs_by_source: dict[str, np.ndarray] = {}
        if "current_base" in sources:
            probs_by_source["current_base"] = fit_predict(
                train_samples,
                test_samples,
                feature_set="base",
                l2=args.l2,
                maxiter=args.maxiter,
            )
        if "team_form" in sources:
            probs_by_source["team_form"] = fit_predict(
                team_train_samples,
                team_test_samples,
                feature_set="team",
                l2=args.l2,
                maxiter=args.maxiter,
            )
        if "team_rich" in sources:
            probs_by_source["team_rich"] = fit_predict(
                team_train_samples,
                team_test_samples,
                feature_set="team_rich",
                l2=args.l2,
                maxiter=args.maxiter,
            )

        market = market_probs(test_samples)
        market_by_match = {sample.match_id: market[i] for i, sample in enumerate(test_samples)}
        samples_by_match = {sample.match_id: sample for sample in test_samples}
        action_lookup = {(row.match_id, row.action_code): row for row in test_action_rows}

        for source, probs in probs_by_source.items():
            append_prediction_rows(prediction_rows, test_issue, source, test_samples, probs)
            probs_by_match = {sample.match_id: probs[i] for i, sample in enumerate(test_samples)}
            depth_legs, depth_weights = transform_legs_for_depth(
                q_legs,
                policy=args.depth_policy,
                probs_by_match=probs_by_match,
                market_by_match=market_by_match,
                min_score_factor=threshold,
            )
            strategy = f"confidence_{args.depth_policy}__prob_{source}"
            depth_tickets = make_depth_weighted_tickets(
                depth_legs,
                depth_weights=depth_weights,
                strategy=strategy,
                issue=test_issue,
                n_legs=args.n_legs,
                max_tickets=args.max_tickets_per_issue,
                overlap_penalty=args.overlap_penalty,
                train_start_issue=train_issues[0],
                train_end_issue=train_issues[-1],
                max_leg_uses=args.max_depth_leg_uses if args.depth_policy.startswith("depth_constrained") else 0,
                max_ticket_overlap=args.max_depth_ticket_overlap if args.depth_policy.startswith("depth_constrained") else 0,
            )
            ticket_rows.extend(settle_ticket(t) for t in depth_tickets)
            coverage_rows.append(coverage_snapshot(strategy, test_issue, depth_legs, depth_tickets))
            for dynamic_policy in dynamic_policies:
                tickets = [
                    dynamic_draw_cover_ticket(
                        ticket,
                        strategy_prefix=strategy,
                        dynamic_policy=dynamic_policy,
                        action_lookup=action_lookup,
                        samples_by_match=samples_by_match,
                        model_probs_by_match=probs_by_match,
                        market_probs_by_match=market_by_match,
                        require_positive_draw_edge=args.require_positive_draw_edge,
                    )
                    for ticket in depth_tickets
                ]
                ticket_rows.extend(settle_ticket(t) for t in tickets)

        window_rows.append(
            {
                "test_issue": test_issue,
                "train_start_issue": train_issues[0],
                "train_end_issue": train_issues[-1],
                "leakage_guard": "train_issues_before_test_issue;train_features_roll_forward;test_features_train_only",
                "snapshot": args.snapshot,
                "n_train_matches": len(train_samples),
                "n_test_matches": len(test_samples),
                "n_q_legs": len(q_legs),
                "sources": ",".join(probs_by_source),
            }
        )

    strategy_summary = summarize_tickets(ticket_rows)
    strategy_summary.sort(key=lambda row: float(row["roi"]), reverse=True)
    pred_summary = probability_summary(prediction_rows)
    pred_summary.sort(key=lambda row: float(row["logloss"]))
    issue_rows = issue_profit_rows(ticket_rows)

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "team_form_tickets.csv", ticket_rows)
    write_csv(out / "team_form_strategy_summary.csv", strategy_summary)
    write_csv(out / "team_form_issue_profit.csv", issue_rows)
    write_csv(out / "team_form_coverage.csv", coverage_rows)
    write_csv(out / "team_form_prediction_rows.csv", prediction_rows)
    write_csv(out / "team_form_prediction_summary.csv", pred_summary)
    write_csv(out / "team_form_windows.csv", window_rows)

    report = [
        "# N=7 team-form feature ablation",
        "",
        f"- DB: `{args.db}`",
        f"- Snapshot: `{args.snapshot}`",
        f"- Train issues: `{args.train_issues}`",
        f"- Sources: `{args.sources}`",
        f"- Team lookback/prior: `{args.team_lookback_matches}` / `{args.team_prior_matches}`",
        f"- Depth policy: `{args.depth_policy}`",
        f"- Dynamic policies: `{args.dynamic_policies}`",
        "",
        "## Probability Summary",
        md_table(pred_summary),
        "",
        "## Strategy Summary",
        md_table(compact_summary(strategy_summary)),
        "",
        "## Files",
        "",
        "- `team_form_prediction_summary.csv`",
        "- `team_form_strategy_summary.csv`",
        "- `team_form_tickets.csv`",
        "- `team_form_issue_profit.csv`",
        "- `team_form_coverage.csv`",
        "- `team_form_windows.csv`",
        "",
    ]
    (out / "team_form_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'team_form_report.md'}")
    print(f"Wrote {len(ticket_rows)} ticket rows and {len(prediction_rows)} prediction rows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_team_form_features"))
    parser.add_argument("--min-year", type=int, default=2024)
    parser.add_argument("--train-issues", type=int, default=12)
    parser.add_argument("--min-train-matches", type=int, default=300)
    parser.add_argument("--n-legs", type=int, default=7)
    parser.add_argument("--max-tickets-per-issue", type=int, default=20)
    parser.add_argument("--overlap-penalty", type=float, default=0.25)
    parser.add_argument("--max-depth-leg-uses", type=int, default=8)
    parser.add_argument("--max-depth-ticket-overlap", type=int, default=6)
    parser.add_argument("--baseline-min-proxy-odds", type=float, default=3.0)
    parser.add_argument("--baseline-max-proxy-odds", type=float, default=8.0)
    parser.add_argument("--snapshot", choices=("final", "1h", "10h"), default="final")
    parser.add_argument("--q-prior-n", type=int, default=80)
    parser.add_argument("--min-factor-margin", type=float, default=0.0)
    parser.add_argument("--l2", type=float, default=0.01)
    parser.add_argument("--maxiter", type=int, default=120)
    parser.add_argument("--sources", default="current_base,team_form,team_rich")
    parser.add_argument("--depth-policy", default="depth_constrained_hybrid")
    parser.add_argument("--dynamic-policies", default="model_draw_ratio_t0.55_k2")
    parser.add_argument("--require-positive-draw-edge", action="store_true")
    parser.add_argument("--team-lookback-matches", type=int, default=10)
    parser.add_argument("--team-prior-matches", type=float, default=4.0)
    parser.add_argument("--team-max-goals", type=int, default=8)
    parser.add_argument("--team-home-advantage", type=float, default=1.10)
    parser.add_argument("--team-away-discount", type=float, default=0.90)
    args = parser.parse_args()
    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")
    run(args)


if __name__ == "__main__":
    main()
