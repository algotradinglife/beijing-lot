#!/usr/bin/env python3
"""One-shot canonical settlement of #105's accepted joint-N7 Gate-A freeze.

This runner deliberately consumes no selection inputs other than the accepted
immutable Gate-A package.  It binds one authenticated canonical final-outcome
payload, preserves every frozen frontier row (including no-bets and canonical
outcome gaps), applies the 0.65 factor once to a covered portfolio, and applies
the current 20% tax cliff after aggregating a paper policy's prizes by issue.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import shutil
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path

def repo_root(anchor: Path) -> Path:
    for item in (anchor.resolve().parent, *anchor.resolve().parents):
        if (item / ".git").exists():
            return item
    raise RuntimeError("repository root not found")


ROOT = repo_root(Path(__file__))
FREEZE = ROOT / "results" / "bj105_gate_a_preoutcome_v2r3"
OUTCOME_SOURCE = ROOT / "results" / "bj95_gate_b_outcome_settlement_v2r8"
OUT = ROOT / "results" / "bj105_gate_b_outcome_settlement_v1r2"

CONTRACT = "BJ-HIST-JOINT-N7-001"
EXPECTED_GATE_A_MANIFEST = "e11b24c31a86582aa254a7af7b7cbdc535547f82c018042253baec196d069912"
EXPECTED_GATE_A_CONTENT_IDENTITY = "c9555e069fd5e593001ebba9d651ed1f08d5619eb770a634f07987a568f6fd8b"
EXPECTED_OUTCOME_MANIFEST = "fbbd3b53bd86f4bb0caff8f2587933cd6b0e4e7d04fb0f709bac934ec2a705cc"
EXPECTED_OUTCOME_PAYLOAD = "13d709d253c31519734dbf0447e6961ac8a6060772975d7461741224e5251a89"
EXPECTED_FRONTIERS = 512_096
EXPECTED_ROLES = 415_800
EXPECTED_AVAILABLE = 13_027
FACTOR = Decimal("0.65")
UNIT_STAKE = Decimal(2)
TAX_RATE = Decimal("0.20")
TAX_THRESHOLD = Decimal("10000")
Q = Decimal("0.000001")
getcontext().prec = 128

FRONTIER_FIELDS = (
    "issue", "fold", "year", "pool_id", "threshold", "gm_threshold", "depth",
    "arm", "disposition", "selected_match_ids", "role_codes", "full_legs", "double_legs",
    "single_legs", "eligible_double_candidates", "gm_e_sp", "gm_top_predicted_sp",
    "expected_portfolio_mass", "formula_k", "candidate_stake_yuan", "active_k",
    "stake_yuan", "g_be_pre_tax", "descriptor_sha256",
)
ROLE_FIELDS = (
    "issue", "fold", "year", "pool_id", "threshold", "gm_threshold", "depth", "arm",
    "match_id", "match_idx", "role", "allowed_codes", "omitted_codes", "p_min", "p_max",
    "e_sp", "d_ratio", "q_max", "predicted_top_sp", "role_rank",
)
OUTCOME_FIELDS = (
    "match_id", "result_code", "winning_sp", "winning_sp_source", "settlement_quality",
    "has_trusted_settlement",
)
SETTLEMENT_FIELDS = (
    "issue", "fold", "year", "pool_id", "threshold", "gm_threshold", "depth", "arm",
    "gate_a_disposition", "settlement_status", "outcome_gap_count", "formula_k", "active_k",
    "stake_yuan", "full_legs", "double_legs", "single_legs", "expected_portfolio_mass", "coverage_hit", "deleted_upset_count",
    "truth_sequence", "final_winning_sp_product", "gross_pre_tax_yuan", "tax_bucket_gross_yuan",
    "tax_yuan", "after_tax_gross_yuan", "tax_adjusted_net_yuan", "gross_retention_vs_full_cover",
    "winning_sp_sources", "descriptor_sha256",
)
SUMMARY_FIELDS = (
    "scope", "scope_value", "threshold", "gm_threshold", "depth", "arm", "frontier_rows",
    "gate_a_available", "settled", "unavailable_canonical_outcome", "no_bet_gate_a", "total_k",
    "stake_yuan", "coverage_hits", "coverage_hit_rate", "mean_expected_coverage", "binomial_p_value",
    "binomial_ci_low", "binomial_ci_high", "issue_cluster_net_ci_low", "issue_cluster_net_ci_high",
    "deleted_upsets", "deleted_upset_rate", "gross_pre_tax_yuan", "tax_yuan", "after_tax_gross_yuan",
    "tax_adjusted_net_yuan", "tax_adjusted_roi", "max_drawdown_yuan", "longest_no_hit_streak",
    "best_payout_pool_id", "best_payout_gross_yuan", "ex_best_payout_net_yuan", "ex_best_payout_roi",
    "best_net_issue", "ex_best_issue_net_yuan", "ex_best_issue_roi", "positive_net_top_issue_share",
    "full_cover_gross_yuan", "gross_retention_vs_full_cover", "pool_count", "coverage_miss_pool_count",
    "unavailable_pool_count", "top_failure_issue_share",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def dec(value: object, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise RuntimeError(f"invalid decimal {label}: {value!r}") from error
    if not result.is_finite():
        raise RuntimeError(f"non-finite decimal {label}: {value!r}")
    return result


def money(value: Decimal) -> str:
    return format(value.quantize(Q), "f")


def ratio(value: Decimal | None) -> str:
    return "" if value is None else format(value, ".12f")


def binomial_log_pmf(successes: int, trials: int, probability: float) -> float:
    """Stable log PMF with no optional scientific-Python dependency."""
    if successes < 0 or successes > trials or not 0.0 < probability < 1.0:
        raise RuntimeError("invalid exact-binomial inputs")
    return (math.lgamma(trials + 1) - math.lgamma(successes + 1)
            - math.lgamma(trials - successes + 1) + successes * math.log(probability)
            + (trials - successes) * math.log1p(-probability))


def exact_binomial_two_sided(successes: int, trials: int, probability: float) -> float:
    """Exact two-sided probability-ordering test, matching the binomial test."""
    observed = binomial_log_pmf(successes, trials, probability)
    values = [binomial_log_pmf(index, trials, probability) for index in range(trials + 1)]
    return min(1.0, sum(math.exp(value) for value in values if value <= observed + 1e-12))


def wilson_interval(successes: int, trials: int) -> tuple[float, float]:
    """95% score interval; exact p-value above is the primary binomial test."""
    if not trials:
        return (0.0, 0.0)
    z = 1.959963984540054
    p = successes / trials
    scale = 1.0 + z*z/trials
    centre = (p + z*z/(2*trials)) / scale
    half = z * math.sqrt((p*(1-p) + z*z/(4*trials))/trials) / scale
    return max(0.0, centre-half), min(1.0, centre+half)


def write_csv(path: Path, fields: tuple[str, ...] | list[str], rows) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def verified_manifest(bundle: Path, expected: str) -> dict[str, str]:
    manifest_path = bundle / "SHA256SUMS.json"
    if sha256(manifest_path) != expected:
        raise RuntimeError(f"unaccepted manifest: {bundle}")
    declared = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = {
        item.name: sha256(item) for item in bundle.iterdir()
        if item.is_file() and item.name != manifest_path.name
    }
    if not isinstance(declared, dict) or declared != actual:
        raise RuntimeError(f"manifest coverage drift: {bundle}")
    return declared


def gzip_rows(path: Path, fields: tuple[str, ...]):
    handle = gzip.open(path, "rt", newline="", encoding="utf-8")
    reader = csv.DictReader(handle)
    if tuple(reader.fieldnames or ()) != fields:
        handle.close()
        raise RuntimeError(f"schema mismatch for {path}: {reader.fieldnames}")
    return handle, reader


def frontier_key(row: dict[str, str]) -> tuple[str, ...]:
    return tuple(row[name] for name in ("issue", "pool_id", "threshold", "gm_threshold", "depth", "arm"))


def tax_bucket(row: dict[str, str]) -> tuple[str, ...]:
    # Arms are counterfactual policies, never co-purchased. Within one policy,
    # all N7 prizes in the same issue/game belong to one paper claimant.
    return tuple(row[name] for name in ("issue", "threshold", "gm_threshold", "depth", "arm"))


def policy_key(row: dict[str, str]) -> tuple[str, ...]:
    return tuple(row[name] for name in ("threshold", "gm_threshold", "depth", "arm"))


def allocated_tax(gross: Decimal, bucket_total: Decimal) -> Decimal:
    """Allocate the policy/issue tax cliff without changing a zero-prize row."""
    if gross < 0 or bucket_total < 0:
        raise RuntimeError("negative gross cannot be taxed")
    return gross * TAX_RATE if bucket_total >= TAX_THRESHOLD else Decimal(0)


def validate_inputs() -> dict[str, str]:
    freeze = verified_manifest(FREEZE, EXPECTED_GATE_A_MANIFEST)
    if freeze.get("CONTENT_IDENTITY.json") != EXPECTED_GATE_A_CONTENT_IDENTITY:
        raise RuntimeError("Gate-A portable content identity drift")
    identity = json.loads((FREEZE / "CONTENT_IDENTITY.json").read_text(encoding="utf-8"))
    if identity.get("contract_version") != "bj105-portable-content-v2":
        raise RuntimeError("unexpected Gate-A content identity contract")
    outcomes = verified_manifest(OUTCOME_SOURCE, EXPECTED_OUTCOME_MANIFEST)
    if outcomes.get("canonical_outcome_join.csv") != EXPECTED_OUTCOME_PAYLOAD:
        raise RuntimeError("canonical outcome payload identity drift")
    card = json.loads((FREEZE / "gate_a_card.json").read_text(encoding="utf-8"))
    if card.get("contract") != CONTRACT or card.get("stage") != "GATE_A_OUTCOME_UNEXPOSED_JOINT_N7_FREEZE":
        raise RuntimeError("unexpected Gate-A contract")
    return {"gate_a_manifest_sha256": EXPECTED_GATE_A_MANIFEST,
            "gate_a_content_identity_sha256": EXPECTED_GATE_A_CONTENT_IDENTITY,
            "outcome_manifest_sha256": EXPECTED_OUTCOME_MANIFEST,
            "canonical_outcome_join_sha256": EXPECTED_OUTCOME_PAYLOAD}


def load_outcomes() -> dict[str, dict[str, str]]:
    path = OUTCOME_SOURCE / "canonical_outcome_join.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != OUTCOME_FIELDS:
            raise RuntimeError("canonical outcome schema drift")
        values = list(reader)
    outcomes = {row["match_id"]: row for row in values}
    if len(outcomes) != len(values):
        raise RuntimeError("duplicate canonical outcome match id")
    for row in outcomes.values():
        if (row["result_code"] not in {"3", "1", "0"} or row["settlement_quality"] != "trusted"
                or row["has_trusted_settlement"] != "1" or dec(row["winning_sp"], "winning SP") <= 0):
            raise RuntimeError("untrusted canonical outcome")
    return outcomes


def load_roles() -> dict[tuple[str, ...], list[dict[str, str]]]:
    grouped: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    handle, reader = gzip_rows(FREEZE / "role_assignments.csv.gz", ROLE_FIELDS)
    try:
        count = 0
        for row in reader:
            grouped[frontier_key(row)].append(row)
            count += 1
    finally:
        handle.close()
    if count != EXPECTED_ROLES:
        raise RuntimeError(f"role cardinality drift: {count}")
    for key, roles in grouped.items():
        roles.sort(key=lambda item: int(item["role_rank"]))
        if len(roles) != 7 or [item["role_rank"] for item in roles] != [str(n) for n in range(1, 8)]:
            raise RuntimeError(f"invalid frozen role geometry: {key}")
    return grouped


def settlement_geometry(frontier: dict[str, str], roles: list[dict[str, str]] | None,
                        outcomes: dict[str, dict[str, str]]) -> dict[str, object]:
    disposition = frontier["disposition"]
    formula_k = int(frontier["formula_k"])
    active_k = int(frontier["active_k"])
    frozen_stake = dec(frontier["stake_yuan"], "frozen stake")
    if disposition != "AVAILABLE":
        # FAIL_GM_GATE deliberately retains its frozen role construction for
        # diagnostic reproducibility, whereas UNAVAILABLE_THRESHOLD has none.
        # Neither is a bet: Gate A fixed active_k and stake to zero.
        if active_k != 0 or frozen_stake != 0:
            raise RuntimeError("non-available Gate-A row changed geometry")
        if disposition == "UNAVAILABLE_THRESHOLD" and roles:
            raise RuntimeError("threshold-unavailable row unexpectedly has roles")
        if disposition not in {"FAIL_GM_GATE", "UNAVAILABLE_THRESHOLD"}:
            raise RuntimeError(f"unknown Gate-A disposition: {disposition}")
        return {"status": "NO_BET_GATE_A", "active_k": 0, "stake": Decimal(0), "hit": "NO",
                "deleted_upsets": 0, "truth": "", "product": Decimal(0), "gross": Decimal(0),
                "gap_count": 0, "sources": ""}
    if roles is None or len(roles) != 7:
        raise RuntimeError("available row lacks frozen roles")
    expected_k = 1
    for role in roles:
        allowed = role["allowed_codes"]
        if not allowed or any(code not in "310" for code in allowed):
            raise RuntimeError("invalid frozen allowed code set")
        expected_k *= len(allowed)
    if expected_k != formula_k or active_k != formula_k or frozen_stake != UNIT_STAKE * formula_k:
        raise RuntimeError("frozen K/stake drift")
    missing = [role for role in roles if role["match_id"] not in outcomes]
    if missing:
        return {"status": "UNAVAILABLE_CANONICAL_OUTCOME", "active_k": 0, "stake": Decimal(0),
                "hit": "NO", "deleted_upsets": 0, "truth": "", "product": Decimal(0),
                "gross": Decimal(0), "gap_count": len(missing), "sources": ""}
    truth = []
    product = Decimal(1)
    sources = set()
    deleted_upsets = 0
    hit = True
    for role in roles:
        outcome = outcomes[role["match_id"]]
        code = outcome["result_code"]
        truth.append(code)
        product *= dec(outcome["winning_sp"], "final winning SP")
        sources.add(outcome["winning_sp_source"])
        hit = hit and code in role["allowed_codes"]
        if role["role"] == "DOUBLE" and code in role["omitted_codes"]:
            deleted_upsets += 1
    gross = UNIT_STAKE * FACTOR * product if hit else Decimal(0)
    return {"status": "SETTLED", "active_k": active_k, "stake": frozen_stake,
            "hit": "YES" if hit else "NO", "deleted_upsets": deleted_upsets,
            "truth": "".join(truth), "product": product, "gross": gross, "gap_count": 0,
            "sources": ";".join(sorted(sources))}


@dataclass
class Metric:
    key: tuple[str, ...]
    scope: str
    scope_value: str
    rows: int = 0
    gate_available: int = 0
    settled: int = 0
    unavailable: int = 0
    no_bet: int = 0
    k: int = 0
    stake: Decimal = Decimal(0)
    gross: Decimal = Decimal(0)
    tax: Decimal = Decimal(0)
    after_tax: Decimal = Decimal(0)
    net: Decimal = Decimal(0)
    hits: int = 0
    expected: Decimal = Decimal(0)
    deleted_upsets: int = 0
    double_legs: int = 0
    full_gross: Decimal = Decimal(0)
    pool_count: int = 0
    miss_pools: int = 0
    unavailable_pools: int = 0
    cumulative: Decimal = Decimal(0)
    peak: Decimal = Decimal(0)
    max_drawdown: Decimal = Decimal(0)
    streak: int = 0
    max_streak: int = 0
    best_payout_gross: Decimal = Decimal(-1)
    best_payout_net: Decimal = Decimal(0)
    best_payout_stake: Decimal = Decimal(0)
    best_payout_pool: str = ""
    issue_net: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    issue_stake: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    issue_failures: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def add(self, row: dict[str, str]) -> None:
        self.rows += 1
        status = row["settlement_status"]
        if row["gate_a_disposition"] == "AVAILABLE":
            self.gate_available += 1
        if status == "NO_BET_GATE_A":
            self.no_bet += 1
            return
        if status == "UNAVAILABLE_CANONICAL_OUTCOME":
            self.unavailable += 1
            self.unavailable_pools += 1
            self.issue_failures[row["issue"]] += 1
            return
        self.settled += 1
        self.pool_count += 1
        stake, gross, tax, after_tax, net = (dec(row[name], name) for name in
            ("stake_yuan", "gross_pre_tax_yuan", "tax_yuan", "after_tax_gross_yuan", "tax_adjusted_net_yuan"))
        self.k += int(row["active_k"])
        self.stake += stake; self.gross += gross; self.tax += tax; self.after_tax += after_tax; self.net += net
        self.expected += dec(row["expected_portfolio_mass"], "expected coverage")
        self.deleted_upsets += int(row["deleted_upset_count"])
        self.double_legs += int(row["double_legs"])
        if row["coverage_hit"] == "YES": self.hits += 1
        else:
            self.miss_pools += 1
            self.issue_failures[row["issue"]] += 1
        if row["arm"] == "FULL_COVER_CONTROL": self.full_gross += gross
        self.cumulative += net
        self.peak = max(self.peak, self.cumulative)
        self.max_drawdown = max(self.max_drawdown, self.peak - self.cumulative)
        self.streak = 0 if row["coverage_hit"] == "YES" else self.streak + 1
        self.max_streak = max(self.max_streak, self.streak)
        if gross > self.best_payout_gross:
            self.best_payout_gross, self.best_payout_net, self.best_payout_stake, self.best_payout_pool = gross, net, stake, row["pool_id"]
        self.issue_net[row["issue"]] += net
        self.issue_stake[row["issue"]] += stake

    def output(self) -> dict[str, object]:
        expected = self.expected / self.settled if self.settled else None
        exact_p = ci_low = ci_high = ""
        if self.settled and expected is not None and Decimal(0) < expected < Decimal(1):
            exact_p = format(exact_binomial_two_sided(self.hits, self.settled, float(expected)), ".12f")
            interval = wilson_interval(self.hits, self.settled)
            ci_low, ci_high = format(interval[0], ".12f"), format(interval[1], ".12f")
        issue_means = [float(value) for value in self.issue_net.values()]
        if len(issue_means) >= 2:
            average = sum(issue_means) / len(issue_means)
            variance = sum((value-average)**2 for value in issue_means) / (len(issue_means)-1)
            half = 1.96 * math.sqrt(variance / len(issue_means))
            issue_low, issue_high = money(Decimal(str(average-half))), money(Decimal(str(average+half)))
        else: issue_low = issue_high = ""
        best_issue = max(self.issue_net, key=self.issue_net.get, default="")
        best_issue_net = self.issue_net.get(best_issue, Decimal(0))
        best_issue_stake = self.issue_stake.get(best_issue, Decimal(0))
        positive = [max(Decimal(0), value) for value in self.issue_net.values()]
        positive_total = sum(positive, Decimal(0))
        total_failures = sum(self.issue_failures.values())
        return {
            "scope": self.scope, "scope_value": self.scope_value,
            "threshold": self.key[0], "gm_threshold": self.key[1], "depth": self.key[2], "arm": self.key[3],
            "frontier_rows": self.rows, "gate_a_available": self.gate_available, "settled": self.settled,
            "unavailable_canonical_outcome": self.unavailable, "no_bet_gate_a": self.no_bet, "total_k": self.k,
            "stake_yuan": money(self.stake), "coverage_hits": self.hits,
            "coverage_hit_rate": ratio(Decimal(self.hits)/self.settled) if self.settled else "",
            "mean_expected_coverage": ratio(expected), "binomial_p_value": exact_p, "binomial_ci_low": ci_low,
            "binomial_ci_high": ci_high, "issue_cluster_net_ci_low": issue_low, "issue_cluster_net_ci_high": issue_high,
            "deleted_upsets": self.deleted_upsets, "deleted_upset_rate": ratio(Decimal(self.deleted_upsets)/self.double_legs) if self.double_legs else "",
            "gross_pre_tax_yuan": money(self.gross), "tax_yuan": money(self.tax), "after_tax_gross_yuan": money(self.after_tax),
            "tax_adjusted_net_yuan": money(self.net), "tax_adjusted_roi": ratio(self.net/self.stake) if self.stake else "",
            "max_drawdown_yuan": money(self.max_drawdown), "longest_no_hit_streak": self.max_streak,
            "best_payout_pool_id": self.best_payout_pool, "best_payout_gross_yuan": money(max(self.best_payout_gross, Decimal(0))),
            "ex_best_payout_net_yuan": money(self.net-self.best_payout_net),
            "ex_best_payout_roi": ratio((self.net-self.best_payout_net)/(self.stake-self.best_payout_stake)) if self.stake > self.best_payout_stake else "",
            "best_net_issue": best_issue, "ex_best_issue_net_yuan": money(self.net-best_issue_net),
            "ex_best_issue_roi": ratio((self.net-best_issue_net)/(self.stake-best_issue_stake)) if self.stake > best_issue_stake else "",
            "positive_net_top_issue_share": ratio(max(positive, default=Decimal(0))/positive_total) if positive_total else "",
            "full_cover_gross_yuan": money(self.full_gross),
            "gross_retention_vs_full_cover": ratio(self.gross/self.full_gross) if self.full_gross else "",
            "pool_count": self.pool_count, "coverage_miss_pool_count": self.miss_pools, "unavailable_pool_count": self.unavailable_pools,
            "top_failure_issue_share": ratio(Decimal(max(self.issue_failures.values(), default=0)) / total_failures) if total_failures else "",
        }


def summary_metrics(rows_path: Path) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    all_metrics: dict[tuple[str, ...], Metric] = {}
    annual: dict[tuple[str, ...], Metric] = {}
    folds: dict[tuple[str, ...], Metric] = {}
    years: set[str] = set()
    with gzip.open(rows_path, "rt", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != SETTLEMENT_FIELDS: raise RuntimeError("settlement schema drift")
        for row in reader:
            key = policy_key(row); year = row["year"]; fold = row["fold"]; years.add(year)
            all_metrics.setdefault(key, Metric(key, "ALL", "ALL")).add(row)
            annual.setdefault((year,*key), Metric(key, "YEAR", year)).add(row)
            folds.setdefault((fold,*key), Metric(key, "FOLD", fold)).add(row)
    # Build one omitted-year population at a time. Holding every LOYO state at
    # once would duplicate large per-policy issue ledgers and defeat the
    # streaming/OOM-recovery purpose of this runner.
    loyo_out: list[dict[str, object]] = []
    for omitted in sorted(years):
        loyo: dict[tuple[str, ...], Metric] = {}
        with gzip.open(rows_path, "rt", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                if row["year"] == omitted:
                    continue
                key = policy_key(row)
                loyo.setdefault(key, Metric(key, "LEAVE_ONE_YEAR_OUT", omitted)).add(row)
        loyo_out.extend(metric.output() for _, metric in sorted(loyo.items()))
    return (attach_full_cover([metric.output() for _, metric in sorted(all_metrics.items())]),
            attach_full_cover([metric.output() for _, metric in sorted(annual.items())]),
            attach_full_cover([metric.output() for _, metric in sorted(folds.items())]),
            attach_full_cover(loyo_out))


def attach_full_cover(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Compare each frozen arm to its same-scope/same-threshold full control."""
    controls = {
        (row["scope"], row["scope_value"], row["threshold"], row["gm_threshold"]): dec(row["gross_pre_tax_yuan"], "control gross")
        for row in rows if row["arm"] == "FULL_COVER_CONTROL" and row["depth"] == "0"
    }
    for row in rows:
        control = controls.get((row["scope"], row["scope_value"], row["threshold"], row["gm_threshold"]), Decimal(0))
        row["full_cover_gross_yuan"] = money(control)
        row["gross_retention_vs_full_cover"] = ratio(dec(row["gross_pre_tax_yuan"], "gross") / control) if control else ""
    return rows


def per_code_calibration(rows_path: Path, roles: dict[tuple[str, ...], list[dict[str, str]]], outcomes: dict[str, dict[str, str]]) -> list[dict[str, object]]:
    values: dict[tuple[str, str], list[Decimal | int]] = defaultdict(lambda: [Decimal(0), 0, 0])
    with gzip.open(rows_path, "rt", newline="", encoding="utf-8") as handle:
        for settled in csv.DictReader(handle):
            if settled["settlement_status"] != "SETTLED": continue
            for role in roles[frontier_key(settled)]:
                if role["role"] != "DOUBLE" or len(role["omitted_codes"]) != 1: continue
                code = role["omitted_codes"]
                state = values[(role["role"], code)]
                state[0] += dec(role["p_min"], "p_min"); state[1] += 1
                state[2] += int(outcomes[role["match_id"]]["result_code"] == code)
    return [{"role": key[0], "omitted_code": key[1], "legs": int(value[1]),
             "mean_predicted_probability": ratio(value[0]/value[1]) if value[1] else "",
             "observed_frequency": ratio(Decimal(value[2])/value[1]) if value[1] else "",
             "observed_minus_predicted": ratio(Decimal(value[2])/value[1]-value[0]/value[1]) if value[1] else ""}
            for key, value in sorted(values.items())]


def decision(all_rows: list[dict[str, object]], annual: list[dict[str, object]], loyo: list[dict[str, object]]) -> dict[str, object]:
    candidates = []
    for row in all_rows:
        required = ("tax_adjusted_roi", "ex_best_payout_roi", "ex_best_issue_roi")
        if (row["arm"] == "FULL_COVER_CONTROL" or any(not row[name] for name in required)
                or Decimal(str(row["tax_adjusted_roi"])) <= 0):
            continue
        related = [item for item in [*annual, *loyo] if all(item[name] == row[name] for name in ("threshold","gm_threshold","depth","arm"))]
        robust = (Decimal(str(row["ex_best_payout_roi"])) > 0 and Decimal(str(row["ex_best_issue_roi"])) > 0
                  and related and all(item["tax_adjusted_roi"] and Decimal(str(item["tax_adjusted_roi"])) > 0 for item in related))
        if robust: candidates.append(row)
    return {"decision": "NO_PROMOTION" if not candidates else "NOMINATION",
            "rule": "Promotion requires positive tax-adjusted ALL, ex-best-payout, ex-best-issue, every annual and every leave-one-year-out ROI; a relative improvement with negative absolute ROI is not promotable.",
            "eligible_candidates": len(candidates)}


def main() -> int:
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args(); OUT = args.output.resolve()
    if OUT.exists(): raise SystemExit(f"refusing to overwrite immutable output: {OUT}")
    stage = Path(tempfile.mkdtemp(prefix="bj105_gate_b_", dir=OUT.parent))
    try:
        provenance = validate_inputs(); outcomes = load_outcomes(); roles = load_roles()
        pre_tax = stage / "_pre_tax.csv"; bucket_gross: dict[tuple[str, ...], Decimal] = defaultdict(Decimal)
        controls: dict[tuple[str, ...], Decimal] = {}
        with pre_tax.open("w", newline="", encoding="utf-8") as handle:
            fields = list(SETTLEMENT_FIELDS[:-6]) + ["gross_retention_vs_full_cover", "winning_sp_sources", "descriptor_sha256"]
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n"); writer.writeheader()
            input_handle, frontiers = gzip_rows(FREEZE / "joint_n7_frontier.csv.gz", FRONTIER_FIELDS)
            try:
                count = 0; available = 0
                for frontier in frontiers:
                    geometry = settlement_geometry(frontier, roles.get(frontier_key(frontier)), outcomes)
                    if frontier["disposition"] == "AVAILABLE": available += 1
                    key = (frontier["issue"], frontier["pool_id"], frontier["threshold"], frontier["gm_threshold"])
                    if frontier["arm"] == "FULL_COVER_CONTROL" and frontier["depth"] == "0": controls[key] = geometry["gross"]
                    if geometry["status"] == "SETTLED": bucket_gross[tax_bucket(frontier)] += geometry["gross"]
                    control = controls.get(key, Decimal(0))
                    writer.writerow({"issue": frontier["issue"], "fold": frontier["fold"], "year": frontier["year"], "pool_id": frontier["pool_id"], "threshold": frontier["threshold"], "gm_threshold": frontier["gm_threshold"], "depth": frontier["depth"], "arm": frontier["arm"], "gate_a_disposition": frontier["disposition"], "settlement_status": geometry["status"], "outcome_gap_count": geometry["gap_count"], "formula_k": frontier["formula_k"], "active_k": geometry["active_k"], "stake_yuan": money(geometry["stake"]), "full_legs": frontier["full_legs"] or "0", "double_legs": frontier["double_legs"] or "0", "single_legs": frontier["single_legs"] or "0", "expected_portfolio_mass": frontier["expected_portfolio_mass"] or "", "coverage_hit": geometry["hit"], "deleted_upset_count": geometry["deleted_upsets"], "truth_sequence": geometry["truth"], "final_winning_sp_product": money(geometry["product"]), "gross_pre_tax_yuan": money(geometry["gross"]), "gross_retention_vs_full_cover": ratio(geometry["gross"]/control) if control else "", "winning_sp_sources": geometry["sources"], "descriptor_sha256": frontier["descriptor_sha256"]})
                    count += 1
            finally: input_handle.close()
        if count != EXPECTED_FRONTIERS or available != EXPECTED_AVAILABLE: raise RuntimeError("frontier cardinality or available count drift")
        with pre_tax.open(newline="", encoding="utf-8") as source, gzip.GzipFile(filename="", mode="wb", fileobj=(stage / "portfolio_settlement.csv.gz").open("wb"), mtime=0) as raw:
            text = raw  # csv accepts text wrapper below; keep gzip mtime deterministic.
            import io
            target = io.TextIOWrapper(text, newline="", encoding="utf-8")
            reader = csv.DictReader(source); writer = csv.DictWriter(target, fieldnames=SETTLEMENT_FIELDS, lineterminator="\n"); writer.writeheader()
            statuses: dict[str, int] = defaultdict(int)
            for row in reader:
                bucket = tax_bucket(row); bucket_total = bucket_gross[bucket]
                gross = dec(row["gross_pre_tax_yuan"], "gross")
                tax = allocated_tax(gross, bucket_total)
                after_tax = gross-tax; net = after_tax-dec(row["stake_yuan"], "stake")
                writer.writerow({**row, "tax_bucket_gross_yuan": money(bucket_total), "tax_yuan": money(tax), "after_tax_gross_yuan": money(after_tax), "tax_adjusted_net_yuan": money(net)})
                statuses[row["settlement_status"]] += 1
            target.flush(); target.detach()
        if statuses["SETTLED"] + statuses["UNAVAILABLE_CANONICAL_OUTCOME"] + statuses["NO_BET_GATE_A"] != EXPECTED_FRONTIERS: raise RuntimeError("settlement status cardinality drift")
        all_rows, annual, folds, loyo = summary_metrics(stage / "portfolio_settlement.csv.gz")
        calibrations = per_code_calibration(stage / "portfolio_settlement.csv.gz", roles, outcomes)
        write_csv(stage / "frontier_summary.csv", SUMMARY_FIELDS, all_rows)
        write_csv(stage / "annual_summary.csv", SUMMARY_FIELDS, annual)
        write_csv(stage / "fold_summary.csv", SUMMARY_FIELDS, folds)
        write_csv(stage / "leave_one_year_out_summary.csv", SUMMARY_FIELDS, loyo)
        write_csv(stage / "per_code_calibration.csv", ("role","omitted_code","legs","mean_predicted_probability","observed_frequency","observed_minus_predicted"), calibrations)
        concentration_fields = ("threshold", "gm_threshold", "depth", "arm", "gate_a_available", "settled",
                                "unavailable_canonical_outcome", "coverage_miss_pool_count", "top_failure_issue_share")
        write_csv(stage / "pool_failure_concentration.csv", concentration_fields,
                  [{field: row[field] for field in concentration_fields} for row in all_rows])
        shutil.copyfile(OUTCOME_SOURCE / "canonical_outcome_join.csv", stage / "canonical_outcome_join.csv")
        settled_decision = decision(all_rows, annual, loyo)
        (stage / "decision.json").write_text(json.dumps(settled_decision, indent=2, sort_keys=True)+"\n", encoding="utf-8")
        shutil.copyfile(__file__, stage / "settlement_runner.py")
        card = {"issue": 105, "contract": CONTRACT, "stage": "GATE_B_ONE_SHOT_CANONICAL_OUTCOME_SETTLEMENT", "provenance": provenance,
                "input_freeze": str(FREEZE.relative_to(ROOT)), "outcome_source": str((OUTCOME_SOURCE / "canonical_outcome_join.csv").relative_to(ROOT)),
                "row_counts": {"frontiers": EXPECTED_FRONTIERS, "gate_a_available": EXPECTED_AVAILABLE, **dict(sorted(statuses.items()))},
                "settlement_rule": "For a settled frozen portfolio, hit iff every final result lies in its frozen allowed set; gross=2*0.65*product(final winning SP) on hit, else 0. K and stake are frozen outputs, never eligibility gates.",
                "tax_rule": "Counterfactual policies are separate. Aggregate that policy's gross prizes by issue/game before tax; if bucket gross is at least 10000 yuan, apply 20% to all gross in the bucket. Tax is allocated proportionally to its winning portfolios.",
                "availability_rule": "All Gate-A rows stay in the denominator. Rows with a selected frozen portfolio but missing canonical outcomes are UNAVAILABLE_CANONICAL_OUTCOME with zero stake and no alternate outcome source.",
                "scope": "historical paper research only; no purchase, production, or promotion recommendation."}
        (stage / "settlement_card.json").write_text(json.dumps(card, indent=2, sort_keys=True)+"\n", encoding="utf-8")
        (stage / "README.md").write_text("# #105 Gate B\n\nRun `python settlement_runner.py --output <empty-directory>` from any checkout containing the two authenticated input packages.\n", encoding="utf-8")
        (stage / "_pre_tax.csv").unlink()
        manifest = {item.name: sha256(item) for item in sorted(stage.iterdir()) if item.is_file()}
        (stage / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2, sort_keys=True)+"\n", encoding="utf-8")
        os.replace(stage, OUT)
        print(json.dumps({"output": str(OUT), "manifest_sha256": sha256(OUT / "SHA256SUMS.json"), "status_counts": dict(sorted(statuses.items())), "decision": settled_decision["decision"]}, sort_keys=True))
        return 0
    except Exception:
        shutil.rmtree(stage, ignore_errors=True); raise


if __name__ == "__main__":
    raise SystemExit(main())
