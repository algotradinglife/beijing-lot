#!/usr/bin/env python3
"""Evaluate standalone N3 selectors after handicap-aware result calibration.

The calibration uses only prior predicted outcomes and their settlements. It
does not skip issues; if a strict arm has too few qualified legs, it falls back
to the best calibrated-probability legs for that issue.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import math
import random
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.analyze_n7_fixed_loss_streaks import issue_sort_key, issue_year
from scripts.evaluate_n3_independent_selector import (
    BASE_MODEL,
    BASE_POLICY,
    SOURCE_STRATEGY,
    fnum,
    load_action_lookup,
    load_issue_metadata,
    load_n7_base,
    load_window_map,
    plot_equity,
    summarize_issue_rows,
    annual_rows,
    compare_with_n7,
    cumulative_rows,
    write_csv_all,
)
from scripts.evaluate_n7_joint_uncertainty_depth import budgeted_ticket_rows, issue_profit_rows
from scripts.walkforward_beidan_strategy_eval import ActionRow, Leg, Ticket, default_db_path, md_table, settle_ticket, write_csv


BREAK_EVEN_N3_Q = (1.0 / 0.65) ** (1.0 / 3.0)


@dataclass(frozen=True)
class OutcomeRow:
    issue: str
    match_id: int
    match_idx: int
    league: str
    hcp: float
    outcome: str
    estimated_sp: float
    p_raw: float
    q_raw: float
    hit: int
    winning_sp: float


@dataclass(frozen=True)
class CalibratedOutcome:
    base: OutcomeRow
    p_cal: float
    calibration_ratio: float
    calibration_group: str
    calibration_n: int


@dataclass(frozen=True)
class ArmSpec:
    name: str
    mode: str
    ticket_cap: int
    min_p: float
    min_estimated_sp: float
    max_estimated_sp: float
    min_q_cal: float


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def stable_seed(*parts: object) -> int:
    digest = hashlib.sha256("|".join(map(str, parts)).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def hcp_bucket(hcp: float) -> str:
    if abs(hcp - round(hcp)) < 1e-9:
        return str(int(round(hcp)))
    return f"{hcp:g}"


def sp_bucket(sp: float) -> str:
    if sp < 2:
        return "sp_lt2"
    if sp < 3:
        return "sp_2_3"
    if sp < 5:
        return "sp_3_5"
    if sp < 8:
        return "sp_5_8"
    return "sp_ge8"


def p_bucket(p: float) -> str:
    if p < 0.25:
        return "p_lt25"
    if p < 0.35:
        return "p_25_35"
    if p < 0.45:
        return "p_35_45"
    if p < 0.55:
        return "p_45_55"
    return "p_ge55"


def load_outcomes(
    *,
    outcomes_path: Path,
    source_strategy: str,
    action_lookup: dict[tuple[str, int, str], ActionRow],
) -> dict[str, dict[int, list[OutcomeRow]]]:
    out: dict[str, dict[int, list[OutcomeRow]]] = defaultdict(lambda: defaultdict(list))
    for row in read_csv(outcomes_path):
        if row.get("strategy") != source_strategy:
            continue
        issue = str(row["issue"])
        match_id = int(float(row["match_id"]))
        outcome = str(row["outcome"])
        action = action_lookup.get((issue, match_id, outcome))
        if action is None:
            continue
        estimated_sp = fnum(row.get("estimated_sp"), math.nan)
        p_raw = fnum(row.get("p_hat"), math.nan)
        q_raw = fnum(row.get("q"), math.nan)
        if not all(math.isfinite(v) for v in (estimated_sp, p_raw, q_raw)) or estimated_sp <= 0:
            continue
        out[issue][match_id].append(
            OutcomeRow(
                issue=issue,
                match_id=match_id,
                match_idx=int(float(row.get("match_idx", action.match_idx))),
                league=str(row.get("league", action.league)),
                hcp=fnum(row.get("hcp"), action.hcp),
                outcome=outcome,
                estimated_sp=estimated_sp,
                p_raw=p_raw,
                q_raw=q_raw,
                hit=int(action.hit),
                winning_sp=action.winning_sp,
            )
        )
    return {issue: dict(matches) for issue, matches in out.items()}


def group_keys(row: OutcomeRow) -> list[tuple[str, tuple[str, ...]]]:
    hb = hcp_bucket(row.hcp)
    return [
        ("outcome_hcp_sp_p", (row.outcome, hb, sp_bucket(row.estimated_sp), p_bucket(row.p_raw))),
        ("outcome_hcp_sp", (row.outcome, hb, sp_bucket(row.estimated_sp))),
        ("outcome_hcp_p", (row.outcome, hb, p_bucket(row.p_raw))),
        ("outcome_hcp", (row.outcome, hb)),
        ("outcome", (row.outcome,)),
        ("global", ("*",)),
    ]


def add_agg(agg: dict[tuple[str, tuple[str, ...]], dict[str, float]], row: OutcomeRow) -> None:
    for name, key in group_keys(row):
        vals = agg.setdefault((name, key), {"n": 0.0, "hits": 0.0, "pred_sum": 0.0})
        vals["n"] += 1
        vals["hits"] += row.hit
        vals["pred_sum"] += row.p_raw


def build_train_agg(train_rows: list[OutcomeRow]) -> dict[tuple[str, tuple[str, ...]], dict[str, float]]:
    agg: dict[tuple[str, tuple[str, ...]], dict[str, float]] = {}
    for row in train_rows:
        add_agg(agg, row)
    return agg


def calibration_for(
    row: OutcomeRow,
    agg: dict[tuple[str, tuple[str, ...]], dict[str, float]],
    *,
    min_group_n: int,
    shrink_n: float,
) -> tuple[float, str, int]:
    fallback = (1.0, "raw", 0)
    for name, key in group_keys(row):
        vals = agg.get((name, key))
        if vals is None or vals["n"] < min_group_n or vals["pred_sum"] <= 0:
            continue
        raw_avg = vals["pred_sum"] / vals["n"]
        empirical = (vals["hits"] + shrink_n * raw_avg) / (vals["n"] + shrink_n)
        ratio = empirical / raw_avg if raw_avg > 0 else 1.0
        return max(0.25, min(2.50, ratio)), name, int(vals["n"])
    return fallback


def calibrate_issue(
    issue_matches: dict[int, list[OutcomeRow]],
    train_rows: list[OutcomeRow],
    *,
    min_group_n: int,
    shrink_n: float,
) -> dict[int, list[CalibratedOutcome]]:
    agg = build_train_agg(train_rows)
    out: dict[int, list[CalibratedOutcome]] = {}
    for match_id, rows in issue_matches.items():
        adjusted = []
        for row in rows:
            ratio, group_name, n = calibration_for(row, agg, min_group_n=min_group_n, shrink_n=shrink_n)
            adjusted.append((row, max(0.001, min(0.999, row.p_raw * ratio)), ratio, group_name, n))
        total = sum(item[1] for item in adjusted)
        if total <= 0:
            continue
        out[match_id] = [
            CalibratedOutcome(
                base=row,
                p_cal=max(0.001, min(0.999, p_adj / total)),
                calibration_ratio=ratio,
                calibration_group=group_name,
                calibration_n=n,
            )
            for row, p_adj, ratio, group_name, n in adjusted
        ]
    return out


def arms(ticket_caps: list[int]) -> list[ArmSpec]:
    templates = [
        ("cal_p_top", "p_cal", 0.36, 1.2, 8.0, 0.0),
        ("cal_p_strict", "p_cal", 0.42, 1.2, 6.0, 0.0),
        ("cal_value", "p2_sp", 0.30, 1.2, 12.0, 0.0),
        ("cal_q_n3", "q_cal", 0.25, 1.2, 15.0, BREAK_EVEN_N3_Q),
        ("cal_standalone_ev", "q_cal", 0.20, 1.2, 15.0, 1.0 / 0.65),
        ("raw_value_control", "raw_q", 0.25, 1.2, 15.0, BREAK_EVEN_N3_Q),
    ]
    return [
        ArmSpec(
            name=f"n3_{name}_t{cap}",
            mode=mode,
            ticket_cap=cap,
            min_p=min_p,
            min_estimated_sp=min_sp,
            max_estimated_sp=max_sp,
            min_q_cal=min_q,
        )
        for cap in ticket_caps
        for name, mode, min_p, min_sp, max_sp, min_q in templates
    ]


def outcome_score(co: CalibratedOutcome, arm: ArmSpec) -> float:
    q_cal = co.p_cal * co.base.estimated_sp
    if arm.mode == "p_cal":
        return co.p_cal
    if arm.mode == "p2_sp":
        return co.p_cal * co.p_cal * co.base.estimated_sp
    if arm.mode == "q_cal":
        return q_cal
    if arm.mode == "raw_q":
        return co.base.q_raw
    raise ValueError(arm.mode)


def pick_legs(
    calibrated_matches: dict[int, list[CalibratedOutcome]],
    arm: ArmSpec,
    action_lookup: dict[tuple[str, int, str], ActionRow],
) -> list[tuple[Leg, CalibratedOutcome]]:
    selected = []
    fallback = []
    for match_id, rows in calibrated_matches.items():
        if not rows:
            continue
        ranked = sorted(rows, key=lambda co: (outcome_score(co, arm), co.p_cal), reverse=True)
        top = ranked[0]
        fallback.append(top)
        q_cal = top.p_cal * top.base.estimated_sp
        if (
            top.p_cal >= arm.min_p
            and arm.min_estimated_sp <= top.base.estimated_sp <= arm.max_estimated_sp
            and q_cal >= arm.min_q_cal
        ):
            selected.append(top)
    if len(selected) < 3:
        seen = {co.base.match_id for co in selected}
        for co in sorted(fallback, key=lambda item: (item.p_cal, item.p_cal * item.base.estimated_sp), reverse=True):
            if co.base.match_id in seen:
                continue
            selected.append(co)
            seen.add(co.base.match_id)
            if len(selected) >= 3:
                break
    legs = []
    for co in selected:
        action = action_lookup.get((co.base.issue, co.base.match_id, co.base.outcome))
        if action is None:
            continue
        q_cal = co.p_cal * co.base.estimated_sp
        leg = Leg(
            row=action,
            strategy=arm.name,
            score_factor=max(q_cal, 1e-9),
            p_hat=co.p_cal,
            source_rule=(
                f"n3_calibrated_result;mode={arm.mode};p_raw={co.base.p_raw:.6g};"
                f"p_cal={co.p_cal:.6g};estimated_sp={co.base.estimated_sp:.6g};"
                f"group={co.calibration_group};group_n={co.calibration_n}"
            ),
        )
        legs.append((leg, co))
    return sorted(legs, key=lambda item: (outcome_score(item[1], arm), item[1].p_cal), reverse=True)


def sample_triples(m: int, cap: int, rng: random.Random) -> list[tuple[int, int, int]]:
    total = m * (m - 1) * (m - 2) // 6
    if total <= cap:
        triples = list(itertools.combinations(range(m), 3))
        rng.shuffle(triples)
        return triples
    seen = set()
    triples = []
    attempts = 0
    while len(triples) < cap and attempts < cap * 60:
        attempts += 1
        triple = tuple(sorted(rng.sample(range(m), 3)))
        if triple in seen:
            continue
        seen.add(triple)
        triples.append(triple)
    return triples


def make_ticket_rows(
    *,
    issues: list[str],
    calibrated_by_issue: dict[str, dict[int, list[CalibratedOutcome]]],
    action_lookup: dict[tuple[str, int, str], ActionRow],
    window_map: dict[str, tuple[str, str]],
    arm_specs: list[ArmSpec],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    ticket_rows = []
    leg_rows = []
    for arm in arm_specs:
        for issue in issues:
            legs = pick_legs(calibrated_by_issue.get(issue, {}), arm, action_lookup)
            if len(legs) < 3:
                continue
            rng = random.Random(stable_seed("n3_calibrated", arm.name, issue))
            triples = sample_triples(len(legs), arm.ticket_cap, rng)
            if triples and len(triples) < arm.ticket_cap:
                base = list(triples)
                while len(triples) < arm.ticket_cap:
                    triples.append(base[len(triples) % len(base)])
            train_start, train_end = window_map.get(issue, ("", ""))
            for idx, triple in enumerate(triples[: arm.ticket_cap], start=1):
                chosen = tuple(legs[i][0] for i in triple)
                row = settle_ticket(
                    Ticket(
                        strategy=arm.name,
                        issue=issue,
                        n_legs=3,
                        ticket_idx=idx,
                        train_start_issue=train_start,
                        train_end_issue=train_end,
                        legs=chosen,
                    )
                )
                row.update(
                    {
                        "mode": arm.mode,
                        "ticket_cap": arm.ticket_cap,
                        "min_p": arm.min_p,
                        "min_estimated_sp": arm.min_estimated_sp,
                        "max_estimated_sp": arm.max_estimated_sp,
                        "min_q_cal": arm.min_q_cal,
                        "n_candidate_legs": len(legs),
                        "coverage_mode": "random_unique_combos_from_calibrated_top1",
                    }
                )
                ticket_rows.append(row)
            for leg, co in legs:
                leg_rows.append(
                    {
                        "strategy": arm.name,
                        "issue": issue,
                        "match_id": co.base.match_id,
                        "match_idx": co.base.match_idx,
                        "league": co.base.league,
                        "hcp": co.base.hcp,
                        "outcome": co.base.outcome,
                        "p_raw": co.base.p_raw,
                        "p_cal": co.p_cal,
                        "estimated_sp": co.base.estimated_sp,
                        "q_raw": co.base.q_raw,
                        "q_cal": co.p_cal * co.base.estimated_sp,
                        "calibration_ratio": co.calibration_ratio,
                        "calibration_group": co.calibration_group,
                        "calibration_n": co.calibration_n,
                        "hit": co.base.hit,
                        "winning_sp": co.base.winning_sp,
                    }
                )
    return ticket_rows, leg_rows


def run(args: argparse.Namespace) -> None:
    action_lookup = load_action_lookup(args.db_path, args.min_year)
    outcomes_by_issue = load_outcomes(
        outcomes_path=args.result_dir / "ev_framework_outcomes.csv",
        source_strategy=args.source_strategy,
        action_lookup=action_lookup,
    )
    issues = sorted(outcomes_by_issue, key=issue_sort_key)
    issue_idx = {issue: idx for idx, issue in enumerate(issues)}
    window_map = load_window_map(args.result_dir)

    calibrated_by_issue = {}
    calibration_audit = []
    flat_by_issue = {
        issue: [row for rows in matches.values() for row in rows]
        for issue, matches in outcomes_by_issue.items()
    }
    for issue in issues:
        idx = issue_idx[issue]
        train_start, _ = window_map.get(issue, ("", ""))
        train_issues = [prev for prev in issues[:idx] if not train_start or issue_sort_key(prev) >= issue_sort_key(train_start)]
        train_rows = [row for train_issue in train_issues for row in flat_by_issue.get(train_issue, [])]
        if len(train_rows) < args.min_train_rows:
            train_rows = [row for train_issue in issues[:idx] for row in flat_by_issue.get(train_issue, [])]
        calibrated = calibrate_issue(
            outcomes_by_issue[issue],
            train_rows,
            min_group_n=args.min_group_n,
            shrink_n=args.shrink_n,
        )
        calibrated_by_issue[issue] = calibrated
        used = [co for rows in calibrated.values() for co in rows]
        calibration_audit.append(
            {
                "issue": issue,
                "train_rows": len(train_rows),
                "n_matches": len(calibrated),
                "avg_abs_p_change": (
                    sum(abs(co.p_cal - co.base.p_raw) for co in used) / len(used) if used else math.nan
                ),
                "share_raw_fallback": (
                    sum(1 for co in used if co.calibration_group == "raw") / len(used) if used else math.nan
                ),
            }
        )

    arm_specs = arms(args.ticket_caps)
    raw_tickets, leg_rows = make_ticket_rows(
        issues=issues,
        calibrated_by_issue=calibrated_by_issue,
        action_lookup=action_lookup,
        window_map=window_map,
        arm_specs=arm_specs,
    )
    budgeted = budgeted_ticket_rows(raw_tickets, issue_budget_units=args.issue_budget_units, fractional=True)
    issue_rows = issue_profit_rows(budgeted)
    metadata = load_issue_metadata(args.n7_base_issue_profit, policy=args.n7_base_policy, model=args.n7_base_model)
    enriched_issue_rows = []
    for row in issue_rows:
        copied = dict(row)
        issue = str(row["issue"])
        copied.update(
            metadata.get(
                issue,
                {
                    "issue_start_ts": "",
                    "issue_close_ts": "",
                    "issue_order": issue_idx.get(issue, 0),
                    "calendar_year": issue_year(issue),
                    "season_year": issue_year(issue),
                },
            )
        )
        enriched_issue_rows.append(copied)

    summaries = summarize_issue_rows(
        enriched_issue_rows,
        issue_budget_units=args.issue_budget_units,
        recent_min_year=args.recent_min_year,
        recent_max_year=args.recent_max_year,
    )
    summaries.sort(
        key=lambda row: (
            fnum(row.get("roi_on_deployed_stake")),
            fnum(row.get("profit_units")),
            fnum(row.get("issue_win_rate")),
        ),
        reverse=True,
    )
    n7_rows = load_n7_base(args.n7_base_issue_profit, policy=args.n7_base_policy, model=args.n7_base_model)
    comparison = compare_with_n7(enriched_issue_rows, n7_rows)
    comparison_by_strategy = {row["strategy"]: row for row in comparison}
    for row in summaries:
        row.update(
            {
                f"n7_{key}": value
                for key, value in comparison_by_strategy.get(str(row["strategy"]), {}).items()
                if key != "strategy"
            }
        )
    annual = annual_rows(enriched_issue_rows)
    plot_strategies = [str(row["strategy"]) for row in summaries[: args.plot_top_n]]
    curve = cumulative_rows(issue_rows=enriched_issue_rows, n7_rows=n7_rows, strategies=plot_strategies)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv_all(args.output_dir / "n3_calibrated_result_raw_tickets.csv", raw_tickets)
    write_csv_all(args.output_dir / "n3_calibrated_result_budget_tickets.csv", budgeted)
    write_csv_all(args.output_dir / "n3_calibrated_result_issue_profit.csv", enriched_issue_rows)
    write_csv_all(args.output_dir / "n3_calibrated_result_leg_choices.csv", leg_rows)
    write_csv_all(args.output_dir / "n3_calibrated_result_calibration_audit.csv", calibration_audit)
    write_csv_all(args.output_dir / "n3_calibrated_result_summary.csv", summaries)
    write_csv_all(args.output_dir / "n3_calibrated_result_annual.csv", annual)
    write_csv_all(args.output_dir / "n3_calibrated_result_vs_n7.csv", comparison)
    write_csv_all(args.output_dir / "n3_calibrated_result_equity_curve.csv", curve)
    plot_equity(curve, args.figure_path)

    keep = [
        "strategy",
        "n_issues",
        "profit_units",
        "roi_on_deployed_stake",
        "issue_win_rate",
        "non_full_loss_rate",
        "max_drawdown_units",
        "max_dead_streak",
        "roi_ex_best_on_fixed_budget",
        "recent_profit_units",
        "recent_roi_on_deployed_stake",
        "avg_tickets_per_issue",
    ]
    report = [
        "# N3 calibrated result selector",
        "",
        "- Current issue calibration uses only prior predicted outcome rows and settlements.",
        "- Calibration hierarchy: outcome+hcp+SP+P bucket -> outcome+hcp+SP -> outcome+hcp+P -> outcome+hcp -> outcome -> raw.",
        "- After independent calibration, the three outcomes in a match are renormalized to sum to 1.",
        "- No issue-level skip gate is used; strict arms fall back to best calibrated-probability legs if needed.",
        f"- N3 break-even per-leg q reference: `{BREAK_EVEN_N3_Q:.4f}`.",
        "",
        "## Summary",
        "",
        md_table([{key: row.get(key, "") for key in keep} for row in summaries], limit=40),
        "",
        f"Equity curve SVG: `{args.figure_path}`",
        "",
    ]
    args.report_path.parent.mkdir(parents=True, exist_ok=True)
    args.report_path.write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {args.report_path}")


def parse_ints(raw: str) -> list[int]:
    return [int(part.strip()) for part in raw.split(",") if part.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--result-dir",
        type=Path,
        default=Path("results/n7_ev_framework_selector_2014_1h_minodds4_optional"),
    )
    parser.add_argument("--source-strategy", default="ev_m0p95_p0p8_full_opt")
    parser.add_argument("--db-path", type=Path, default=default_db_path())
    parser.add_argument("--min-year", type=int, default=2014)
    parser.add_argument("--ticket-caps", type=parse_ints, default=parse_ints("80,180"))
    parser.add_argument("--issue-budget-units", type=float, default=256.0)
    parser.add_argument("--min-train-rows", type=int, default=10_000)
    parser.add_argument("--min-group-n", type=int, default=120)
    parser.add_argument("--shrink-n", type=float, default=250.0)
    parser.add_argument(
        "--n7-base-issue-profit",
        type=Path,
        default=Path("results/n7_high_win_sleeve_20260628/high_win_sleeve_issue_profit.csv"),
    )
    parser.add_argument("--n7-base-policy", default=BASE_POLICY)
    parser.add_argument("--n7-base-model", default=BASE_MODEL)
    parser.add_argument("--recent-min-year", type=int, default=2023)
    parser.add_argument("--recent-max-year", type=int, default=2025)
    parser.add_argument("--plot-top-n", type=int, default=6)
    parser.add_argument("--output-dir", type=Path, default=Path("results/n3_calibrated_result_selector_20260628"))
    parser.add_argument(
        "--report-path",
        type=Path,
        default=Path("docs/research/n3_calibrated_result_selector_2026-06-28.md"),
    )
    parser.add_argument(
        "--figure-path",
        type=Path,
        default=Path("docs/research/figures/n3_calibrated_result_selector_equity_2026-06-28.svg"),
    )
    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
