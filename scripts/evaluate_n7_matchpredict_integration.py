#!/usr/bin/env python3
"""Evaluate MatchPredict-style probabilities integrated with the current N=7 strategy."""
from __future__ import annotations

import argparse
import math
import sqlite3
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_n7_confidence_coverage import (
    make_depth_weighted_tickets,
    model_probabilities,
    transform_legs_for_depth,
)
from scripts.evaluate_n7_depth_draw_cover import compact_summary, coverage_snapshot, group_samples_by_issue, issue_profit_rows
from scripts.evaluate_n7_dynamic_draw_cover import dynamic_draw_cover_ticket
from scripts.walkforward_beidan_result_model_eval import OUTCOMES, build_samples, load_match_extras, market_probs
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


DRAW_INDEX = OUTCOMES.index("1")


@dataclass(frozen=True)
class MatchInfo:
    match_id: int
    issue: str
    match_idx: int
    league: str
    home: str
    away: str
    fthg: int
    ftag: int
    hcp: float


def parse_strings(raw: str) -> list[str]:
    return [x.strip() for x in raw.split(",") if x.strip()]


def normalize_probs(probs: np.ndarray) -> np.ndarray:
    probs = np.clip(np.asarray(probs, dtype=float), 1e-9, 1.0)
    return probs / probs.sum(axis=1, keepdims=True)


def load_match_info(db_path: Path, min_year: int) -> dict[int, MatchInfo]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT match_id, issue, match_idx, league, home, away, fthg, ftag, handicap_line_norm
        FROM match_features
        WHERE has_winning_sp=1
          AND season_year>=?
          AND fthg IS NOT NULL
          AND ftag IS NOT NULL
          AND home IS NOT NULL
          AND away IS NOT NULL
          AND handicap_line_norm IS NOT NULL
        """,
        (min_year,),
    )
    out: dict[int, MatchInfo] = {}
    for row in rows:
        out[int(row["match_id"])] = MatchInfo(
            match_id=int(row["match_id"]),
            issue=str(row["issue"]),
            match_idx=int(row["match_idx"]),
            league=str(row["league"] or ""),
            home=str(row["home"]),
            away=str(row["away"]),
            fthg=int(row["fthg"]),
            ftag=int(row["ftag"]),
            hcp=float(row["handicap_line_norm"]),
        )
    conn.close()
    return out


def raw_result(fthg: int, ftag: int) -> int:
    if fthg > ftag:
        return 0
    if fthg == ftag:
        return 1
    return 2


def handicap_result(home_goals: int, away_goals: int, hcp: float) -> int:
    diff = home_goals + hcp - away_goals
    if diff > 0:
        return 0
    if diff == 0:
        return 1
    return 2


def poisson_pmf(lam: float, max_goals: int) -> list[float]:
    lam = max(0.05, min(5.50, float(lam)))
    probs = [math.exp(-lam)]
    for k in range(1, max_goals + 1):
        probs.append(probs[-1] * lam / k)
    return probs


class MatchPredictPoissonModel:
    """A walk-forward-safe version of MatchPredict's expected-goals Poisson idea."""

    def __init__(
        self,
        match_info: dict[int, MatchInfo],
        train_match_ids: list[int],
        *,
        lookback_matches: int,
        prior_matches: float,
        max_goals: int,
        home_advantage: float,
        away_discount: float,
    ) -> None:
        self.match_info = match_info
        self.lookback_matches = lookback_matches
        self.prior_matches = prior_matches
        self.max_goals = max_goals
        self.home_advantage = home_advantage
        self.away_discount = away_discount
        self.by_team_role: dict[tuple[str, str, str], list[tuple[float, float, int]]] = defaultdict(list)
        self.league_role: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
        self.global_role: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
        self._fit(train_match_ids)

    def _fit(self, train_match_ids: list[int]) -> None:
        records = [self.match_info[mid] for mid in train_match_ids if mid in self.match_info]
        records.sort(key=lambda r: (r.issue, r.match_idx, r.match_id))
        for r in records:
            home_key = (r.league, r.home, "home")
            away_key = (r.league, r.away, "away")
            self.by_team_role[home_key].append((float(r.fthg), float(r.ftag), raw_result(r.fthg, r.ftag)))
            self.by_team_role[away_key].append((float(r.ftag), float(r.fthg), raw_result(r.ftag, r.fthg)))
            for role, gf, ga in (("home", float(r.fthg), float(r.ftag)), ("away", float(r.ftag), float(r.fthg))):
                self.league_role[(r.league, role)][0] += gf
                self.league_role[(r.league, role)][1] += ga
                self.league_role[(r.league, role)][2] += 1.0
                self.global_role[role][0] += gf
                self.global_role[role][1] += ga
                self.global_role[role][2] += 1.0

    def role_prior(self, league: str, role: str, field: str) -> float:
        idx = 0 if field == "gf" else 1
        vals = self.league_role.get((league, role))
        if vals and vals[2] > 0:
            return vals[idx] / vals[2]
        vals = self.global_role.get(role)
        if vals and vals[2] > 0:
            return vals[idx] / vals[2]
        return 1.25

    def team_role_avg(self, league: str, team: str, role: str, field: str) -> float:
        idx = 0 if field == "gf" else 1
        prior = self.role_prior(league, role, field)
        history = self.by_team_role.get((league, team, role), [])[-self.lookback_matches :]
        if not history:
            return prior
        raw = sum(row[idx] for row in history) / len(history)
        n = float(len(history))
        return (raw * n + prior * self.prior_matches) / (n + self.prior_matches)

    def predict_one(self, info: MatchInfo) -> np.ndarray:
        # Do not read info.fthg/info.ftag here. Test-match scores are only used
        # when the match is part of a previous training window.
        home_attack = self.team_role_avg(info.league, info.home, "home", "gf")
        home_defense = self.team_role_avg(info.league, info.home, "home", "ga")
        away_attack = self.team_role_avg(info.league, info.away, "away", "gf")
        away_defense = self.team_role_avg(info.league, info.away, "away", "ga")

        home_goals = (0.70 * home_attack + 0.30 * away_defense) * self.home_advantage
        away_goals = (0.70 * away_attack + 0.30 * home_defense) * self.away_discount
        home_pmf = poisson_pmf(home_goals, self.max_goals)
        away_pmf = poisson_pmf(away_goals, self.max_goals)
        probs = np.zeros(3, dtype=float)
        total_mass = 0.0
        for h, hp in enumerate(home_pmf):
            for a, ap in enumerate(away_pmf):
                mass = hp * ap
                probs[handicap_result(h, a, info.hcp)] += mass
                total_mass += mass
        if total_mass <= 0:
            return np.asarray([1 / 3, 1 / 3, 1 / 3], dtype=float)
        return probs / total_mass

    def predict(self, samples) -> np.ndarray:
        out = []
        for sample in samples:
            info = self.match_info.get(sample.match_id)
            if info is None:
                out.append([1 / 3, 1 / 3, 1 / 3])
            else:
                out.append(self.predict_one(info))
        return np.asarray(out, dtype=float)


def blend_sources(current: np.ndarray, mp_poisson: np.ndarray, weights: list[float]) -> dict[str, np.ndarray]:
    out = {
        "current": normalize_probs(current),
        "mp_poisson": normalize_probs(mp_poisson),
    }
    for weight in weights:
        name = f"blend_mp{int(round(weight * 100)):02d}"
        out[name] = normalize_probs((1.0 - weight) * current + weight * mp_poisson)
    return out


def append_prediction_rows(rows: list[dict[str, object]], issue: str, source: str, samples, probs: np.ndarray) -> None:
    for sample, row in zip(samples, probs):
        pred = int(np.argmax(row))
        rows.append(
            {
                "issue": issue,
                "source": source,
                "match_id": sample.match_id,
                "y": OUTCOMES[sample.y],
                "pred": OUTCOMES[pred],
                "hit": int(pred == sample.y),
                "top2_hit": int(sample.y in set(np.argsort(-row)[:2])),
                "p_3": float(row[0]),
                "p_1": float(row[1]),
                "p_0": float(row[2]),
                "draw_y": int(sample.y == DRAW_INDEX),
                "draw_p": float(row[DRAW_INDEX]),
            }
        )


def average_precision(y: np.ndarray, score: np.ndarray) -> float:
    positives = int(y.sum())
    if positives <= 0:
        return float("nan")
    order = np.argsort(-score)
    y_sorted = y[order]
    hits = np.cumsum(y_sorted)
    precision = hits / (np.arange(len(y_sorted)) + 1)
    return float((precision * y_sorted).sum() / positives)


def auc_score(y: np.ndarray, score: np.ndarray) -> float:
    positives = int(y.sum())
    negatives = len(y) - positives
    if positives <= 0 or negatives <= 0:
        return float("nan")
    order = np.argsort(score)
    ranks = np.empty(len(score), dtype=float)
    ranks[order] = np.arange(1, len(score) + 1)
    pos_rank_sum = ranks[y == 1].sum()
    return float((pos_rank_sum - positives * (positives + 1) / 2) / (positives * negatives))


def probability_summary(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["source"])].append(row)
    out = []
    for source, source_rows in sorted(grouped.items()):
        probs = np.asarray([[float(r["p_3"]), float(r["p_1"]), float(r["p_0"])] for r in source_rows], dtype=float)
        y_codes = [str(r["y"]) for r in source_rows]
        y = np.asarray([OUTCOMES.index(code) for code in y_codes], dtype=int)
        one_hot = np.zeros_like(probs)
        one_hot[np.arange(len(y)), y] = 1.0
        draw_y = np.asarray([int(r["draw_y"]) for r in source_rows], dtype=int)
        draw_p = probs[:, DRAW_INDEX]
        out.append(
            {
                "source": source,
                "n_matches": len(source_rows),
                "logloss": float(-np.log(np.maximum(probs[np.arange(len(y)), y], 1e-12)).mean()),
                "brier": float(np.mean(np.sum((probs - one_hot) ** 2, axis=1))),
                "accuracy": float(np.mean(probs.argmax(axis=1) == y)),
                "top2_accuracy": float(np.mean([int(r["top2_hit"]) for r in source_rows])),
                "draw_brier": float(np.mean((draw_p - draw_y) ** 2)),
                "draw_auc": auc_score(draw_y, draw_p),
                "draw_ap": average_precision(draw_y, draw_p),
                "pred_3_rate": float(np.mean(probs.argmax(axis=1) == 0)),
                "pred_1_rate": float(np.mean(probs.argmax(axis=1) == 1)),
                "pred_0_rate": float(np.mean(probs.argmax(axis=1) == 2)),
                "avg_p_3": float(probs[:, 0].mean()),
                "avg_p_1": float(probs[:, 1].mean()),
                "avg_p_0": float(probs[:, 2].mean()),
            }
        )
    return out


def run(args: argparse.Namespace) -> None:
    action_rows = load_action_rows(args.db, args.min_year)
    samples = build_samples(action_rows, load_match_extras(args.db, args.min_year))
    match_info = load_match_info(args.db, args.min_year)
    action_by_issue = group_action_rows_by_issue(action_rows)
    samples_by_issue = group_samples_by_issue(samples)
    issues = sorted(samples_by_issue)
    depth_policies = parse_strings(args.depth_policies)
    dynamic_policies = parse_strings(args.dynamic_policies)
    blend_weights = [float(x) for x in parse_strings(args.blend_weights)]
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

        current_probs = model_probabilities(args, train_samples, test_samples)
        train_match_ids = [sample.match_id for sample in train_samples]
        mp_model = MatchPredictPoissonModel(
            match_info,
            train_match_ids,
            lookback_matches=args.mp_lookback_matches,
            prior_matches=args.mp_prior_matches,
            max_goals=args.mp_max_goals,
            home_advantage=args.mp_home_advantage,
            away_discount=args.mp_away_discount,
        )
        mp_probs = mp_model.predict(test_samples)
        sources = blend_sources(current_probs, mp_probs, blend_weights)

        market = market_probs(test_samples)
        market_by_match = {sample.match_id: market[i] for i, sample in enumerate(test_samples)}
        samples_by_match = {sample.match_id: sample for sample in test_samples}
        action_lookup = {(row.match_id, row.action_code): row for row in test_action_rows}

        for source, probs in sources.items():
            append_prediction_rows(prediction_rows, test_issue, source, test_samples, probs)
            probs_by_match = {sample.match_id: probs[i] for i, sample in enumerate(test_samples)}
            for policy in depth_policies:
                depth_legs, depth_weights = transform_legs_for_depth(
                    q_legs,
                    policy=policy,
                    probs_by_match=probs_by_match,
                    market_by_match=market_by_match,
                    min_score_factor=threshold,
                )
                strategy = f"confidence_{policy}__prob_{source}"
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
                    max_leg_uses=args.max_depth_leg_uses if policy.startswith("depth_constrained") else 0,
                    max_ticket_overlap=args.max_depth_ticket_overlap if policy.startswith("depth_constrained") else 0,
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
                "leakage_guard": "train_issues_before_test_issue",
                "snapshot": args.snapshot,
                "n_train_matches": len(train_samples),
                "n_test_matches": len(test_samples),
                "n_q_legs": len(q_legs),
                "n_sources": len(sources),
            }
        )

    ticket_summary = summarize_tickets(ticket_rows)
    ticket_summary.sort(key=lambda row: float(row["roi"]), reverse=True)
    prob_summary = probability_summary(prediction_rows)
    prob_summary.sort(key=lambda row: float(row["logloss"]))
    issue_rows = issue_profit_rows(ticket_rows)

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "matchpredict_tickets.csv", ticket_rows)
    write_csv(out / "matchpredict_strategy_summary.csv", ticket_summary)
    write_csv(out / "matchpredict_issue_profit.csv", issue_rows)
    write_csv(out / "matchpredict_coverage.csv", coverage_rows)
    write_csv(out / "matchpredict_prediction_rows.csv", prediction_rows)
    write_csv(out / "matchpredict_prediction_summary.csv", prob_summary)
    write_csv(out / "matchpredict_windows.csv", window_rows)

    report = [
        "# N=7 MatchPredict integration evaluation",
        "",
        f"- DB: `{args.db}`",
        f"- Snapshot: `{args.snapshot}`",
        f"- Train issues: `{args.train_issues}`",
        f"- Current model: `{args.model_source}` / `{args.feature_set}` / l2 `{args.l2}`",
        f"- MP Poisson: lookback `{args.mp_lookback_matches}`, prior `{args.mp_prior_matches}`, max_goals `{args.mp_max_goals}`",
        f"- Blend weights: `{args.blend_weights}`",
        f"- Depth policies: `{args.depth_policies}`",
        f"- Dynamic policies: `{args.dynamic_policies}`",
        "",
        "## Probability Summary",
        md_table(prob_summary),
        "",
        "## Strategy Summary",
        md_table(compact_summary(ticket_summary)),
        "",
        "## Files",
        "",
        "- `matchpredict_prediction_summary.csv`",
        "- `matchpredict_strategy_summary.csv`",
        "- `matchpredict_tickets.csv`",
        "- `matchpredict_issue_profit.csv`",
        "- `matchpredict_coverage.csv`",
        "- `matchpredict_windows.csv`",
        "",
    ]
    (out / "matchpredict_report.md").write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {out / 'matchpredict_report.md'}")
    print(f"Wrote {len(ticket_rows)} ticket rows and {len(prediction_rows)} prediction rows")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--output-dir", type=Path, default=Path("results/n7_matchpredict_integration"))
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
    parser.add_argument("--model-source", choices=("multiclass", "ovr_shared", "ovr_separate"), default="multiclass")
    parser.add_argument("--feature-set", choices=("base", "kelly", "priors", "extras", "rich", "team", "team_rich"), default="base")
    parser.add_argument("--l2", type=float, default=0.01)
    parser.add_argument("--class-weight", choices=("none", "balanced"), default="none")
    parser.add_argument("--maxiter", type=int, default=120)
    parser.add_argument("--depth-policies", default="depth_constrained_hybrid")
    parser.add_argument("--dynamic-policies", default="model_draw_ratio_t0.55_k2")
    parser.add_argument("--require-positive-draw-edge", action="store_true")
    parser.add_argument("--blend-weights", default="0.10,0.25,0.50")
    parser.add_argument("--mp-lookback-matches", type=int, default=10)
    parser.add_argument("--mp-prior-matches", type=float, default=4.0)
    parser.add_argument("--mp-max-goals", type=int, default=8)
    parser.add_argument("--mp-home-advantage", type=float, default=1.10)
    parser.add_argument("--mp-away-discount", type=float, default=0.90)
    args = parser.parse_args()
    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")
    run(args)


if __name__ == "__main__":
    main()
