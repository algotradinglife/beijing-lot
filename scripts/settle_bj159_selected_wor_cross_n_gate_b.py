#!/usr/bin/env python3
"""Canonical Gate-B settlement for #159's accepted cross-N WOR freeze.

The runner verifies the immutable Gate-A package before opening the canonical
final-outcome join.  It settles complete identities only, aggregates reporting
by complete lottery issue, and treats every winning ¥2 ticket as an independent
tax unit.  No issue/policy pooling can create a tax charge.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import itertools
import json
import math
import os
import random
import shutil
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path


CONTRACT = "BJ-HIST-SELECTED-WOR-CROSS-N-001"
VERSION = "bj159-gate-b-v2"
FREEZE_MANIFEST = "a15c585fc1836da4f558d07ce19c925561bfd1c240e834b7e3e0da22701cd325"
OUTCOME_MANIFEST = "fbbd3b53bd86f4bb0caff8f2587933cd6b0e4e7d04fb0f709bac934ec2a705cc"
OUTCOME_PAYLOAD = "13d709d253c31519734dbf0447e6961ac8a6060772975d7461741224e5251a89"
N_GRID = tuple(range(2, 11))
M_GRID = (32, 64, 128)
SEEDS = ("137001", "137002", "137003")
CODES = ("3", "1", "0")
UNIT_STAKE = Decimal("2")
PAYOUT_FACTOR = Decimal("0.65")
TAX_RATE = Decimal("0.20")
TAX_THRESHOLD = Decimal("10000")
MONEY_Q = Decimal("0.000001")
BOOTSTRAP_REPLICATES = 1000
getcontext().prec = 96

OUTCOME_FIELDS = ("match_id", "result_code", "winning_sp", "winning_sp_source", "settlement_quality", "has_trusted_settlement")
IDENTITY_FIELDS = (
    "identity_id", "issue", "fold", "year", "issue_instance", "source_pool_ids", "source_segment_indices", "n",
    "candidate_match_id", "candidate_rank_in_issue", "candidate_count_in_issue", "candidate_search_count",
    "candidate_cap_applied", "selected_match_ids", "selected_n", "selected_source_pool_count", "gm_e_sp", "selection_scope",
    "selection_rule", "source_variant", "descriptor_sha256", "outcome_boundary",
)
ROLE_FIELDS = (
    "identity_id", "issue", "fold", "year", "issue_instance", "source_pool_id", "source_segment_index", "n", "match_id",
    "match_idx", "kickoff_ts", "selection_rank", "is_candidate", "e_sp", "p_min", "p3", "p1", "p0",
    "q3", "q1", "q0", "q_weight3", "q_weight1", "q_weight0", "predicted_sp3", "predicted_sp1",
    "predicted_sp0", "outcome_boundary",
)
PART_FIELDS = ("issue", "fold", "year", "issue_instance", "n", "source_pool_count", "available_pool_count", "selected_identity_count", "selected_identity_ids", "selection_status", "planned_M_values", "effective_M_by_n", "planned_seed_values", "complete_issue_unit", "outcome_boundary")
IDENTITY_SETTLEMENT_FIELDS = (
    "identity_id", "issue", "fold", "year", "issue_instance", "n", "M", "nominal_M", "effective_M", "seed", "saturation_status", "allocation_equivalence_key", "settlement_status", "outcome_gap_count",
    "planned_draw_count", "executed_draw_count", "stake_yuan", "unique_ticket_count", "duplicate_ticket_count", "duplicate_ticket_ratio",
    "truth_sequence", "truth_ordinal", "truth_rank", "coverage_hit", "winning_ticket_count", "gm_e_sp", "expected_sp_product_q",
    "actual_winning_sp_product", "gross_pre_tax_yuan", "taxable_winning_ticket_count", "tax_yuan", "after_tax_gross_yuan",
    "pre_tax_net_yuan", "tax_adjusted_net_yuan", "no_tax_roi", "tax_adjusted_roi", "allocation_fingerprint", "winning_sp_sources",
)
ISSUE_SETTLEMENT_FIELDS = (
    "issue", "fold", "year", "issue_instance", "n", "M", "nominal_M", "effective_M", "seed", "saturation_status", "selection_status", "planned_identity_count", "settled_identity_count",
    "unavailable_identity_count", "planned_draw_count", "executed_draw_count", "planned_stake_yuan", "stake_yuan", "full_control_stake_yuan",
    "unique_ticket_count", "duplicate_ticket_count", "hit_identity_count", "winning_ticket_count", "coverage_hit", "gross_pre_tax_yuan",
    "taxable_winning_ticket_count", "tax_yuan", "after_tax_gross_yuan", "pre_tax_net_yuan", "tax_adjusted_net_yuan", "no_tax_roi",
    "tax_adjusted_roi", "gm_expected_sp_mean", "expected_sp_product_q_mean", "actual_winning_sp_product_mean", "tax_line_share",
    "largest_identity_gross_yuan", "first_kickoff_ts",
)
SUMMARY_FIELDS = (
    "scope", "scope_value", "n", "M", "nominal_M", "effective_M", "seed", "saturation_status", "frozen_issue_count", "frozen_available_issue_count", "frozen_no_bet_issue_count",
    "settled_issue_count", "unavailable_outcome_issue_count", "planned_identity_count", "settled_identity_count", "planned_draw_count",
    "executed_draw_count", "planned_stake_yuan", "stake_yuan", "full_control_stake_yuan", "capital_utilization_vs_full", "stake_mean_yuan",
    "stake_p50_yuan", "stake_p90_yuan", "stake_p95_yuan", "stake_max_yuan", "unique_ticket_count", "duplicate_ticket_count",
    "duplicate_ticket_ratio", "winning_ticket_count", "hit_identity_count", "coverage_hit_rate", "ticket_hit_rate", "gross_pre_tax_yuan",
    "taxable_winning_ticket_count", "tax_line_share", "tax_yuan", "after_tax_gross_yuan", "pre_tax_net_yuan", "tax_adjusted_net_yuan",
    "no_tax_roi", "tax_adjusted_roi", "gm_expected_sp_mean", "expected_sp_product_q_mean", "actual_winning_sp_product_mean",
    "gross_top_issue_share", "gross_issue_hhi", "largest_issue", "largest_issue_gross_yuan", "ex_largest_issue_roi", "max_drawdown_yuan",
    "longest_miss_streak",
)
BOOT_FIELDS = ("n", "M", "nominal_M", "effective_M", "seed", "saturation_status", "metric", "support_issue_count", "replicates", "point_estimate", "ci95_low", "ci95_high", "positive_fraction")
DELTA_FIELDS = ("n", "M", "nominal_M", "effective_M", "n7_nominal_M", "n7_effective_M", "seed", "common_issue_count", "n_stake_yuan", "n7_stake_yuan", "n_no_tax_roi", "n7_no_tax_roi", "no_tax_roi_delta", "n_tax_adjusted_roi", "n7_tax_adjusted_roi", "tax_adjusted_roi_delta", "rule")
OVERLAP_FIELDS = ("n", "identity_count", "issue_count", "pair_count", "mean_shared_leg_count", "max_shared_leg_count", "mean_jaccard", "max_jaccard", "duplicate_ticket_policy")
SOURCE_FIELDS = ("source", "role", "identity", "sha256", "rows", "join_status")


def repository_root(anchor: Path) -> Path:
    for candidate in (anchor.resolve().parent, *anchor.resolve().parents):
        if (candidate / ".git").exists() and (candidate / "results").is_dir():
            return candidate
    raise RuntimeError("repository root unavailable")


ROOT = repository_root(Path(__file__))
FREEZE = ROOT / "results" / "bj159_gate_a_preoutcome_v2r1"
OUTCOME_SOURCE = ROOT / "results" / "bj95_gate_b_outcome_settlement_v2r8"
OUTPUT = ROOT / "results" / "bj159_gate_b_outcome_settlement_v2"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def dec(value: object, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise RuntimeError(f"invalid {label}: {value!r}") from error
    if not result.is_finite():
        raise RuntimeError(f"non-finite {label}: {value!r}")
    return result


def money(value: Decimal) -> str:
    return format(value.quantize(MONEY_Q), "f")


def ratio(value: Decimal | float | None) -> str:
    return "" if value is None else f"{float(value):.12f}"


def verified_bundle(path: Path, expected: str) -> dict[str, str]:
    manifest_path = path / "SHA256SUMS.json"
    if not manifest_path.is_file() or sha256(manifest_path) != expected:
        raise RuntimeError(f"unaccepted immutable package: {path}")
    declared = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = {p.name: sha256(p) for p in path.iterdir() if p.is_file() and p.name != manifest_path.name}
    if declared != actual:
        raise RuntimeError(f"manifest coverage drift: {path}")
    return declared


def gzip_writer(path: Path, fields: tuple[str, ...]):
    raw = path.open("wb")
    zipped = gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0)
    text = io.TextIOWrapper(zipped, encoding="utf-8", newline="")
    writer = csv.DictWriter(text, fieldnames=fields, lineterminator="\n", extrasaction="raise")
    writer.writeheader()
    return raw, zipped, text, writer


def close_gzip(handles) -> None:
    raw, zipped, text, _ = handles
    text.flush(); text.detach(); zipped.close(); raw.close()


def write_csv(path: Path, fields: tuple[str, ...], rows) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n", extrasaction="raise")
        writer.writeheader(); writer.writerows(rows)


def stable_uniform(*parts: object) -> float:
    value = int.from_bytes(hashlib.sha256("|".join(str(p) for p in parts).encode()).digest()[:8], "big")
    return (value + 0.5) / (2 ** 64)


def ticket_code(ordinal: int, n: int) -> str:
    digits = ["3"] * n
    value = ordinal
    for index in range(n - 1, -1, -1):
        digits[index] = CODES[value % 3]; value //= 3
    return "".join(digits)


def truth_ordinal(code: str) -> int:
    result = 0
    for value in code:
        result = result * 3 + CODES.index(value)
    return result


def ticket_tax(gross: Decimal) -> Decimal:
    return gross * TAX_RATE if gross >= TAX_THRESHOLD else Decimal(0)


def allocation_rank(weights: tuple[float, ...], seed: str, signature: str, n: int) -> tuple[int, ...]:
    keys: list[tuple[float, int]] = []
    for ordinal, weight in enumerate(weights):
        if weight <= 0:
            key = math.inf
        else:
            key = -math.log(max(stable_uniform("bj137", "WOR", seed, signature, ordinal), 1e-18)) / weight
        keys.append((key, ordinal))
    return tuple(ordinal for _, ordinal in sorted(keys))


def quantile(values: list[Decimal], q: float) -> Decimal:
    if not values: return Decimal(0)
    return sorted(values)[max(0, min(len(values) - 1, math.ceil(len(values) * q) - 1))]


@dataclass
class IssueAgg:
    issue: str
    fold: str
    year: str
    issue_instance: str
    n: int
    m: int
    nominal_m: int
    saturation_status: str
    seed: str
    selection_status: str
    planned_identities: int
    first_kickoff_ts: str = ""
    settled: int = 0
    unavailable: int = 0
    planned_draws: int = 0
    executed_draws: int = 0
    planned_stake: Decimal = Decimal(0)
    stake: Decimal = Decimal(0)
    full_stake: Decimal = Decimal(0)
    unique: int = 0
    duplicate: int = 0
    hit_identities: int = 0
    wins: int = 0
    gross: Decimal = Decimal(0)
    taxable_wins: int = 0
    tax: Decimal = Decimal(0)
    after_tax: Decimal = Decimal(0)
    pre_net: Decimal = Decimal(0)
    tax_net: Decimal = Decimal(0)
    gm_sum: Decimal = Decimal(0)
    expected_sp_sum: Decimal = Decimal(0)
    actual_sp_sum: Decimal = Decimal(0)
    largest_identity_gross: Decimal = Decimal(0)
    hit_any: bool = False

    def add(self, row: dict[str, str]) -> None:
        self.planned_draws += int(row["planned_draw_count"])
        self.executed_draws += int(row["executed_draw_count"])
        self.planned_stake += dec(row["planned_draw_count"], "planned draws") * UNIT_STAKE
        self.stake += dec(row["stake_yuan"], "stake")
        self.full_stake += dec(row["planned_draw_count"], "full draws") * (Decimal(3) ** self.n) / dec(row["effective_M"], "effective M") * UNIT_STAKE
        self.unique += int(row["unique_ticket_count"]); self.duplicate += int(row["duplicate_ticket_count"])
        if row["settlement_status"] == "SETTLED":
            self.settled += 1; self.hit_identities += row["coverage_hit"] == "YES"; self.hit_any |= row["coverage_hit"] == "YES"
            self.wins += int(row["winning_ticket_count"]); self.gross += dec(row["gross_pre_tax_yuan"], "gross")
            self.taxable_wins += int(row["taxable_winning_ticket_count"]); self.tax += dec(row["tax_yuan"], "tax")
            self.after_tax += dec(row["after_tax_gross_yuan"], "after-tax gross"); self.pre_net += dec(row["pre_tax_net_yuan"], "pre-tax net"); self.tax_net += dec(row["tax_adjusted_net_yuan"], "tax net")
            self.gm_sum += dec(row["gm_e_sp"], "GM E_SP"); self.expected_sp_sum += dec(row["expected_sp_product_q"], "expected SP product")
            if row["actual_winning_sp_product"]: self.actual_sp_sum += dec(row["actual_winning_sp_product"], "actual SP product")
            self.largest_identity_gross = max(self.largest_identity_gross, dec(row["gross_pre_tax_yuan"], "gross"))
        else:
            self.unavailable += 1

    def as_row(self) -> dict[str, object]:
        coverage = Decimal(self.hit_identities) / self.settled if self.settled else None
        stake = self.stake
        return {"issue": self.issue, "fold": self.fold, "year": self.year, "issue_instance": self.issue_instance, "n": self.n, "M": self.nominal_m, "nominal_M": self.nominal_m, "effective_M": self.m, "seed": self.seed, "saturation_status": self.saturation_status, "selection_status": self.selection_status, "planned_identity_count": self.planned_identities, "settled_identity_count": self.settled, "unavailable_identity_count": self.unavailable, "planned_draw_count": self.planned_draws, "executed_draw_count": self.executed_draws, "planned_stake_yuan": money(self.planned_stake), "stake_yuan": money(stake), "full_control_stake_yuan": money(self.full_stake), "unique_ticket_count": self.unique, "duplicate_ticket_count": self.duplicate, "hit_identity_count": self.hit_identities, "winning_ticket_count": self.wins, "coverage_hit": "YES" if self.hit_any else "NO", "gross_pre_tax_yuan": money(self.gross), "taxable_winning_ticket_count": self.taxable_wins, "tax_yuan": money(self.tax), "after_tax_gross_yuan": money(self.after_tax), "pre_tax_net_yuan": money(self.pre_net), "tax_adjusted_net_yuan": money(self.tax_net), "no_tax_roi": ratio(self.pre_net / stake if stake else None), "tax_adjusted_roi": ratio(self.tax_net / stake if stake else None), "gm_expected_sp_mean": ratio(self.gm_sum / self.settled if self.settled else None), "expected_sp_product_q_mean": ratio(self.expected_sp_sum / self.settled if self.settled else None), "actual_winning_sp_product_mean": ratio(self.actual_sp_sum / self.hit_identities if self.hit_identities else None), "tax_line_share": ratio(Decimal(self.taxable_wins) / self.wins if self.wins else None), "largest_identity_gross_yuan": money(self.largest_identity_gross), "first_kickoff_ts": self.first_kickoff_ts}


def validate_inputs() -> dict[str, str]:
    freeze = verified_bundle(FREEZE, FREEZE_MANIFEST)
    card = json.loads((FREEZE / "gate_a_card.json").read_text(encoding="utf-8"))
    if card.get("contract") != CONTRACT or card.get("stage") != "GATE_A_OUTCOME_UNEXPOSED_SELECTED_BASELINE_CROSS_N_FREEZE":
        raise RuntimeError("Gate-A contract drift")
    if card.get("selection", {}).get("n_grid") != list(N_GRID): raise RuntimeError("N grid drift")
    sampling = card.get("sampling", {})
    if sampling.get("nominal_M_grid") != list(M_GRID): raise RuntimeError("nominal M grid drift")
    if "effective_M=min(nominal_M,3^N)" not in sampling.get("saturation_rule", ""): raise RuntimeError("saturation rule drift")
    outcome = verified_bundle(OUTCOME_SOURCE, OUTCOME_MANIFEST)
    if outcome.get("canonical_outcome_join.csv") != OUTCOME_PAYLOAD: raise RuntimeError("canonical outcome payload drift")
    return {"gate_a_manifest_sha256": FREEZE_MANIFEST, "gate_a_content_identity_sha256": freeze["CONTENT_IDENTITY.json"], "gate_a_identity_sha256": freeze["identity_catalog.csv.gz"], "gate_a_role_sha256": freeze["role_vectors.csv.gz"], "gate_a_participation_sha256": freeze["issue_participation.csv"], "canonical_outcome_manifest_sha256": OUTCOME_MANIFEST, "canonical_outcome_join_sha256": OUTCOME_PAYLOAD}


def load_outcomes() -> dict[str, dict[str, str]]:
    with (OUTCOME_SOURCE / "canonical_outcome_join.csv").open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != OUTCOME_FIELDS: raise RuntimeError("outcome schema drift")
        rows = list(reader)
    out = {row["match_id"]: row for row in rows}
    if len(out) != len(rows): raise RuntimeError("duplicate outcome match id")
    for row in out.values():
        if row["result_code"] not in CODES or row["settlement_quality"] != "trusted" or row["has_trusted_settlement"] != "1" or dec(row["winning_sp"], "winning SP") <= 0: raise RuntimeError("untrusted outcome")
    return out


def load_freeze() -> tuple[list[dict[str, str]], dict[str, list[dict[str, str]]], dict[str, dict[str, str]], dict[str, str], dict[tuple[int, int, str], dict[str, str]]]:
    with (FREEZE / "issue_participation.csv").open(newline="", encoding="utf-8") as handle:
        participation = list(csv.DictReader(handle))
    if len(participation) != 348 * 9: raise RuntimeError("participation denominator drift")
    with gzip.open(FREEZE / "identity_catalog.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        identities = list(csv.DictReader(handle))
    with gzip.open(FREEZE / "role_vectors.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        roles = list(csv.DictReader(handle))
    role_map: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in roles: role_map[row["identity_id"]].append(row)
    for identity in identities:
        rs = sorted(role_map[identity["identity_id"]], key=lambda row: int(row["selection_rank"]))
        if len(rs) != int(identity["n"]) or [int(row["selection_rank"]) for row in rs] != list(range(1, int(identity["n"]) + 1)): raise RuntimeError("role cardinality drift")
        if "|".join(row["match_id"] for row in rs) != identity["selected_match_ids"]: raise RuntimeError("identity role join drift")
    meta: dict[str, dict[str, str]] = {}
    for row in participation:
        meta[(row["issue"], row["fold"], row["year"], row["n"]).__str__()] = row
    kickoff_by_issue: dict[str, str] = {}
    for role in roles:
        key = role["issue_instance"]
        value = role["kickoff_ts"]
        if value and (key not in kickoff_by_issue or value < kickoff_by_issue[key]):
            kickoff_by_issue[key] = value
    with (FREEZE / "sampling_plan.csv").open(newline="", encoding="utf-8") as handle:
        plans = list(csv.DictReader(handle))
    if len(plans) != len(N_GRID) * len(M_GRID) * len(SEEDS):
        raise RuntimeError("sampling plan denominator drift")
    plan_map: dict[tuple[int, int, str], dict[str, str]] = {}
    for row in plans:
        key = (int(row["n"]), int(row["nominal_M"]), row["seed"])
        if key in plan_map: raise RuntimeError("duplicate sampling plan cell")
        effective = min(int(row["nominal_M"]), 3 ** int(row["n"]))
        if int(row["effective_M"]) != effective: raise RuntimeError("effective M drift")
        expected_status = "FULL_SPACE_SATURATED" if int(row["nominal_M"]) > 3 ** int(row["n"]) else "PARTIAL_WOR"
        if row["saturation_status"] != expected_status: raise RuntimeError("saturation status drift")
        plan_map[key] = row
    return participation, dict(role_map), {row["identity_id"]: row for row in identities}, kickoff_by_issue, plan_map


def settlement_row(identity: dict[str, str], roles: list[dict[str, str]], plan: dict[str, str], seed: str, outcomes: dict[str, dict[str, str]], allocation_cache: dict[tuple[str, str, int], tuple[tuple[int, ...], str]]) -> dict[str, object]:
    n = int(identity["n"]); nominal_m = int(plan["nominal_M"]); effective_m = int(plan["effective_M"]); saturation_status = plan["saturation_status"]; signature = identity["selected_match_ids"]
    missing = [row["match_id"] for row in roles if row["match_id"] not in outcomes]
    planned = effective_m; full_stake = Decimal(effective_m) * UNIT_STAKE
    allocation_key = f"{identity['identity_id']}|{seed}|effective_M={effective_m}"
    cache_key = (identity["identity_id"], seed, effective_m)
    weights = [math.prod(float(roles[i][f"q_weight{code}"]) for i, code in enumerate(ticket)) for ticket in itertools.product(CODES, repeat=n)]
    if abs(sum(weights) - 1.0) > 2e-8: raise RuntimeError(f"ticket q mass drift: {identity['identity_id']}")
    if cache_key not in allocation_cache:
        ranked = allocation_rank(tuple(weights), seed, signature, n); selected = tuple(ranked[:effective_m]); fingerprint = hashlib.sha256(json.dumps(selected, separators=(",", ":")).encode()).hexdigest(); allocation_cache[cache_key] = (selected, fingerprint)
    selected, fingerprint = allocation_cache[cache_key]
    base = {"identity_id": identity["identity_id"], "issue": identity["issue"], "fold": identity["fold"], "year": identity["year"], "issue_instance": identity["issue_instance"], "n": n, "M": nominal_m, "nominal_M": nominal_m, "effective_M": effective_m, "seed": seed, "saturation_status": saturation_status, "allocation_equivalence_key": allocation_key, "planned_draw_count": planned, "executed_draw_count": 0 if missing else planned, "stake_yuan": money(Decimal(0) if missing else full_stake), "unique_ticket_count": 0 if missing else effective_m, "duplicate_ticket_count": 0, "duplicate_ticket_ratio": ratio(0), "allocation_fingerprint": fingerprint, "outcome_gap_count": len(missing), "settlement_status": "UNAVAILABLE_CANONICAL_OUTCOME" if missing else "SETTLED"}
    if missing:
        return {**base, "truth_sequence": "", "truth_ordinal": "", "truth_rank": "", "coverage_hit": "", "winning_ticket_count": 0, "gm_e_sp": identity["gm_e_sp"], "expected_sp_product_q": "", "actual_winning_sp_product": "", "gross_pre_tax_yuan": money(Decimal(0)), "taxable_winning_ticket_count": 0, "tax_yuan": money(Decimal(0)), "after_tax_gross_yuan": money(Decimal(0)), "pre_tax_net_yuan": money(Decimal(0)), "tax_adjusted_net_yuan": money(Decimal(0)), "no_tax_roi": "", "tax_adjusted_roi": "", "winning_sp_sources": ""}
    truth = "".join(outcomes[row["match_id"]]["result_code"] for row in roles); truth_idx = truth_ordinal(truth)
    product = Decimal(1); sources = set(); expected_product = Decimal(1)
    for role in roles:
        outcome = outcomes[role["match_id"]]; product *= dec(outcome["winning_sp"], "winning SP"); sources.add(outcome["winning_sp_source"])
        expected_leg = sum(dec(role[f"q_weight{code}"], "q weight") * dec(role[f"predicted_sp{code}"], "predicted SP") for code in CODES); expected_product *= expected_leg
    ranked = allocation_rank(tuple(weights), seed, signature, n); rank = ranked.index(truth_idx) + 1; hit = rank <= effective_m
    gross = UNIT_STAKE * PAYOUT_FACTOR * product if hit else Decimal(0); tax = ticket_tax(gross) if hit else Decimal(0); after = gross - tax; stake = full_stake
    return {**base, "truth_sequence": truth, "truth_ordinal": truth_idx, "truth_rank": rank, "coverage_hit": "YES" if hit else "NO", "winning_ticket_count": int(hit), "gm_e_sp": identity["gm_e_sp"], "expected_sp_product_q": money(expected_product), "actual_winning_sp_product": money(product) if hit else "", "gross_pre_tax_yuan": money(gross), "taxable_winning_ticket_count": int(bool(tax)), "tax_yuan": money(tax), "after_tax_gross_yuan": money(after), "pre_tax_net_yuan": money(gross - stake), "tax_adjusted_net_yuan": money(after - stake), "no_tax_roi": ratio((gross - stake) / stake), "tax_adjusted_roi": ratio((after - stake) / stake), "winning_sp_sources": ";".join(sorted(sources))}


def summary_rows(issue_rows: list[dict[str, object]], scope: str, scope_value: str) -> dict[str, object]:
    if not issue_rows: raise RuntimeError("empty summary support")
    n, nominal_m, effective_m, seed = int(issue_rows[0]["n"]), int(issue_rows[0]["nominal_M"]), int(issue_rows[0]["effective_M"]), str(issue_rows[0]["seed"]); saturation_status = str(issue_rows[0]["saturation_status"])
    frozen = len(issue_rows); available = sum(row["selection_status"] == "AVAILABLE" for row in issue_rows); no_bet = frozen - available
    settled = [row for row in issue_rows if int(row["settled_identity_count"]) > 0]; stake = sum((dec(row["stake_yuan"], "stake") for row in issue_rows), Decimal(0)); full = sum((dec(row["full_control_stake_yuan"], "full stake") for row in issue_rows), Decimal(0))
    planned_ids = sum(int(row["planned_identity_count"]) for row in issue_rows); settled_ids = sum(int(row["settled_identity_count"]) for row in issue_rows); planned_draw = sum(int(row["planned_draw_count"]) for row in issue_rows); executed_draw = sum(int(row["executed_draw_count"]) for row in issue_rows)
    unique = sum(int(row["unique_ticket_count"]) for row in issue_rows); duplicate = sum(int(row["duplicate_ticket_count"]) for row in issue_rows); wins = sum(int(row["winning_ticket_count"]) for row in issue_rows); hit_ids = sum(int(row["hit_identity_count"]) for row in issue_rows); gross = sum((dec(row["gross_pre_tax_yuan"], "gross") for row in issue_rows), Decimal(0)); tax = sum((dec(row["tax_yuan"], "tax") for row in issue_rows), Decimal(0)); after = sum((dec(row["after_tax_gross_yuan"], "after") for row in issue_rows), Decimal(0)); pre_net = sum((dec(row["pre_tax_net_yuan"], "pre net") for row in issue_rows), Decimal(0)); tax_net = sum((dec(row["tax_adjusted_net_yuan"], "tax net") for row in issue_rows), Decimal(0))
    stake_values = [dec(row["stake_yuan"], "stake") for row in issue_rows if dec(row["stake_yuan"], "stake") > 0]; gross_values = {row["issue_instance"]: dec(row["gross_pre_tax_yuan"], "gross") for row in issue_rows}; positive = [(k, v) for k, v in gross_values.items() if v > 0]; largest_issue, largest_gross = max(gross_values.items(), key=lambda item: item[1], default=("", Decimal(0))); total_gross = sum(gross_values.values(), Decimal(0)); hhi = sum((v / total_gross) ** 2 for v in gross_values.values()) if total_gross else Decimal(0)
    ordered = sorted(issue_rows, key=lambda row: (row.get("first_kickoff_ts", ""), row["issue_instance"])); cumulative = peak = drawdown = Decimal(0); streak = longest = 0
    for row in ordered:
        cumulative += dec(row["tax_adjusted_net_yuan"], "net"); peak = max(peak, cumulative); drawdown = max(drawdown, peak - cumulative); streak = 0 if row["coverage_hit"] == "YES" else streak + 1; longest = max(longest, streak)
    ex_stake = stake - largest_gross if largest_gross < stake else Decimal(0); ex_roi = (tax_net - largest_gross) / ex_stake if ex_stake else None
    gm_values = [dec(row["gm_expected_sp_mean"], "GM") for row in settled if row["gm_expected_sp_mean"]]; expected_values = [dec(row["expected_sp_product_q_mean"], "expected") for row in settled if row["expected_sp_product_q_mean"]]; actual_values = [dec(row["actual_winning_sp_product_mean"], "actual") for row in settled if row["actual_winning_sp_product_mean"]]
    return {"scope": scope, "scope_value": scope_value, "n": n, "M": nominal_m, "nominal_M": nominal_m, "effective_M": effective_m, "seed": seed, "saturation_status": saturation_status, "frozen_issue_count": frozen, "frozen_available_issue_count": available, "frozen_no_bet_issue_count": no_bet, "settled_issue_count": len(settled), "unavailable_outcome_issue_count": sum(int(row["unavailable_identity_count"]) > 0 for row in issue_rows), "planned_identity_count": planned_ids, "settled_identity_count": settled_ids, "planned_draw_count": planned_draw, "executed_draw_count": executed_draw, "planned_stake_yuan": money(sum((dec(row["planned_stake_yuan"], "planned stake") for row in issue_rows), Decimal(0))), "stake_yuan": money(stake), "full_control_stake_yuan": money(full), "capital_utilization_vs_full": ratio(stake / full if full else None), "stake_mean_yuan": money(sum(stake_values, Decimal(0)) / len(stake_values)) if stake_values else money(Decimal(0)), "stake_p50_yuan": money(quantile(stake_values, .50)), "stake_p90_yuan": money(quantile(stake_values, .90)), "stake_p95_yuan": money(quantile(stake_values, .95)), "stake_max_yuan": money(max(stake_values, default=Decimal(0))), "unique_ticket_count": unique, "duplicate_ticket_count": duplicate, "duplicate_ticket_ratio": ratio(Decimal(duplicate) / (unique + duplicate) if unique + duplicate else None), "winning_ticket_count": wins, "hit_identity_count": hit_ids, "coverage_hit_rate": ratio(Decimal(hit_ids) / settled_ids if settled_ids else None), "ticket_hit_rate": ratio(Decimal(wins) / executed_draw if executed_draw else None), "gross_pre_tax_yuan": money(gross), "taxable_winning_ticket_count": sum(int(row["taxable_winning_ticket_count"]) for row in issue_rows), "tax_line_share": ratio(Decimal(sum(int(row["taxable_winning_ticket_count"]) for row in issue_rows)) / wins if wins else None), "tax_yuan": money(tax), "after_tax_gross_yuan": money(after), "pre_tax_net_yuan": money(pre_net), "tax_adjusted_net_yuan": money(tax_net), "no_tax_roi": ratio(pre_net / stake if stake else None), "tax_adjusted_roi": ratio(tax_net / stake if stake else None), "gm_expected_sp_mean": ratio(sum(gm_values, Decimal(0)) / len(gm_values) if gm_values else None), "expected_sp_product_q_mean": ratio(sum(expected_values, Decimal(0)) / len(expected_values) if expected_values else None), "actual_winning_sp_product_mean": ratio(sum(actual_values, Decimal(0)) / len(actual_values) if actual_values else None), "gross_top_issue_share": ratio(largest_gross / total_gross if total_gross else None), "gross_issue_hhi": ratio(hhi), "largest_issue": largest_issue, "largest_issue_gross_yuan": money(largest_gross), "ex_largest_issue_roi": ratio(ex_roi), "max_drawdown_yuan": money(drawdown), "longest_miss_streak": longest}


def bootstrap(issue_rows_by_config: dict[tuple[int, int, str], list[dict[str, object]]], n: int, nominal_m: int, seed: str) -> list[dict[str, object]]:
    rows = [row for row in issue_rows_by_config[(n, nominal_m, seed)] if dec(row["stake_yuan"], "stake") > 0]
    if not rows: return []
    rng = random.Random(int.from_bytes(hashlib.sha256(f"{CONTRACT}|bootstrap|{n}|{m}|{seed}".encode()).digest()[:8], "big")); output = []
    for metric in ("pre_tax_net_yuan", "tax_adjusted_net_yuan"):
        values = []
        for _ in range(BOOTSTRAP_REPLICATES):
            sample = [rows[rng.randrange(len(rows))] for _ in rows]; st = sum((dec(row["stake_yuan"], "stake") for row in sample), Decimal(0)); net = sum((dec(row[metric], metric) for row in sample), Decimal(0)); values.append(float(net / st if st else 0))
        values.sort(); point_rows = rows; point_stake = sum((dec(row["stake_yuan"], "stake") for row in point_rows), Decimal(0)); point = sum((dec(row[metric], metric) for row in point_rows), Decimal(0)) / point_stake if point_stake else Decimal(0)
        first = rows[0]
        output.append({"n": n, "M": nominal_m, "nominal_M": nominal_m, "effective_M": first["effective_M"], "seed": seed, "saturation_status": first["saturation_status"], "metric": "no_tax_roi" if metric == "pre_tax_net_yuan" else "tax_adjusted_roi", "support_issue_count": len(rows), "replicates": BOOTSTRAP_REPLICATES, "point_estimate": ratio(point), "ci95_low": f"{values[25]:.12f}", "ci95_high": f"{values[974]:.12f}", "positive_fraction": f"{sum(value > 0 for value in values)/len(values):.12f}"})
    return output


def overlap_rows(identities: list[dict[str, str]]) -> list[dict[str, object]]:
    by_n: dict[int, list[dict[str, str]]] = defaultdict(list)
    for row in identities: by_n[int(row["n"])].append(row)
    output = []
    for n in N_GRID:
        rows = by_n[n]; pairs = shared = jaccards = 0.0; max_shared = max_j = 0.0; issue_count = len({row["issue_instance"] for row in rows})
        by_issue: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in rows: by_issue[row["issue_instance"]].append(row)
        for issue_rows in by_issue.values():
            for left, right in itertools.combinations(issue_rows, 2):
                a, b = set(left["selected_match_ids"].split("|")), set(right["selected_match_ids"].split("|")); inter = len(a & b); union = len(a | b); pairs += 1; shared += inter; jaccards += inter / union; max_shared = max(max_shared, inter); max_j = max(max_j, inter / union)
        output.append({"n": n, "identity_count": len(rows), "issue_count": issue_count, "pair_count": int(pairs), "mean_shared_leg_count": ratio(shared / pairs if pairs else 0), "max_shared_leg_count": int(max_shared), "mean_jaccard": ratio(jaccards / pairs if pairs else 0), "max_jaccard": ratio(max_j), "duplicate_ticket_policy": "WOR distinct within each identity; cross-identity shared legs reported, no ticket deduplication"})
    return output


def svg_curve(path: Path, rows: list[dict[str, object]], y_field: str, title: str, ylabel: str) -> None:
    width, height, left, bottom = 760, 430, 70, 55; chart_w, chart_h = width - left - 30, height - 40 - bottom; points = [(int(row["n"]), float(row[y_field])) for row in rows if row.get(y_field) not in (None, "")]
    if not points: return
    ymin, ymax = min(value for _, value in points), max(value for _, value in points); span = max(ymax - ymin, .05); ymin -= span * .1; ymax += span * .1
    def x(n): return left + chart_w * (n - 2) / 8
    def y(v): return 40 + chart_h * (ymax - v) / (ymax - ymin)
    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"><rect width="100%" height="100%" fill="white"/><text x="{left}" y="22" font-size="16">{title}</text><line x1="{left}" y1="{height-bottom}" x2="{width-30}" y2="{height-bottom}" stroke="#333"/><line x1="{left}" y1="40" x2="{left}" y2="{height-bottom}" stroke="#333"/><text x="8" y="{height/2}" font-size="12" transform="rotate(-90 8 {height/2})">{ylabel}</text>']
    for n in range(2, 11): lines.append(f'<text x="{x(n)-5:.1f}" y="{height-bottom+18}" font-size="11">{n}</text>')
    coords = " ".join(f"{x(n):.1f},{y(value):.1f}" for n, value in points); lines.append(f'<polyline fill="none" stroke="#1f77b4" stroke-width="2" points="{coords}"/>')
    for n, value in points: lines.append(f'<circle cx="{x(n):.1f}" cy="{y(value):.1f}" r="4" fill="#1f77b4"><title>N={n}: {value:.6f}</title></circle>')
    lines.append("</svg>\n"); path.write_text("\n".join(lines), encoding="utf-8")


def build(output: Path) -> dict[str, object]:
    if output.exists(): raise RuntimeError(f"refusing immutable overwrite: {output}")
    output.parent.mkdir(parents=True, exist_ok=True); stage = Path(tempfile.mkdtemp(prefix=".bj159_gateb_", dir=output.parent))
    try:
        provenance = validate_inputs(); outcomes = load_outcomes(); participation, role_map, identities_map, kickoff_by_issue, plan_map = load_freeze(); identities = list(identities_map.values())
        # The Gate-A participation surface is per issue×N, while M/seed are
        # allocator cells.  Build one immutable issue row for every cell.
        part_by_issue_n: dict[tuple[str, int], dict[str, str]] = {(row["issue_instance"], int(row["n"])): row for row in participation}
        issue_rows_by_config: dict[tuple[int, int, str], list[dict[str, object]]] = defaultdict(list)
        identity_handles = gzip_writer(stage / "identity_settlement.csv.gz", IDENTITY_SETTLEMENT_FIELDS); identity_writer = identity_handles[-1]
        tax_handles = gzip_writer(stage / "winning_ticket_tax_ledger.csv.gz", ("identity_id", "issue", "issue_instance", "n", "M", "nominal_M", "effective_M", "seed", "saturation_status", "gross_yuan", "tax_yuan", "tax_rule")); tax_writer = tax_handles[-1]
        allocation_cache: dict[tuple[str, str, int], tuple[tuple[int, ...], str]] = {}
        identity_count_by_n = Counter(int(row["n"]) for row in identities); settled_count = Counter(); unavailable_count = Counter()
        for identity in sorted(identities, key=lambda row: (int(row["year"]), int(row["issue"]), int(row["n"]), row["identity_id"])):
            roles = sorted(role_map[identity["identity_id"]], key=lambda row: int(row["selection_rank"]))
            for nominal_m in M_GRID:
                for seed in SEEDS:
                    plan = plan_map[(int(identity["n"]), nominal_m, seed)]
                    row = settlement_row(identity, roles, plan, seed, outcomes, allocation_cache); identity_writer.writerow(row)
                    issue_rows_by_config[(int(identity["n"]), nominal_m, seed)].append(row)
                    if row["settlement_status"] == "SETTLED": settled_count[int(identity["n"])] += 1
                    else: unavailable_count[int(identity["n"])] += 1
                    if int(row["winning_ticket_count"]): tax_writer.writerow({"identity_id": row["identity_id"], "issue": row["issue"], "issue_instance": row["issue_instance"], "n": row["n"], "M": row["M"], "nominal_M": row["nominal_M"], "effective_M": row["effective_M"], "seed": row["seed"], "saturation_status": row["saturation_status"], "gross_yuan": row["gross_pre_tax_yuan"], "tax_yuan": row["tax_yuan"], "tax_rule": "20% iff this individual winning ¥2 ticket gross >= ¥10,000; no pooling"})
        close_gzip(identity_handles); close_gzip(tax_handles)
        # Re-read the compact identity surface once to aggregate per complete
        # issue.  This keeps the final package portable and bounded in memory.
        with gzip.open(stage / "identity_settlement.csv.gz", "rt", newline="", encoding="utf-8") as handle: settled_rows = list(csv.DictReader(handle))
        issue_agg: dict[tuple[int, int, str, str], IssueAgg] = {}
        for n in N_GRID:
            for m in M_GRID:
                for seed in SEEDS:
                    plan = plan_map[(n, m, seed)]
                    for part in (row for row in participation if int(row["n"]) == n):
                        key = (n, m, seed, part["issue_instance"]); issue_agg[key] = IssueAgg(part["issue"], part["fold"], part["year"], part["issue_instance"], n, int(plan["effective_M"]), m, plan["saturation_status"], seed, part["selection_status"], int(part["selected_identity_count"]), first_kickoff_ts=kickoff_by_issue.get(part["issue_instance"], ""))
        for row in settled_rows:
            agg = issue_agg[(int(row["n"]), int(row["M"]), row["seed"], row["issue_instance"])]
            agg.add(row)
        issue_output = [agg.as_row() for _, agg in sorted(issue_agg.items(), key=lambda item: (item[0][0], item[0][1], item[0][2], item[0][3]))]
        # Put deterministic issue chronology from the earliest frozen row into
        # each issue; source rows do not expose outcome timestamps.
        write_gzip = gzip_writer(stage / "issue_settlement.csv.gz", ISSUE_SETTLEMENT_FIELDS); write_gzip[-1].writerows(issue_output); close_gzip(write_gzip)
        all_summaries = []; robustness = []
        by_cfg: dict[tuple[int, int, str], list[dict[str, object]]] = defaultdict(list)
        for row in issue_output: by_cfg[(int(row["n"]), int(row["M"]), row["seed"])].append(row)
        for key, rows in sorted(by_cfg.items()):
            all_summaries.append(summary_rows(rows, "ALL", "ALL"))
            years = sorted({str(row["year"]) for row in rows})
            folds = sorted({str(row["fold"]) for row in rows})
            for year in years: robustness.append(summary_rows([row for row in rows if str(row["year"]) == year], "YEAR", year))
            for fold in folds: robustness.append(summary_rows([row for row in rows if str(row["fold"]) == fold], "FOLD", fold))
            for year in years: robustness.append(summary_rows([row for row in rows if str(row["year"]) != year], "LOYO", year))
        write_csv(stage / "surface_summary.csv", SUMMARY_FIELDS, all_summaries + robustness)
        write_csv(stage / "issue_bootstrap.csv", BOOT_FIELDS, (row for n, m, seed in sorted(by_cfg) for row in bootstrap(by_cfg, n, m, seed)))
        # Matched/common support against N=7 at the same M/seed.
        deltas = []
        for n in N_GRID:
            for m in M_GRID:
                for seed in SEEDS:
                    left = {row["issue_instance"]: row for row in by_cfg[(n, m, seed)] if dec(row["stake_yuan"], "stake") > 0}; base = {row["issue_instance"]: row for row in by_cfg[(7, m, seed)] if dec(row["stake_yuan"], "stake") > 0}; common = sorted(set(left) & set(base))
                    def roi(rows, field):
                        stake = sum((dec(rows[k]["stake_yuan"], "stake") for k in common), Decimal(0)); net = sum((dec(rows[k][field], field) for k in common), Decimal(0)); return net / stake if stake else Decimal(0), stake
                    n_roi, n_stake = roi(left, "pre_tax_net_yuan"); b_roi, b_stake = roi(base, "pre_tax_net_yuan"); n_tax, _ = roi(left, "tax_adjusted_net_yuan"); b_tax, _ = roi(base, "tax_adjusted_net_yuan")
                    n_eff = min(m, 3 ** n); b_eff = min(m, 3 ** 7)
                    deltas.append({"n": n, "M": m, "nominal_M": m, "effective_M": n_eff, "n7_nominal_M": m, "n7_effective_M": b_eff, "seed": seed, "common_issue_count": len(common), "n_stake_yuan": money(n_stake), "n7_stake_yuan": money(b_stake), "n_no_tax_roi": ratio(n_roi), "n7_no_tax_roi": ratio(b_roi), "no_tax_roi_delta": ratio(n_roi - b_roi), "n_tax_adjusted_roi": ratio(n_tax), "n7_tax_adjusted_roi": ratio(b_tax), "tax_adjusted_roi_delta": ratio(n_tax - b_tax), "rule": "matched issue-instance support only; N7 is descriptive baseline, not a causal estimate"})
        write_csv(stage / "matched_n7_deltas.csv", DELTA_FIELDS, deltas)
        write_csv(stage / "overlap_summary.csv", OVERLAP_FIELDS, overlap_rows(identities))
        curve = [row for row in all_summaries if int(row["M"]) == 64]
        curve_by_n = []
        for n in N_GRID:
            rows = [row for row in curve if int(row["n"]) == n]
            def mean(field):
                vals = [dec(row[field], field) for row in rows if row[field] != ""]
                return ratio(sum(vals, Decimal(0)) / len(vals)) if vals else ""
            curve_by_n.append({"n": n, "no_tax_roi_mean": mean("no_tax_roi"), "tax_adjusted_roi_mean": mean("tax_adjusted_roi"), "coverage_hit_rate_mean": mean("coverage_hit_rate"), "stake_yuan_mean": mean("stake_yuan"), "tax_line_share_mean": mean("tax_line_share")})
        write_csv(stage / "n_curve_M64.csv", ("n", "no_tax_roi_mean", "tax_adjusted_roi_mean", "coverage_hit_rate_mean", "stake_yuan_mean", "tax_line_share_mean"), curve_by_n)
        svg_curve(stage / "roi_vs_n_M64.svg", curve_by_n, "no_tax_roi_mean", "#159 N→pre-tax ROI (M=64, seed mean)", "no-tax ROI")
        svg_curve(stage / "coverage_vs_n_M64.svg", curve_by_n, "coverage_hit_rate_mean", "#159 N→coverage (M=64, seed mean)", "identity coverage")
        svg_curve(stage / "stake_vs_n_M64.svg", curve_by_n, "stake_yuan_mean", "#159 N→executed stake (M=64, seed mean)", "stake (¥)")
        positives = [row for row in all_summaries if row["no_tax_roi"] and dec(row["no_tax_roi"], "ROI") > 0]
        decision = {"decision": "POSITIVE_REQUIRES_STRICT_INDEPENDENT_EV" if positives else "NO_PROMOTION", "positive_all_rows": len(positives), "strict_independent_ev_required": bool(positives), "promotion_authorized": False, "rule": "Pre-tax no_tax_roi is primary and tax-adjusted ROI secondary; same-window historical positives are descriptive and require strict independent EV plus held-out/forward validation; no purchase, production, betting or promotion authority."}
        (stage / "decision.json").write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        report = ["# #159 Gate B v2 — selected-baseline WOR cross-N", "", "Canonical settlement of the accepted outcome-unexposed Gate-A package.", "", f"Decision: **{decision['decision']}**.", "", "The primary nominal M=64 surface and nominal M=32/128 sensitivity use deterministic Q-informed WOR without replacement. Actual draws and stake use `effective_M=min(nominal_M,3^N)`. Every selected identity gets effective_M distinct tickets at ¥2 each; the 21 FULL_SPACE_SATURATED nominal rows are the same allocation per identity/seed/effective_M, not duplicate WOR tickets. Tax is applied only per individual winning ticket reaching ¥10,000 gross, never by pooling issue or policy stakes.", "", "## Identity counts", "", "| N | identities |", "|---:|---:|"] + [f"| {n} | {identity_count_by_n[n]} |" for n in N_GRID] + ["", "## Interpretation", "", "The N curve is descriptive. Matched N-versus-N7 deltas use common positive-stake issue support only; YEAR/FOLD/LOYO, issue bootstrap, overlap and largest-issue controls are included in the package. No historical row authorizes purchase, production, betting or promotion.", ""]
        (stage / "report.md").write_text("\n".join(report), encoding="utf-8")
        write_csv(stage / "source_census.csv", SOURCE_FIELDS, [{"source": "bj159_gate_a_preoutcome_v2r1", "role": "accepted immutable complete-issue identities and nominal/effective WOR plan", "identity": "SHA256SUMS.json", "sha256": FREEZE_MANIFEST, "rows": len(identities), "join_status": "all identities retained; no selection recomputation"}, {"source": "bj95_gate_b_outcome_settlement_v2r8", "role": "canonical trusted result/final-SP only", "identity": "canonical_outcome_join.csv", "sha256": OUTCOME_PAYLOAD, "rows": len(outcomes), "join_status": "complete identity settlement; missing legs receive zero executed stake"}])
        card = {"issue": 159, "contract": CONTRACT, "runner_version": VERSION, "stage": "GATE_B_CANONICAL_OUTCOME_SETTLEMENT", "provenance": provenance, "settlement_rule": "Hit iff the frozen truth code is among the effective_M distinct Q-WOR tickets; gross=¥2×0.65×product(trusted final winning SP) exactly once on hit.", "saturation_rule": "nominal_M is a reporting label; effective_M=min(nominal_M,3^N) controls actual draw count and stake; FULL_SPACE_SATURATED nominal rows share one allocation per identity/seed/effective_M and are not extra WR tickets.", "tax_rule": "20% is applied per individual winning ¥2 ticket iff that ticket gross >= ¥10,000; no issue/policy pooling or aggregation.", "unit": "complete lottery issue; native pool is provenance only", "decision": decision, "output": {"identity_settlement_rows": len(settled_rows), "issue_settlement_rows": len(issue_output), "surface_summary_rows": len(all_summaries) + len(robustness), "bootstrap_rows": len(list((stage / "issue_bootstrap.csv").open())) - 1, "matched_delta_rows": len(deltas), "saturated_nominal_rows": 21 * len(identities)}, "scope": "historical paper-only research; no purchase, production, betting or promotion authority"}
        (stage / "settlement_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        shutil.copy2(Path(__file__), stage / "settlement_runner.py")
        (stage / "README.md").write_text("# #159 Gate B v2\n\nCanonical outcome settlement of the accepted selected-baseline Q-informed WOR cross-N freeze. `M`/`nominal_M` is the frozen reporting label; `effective_M=min(nominal_M,3^N)` is the actual number of distinct tickets and actual stake. Saturated nominal cells are one allocation per identity/seed/effective_M, not duplicate WOR tickets. Replay with `python3 settlement_runner.py --output <new-dir>`; staging is beside the output and never uses `/tmp`.\n", encoding="utf-8")
        gzip_names = ("identity_settlement.csv.gz", "issue_settlement.csv.gz", "winning_ticket_tax_ledger.csv.gz")
        def digest(path: Path) -> tuple[str, int]:
            h, size = hashlib.sha256(), 0
            with gzip.open(path, "rb") as handle:
                for block in iter(lambda: handle.read(1 << 20), b""): h.update(block); size += len(block)
            return h.hexdigest(), size
        content = {"contract_version": "bj159-gateb-content-v2", "gzip_payloads": {name: {"canonical_decompressed_sha256": digest(stage / name)[0], "canonical_decompressed_bytes": digest(stage / name)[1]} for name in gzip_names}, "non_compressed_controls": {p.name: sha256(p) for p in sorted(stage.iterdir()) if p.is_file() and p.name not in gzip_names}}
        (stage / "CONTENT_IDENTITY.json").write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        sums = {p.name: sha256(p) for p in sorted(stage.iterdir()) if p.is_file()}; (stage / "SHA256SUMS.json").write_text(json.dumps(sums, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(stage, output)
        return {"manifest_sha256": sha256(output / "SHA256SUMS.json"), "content_identity_sha256": sha256(output / "CONTENT_IDENTITY.json"), "identity_settlement_rows": len(settled_rows), "issue_settlement_rows": len(issue_output), "positive_rows": len(positives), "decision": decision}
    except Exception:
        shutil.rmtree(stage, ignore_errors=True); raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--output", type=Path, default=OUTPUT); args = parser.parse_args(); print(json.dumps(build(args.output.resolve()), sort_keys=True))


if __name__ == "__main__": main()
