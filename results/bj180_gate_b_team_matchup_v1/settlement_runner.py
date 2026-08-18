#!/usr/bin/env python3
"""Settle #180's immutable team/matchup probability and FULL-N7 surface.

The implementation deliberately reuses the accepted #179 settlement primitives
for payout, tax, bootstrap, chronology and risk accounting.  Only the frozen
#180 model vectors and arm names differ.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import importlib.util
import json
import math
import os
import shutil
import statistics
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Sequence


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


ROOT = repo_root()


def load_base():
    path = ROOT / "scripts" / "settle_bj179_hierarchical_league_gate_b.py"
    spec = importlib.util.spec_from_file_location("bj180_bj179_settlement_base", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load accepted settlement base: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B = load_base()

CONTRACT = "BJ-HIST-TEAM-MODEL-N7-001"
VERSION = "bj180-gate-b-v1"
GATE_A = ROOT / "results" / "bj180_gate_a_preoutcome_v2"
OUTCOME_DIR = ROOT / "results" / "bj95_gate_b_outcome_settlement_v2r8"
OUTCOME_PATH = OUTCOME_DIR / "canonical_outcome_join.csv"
DEFAULT_OUTPUT = ROOT / "results" / "bj180_gate_b_team_matchup_v1"

EXPECTED_GATE_A_MANIFEST = (
    "96cbd2565f5d1f837700e476d7a7412225677581b5e4448a4f9bfac4c9220835"
)
EXPECTED_GATE_A_CONTENT = (
    "6a0abe9cb36198dae11a5da06679d22b786cdf49f3619e6e34d7782f29915288"
)
EXPECTED_OUTCOME_MANIFEST = B.EXPECTED_OUTCOME_MANIFEST
EXPECTED_OUTCOME_PAYLOAD = B.EXPECTED_OUTCOME_PAYLOAD

EXPECTED_B0_SETTLED = B.EXPECTED_B0_SETTLED
EXPECTED_B0_STAKE = B.EXPECTED_B0_STAKE
EXPECTED_B0_GROSS = B.EXPECTED_B0_GROSS
EXPECTED_B0_ROI = B.EXPECTED_B0_ROI
EXPECTED_L0_SETTLED = B.EXPECTED_Q1_SETTLED
EXPECTED_L0_STAKE = B.EXPECTED_Q1_STAKE
EXPECTED_L0_GROSS = B.EXPECTED_Q1_GROSS
EXPECTED_L0_ROI = B.EXPECTED_Q1_ROI

ARMS = (
    "B0_BEST_FULL",
    "L0_QUICK_LEAGUE",
    "H0_LEAGUE_DIAGNOSTIC",
    "T1_DEEP_TEAM",
    "TL1_TEAM_LEAGUE",
    "TL_CFG_CONSERVATIVE",
    "TL_CFG_RESPONSIVE",
    "TL_MINUS_LATENT",
    "TL_MINUS_HOME_AWAY",
    "TL_MINUS_FORM",
    "TL_MINUS_REST",
    "TL_MINUS_OPPONENT",
    "TL_MINUS_INITIALIZATION",
    "TL_MINUS_H2H",
)
ARM_LABELS = {
    "B0_BEST_FULL": "B0 market baseline",
    "L0_QUICK_LEAGUE": "quick league baseline",
    "H0_LEAGUE_DIAGNOSTIC": "#179 league diagnostic",
    "T1_DEEP_TEAM": "deep team only",
    "TL1_TEAM_LEAGUE": "70% league + 30% team",
    "TL_CFG_CONSERVATIVE": "80% league + 20% conservative team",
    "TL_CFG_RESPONSIVE": "60% league + 40% responsive team",
    "TL_MINUS_LATENT": "team+league minus latent strength",
    "TL_MINUS_HOME_AWAY": "team+league minus home/away split",
    "TL_MINUS_FORM": "team+league minus rolling form",
    "TL_MINUS_REST": "team+league minus rest/congestion",
    "TL_MINUS_OPPONENT": "team+league minus opponent adjustment",
    "TL_MINUS_INITIALIZATION": "team+league minus initialization",
    "TL_MINUS_H2H": "team+league minus prior-only H2H",
}
ARM_VECTORS = {
    "B0_BEST_FULL": "market",
    "L0_QUICK_LEAGUE": "quick",
    "H0_LEAGUE_DIAGNOSTIC": "league_diagnostic",
    "T1_DEEP_TEAM": "team_primary",
    "TL1_TEAM_LEAGUE": "team_league_primary",
    "TL_CFG_CONSERVATIVE": "team_league_conservative",
    "TL_CFG_RESPONSIVE": "team_league_responsive",
    "TL_MINUS_LATENT": "team_league_minus_latent",
    "TL_MINUS_HOME_AWAY": "team_league_minus_home_away",
    "TL_MINUS_FORM": "team_league_minus_form",
    "TL_MINUS_REST": "team_league_minus_rest",
    "TL_MINUS_OPPONENT": "team_league_minus_opponent",
    "TL_MINUS_INITIALIZATION": "team_league_minus_initialization",
    "TL_MINUS_H2H": "team_league_minus_h2h",
}
ARM_SCORES = {
    "B0_BEST_FULL": "market_gm_e_sp",
    "L0_QUICK_LEAGUE": "quick_league_gm_e_sp",
    "H0_LEAGUE_DIAGNOSTIC": "league_diagnostic_gm_e_sp",
    **{
        arm: f"{vector}_gm_e_sp"
        for arm, vector in ARM_VECTORS.items()
        if arm not in {"B0_BEST_FULL", "L0_QUICK_LEAGUE", "H0_LEAGUE_DIAGNOSTIC"}
    },
}
SEGMENTS = B.SEGMENTS
BOOTSTRAP_REPLICATES = B.BOOTSTRAP_REPLICATES
BOOTSTRAP_SEED = 180_189


def configure_base() -> None:
    B.CONTRACT = CONTRACT
    B.VERSION = VERSION
    B.GATE_A = GATE_A
    B.OUTCOME_DIR = OUTCOME_DIR
    B.OUTCOME_PATH = OUTCOME_PATH
    B.DEFAULT_OUTPUT = DEFAULT_OUTPUT
    B.EXPECTED_GATE_A_MANIFEST = EXPECTED_GATE_A_MANIFEST
    B.EXPECTED_GATE_A_CONTENT = EXPECTED_GATE_A_CONTENT
    B.ARMS = ARMS
    B.ARM_LABELS = ARM_LABELS
    B.ARM_VECTOR_FIELDS = ARM_VECTORS
    B.ARM_SCORE_FIELDS = ARM_SCORES
    B.SEGMENTS = SEGMENTS
    B.BOOTSTRAP_SEED = BOOTSTRAP_SEED


configure_base()


def read_csv(path: Path) -> list[dict[str, str]]:
    return B.read_csv(path)


def read_gzip(path: Path) -> list[dict[str, str]]:
    return B.read_gzip(path)


def load_inputs():
    gate_manifest = B.verify_package(
        GATE_A, EXPECTED_GATE_A_MANIFEST, EXPECTED_GATE_A_CONTENT
    )
    outcome_manifest = B.verify_package(OUTCOME_DIR, EXPECTED_OUTCOME_MANIFEST)
    if outcome_manifest.get(OUTCOME_PATH.name) != EXPECTED_OUTCOME_PAYLOAD:
        raise RuntimeError("canonical outcome payload drift")

    selections = read_csv(GATE_A / "selection_freeze.csv")
    active = [row for row in selections if row["policy_status"] == "SELECTED_PREOUTCOME"]
    if len(selections) != 348 * len(ARMS) or len(active) != 189 * len(ARMS):
        raise RuntimeError("Gate-A selection denominator drift")
    if tuple(dict.fromkeys(row["arm"] for row in active)) != ARMS:
        raise RuntimeError("Gate-A arm order/surface drift")
    if any(
        int(row["ticket_count"]) != B.FULL_TICKETS
        or float(row["planned_stake_yuan"]) != B.FULL_STAKE
        for row in active
    ):
        raise RuntimeError("FULL N7 accounting drift")

    candidates = read_gzip(GATE_A / "candidate_universe_scores.csv.gz")
    if len(candidates) != 424:
        raise RuntimeError("candidate census drift")
    candidate_by_key = {
        (row["issue_instance"], row["portfolio_id"]): row for row in candidates
    }

    probabilities = read_gzip(GATE_A / "match_probability_freeze.csv.gz")
    if len(probabilities) != 1558 or len({row["match_id"] for row in probabilities}) != 1558:
        raise RuntimeError("probability denominator drift")
    if any(
        abs(sum(float(row[f"{vector}_p{code}"]) for code in ("3", "1", "0")) - 1)
        > 2e-12
        for row in probabilities
        for vector in ARM_VECTORS.values()
    ):
        raise RuntimeError("frozen probability normalization drift")

    outcomes = {row["match_id"]: row for row in read_csv(OUTCOME_PATH)}
    if any(
        row["has_trusted_settlement"] != "1" or row["settlement_quality"] != "trusted"
        for row in outcomes.values()
    ):
        raise RuntimeError("untrusted canonical outcome row")
    chronology: dict[str, str] = {}
    for row in probabilities:
        issue_instance = f"{row['issue']}@OOS_{row['year']}"
        chronology[issue_instance] = min(
            chronology.get(issue_instance, row["kickoff_ts"]), row["kickoff_ts"]
        )
    if len(chronology) != 189:
        raise RuntimeError("issue chronology denominator drift")
    source = {
        "gate_a": {
            "package": GATE_A.name,
            "manifest_sha256": EXPECTED_GATE_A_MANIFEST,
            "content_identity_sha256": EXPECTED_GATE_A_CONTENT,
            "payload_count": len(gate_manifest),
        },
        "outcomes": {
            "package": OUTCOME_DIR.name,
            "manifest_sha256": EXPECTED_OUTCOME_MANIFEST,
            "canonical_outcome_join_sha256": EXPECTED_OUTCOME_PAYLOAD,
            "row_count": len(outcomes),
        },
        "accepted_settlement_base": {
            "script": "scripts/settle_bj179_hierarchical_league_gate_b.py",
            "sha256": B.sha256_file(ROOT / "scripts" / "settle_bj179_hierarchical_league_gate_b.py"),
        },
    }
    return active, candidate_by_key, probabilities, chronology, outcomes, source


def probability_rows(frozen, outcomes):
    output = []
    for source in frozen:
        outcome = outcomes.get(source["match_id"])
        truth = outcome["result_code"] if outcome else ""
        for arm in ARMS:
            vector = ARM_VECTORS[arm]
            probs = {code: float(source[f"{vector}_p{code}"]) for code in ("3", "1", "0")}
            available = truth in probs
            output.append(
                {
                    "match_id": source["match_id"],
                    "issue": source["issue"],
                    "year": source["year"],
                    "fold": f"OOS_{source['year']}",
                    "kickoff_ts": source["kickoff_ts"],
                    "league": source["league"],
                    "arm": arm,
                    "arm_label": ARM_LABELS[arm],
                    "vector_name": vector,
                    "outcome_status": "SETTLED" if available else "MISSING_CANONICAL_OUTCOME",
                    "result_code": truth,
                    "p3": B.fmt_ratio(probs["3"]),
                    "p1": B.fmt_ratio(probs["1"]),
                    "p0": B.fmt_ratio(probs["0"]),
                    "log_loss": B.fmt_ratio(-math.log(max(1e-15, probs[truth])) if available else None),
                    "brier": B.fmt_ratio(
                        sum((probs[code] - float(code == truth)) ** 2 for code in probs)
                        if available else None
                    ),
                    "min_history_n": source["min_history_n"],
                    "new_team_fallback": source["new_team_fallback"],
                    "h2h_prior_n": source["h2h_prior_n"],
                }
            )
    return output


def probability_frontier(rows, reliability):
    ece = {}
    for arm in ARMS:
        bins = [r for r in reliability if r["arm"] == arm and int(r["support"])]
        denominator = sum(int(r["support"]) for r in bins)
        ece[arm] = sum(int(r["support"]) * abs(float(r["calibration_gap"])) for r in bins) / denominator
    views = [("ALL", "ALL")]
    views += [("FOLD", value) for value in sorted({str(r["fold"]) for r in rows})]
    output = []
    for arm in ARMS:
        native = [r for r in rows if r["arm"] == arm]
        for view, value in views:
            subset = native if view == "ALL" else [r for r in native if r["fold"] == value]
            settled = [r for r in subset if r["outcome_status"] == "SETTLED"]
            output.append(
                {
                    "arm": arm,
                    "arm_label": ARM_LABELS[arm],
                    "vector_name": ARM_VECTORS[arm],
                    "view": view,
                    "value": value,
                    "frozen_match_count": len(subset),
                    "settled_match_count": len(settled),
                    "missing_outcome_count": len(subset) - len(settled),
                    "new_team_fallback_count": sum(int(r["new_team_fallback"]) for r in subset),
                    "h2h_prior_available_count": sum(int(r["h2h_prior_n"]) > 0 for r in subset),
                    "mean_min_history_n": B.fmt_ratio(statistics.fmean(float(r["min_history_n"]) for r in subset) if subset else None),
                    "multiclass_log_loss": B.fmt_ratio(statistics.fmean(float(r["log_loss"]) for r in settled) if settled else None),
                    "multiclass_brier": B.fmt_ratio(statistics.fmean(float(r["brier"]) for r in settled) if settled else None),
                    "multiclass_ece": B.fmt_ratio(ece[arm] if view == "ALL" else None),
                }
            )
    return output


def model_frontier(probability_summary):
    metrics = {r["arm"]: r for r in probability_summary if r["view"] == "ALL"}
    registry = {r["arm"]: r for r in read_csv(GATE_A / "arm_registry.csv")}
    configs = list(read_csv(GATE_A / "configuration_registry.csv"))
    output = []
    for arm in ARMS:
        reg = registry[arm]
        metric = metrics[arm]
        output.append(
            {
                "arm": arm,
                "arm_role": reg["arm_role"],
                "definition": reg["definition"],
                "score_field": reg["score_field"],
                "vector_name": ARM_VECTORS[arm],
                "settled_match_count": metric["settled_match_count"],
                "multiclass_log_loss": metric["multiclass_log_loss"],
                "multiclass_brier": metric["multiclass_brier"],
                "multiclass_ece": metric["multiclass_ece"],
                "selection_authority": "NONE_FROZEN_FRONTIER_ONLY",
            }
        )
    return output, configs


def totals(rows):
    return B.totals(rows)


def paired_rows(native, comparator):
    controls = {r["issue_instance"]: r for r in comparator}
    candidates = [
        r for r in native
        if r["policy_status"] == "SETTLED"
        and controls[r["issue_instance"]]["policy_status"] == "SETTLED"
    ]
    return candidates, [controls[r["issue_instance"]] for r in candidates]


def primary_tables(rows):
    by_arm = {arm: [r for r in rows if r["arm"] == arm] for arm in ARMS}
    summaries, bootstraps, draw_meta = [], [], {}
    for segment_index, segment in enumerate(SEGMENTS):
        selected = {arm: B.choose_segment(by_arm[arm], segment) for arm in ARMS}
        expected = {"ALL_189": 189, "CHOICE_113": 113, "INVARIANT_76": 76}[segment]
        if len(selected["B0_BEST_FULL"]) != expected:
            raise RuntimeError(f"segment denominator drift: {segment}")
        for arm_index, arm in enumerate(ARMS):
            native = selected[arm]
            settled = [r for r in native if r["policy_status"] == "SETTLED"]
            paired, base = paired_rows(native, selected["B0_BEST_FULL"])
            paired_l0, l0 = paired_rows(native, selected["L0_QUICK_LEAGUE"])
            nt, pt, bt, lt, l0t = map(totals, (settled, paired, base, paired_l0, l0))
            roi = B.safe_ratio(nt["pre_tax_net_yuan"], nt["stake_yuan"])
            paired_roi = B.safe_ratio(pt["pre_tax_net_yuan"], pt["stake_yuan"])
            base_roi = B.safe_ratio(bt["pre_tax_net_yuan"], bt["stake_yuan"])
            lroi = B.safe_ratio(lt["pre_tax_net_yuan"], lt["stake_yuan"])
            l0roi = B.safe_ratio(l0t["pre_tax_net_yuan"], l0t["stake_yuan"])
            base_by_issue = {r["issue_instance"]: r for r in selected["B0_BEST_FULL"]}
            summaries.append(
                {
                    "segment": segment,
                    "arm": arm,
                    "arm_label": ARM_LABELS[arm],
                    "planned_issue_count": len(native),
                    "settled_native_issue_count": len(settled),
                    "unavailable_native_issue_count": len(native) - len(settled),
                    "paired_settled_issue_count": len(paired),
                    "paired_l0_settled_issue_count": len(paired_l0),
                    "choice_identity_changed_count": sum(r["selected_identity_fingerprint"] != base_by_issue[r["issue_instance"]]["selected_identity_fingerprint"] for r in native),
                    "stake_yuan": B.fmt_money(nt["stake_yuan"]),
                    "gross_pre_tax_yuan": B.fmt_money(nt["gross_pre_tax_yuan"]),
                    "tax_yuan": B.fmt_money(nt["tax_yuan"]),
                    "no_tax_roi": B.fmt_ratio(roi),
                    "tax_adjusted_roi": B.fmt_ratio(B.safe_ratio(nt["tax_adjusted_net_yuan"], nt["stake_yuan"])),
                    "paired_no_tax_roi": B.fmt_ratio(paired_roi),
                    "paired_b0_no_tax_roi": B.fmt_ratio(base_roi),
                    "paired_profit_lift_yuan": B.fmt_money(pt["pre_tax_net_yuan"] - bt["pre_tax_net_yuan"]),
                    "paired_roi_lift": B.fmt_ratio(None if paired_roi is None or base_roi is None else paired_roi - base_roi),
                    "paired_l0_no_tax_roi": B.fmt_ratio(lroi),
                    "paired_l0_baseline_no_tax_roi": B.fmt_ratio(l0roi),
                    "paired_l0_profit_lift_yuan": B.fmt_money(lt["pre_tax_net_yuan"] - l0t["pre_tax_net_yuan"]),
                    "paired_l0_roi_lift": B.fmt_ratio(None if lroi is None or l0roi is None else lroi - l0roi),
                    "coverage_hit_rate": B.fmt_ratio(B.safe_ratio(nt["hit_ticket_count"], len(settled))),
                    "ticket_hit_rate": B.fmt_ratio(B.safe_ratio(nt["hit_ticket_count"], nt["executed_ticket_count"])),
                    "mean_gm_expected_sp": B.fmt_ratio(statistics.fmean(float(r["gm_expected_sp"]) for r in settled) if settled else None),
                    "realized_payout_yuan": B.fmt_money(nt["gross_pre_tax_yuan"]),
                    "profitable_issue_count": sum(float(r["pre_tax_net_yuan"]) > 0 for r in settled),
                }
            )
            draws, meta = B.build_draw_matrix(len(paired), segment_index * 100 + arm_index)
            result = B.bootstrap_pair(paired, base, draws)
            ldraws, lmeta = B.build_draw_matrix(len(paired_l0), 10_000 + segment_index * 100 + arm_index)
            lresult = B.bootstrap_pair(paired_l0, l0, ldraws)
            bootstraps.append(
                {
                    "segment": segment,
                    "arm": arm,
                    "paired_issue_count": len(paired),
                    **{k: B.fmt_ratio(v) for k, v in result.items()},
                    "l0_paired_issue_count": len(paired_l0),
                    **{f"l0_{k}": B.fmt_ratio(v) for k, v in lresult.items()},
                    "replicates": BOOTSTRAP_REPLICATES,
                    "draw_matrix_sha256": meta["sha256"],
                    "l0_draw_matrix_sha256": lmeta["sha256"],
                }
            )
            draw_meta[f"{segment}/{arm}"] = meta
            draw_meta[f"L0/{segment}/{arm}"] = lmeta
    return summaries, bootstraps, draw_meta


def identity_attribution(rows):
    by_key = {(r["arm"], r["issue_instance"]): r for r in rows}
    issues = sorted({r["issue_instance"] for r in rows if str(r["choice_opportunity"]) == "1"})
    output = []
    for arm in ARMS:
        row_out = {"arm": arm, "choice_issue_count": len(issues)}
        for prefix, comparator in (("b0", "B0_BEST_FULL"), ("l0", "L0_QUICK_LEAGUE")):
            stats = defaultdict(int); lift = 0.0
            for issue in issues:
                row, base = by_key[(arm, issue)], by_key[(comparator, issue)]
                if row["selected_identity_fingerprint"] == base["selected_identity_fingerprint"]:
                    stats["same"] += 1; continue
                stats["changed"] += 1
                if row["policy_status"] != "SETTLED" or base["policy_status"] != "SETTLED":
                    stats["unavailable"] += 1; continue
                stats["paired"] += 1
                delta = float(row["pre_tax_net_yuan"]) - float(base["pre_tax_net_yuan"])
                lift += delta
                stats["win" if delta > 1e-9 else "loss" if delta < -1e-9 else "tie"] += 1
            for key in ("changed", "same", "paired", "unavailable", "win", "loss", "tie"):
                row_out[f"{prefix}_{key}_count"] = stats[key]
            row_out[f"{prefix}_paired_profit_lift_yuan"] = B.fmt_money(lift)
            row_out[f"{prefix}_paired_roi_lift"] = B.fmt_ratio(B.safe_ratio(lift, stats["paired"] * B.FULL_STAKE))
        output.append(row_out)
    return output


def write_charts(stage, summary, probability_summary, series_rows):
    primary = [r for r in summary if r["segment"] == "ALL_189"]
    probability = [r for r in probability_summary if r["view"] == "ALL"]
    B.write_csv(stage / "chart_source_primary_comparison.csv", list(primary[0]), primary)
    B.write_csv(stage / "chart_source_probability_frontier.csv", list(probability[0]), probability)
    selection = [{"arm": r["arm"], "identity_changed_count": r["choice_identity_changed_count"], "identity_unchanged_count": 113-int(r["choice_identity_changed_count"]), "paired_roi_lift": r["paired_roi_lift"], "paired_l0_roi_lift": r["paired_l0_roi_lift"]} for r in primary]
    B.write_csv(stage / "chart_source_selection_flow.csv", list(selection[0]), selection)
    colors = ("#1d4ed8", "#7c3aed", "#059669", "#d97706", "#dc2626", "#0891b2", "#4f46e5", "#65a30d", "#ea580c", "#be123c", "#0f766e", "#9333ea", "#ca8a04", "#475569")
    grouped = defaultdict(list)
    for row in series_rows:
        if row["segment"] == "ALL_189": grouped[row["arm"]].append(row)
    B.svg_lines(stage / "equity_curves_pre_tax.svg", "#180 FULL-N7 pre-tax equity", [(ARM_LABELS[a], [float(r["cumulative_pre_tax_profit_yuan"]) for r in grouped[a]], colors[i]) for i,a in enumerate(ARMS)], "Cumulative profit (CNY)")
    B.svg_lines(stage / "drawdown_curves_pre_tax.svg", "#180 FULL-N7 pre-tax drawdown", [(ARM_LABELS[a], [float(r["pre_tax_drawdown_yuan"]) for r in grouped[a]], colors[i]) for i,a in enumerate(ARMS)], "Drawdown (CNY)")
    B.svg_lines(stage / "probability_frontier.svg", "#180 frozen multiclass probability frontier", [(m, [float(r[f]) for r in probability], c) for m,f,c in (("log loss","multiclass_log_loss","#1d4ed8"),("Brier","multiclass_brier","#059669"),("ECE","multiclass_ece","#dc2626"))], "Loss / calibration error")
    B.svg_lines(stage / "economic_lift_frontier.svg", "#180 matched FULL-N7 pre-tax ROI lift", [("lift versus B0", [float(r["paired_roi_lift"]) for r in primary], "#1d4ed8"),("lift versus L0", [float(r["paired_l0_roi_lift"]) for r in primary], "#7c3aed")], "Paired pre-tax ROI lift")


def report(probability_summary, summary, attribution):
    p = [r for r in probability_summary if r["view"] == "ALL"]
    s = [r for r in summary if r["segment"] == "ALL_189"]
    lines = ["# #180 Gate B — league-aware team and matchup model", "", "## Executive disposition", "", "This is a frozen retrospective comparison. B0 remains the controlling incumbent; any positive row requires strict independent EV before promotion.", "", "## Probability-first frontier", "", "| Arm | Settled | LogLoss | Brier | ECE | New-team fallback |", "|---|---:|---:|---:|---:|---:|"]
    for r in p: lines.append(f"| {r['arm']} | {r['settled_match_count']} | {float(r['multiclass_log_loss']):.6f} | {float(r['multiclass_brier']):.6f} | {float(r['multiclass_ece']):.6f} | {r['new_team_fallback_count']} |")
    lines += ["", "Reliability bins and fold-specific coverage are manifest-covered. Lower probability losses are better.", "", "## Matched FULL-N7 economics", "", "| Arm | Settled | Pre-tax ROI | Lift vs B0 | Lift vs L0 | Tax ROI | Hits | Identity changes |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in s: lines.append(f"| {r['arm']} | {r['settled_native_issue_count']} | {float(r['no_tax_roi']):+.2%} | {float(r['paired_roi_lift']):+.2%} | {float(r['paired_l0_roi_lift']):+.2%} | {float(r['tax_adjusted_roi']):+.2%} | {r['profitable_issue_count']} | {r['choice_identity_changed_count']} |")
    lines += ["", "Pre-tax ROI is controlling. Tax is a separate reference view and is applied per winning ¥2 ticket, never after aggregating claimant or issue payouts.", "", "## Mechanism and ablations", "", "T1 isolates the deep team model; TL1 blends league and team signals. Conservative/responsive configurations vary shrinkage, while the seven TL_MINUS arms remove latent strength, home/away, form, rest, opponent adjustment, initialization and prior-only H2H one at a time. `identity_change_attribution.csv` separates selection changes from invariant identities.", "", "## Stability and risk", "", "YEAR/FOLD/LOYO, 20,000 paired issue bootstraps, ex-largest year/issue, payout HHI, percentage drawdown, Sharpe/Sortino/Calmar and miss streaks are published in the manifest-covered tables and charts.", "", "## Decision boundary", "", "No probability, candidate, identity, selector, M, allocation, pruning, ticket, SP, embargo or tax rule was altered after outcomes. A retrospective positive is only a research candidate; negative or inconclusive rows are not rescued by post-hoc tuning.", ""]
    return "\n".join(lines)


def assert_control(rows, arm, expected):
    settled = [r for r in rows if r["arm"] == arm and r["policy_status"] == "SETTLED"]
    aggregate = totals(settled)
    roi = aggregate["pre_tax_net_yuan"] / aggregate["stake_yuan"]
    n, stake, gross, expected_roi = expected
    if len(settled) != n or abs(aggregate["stake_yuan"]-stake) > 5e-7 or abs(aggregate["gross_pre_tax_yuan"]-gross) > 5e-6 or abs(roi-expected_roi) > 1e-10:
        raise RuntimeError(f"{arm} accepted incumbent reproduction drift: settled={len(settled)} stake={aggregate['stake_yuan']} gross={aggregate['gross_pre_tax_yuan']} roi={roi}")
    return settled, aggregate, roi


def package_identity(stage, controls):
    return B.package_identity(stage, controls)


def build(output: Path = DEFAULT_OUTPUT):
    output = output.resolve()
    if output.exists(): raise RuntimeError(f"immutable output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.stage.", dir=output.parent))
    try:
        active, candidates, frozen, chronology, outcomes, source = load_inputs()
        probability_settlement = probability_rows(frozen, outcomes)
        reliability = B.reliability_rows(probability_settlement)
        probability_summary = probability_frontier(probability_settlement, reliability)
        frontier, configs = model_frontier(probability_summary)
        B.write_gzip(stage/"probability_match_settlement.csv.gz", list(probability_settlement[0]), probability_settlement)
        B.write_csv(stage/"probability_frontier.csv", list(probability_summary[0]), probability_summary)
        B.write_csv(stage/"reliability_bins.csv", list(reliability[0]), reliability)
        B.write_csv(stage/"complete_model_frontier.csv", list(frontier[0]), frontier)
        B.write_csv(stage/"configuration_registry.csv", list(configs[0]), configs)

        contributions = B.settle_rows(active, candidates, outcomes, chronology)
        b0, b0t, b0roi = assert_control(contributions, "B0_BEST_FULL", (EXPECTED_B0_SETTLED, EXPECTED_B0_STAKE, EXPECTED_B0_GROSS, EXPECTED_B0_ROI))
        l0, l0t, l0roi = assert_control(contributions, "L0_QUICK_LEAGUE", (EXPECTED_L0_SETTLED, EXPECTED_L0_STAKE, EXPECTED_L0_GROSS, EXPECTED_L0_ROI))
        summary, bootstraps, draw_meta = primary_tables(contributions)
        attribution = identity_attribution(contributions)
        stability, risk, time_series = B.stability_and_risk(contributions)
        B.write_gzip(stage/"issue_contributions.csv.gz", list(contributions[0]), contributions)
        B.write_csv(stage/"primary_comparison.csv", list(summary[0]), summary)
        B.write_csv(stage/"identity_change_attribution.csv", list(attribution[0]), attribution)
        B.write_csv(stage/"bootstrap_paired_lift_20000.csv", list(bootstraps[0]), bootstraps)
        B.write_csv(stage/"stability_year_fold_loyo.csv", list(stability[0]), stability)
        B.write_csv(stage/"risk_metrics.csv", list(risk[0]), risk)
        B.write_gzip(stage/"issue_time_series.csv.gz", list(time_series[0]), time_series)
        bridge = []
        for arm, expected, actual, agg, roi in (("B0_BEST_FULL",(EXPECTED_B0_SETTLED,EXPECTED_B0_STAKE,EXPECTED_B0_GROSS,EXPECTED_B0_ROI),b0,b0t,b0roi),("L0_QUICK_LEAGUE",(EXPECTED_L0_SETTLED,EXPECTED_L0_STAKE,EXPECTED_L0_GROSS,EXPECTED_L0_ROI),l0,l0t,l0roi)):
            bridge.append({"control":arm,"expected_settled_issue_count":expected[0],"actual_settled_issue_count":len(actual),"expected_stake_yuan":B.fmt_money(expected[1]),"actual_stake_yuan":B.fmt_money(agg['stake_yuan']),"expected_gross_yuan":B.fmt_money(expected[2]),"actual_gross_yuan":B.fmt_money(agg['gross_pre_tax_yuan']),"expected_no_tax_roi":B.fmt_ratio(expected[3]),"actual_no_tax_roi":B.fmt_ratio(roi),"reconciliation_status":"PASS"})
        B.write_csv(stage/"source_reconciliation.csv", list(bridge[0]), bridge)
        (stage/"source_binding.json").write_text(json.dumps(source,indent=2,sort_keys=True)+"\n")
        card = {"contract":CONTRACT,"version":VERSION,"gate_a_manifest_sha256":EXPECTED_GATE_A_MANIFEST,"gate_a_content_identity_sha256":EXPECTED_GATE_A_CONTENT,"canonical_outcome_manifest_sha256":EXPECTED_OUTCOME_MANIFEST,"canonical_outcome_join_sha256":EXPECTED_OUTCOME_PAYLOAD,"arm_count":len(ARMS),"frozen_probability_match_count":len(frozen),"probability_settlement_row_count":len(probability_settlement),"probability_frontier_row_count":len(probability_summary),"reliability_bin_row_count":len(reliability),"active_issue_count":189,"choice_issue_count":113,"invariant_issue_count":76,"contribution_row_count":len(contributions),"full_ticket_count":B.FULL_TICKETS,"stake_per_ticket_yuan":B.STAKE_PER_TICKET,"full_stake_per_issue_yuan":B.FULL_STAKE,"payout_factor":B.PAYOUT_FACTOR,"tax_rate":B.TAX_RATE,"tax_line_yuan_per_winning_ticket":B.TAX_LINE_YUAN,"bootstrap_replicates":BOOTSTRAP_REPLICATES,"bootstrap_draws":draw_meta,"probability_first_evaluation":True,"frozen_full_surface":True,"completion_embargo_minutes":180,"retuning_permitted":False,"strict_independent_ev_required_for_positive_claim":True,"promotion_authority":False}
        (stage/"settlement_card.json").write_text(json.dumps(card,indent=2,sort_keys=True)+"\n")
        write_charts(stage, summary, probability_summary, time_series)
        (stage/"REPORT.md").write_text(report(probability_summary,summary,attribution))
        (stage/"README.md").write_text("# #180 Gate B immutable probability and FULL-N7 settlement\n\nSee `REPORT.md` and the manifest-covered probability, economic, stability, risk and chart-source artifacts.\n")
        shutil.copy2(Path(__file__), stage/"settlement_runner.py")
        controls={"gate_a_manifest_sha256":EXPECTED_GATE_A_MANIFEST,"outcome_manifest_sha256":EXPECTED_OUTCOME_MANIFEST,"active_issue_count":189,"arms":list(ARMS),"segments":list(SEGMENTS),"full_tickets":B.FULL_TICKETS,"bootstrap_replicates":BOOTSTRAP_REPLICATES,"b0_reproduction_status":"PASS","l0_reproduction_status":"PASS","probability_first_evaluation":True,"retuning_permitted":False}
        manifest_hash, content_hash = package_identity(stage, controls)
        os.rename(stage, output)
        all_rows=[r for r in summary if r["segment"]=="ALL_189"]
        return {"output":str(output),"manifest_sha256":manifest_hash,"content_identity_sha256":content_hash,"payload_count":len(json.loads((output/"SHA256SUMS.json").read_text())),"b0_no_tax_roi":b0roi,"l0_no_tax_roi":l0roi,"positive_lift_vs_b0_all_189_arms":[r["arm"] for r in all_rows if r["arm"]!="B0_BEST_FULL" and float(r["paired_roi_lift"])>0]}
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,default=DEFAULT_OUTPUT)
    args=parser.parse_args()
    print(json.dumps(build(args.output),indent=2,sort_keys=True))


if __name__ == "__main__":
    main()
