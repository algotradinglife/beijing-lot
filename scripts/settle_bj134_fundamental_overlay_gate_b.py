#!/usr/bin/env python3
"""Settle #134's frozen fundamental/decision overlays on FULL N7 tickets.

The runner consumes only the accepted #134 Gate-A v3 identities and the
canonical #95 outcome join.  Every selected identity is a 2,187-ticket FULL
N7 portfolio (stake CNY 4,374).  If any selected match lacks a trusted outcome,
that arm/issue is unavailable and executes zero stake.  Tax is assessed per
winning ticket, never pooled across tickets or issues.
"""

from __future__ import annotations

import argparse
import array
import csv
import gzip
import hashlib
import io
import json
import math
import os
import random
import shutil
import statistics
import tempfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence


CONTRACT = "BJ-HIST-FUNDAMENTAL-OVERLAY-N7-001"
VERSION = "bj134-gate-b-v1"
STAKE_PER_TICKET = 2.0
FULL_TICKETS = 2187
FULL_STAKE = 4374.0
PAYOUT_FACTOR = 0.65
TAX_RATE = 0.20
TAX_LINE_YUAN = 10_000.0
BOOTSTRAP_REPLICATES = 20_000
BOOTSTRAP_SEED = 134_189

EXPECTED_GATE_A_MANIFEST = (
    "0a7e4d673e7fc5fd4832c91e3b519afe5a2bc3211b99f4c95f57c691921b65fd"
)
EXPECTED_GATE_A_CONTENT = (
    "3fe014f3decdbd589cdded52d8a9b2bac0f3cb988c2ae8e15cf79314a02eede1"
)
EXPECTED_OUTCOME_MANIFEST = (
    "fbbd3b53bd86f4bb0caff8f2587933cd6b0e4e7d04fb0f709bac934ec2a705cc"
)
EXPECTED_OUTCOME_PAYLOAD = (
    "13d709d253c31519734dbf0447e6961ac8a6060772975d7461741224e5251a89"
)
EXPECTED_B0_STAKE = 712_962.0
EXPECTED_B0_GROSS = 645_459.393809
EXPECTED_B0_ROI = -0.094679107990
EXPECTED_B0_SETTLED = 163
EXPECTED_HANDICAP_CONTRADICTIONS = 0

ARMS = (
    "B0_BEST_FULL",
    "L1_LEAGUE_CORE",
    "T1_TEAM_CORE",
    "M1_MARKET_DYNAMICS",
    "F1_CORE_ALL",
    "D1_DECISION_CHAIN_CORE",
    "F_MINUS_L",
    "F_MINUS_T",
    "F_MINUS_M",
)
SEGMENTS = ("ALL_189", "CHOICE_113", "INVARIANT_76")
ARM_LABELS = {
    "B0_BEST_FULL": "B0 market baseline",
    "L1_LEAGUE_CORE": "L1 league/regime",
    "T1_TEAM_CORE": "T1 team strength",
    "M1_MARKET_DYNAMICS": "M1 market dynamics",
    "F1_CORE_ALL": "F1 combined core",
    "D1_DECISION_CHAIN_CORE": "D1 decision chain",
    "F_MINUS_L": "F-L leave league out",
    "F_MINUS_T": "F-T leave team out",
    "F_MINUS_M": "F-M leave market out",
}


def repo_root() -> Path:
    for candidate in (
        Path(__file__).resolve().parent,
        *Path(__file__).resolve().parents,
    ):
        if (candidate / ".git").exists() and (candidate / "results").is_dir():
            return candidate
    raise RuntimeError("repository root unavailable")


ROOT = repo_root()
GATE_A = ROOT / "results" / "bj134_gate_a_preoutcome_v3"
OUTCOME_DIR = ROOT / "results" / "bj95_gate_b_outcome_settlement_v2r8"
OUTCOME_PATH = OUTCOME_DIR / "canonical_outcome_join.csv"
DEFAULT_OUTPUT = ROOT / "results" / "bj134_gate_b_fundamental_overlay_v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode()
    ).hexdigest()


def verify_package(
    directory: Path, manifest_hash: str, content_hash: str | None = None
) -> dict[str, str]:
    if sha256_file(directory / "SHA256SUMS.json") != manifest_hash:
        raise RuntimeError(f"manifest drift: {directory.name}")
    if (
        content_hash
        and sha256_file(directory / "CONTENT_IDENTITY.json") != content_hash
    ):
        raise RuntimeError(f"content identity drift: {directory.name}")
    manifest = json.loads((directory / "SHA256SUMS.json").read_text(encoding="utf-8"))
    actual = sorted(
        p.name
        for p in directory.iterdir()
        if p.is_file() and p.name != "SHA256SUMS.json"
    )
    if sorted(manifest) != actual:
        raise RuntimeError(f"manifest coverage drift: {directory.name}")
    for name, expected in manifest.items():
        if sha256_file(directory / name) != expected:
            raise RuntimeError(f"payload drift: {directory.name}/{name}")
    return manifest


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_gzip(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(
    path: Path, fields: Sequence[str], rows: Iterable[dict[str, object]]
) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fields, lineterminator="\n", extrasaction="raise"
        )
        writer.writeheader()
        writer.writerows(rows)


def write_gzip(
    path: Path, fields: Sequence[str], rows: Iterable[dict[str, object]]
) -> None:
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            text = io.TextIOWrapper(zipped, encoding="utf-8", newline="")
            writer = csv.DictWriter(
                text, fieldnames=fields, lineterminator="\n", extrasaction="raise"
            )
            writer.writeheader()
            writer.writerows(rows)
            text.flush()
            text.detach()


def fmt_money(value: float) -> str:
    return f"{value:.6f}"


def fmt_ratio(value: float | None) -> str:
    return "" if value is None or not math.isfinite(value) else f"{value:.12f}"


def safe_ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def segment_for(row: dict[str, object]) -> tuple[str, ...]:
    specific = "CHOICE_113" if str(row["choice_opportunity"]) == "1" else "INVARIANT_76"
    return ("ALL_189", specific)


def full_ticket_settlement(
    winning_sps: Sequence[float], available: bool
) -> dict[str, float | int]:
    if not available:
        return {"gross_pre_tax_yuan": 0.0, "tax_yuan": 0.0, "hit_ticket_count": 0}
    payout = STAKE_PER_TICKET * PAYOUT_FACTOR * math.prod(winning_sps)
    tax = payout * TAX_RATE if payout >= TAX_LINE_YUAN else 0.0
    return {"gross_pre_tax_yuan": payout, "tax_yuan": tax, "hit_ticket_count": 1}


def load_inputs() -> tuple[
    list[dict[str, str]], dict[str, dict[str, str]], dict[str, str], dict[str, object]
]:
    gate_manifest = verify_package(
        GATE_A, EXPECTED_GATE_A_MANIFEST, EXPECTED_GATE_A_CONTENT
    )
    outcome_manifest = verify_package(OUTCOME_DIR, EXPECTED_OUTCOME_MANIFEST)
    if outcome_manifest.get("canonical_outcome_join.csv") != EXPECTED_OUTCOME_PAYLOAD:
        raise RuntimeError("canonical outcome payload drift")
    selections = read_csv(GATE_A / "selection_freeze.csv")
    active = [row for row in selections if row["policy_status"] == "SELECTED_PREOUTCOME"]
    if len(selections) != 348 * len(ARMS) or len(active) != 189 * len(ARMS):
        raise RuntimeError("Gate-A selection denominator drift")
    if tuple(dict.fromkeys(row["arm"] for row in active)) != ARMS:
        raise RuntimeError("Gate-A arm order/surface drift")
    if any(
        int(row["ticket_count"]) != FULL_TICKETS
        or float(row["planned_stake_yuan"]) != FULL_STAKE
        for row in active
    ):
        raise RuntimeError("FULL N7 accounting drift")
    candidates = read_gzip(GATE_A / "candidate_universe_scores.csv.gz")
    if len(candidates) != 424:
        raise RuntimeError("candidate census drift")
    contradiction_total = sum(
        int(row["decision_handicap_contradiction_legs"]) for row in candidates
    )
    if contradiction_total != EXPECTED_HANDICAP_CONTRADICTIONS:
        raise RuntimeError("frozen handicap-contradiction stage gained ranking power")
    candidate_by_key = {
        (row["issue_instance"], row["portfolio_id"]): row for row in candidates
    }
    outcomes = {row["match_id"]: row for row in read_csv(OUTCOME_PATH)}
    if any(
        row["has_trusted_settlement"] != "1" or row["settlement_quality"] != "trusted"
        for row in outcomes.values()
    ):
        raise RuntimeError("untrusted canonical outcome row")
    chronology = {
        row["issue_instance"]: row["feature_cutoff_ts"]
        for row in read_csv(GATE_A / "issue_cutoff_registry.csv")
    }
    if len(chronology) != 189:
        raise RuntimeError("issue chronology denominator drift")
    return (
        active,
        candidate_by_key,
        chronology,
        {
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
        },
    )


def settle_rows(
    active: Sequence[dict[str, str]],
    candidates: dict[tuple[str, str], dict[str, str]],
    outcomes: dict[str, dict[str, str]] | None = None,
    chronology: dict[str, str] | None = None,
) -> list[dict[str, object]]:
    if outcomes is None:
        outcomes = {row["match_id"]: row for row in read_csv(OUTCOME_PATH)}
    chronology = chronology or {
        row["issue_instance"]: row["feature_cutoff_ts"]
        for row in read_csv(GATE_A / "issue_cutoff_registry.csv")
    }
    rows: list[dict[str, object]] = []
    for selection in active:
        candidate = candidates[
            (selection["issue_instance"], selection["selected_portfolio_id"])
        ]
        mids = candidate["selected_match_ids"].split("|")
        if (
            len(mids) != 7
            or selection["selected_identity_fingerprint"]
            != candidate["identity_fingerprint"]
        ):
            raise RuntimeError("selection/candidate identity mismatch")
        missing = [mid for mid in mids if mid not in outcomes]
        available = not missing
        sps = [float(outcomes[mid]["winning_sp"]) for mid in mids] if available else []
        economics = full_ticket_settlement(sps, available)
        stake = FULL_STAKE if available else 0.0
        gross = float(economics["gross_pre_tax_yuan"])
        tax = float(economics["tax_yuan"])
        rows.append(
            {
                "issue": selection["issue"],
                "year": selection["year"],
                "fold": selection["fold"],
                "issue_instance": selection["issue_instance"],
                "first_kickoff_ts": chronology[selection["issue_instance"]],
                "arm": selection["arm"],
                "arm_role": selection["arm_role"],
                "policy_status": "SETTLED"
                if available
                else "UNAVAILABLE_CANONICAL_OUTCOME",
                "choice_opportunity": selection["choice_opportunity"],
                "selected_portfolio_id": selection["selected_portfolio_id"],
                "selected_identity_fingerprint": selection[
                    "selected_identity_fingerprint"
                ],
                "selected_score": selection["selected_score"],
                "missing_match_ids": "|".join(sorted(missing)),
                "planned_ticket_count": FULL_TICKETS,
                "executed_ticket_count": FULL_TICKETS if available else 0,
                "planned_stake_yuan": fmt_money(FULL_STAKE),
                "stake_yuan": fmt_money(stake),
                "gross_pre_tax_yuan": fmt_money(gross),
                "tax_yuan": fmt_money(tax),
                "pre_tax_net_yuan": fmt_money(gross - stake),
                "tax_adjusted_net_yuan": fmt_money(gross - tax - stake),
                "hit_ticket_count": int(economics["hit_ticket_count"]),
                "gm_expected_sp": candidate[
                    {
                        "B0_BEST_FULL": "market_gm_e_sp",
                        "L1_LEAGUE_CORE": "league_gm_e_sp",
                        "T1_TEAM_CORE": "team_gm_e_sp",
                        "M1_MARKET_DYNAMICS": "market_dynamics_gm_e_sp",
                        "F1_CORE_ALL": "combined_gm_e_sp",
                        "D1_DECISION_CHAIN_CORE": "decision_f1_gm_e_sp",
                        "F_MINUS_L": "combined_minus_league_gm_e_sp",
                        "F_MINUS_T": "combined_minus_team_gm_e_sp",
                        "F_MINUS_M": "combined_minus_market_gm_e_sp",
                    }[selection["arm"]]
                ],
                "realized_winning_ticket_payout_yuan": fmt_money(gross),
            }
        )
    rows.sort(
        key=lambda row: (
            row["first_kickoff_ts"],
            row["issue_instance"],
            ARMS.index(str(row["arm"])),
        )
    )
    return rows


def totals(rows: Sequence[dict[str, object]]) -> dict[str, float]:
    fields = (
        "planned_ticket_count",
        "executed_ticket_count",
        "planned_stake_yuan",
        "stake_yuan",
        "gross_pre_tax_yuan",
        "tax_yuan",
        "pre_tax_net_yuan",
        "tax_adjusted_net_yuan",
        "hit_ticket_count",
    )
    return {field: sum(float(row[field]) for row in rows) for field in fields}


def quantile(values: Sequence[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return math.nan
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def build_draw_matrix(
    path: Path, issue_count: int, seed_offset: int
) -> tuple[array.array, dict[str, object]]:
    rng = random.Random(BOOTSTRAP_SEED + seed_offset)
    draws = array.array(
        "H",
        (rng.randrange(issue_count) for _ in range(BOOTSTRAP_REPLICATES * issue_count)),
    )
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            zipped.write(draws.tobytes())
    return draws, {
        "replicates": BOOTSTRAP_REPLICATES,
        "issue_count": issue_count,
        "seed": BOOTSTRAP_SEED + seed_offset,
        "sha256": sha256_file(path),
    }


def bootstrap_pair(
    candidate: Sequence[dict[str, object]],
    baseline: Sequence[dict[str, object]],
    draws: array.array,
) -> dict[str, float]:
    if len(candidate) != len(baseline) or not candidate:
        raise RuntimeError("paired bootstrap denominator mismatch")
    n = len(candidate)
    candidate_net = [float(row["pre_tax_net_yuan"]) for row in candidate]
    candidate_tax_net = [float(row["tax_adjusted_net_yuan"]) for row in candidate]
    base_net = [float(row["pre_tax_net_yuan"]) for row in baseline]
    stakes = [float(row["stake_yuan"]) for row in candidate]
    roi_values: list[float] = []
    lift_values: list[float] = []
    tax_roi_values: list[float] = []
    for rep in range(BOOTSTRAP_REPLICATES):
        start = rep * n
        idxs = draws[start : start + n]
        stake = sum(stakes[i] for i in idxs)
        roi_values.append(sum(candidate_net[i] for i in idxs) / stake)
        tax_roi_values.append(sum(candidate_tax_net[i] for i in idxs) / stake)
        lift_values.append(sum(candidate_net[i] - base_net[i] for i in idxs) / stake)
    return {
        "roi_ci_low": quantile(roi_values, 0.025),
        "roi_ci_high": quantile(roi_values, 0.975),
        "lift_ci_low": quantile(lift_values, 0.025),
        "lift_ci_high": quantile(lift_values, 0.975),
        "tax_roi_ci_low": quantile(tax_roi_values, 0.025),
        "tax_roi_ci_high": quantile(tax_roi_values, 0.975),
        "positive_lift_fraction": sum(value > 0 for value in lift_values)
        / len(lift_values),
    }


def choose_segment(
    rows: Sequence[dict[str, object]], segment: str
) -> list[dict[str, object]]:
    if segment == "ALL_189":
        return list(rows)
    wanted = "1" if segment == "CHOICE_113" else "0"
    return [row for row in rows if str(row["choice_opportunity"]) == wanted]


def primary_tables(
    rows: Sequence[dict[str, object]], stage: Path
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    by_arm = {arm: [row for row in rows if row["arm"] == arm] for arm in ARMS}
    summaries: list[dict[str, object]] = []
    bootstraps: list[dict[str, object]] = []
    draw_meta: dict[str, object] = {}
    for segment_index, segment in enumerate(SEGMENTS):
        segment_by_arm = {arm: choose_segment(by_arm[arm], segment) for arm in ARMS}
        base_by_issue = {
            row["issue_instance"]: row for row in segment_by_arm["B0_BEST_FULL"]
        }
        if (
            len(base_by_issue)
            != {"ALL_189": 189, "CHOICE_113": 113, "INVARIANT_76": 76}[segment]
        ):
            raise RuntimeError(f"segment denominator drift: {segment}")
        for arm in ARMS:
            native = segment_by_arm[arm]
            native_settled = [
                row for row in native if row["policy_status"] == "SETTLED"
            ]
            paired = [
                row
                for row in native
                if row["policy_status"] == "SETTLED"
                and base_by_issue[row["issue_instance"]]["policy_status"] == "SETTLED"
            ]
            base_paired = [base_by_issue[row["issue_instance"]] for row in paired]
            native_totals = totals(native_settled)
            paired_totals = totals(paired)
            base_totals = totals(base_paired)
            native_roi = safe_ratio(
                native_totals["pre_tax_net_yuan"], native_totals["stake_yuan"]
            )
            paired_roi = safe_ratio(
                paired_totals["pre_tax_net_yuan"], paired_totals["stake_yuan"]
            )
            base_roi = safe_ratio(
                base_totals["pre_tax_net_yuan"], base_totals["stake_yuan"]
            )
            tax_roi = safe_ratio(
                native_totals["tax_adjusted_net_yuan"], native_totals["stake_yuan"]
            )
            summaries.append(
                {
                    "segment": segment,
                    "arm": arm,
                    "arm_label": ARM_LABELS[arm],
                    "planned_issue_count": len(native),
                    "settled_native_issue_count": len(native_settled),
                    "unavailable_native_issue_count": len(native) - len(native_settled),
                    "paired_settled_issue_count": len(paired),
                    "choice_identity_changed_count": sum(
                        row["selected_identity_fingerprint"]
                        != base_by_issue[row["issue_instance"]][
                            "selected_identity_fingerprint"
                        ]
                        for row in native
                    ),
                    "stake_yuan": fmt_money(native_totals["stake_yuan"]),
                    "gross_pre_tax_yuan": fmt_money(
                        native_totals["gross_pre_tax_yuan"]
                    ),
                    "tax_yuan": fmt_money(native_totals["tax_yuan"]),
                    "no_tax_roi": fmt_ratio(native_roi),
                    "tax_adjusted_roi": fmt_ratio(tax_roi),
                    "paired_no_tax_roi": fmt_ratio(paired_roi),
                    "paired_b0_no_tax_roi": fmt_ratio(base_roi),
                    "paired_profit_lift_yuan": fmt_money(
                        paired_totals["pre_tax_net_yuan"]
                        - base_totals["pre_tax_net_yuan"]
                    ),
                    "paired_roi_lift": fmt_ratio(
                        None
                        if paired_roi is None or base_roi is None
                        else paired_roi - base_roi
                    ),
                    "coverage_hit_rate": fmt_ratio(
                        safe_ratio(
                            native_totals["hit_ticket_count"], len(native_settled)
                        )
                    ),
                    "ticket_hit_rate": fmt_ratio(
                        safe_ratio(
                            native_totals["hit_ticket_count"],
                            native_totals["executed_ticket_count"],
                        )
                    ),
                    "mean_gm_expected_sp": fmt_ratio(
                        statistics.fmean(
                            float(row["gm_expected_sp"]) for row in native_settled
                        )
                        if native_settled
                        else None
                    ),
                    "geometric_mean_gm_expected_sp": fmt_ratio(
                        math.exp(
                            statistics.fmean(
                                math.log(float(row["gm_expected_sp"]))
                                for row in native_settled
                            )
                        )
                        if native_settled
                        else None
                    ),
                    "realized_payout_yuan": fmt_money(
                        native_totals["gross_pre_tax_yuan"]
                    ),
                }
            )
            draw_path = (
                stage / f"bootstrap_draws_{segment.lower()}_{arm.lower()}.u16.gz"
            )
            draws, meta = build_draw_matrix(
                draw_path, len(paired), segment_index * 100 + ARMS.index(arm)
            )
            result = bootstrap_pair(paired, base_paired, draws)
            bootstraps.append(
                {
                    "segment": segment,
                    "arm": arm,
                    "paired_issue_count": len(paired),
                    **{key: fmt_ratio(value) for key, value in result.items()},
                    "replicates": BOOTSTRAP_REPLICATES,
                    "draw_matrix_sha256": meta["sha256"],
                }
            )
            draw_meta[f"{segment}/{arm}"] = meta
    return summaries, bootstraps, draw_meta


def identity_attribution(rows: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    by_arm_issue = {(row["arm"], row["issue_instance"]): row for row in rows}
    choice_issues = sorted(
        {row["issue_instance"] for row in rows if str(row["choice_opportunity"]) == "1"}
    )
    output = []
    for arm in ARMS:
        counts = defaultdict(int)
        changed = paired = 0
        lift = 0.0
        for issue in choice_issues:
            row = by_arm_issue[(arm, issue)]
            base = by_arm_issue[("B0_BEST_FULL", issue)]
            if (
                row["selected_identity_fingerprint"]
                == base["selected_identity_fingerprint"]
            ):
                counts["SAME_IDENTITY"] += 1
                continue
            changed += 1
            if row["policy_status"] != "SETTLED" or base["policy_status"] != "SETTLED":
                counts["UNAVAILABLE_PAIR"] += 1
                continue
            paired += 1
            delta = float(row["pre_tax_net_yuan"]) - float(base["pre_tax_net_yuan"])
            lift += delta
            counts["WIN" if delta > 1e-9 else "LOSS" if delta < -1e-9 else "TIE"] += 1
        output.append(
            {
                "arm": arm,
                "choice_issue_count": len(choice_issues),
                "identity_changed_count": changed,
                "same_identity_count": counts["SAME_IDENTITY"],
                "paired_changed_count": paired,
                "unavailable_changed_pair_count": counts["UNAVAILABLE_PAIR"],
                "win_count": counts["WIN"],
                "loss_count": counts["LOSS"],
                "tie_count": counts["TIE"],
                "paired_changed_profit_lift_yuan": fmt_money(lift),
                "paired_changed_roi_lift": fmt_ratio(
                    safe_ratio(lift, paired * FULL_STAKE)
                ),
            }
        )
    return output


def max_drawdown(path: Sequence[float]) -> tuple[float, float]:
    cumulative = peak = max_dd = 0.0
    worst_cumulative = 0.0
    for value in path:
        cumulative += value
        peak = max(peak, cumulative)
        max_dd = max(max_dd, peak - cumulative)
        worst_cumulative = min(worst_cumulative, cumulative)
    return max_dd, worst_cumulative


def risk_row(
    records: Sequence[dict[str, object]], basis: str, segment: str, arm: str
) -> dict[str, object]:
    net_field = "pre_tax_net_yuan" if basis == "PRE_TAX" else "tax_adjusted_net_yuan"
    active = [row for row in records if row["policy_status"] == "SETTLED"]
    nets = [float(row[net_field]) for row in active]
    stakes = [float(row["stake_yuan"]) for row in active]
    gross = [float(row["gross_pre_tax_yuan"]) for row in active]
    max_dd, worst_cum = max_drawdown(nets)
    bankroll = max(10_000.0, math.ceil((-2 * worst_cum + 1) / 10_000.0) * 10_000.0)
    returns = [net / bankroll for net in nets]
    years = {row["year"] for row in active}
    annual_frequency = len(active) / max(len(years), 1)
    mean_return = statistics.fmean(returns) if returns else 0.0
    stdev = statistics.stdev(returns) if len(returns) > 1 else 0.0
    downside = (
        math.sqrt(statistics.fmean(min(value, 0.0) ** 2 for value in returns))
        if returns
        else 0.0
    )
    sharpe = mean_return / stdev * math.sqrt(annual_frequency) if stdev else None
    sortino = mean_return / downside * math.sqrt(annual_frequency) if downside else None
    total_net = sum(nets)
    total_stake = sum(stakes)
    total_gross = sum(gross)
    elapsed_years = (
        max(
            (
                datetime.fromisoformat(str(active[-1]["first_kickoff_ts"]))
                - datetime.fromisoformat(str(active[0]["first_kickoff_ts"]))
            ).total_seconds()
            / (365.2425 * 86400),
            1 / 365.2425,
        )
        if len(active) > 1
        else 1.0
    )
    ending = bankroll + total_net
    cagr = (ending / bankroll) ** (1 / elapsed_years) - 1 if ending > 0 else None
    max_dd_pct = max_dd / bankroll
    payout_hhi = (
        sum((value / total_gross) ** 2 for value in gross) if total_gross else 0.0
    )
    top_issue_index = max(range(len(active)), key=lambda i: gross[i], default=None)
    year_gross = defaultdict(float)
    year_net = defaultdict(float)
    year_stake = defaultdict(float)
    for row in active:
        year_gross[str(row["year"])] += float(row["gross_pre_tax_yuan"])
        year_net[str(row["year"])] += float(row[net_field])
        year_stake[str(row["year"])] += float(row["stake_yuan"])
    top_year = max(year_gross, key=year_gross.get, default="")
    ex_issue_roi = safe_ratio(
        total_net - (nets[top_issue_index] if top_issue_index is not None else 0),
        total_stake - (stakes[top_issue_index] if top_issue_index is not None else 0),
    )
    ex_year_roi = (
        safe_ratio(total_net - year_net[top_year], total_stake - year_stake[top_year])
        if top_year
        else None
    )
    miss = longest = 0
    for row in active:
        if int(row["hit_ticket_count"]):
            miss = 0
        else:
            miss += 1
            longest = max(longest, miss)
    return {
        "segment": segment,
        "arm": arm,
        "basis": basis,
        "settled_issue_count": len(active),
        "research_bankroll_yuan": fmt_money(bankroll),
        "stake_yuan": fmt_money(total_stake),
        "net_yuan": fmt_money(total_net),
        "roi": fmt_ratio(safe_ratio(total_net, total_stake)),
        "annualized_sharpe": fmt_ratio(sharpe),
        "annualized_sortino": fmt_ratio(sortino),
        "cagr": fmt_ratio(cagr),
        "calmar": fmt_ratio(
            None if cagr is None or not max_dd_pct else cagr / max_dd_pct
        ),
        "max_drawdown_yuan": fmt_money(max_dd),
        "max_drawdown_pct": fmt_ratio(max_dd_pct),
        "longest_miss_streak": longest,
        "payout_issue_hhi": fmt_ratio(payout_hhi),
        "largest_payout_issue": active[top_issue_index]["issue_instance"]
        if top_issue_index is not None
        else "",
        "ex_largest_issue_roi": fmt_ratio(ex_issue_roi),
        "largest_payout_year": top_year,
        "ex_largest_year_roi": fmt_ratio(ex_year_roi),
    }


def stability_and_risk(
    rows: Sequence[dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    stability: list[dict[str, object]] = []
    risk: list[dict[str, object]] = []
    series: list[dict[str, object]] = []
    for segment in SEGMENTS:
        for arm in ARMS:
            selected = choose_segment(
                [row for row in rows if row["arm"] == arm], segment
            )
            for basis in ("PRE_TAX", "TAX_ADJUSTED"):
                risk.append(risk_row(selected, basis, segment, arm))
            for dimension in ("YEAR", "FOLD"):
                values = sorted({str(row[dimension.lower()]) for row in selected})
                for value in values:
                    subset = [
                        row
                        for row in selected
                        if str(row[dimension.lower()]) == value
                        and row["policy_status"] == "SETTLED"
                    ]
                    aggregate = totals(subset)
                    stability.append(
                        {
                            "segment": segment,
                            "arm": arm,
                            "view": dimension,
                            "excluded_value": "",
                            "included_value": value,
                            "settled_issue_count": len(subset),
                            "stake_yuan": fmt_money(aggregate["stake_yuan"]),
                            "no_tax_roi": fmt_ratio(
                                safe_ratio(
                                    aggregate["pre_tax_net_yuan"],
                                    aggregate["stake_yuan"],
                                )
                            ),
                            "tax_adjusted_roi": fmt_ratio(
                                safe_ratio(
                                    aggregate["tax_adjusted_net_yuan"],
                                    aggregate["stake_yuan"],
                                )
                            ),
                        }
                    )
            for year in sorted({str(row["year"]) for row in selected}):
                subset = [
                    row
                    for row in selected
                    if str(row["year"]) != year and row["policy_status"] == "SETTLED"
                ]
                aggregate = totals(subset)
                stability.append(
                    {
                        "segment": segment,
                        "arm": arm,
                        "view": "LOYO",
                        "excluded_value": year,
                        "included_value": "",
                        "settled_issue_count": len(subset),
                        "stake_yuan": fmt_money(aggregate["stake_yuan"]),
                        "no_tax_roi": fmt_ratio(
                            safe_ratio(
                                aggregate["pre_tax_net_yuan"], aggregate["stake_yuan"]
                            )
                        ),
                        "tax_adjusted_roi": fmt_ratio(
                            safe_ratio(
                                aggregate["tax_adjusted_net_yuan"],
                                aggregate["stake_yuan"],
                            )
                        ),
                    }
                )
            cumulative_pre = cumulative_tax = peak_pre = peak_tax = 0.0
            for index, row in enumerate(selected):
                cumulative_pre += float(row["pre_tax_net_yuan"])
                cumulative_tax += float(row["tax_adjusted_net_yuan"])
                peak_pre = max(peak_pre, cumulative_pre)
                peak_tax = max(peak_tax, cumulative_tax)
                series.append(
                    {
                        "segment": segment,
                        "arm": arm,
                        "issue_index": index,
                        "issue_instance": row["issue_instance"],
                        "first_kickoff_ts": row["first_kickoff_ts"],
                        "policy_status": row["policy_status"],
                        "cumulative_pre_tax_profit_yuan": fmt_money(cumulative_pre),
                        "pre_tax_drawdown_yuan": fmt_money(peak_pre - cumulative_pre),
                        "cumulative_tax_adjusted_profit_yuan": fmt_money(
                            cumulative_tax
                        ),
                        "tax_adjusted_drawdown_yuan": fmt_money(
                            peak_tax - cumulative_tax
                        ),
                    }
                )
    return stability, risk, series


def svg_lines(
    path: Path,
    title: str,
    series: Sequence[tuple[str, Sequence[float], str]],
    ylabel: str,
) -> None:
    width, height = 1200, 680
    left, top, right, bottom = 95, 70, 30, 100
    all_values = [value for _, values, _ in series for value in values] or [0.0]
    low, high = min(all_values + [0.0]), max(all_values + [0.0])
    span = high - low or 1.0

    def x(index: int, count: int) -> float:
        return left + (width - left - right) * index / max(count - 1, 1)

    def y(value: float) -> float:
        return top + (height - top - bottom) * (high - value) / span

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{left}" y="35" font-size="22" font-family="sans-serif">{title}</text>',
        f'<text x="20" y="{height / 2}" transform="rotate(-90 20 {height / 2})" font-size="13">{ylabel}</text>',
        f'<line x1="{left}" y1="{y(0):.2f}" x2="{width - right}" y2="{y(0):.2f}" stroke="#9ca3af"/>',
    ]
    for label, values, color in series:
        points = " ".join(
            f"{x(i, len(values)):.2f},{y(value):.2f}" for i, value in enumerate(values)
        )
        parts.append(
            f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{points}"/>'
        )
    for i, (label, _, color) in enumerate(series):
        lx = left + (i % 3) * 350
        ly = height - 64 + (i // 3) * 20
        parts.append(
            f'<line x1="{lx}" y1="{ly}" x2="{lx + 25}" y2="{ly}" stroke="{color}" stroke-width="3"/><text x="{lx + 31}" y="{ly + 4}" font-size="11">{label}</text>'
        )
    parts.append("</svg>\n")
    path.write_text("".join(parts), encoding="utf-8")


def write_charts(
    stage: Path,
    summary: Sequence[dict[str, object]],
    series_rows: Sequence[dict[str, object]],
) -> None:
    primary = [row for row in summary if row["segment"] == "ALL_189"]
    write_csv(stage / "chart_source_primary_comparison.csv", list(primary[0]), primary)
    selection = [
        {
            "arm": row["arm"],
            "identity_changed_count": row["choice_identity_changed_count"],
            "identity_unchanged_count": 113 - int(row["choice_identity_changed_count"]),
            "paired_roi_lift": row["paired_roi_lift"],
        }
        for row in primary
    ]
    write_csv(stage / "chart_source_selection_flow.csv", list(selection[0]), selection)
    colors = (
        "#1d4ed8",
        "#7c3aed",
        "#059669",
        "#d97706",
        "#dc2626",
        "#0891b2",
        "#4f46e5",
        "#65a30d",
        "#ea580c",
    )
    grouped = defaultdict(list)
    for row in series_rows:
        if row["segment"] == "ALL_189":
            grouped[row["arm"]].append(row)
    svg_lines(
        stage / "equity_curves_pre_tax.svg",
        "#134 FULL-N7 pre-tax equity",
        [
            (
                ARM_LABELS[arm],
                [float(row["cumulative_pre_tax_profit_yuan"]) for row in grouped[arm]],
                colors[i],
            )
            for i, arm in enumerate(ARMS)
        ],
        "Cumulative profit (CNY)",
    )
    svg_lines(
        stage / "drawdown_curves_pre_tax.svg",
        "#134 FULL-N7 pre-tax drawdown",
        [
            (
                ARM_LABELS[arm],
                [float(row["pre_tax_drawdown_yuan"]) for row in grouped[arm]],
                colors[i],
            )
            for i, arm in enumerate(ARMS)
        ],
        "Drawdown (CNY)",
    )


def report(
    summary: Sequence[dict[str, object]],
    attribution: Sequence[dict[str, object]],
    risk: Sequence[dict[str, object]],
) -> str:
    primary = [row for row in summary if row["segment"] == "ALL_189"]
    lines = [
        "# #134 Gate B — fundamental and decision-chain overlay",
        "",
        "## Primary result",
        "",
        "| Arm | Native settled | Pre-tax ROI | Paired B0 ROI | Paired lift | Tax-adjusted ROI | Identity changes |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in primary:
        lines.append(
            f"| {row['arm']} | {row['settled_native_issue_count']} | {float(row['no_tax_roi']):+.2%} | {float(row['paired_b0_no_tax_roi']):+.2%} | {float(row['paired_roi_lift']):+.2%} | {float(row['tax_adjusted_roi']):+.2%} | {row['choice_identity_changed_count']} |"
        )
    lines += [
        "",
        "Pre-tax ROI and paired profit lift versus B0 are primary. Tax-adjusted ROI is secondary. FULL N7 remains 2,187 independent CNY2 tickets per selected issue; tax is assessed per winning ticket.",
        "",
        "## Frozen decision-chain attribution",
        "",
        "The handicap-contradiction stage is identically zero across all 424 candidate identities and therefore has no ranking power. No selector, candidate, arm, threshold, identity, allocation or outcome rule was retuned in Gate B.",
        "",
        "## Identity-change outcome attribution",
        "",
        "| Arm | Changed | Paired | Win | Loss | Tie | Lift |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in attribution:
        lines.append(
            f"| {row['arm']} | {row['identity_changed_count']} | {row['paired_changed_count']} | {row['win_count']} | {row['loss_count']} | {row['tie_count']} | {float(row['paired_changed_roi_lift'] or 0):+.2%} |"
        )
    lines += [
        "",
        "## Risk",
        "",
        "YEAR/FOLD/LOYO, paired 20,000-replicate bootstrap intervals, ex-largest issue/year, payout HHI, issue-level Sharpe/Sortino/Calmar, percentage maximum drawdown and longest miss streak are published as manifest-covered tables. The accepted B0 incumbent remains the control even though its native pre-tax ROI is negative.",
        "",
        "This retrospective result grants no purchase, betting, execution, production or promotion authority.",
        "",
    ]
    return "\n".join(lines)


def package_identity(stage: Path, controls: dict[str, object]) -> tuple[str, str]:
    names = sorted(
        path.name
        for path in stage.iterdir()
        if path.is_file()
        and path.name not in {"CONTENT_IDENTITY.json", "SHA256SUMS.json"}
    )
    content = {
        "contract_version": VERSION,
        "controls": controls,
        "payloads": {name: sha256_file(stage / name) for name in names},
    }
    (stage / "CONTENT_IDENTITY.json").write_text(
        json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    sums = {
        path.name: sha256_file(path)
        for path in stage.iterdir()
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    (stage / "SHA256SUMS.json").write_text(
        json.dumps(sums, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return sha256_file(stage / "SHA256SUMS.json"), sha256_file(
        stage / "CONTENT_IDENTITY.json"
    )


def build(output: Path = DEFAULT_OUTPUT) -> dict[str, object]:
    output = output.resolve()
    if output.exists():
        raise RuntimeError(f"immutable output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.stage.", dir=output.parent))
    try:
        active, candidates, chronology, source_binding = load_inputs()
        outcomes = {row["match_id"]: row for row in read_csv(OUTCOME_PATH)}
        contributions = settle_rows(active, candidates, outcomes, chronology)
        b0 = [
            row
            for row in contributions
            if row["arm"] == "B0_BEST_FULL" and row["policy_status"] == "SETTLED"
        ]
        b0_totals = totals(b0)
        b0_roi = b0_totals["pre_tax_net_yuan"] / b0_totals["stake_yuan"]
        if (
            len(b0) != EXPECTED_B0_SETTLED
            or abs(b0_totals["stake_yuan"] - EXPECTED_B0_STAKE) > 5e-7
            or abs(b0_totals["gross_pre_tax_yuan"] - EXPECTED_B0_GROSS) > 5e-6
            or abs(b0_roi - EXPECTED_B0_ROI) > 1e-10
        ):
            raise RuntimeError(
                f"B0 accepted incumbent reproduction drift: settled={len(b0)} stake={b0_totals['stake_yuan']} gross={b0_totals['gross_pre_tax_yuan']} roi={b0_roi}"
            )
        summary, bootstraps, draw_meta = primary_tables(contributions, stage)
        attribution = identity_attribution(contributions)
        stability, risk, time_series = stability_and_risk(contributions)
        write_gzip(
            stage / "issue_contributions.csv.gz", list(contributions[0]), contributions
        )
        write_csv(stage / "primary_comparison.csv", list(summary[0]), summary)
        write_csv(
            stage / "identity_change_attribution.csv", list(attribution[0]), attribution
        )
        write_csv(
            stage / "bootstrap_paired_lift_20000.csv", list(bootstraps[0]), bootstraps
        )
        write_csv(stage / "stability_year_fold_loyo.csv", list(stability[0]), stability)
        write_csv(stage / "risk_metrics.csv", list(risk[0]), risk)
        write_gzip(
            stage / "issue_time_series.csv.gz", list(time_series[0]), time_series
        )
        source_bridge = [
            {
                "control": "B0_BEST_FULL",
                "expected_settled_issue_count": EXPECTED_B0_SETTLED,
                "actual_settled_issue_count": len(b0),
                "expected_stake_yuan": fmt_money(EXPECTED_B0_STAKE),
                "actual_stake_yuan": fmt_money(b0_totals["stake_yuan"]),
                "expected_gross_yuan": fmt_money(EXPECTED_B0_GROSS),
                "actual_gross_yuan": fmt_money(b0_totals["gross_pre_tax_yuan"]),
                "expected_no_tax_roi": fmt_ratio(EXPECTED_B0_ROI),
                "actual_no_tax_roi": fmt_ratio(b0_roi),
                "reconciliation_status": "PASS",
            }
        ]
        write_csv(
            stage / "source_reconciliation.csv", list(source_bridge[0]), source_bridge
        )
        (stage / "source_binding.json").write_text(
            json.dumps(source_binding, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        settlement_card = {
            "contract": CONTRACT,
            "version": VERSION,
            "gate_a_manifest_sha256": EXPECTED_GATE_A_MANIFEST,
            "gate_a_content_identity_sha256": EXPECTED_GATE_A_CONTENT,
            "canonical_outcome_manifest_sha256": EXPECTED_OUTCOME_MANIFEST,
            "canonical_outcome_join_sha256": EXPECTED_OUTCOME_PAYLOAD,
            "arm_count": len(ARMS),
            "active_issue_count": 189,
            "choice_issue_count": 113,
            "invariant_issue_count": 76,
            "contribution_row_count": len(contributions),
            "full_ticket_count": FULL_TICKETS,
            "stake_per_ticket_yuan": STAKE_PER_TICKET,
            "full_stake_per_issue_yuan": FULL_STAKE,
            "payout_factor": PAYOUT_FACTOR,
            "tax_rate": TAX_RATE,
            "tax_line_yuan_per_winning_ticket": TAX_LINE_YUAN,
            "bootstrap_replicates": BOOTSTRAP_REPLICATES,
            "bootstrap_draws": draw_meta,
            "handicap_contradiction_candidate_count": 424,
            "handicap_contradiction_leg_total": 0,
            "promotion_authority": False,
        }
        (stage / "settlement_card.json").write_text(
            json.dumps(settlement_card, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        write_charts(stage, summary, time_series)
        (stage / "REPORT.md").write_text(
            report(summary, attribution, risk), encoding="utf-8"
        )
        (stage / "README.md").write_text(
            "# #134 Gate B immutable outcome settlement\n\nSee `REPORT.md` and manifest-covered CSV/chart sources.\n",
            encoding="utf-8",
        )
        shutil.copy2(Path(__file__), stage / "settlement_runner.py")
        controls = {
            "gate_a_manifest_sha256": EXPECTED_GATE_A_MANIFEST,
            "outcome_manifest_sha256": EXPECTED_OUTCOME_MANIFEST,
            "active_issue_count": 189,
            "arms": list(ARMS),
            "segments": list(SEGMENTS),
            "full_tickets": FULL_TICKETS,
            "bootstrap_replicates": BOOTSTRAP_REPLICATES,
            "b0_reproduction_status": "PASS",
        }
        manifest_hash, content_hash = package_identity(stage, controls)
        os.rename(stage, output)
        return {
            "output": str(output),
            "manifest_sha256": manifest_hash,
            "content_identity_sha256": content_hash,
            "payload_count": len(json.loads((output / "SHA256SUMS.json").read_text())),
            "b0_no_tax_roi": b0_roi,
            "material_positive_all_189_arms": [
                row["arm"]
                for row in summary
                if row["segment"] == "ALL_189"
                and row["arm"] != "B0_BEST_FULL"
                and float(row["paired_roi_lift"]) > 0
            ],
        }
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(json.dumps(build(args.output), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
