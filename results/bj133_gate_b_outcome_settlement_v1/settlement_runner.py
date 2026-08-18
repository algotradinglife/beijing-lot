#!/usr/bin/env python3
"""One-shot outcome settlement for #133's accepted diversified N7 freeze.

Only the immutable #133 Gate-A bundle and the canonical final-SP outcome
payload are read.  Sampling is deterministic Q-weighted sampling without
replacement; every tax decision is made on an individual winning ticket, never
on an issue, arm, or policy aggregate.  Temporary files are staged beside the
requested result directory (under ``results/``), never in ``/tmp``.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import os
import random
import shutil
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path
from typing import Iterable, Iterator


CONTRACT = "BJ-HIST-DIVERSIFIED-N7-ALLOCATOR-001"
VERSION = "bj133-gate-b-v1-ticket-tax"
FREEZE_MANIFEST = "1fff3f904fcb9a5efed231771880be8ae0603b0d8f3c7d0365937fcfe9985e79"
OUTCOME_MANIFEST = "fbbd3b53bd86f4bb0caff8f2587933cd6b0e4e7d04fb0f709bac934ec2a705cc"
OUTCOME_PAYLOAD = "13d709d253c31519734dbf0447e6961ac8a6060772975d7461741224e5251a89"
CODES = ("3", "1", "0")
N, FULL_K = 7, 2187
UNIT_STAKE = Decimal("2")
PAYOUT_FACTOR = Decimal("0.65")
TAX_RATE, TAX_THRESHOLD = Decimal("0.20"), Decimal("10000")
MONEY_QUANTUM = Decimal("0.000001")
BOOTSTRAP_REPLICATES = 1000
getcontext().prec = 80


def repo_root(anchor: Path) -> Path:
    for candidate in (anchor.resolve().parent, *anchor.resolve().parents):
        if (candidate / ".git").exists() and (candidate / "scripts").is_dir():
            return candidate
    raise RuntimeError("repository root unavailable")


ROOT = repo_root(Path(__file__))
FREEZE = ROOT / "results" / "bj133_gate_a_preoutcome_v1"
OUTCOME_SOURCE = ROOT / "results" / "bj95_gate_b_outcome_settlement_v2r8"
OUTPUT = ROOT / "results" / "bj133_gate_b_outcome_settlement_v1"

PLAN_FIELDS = (
    "config_id", "config_role", "gate_id", "top_k_id", "issue", "fold", "year", "issue_instance",
    "allocator_id", "allocator_family", "target_identity_count", "candidate_pool_count", "candidate_search_count",
    "match_exposure_cap", "q_delete_exposure_cap", "pairwise_jaccard_cap", "ticket_M", "probability_vector",
    "ticket_mechanism", "selected_identity_count", "selected_portfolio_ids", "selection_status", "reason",
    "planned_draw_count", "planned_stake_yuan", "full_control_draw_count", "full_control_stake_yuan",
    "unique_match_count", "total_leg_slots", "overlap_leg_slots", "max_match_exposure",
    "effective_independent_match_count", "max_pairwise_jaccard", "mean_pairwise_jaccard",
    "max_q_delete_exposure", "selected_q_delete_pairs", "selection_scope", "outcome_boundary",
)
IDENTITY_REQUIRED = {
    "issue", "fold", "year", "issue_instance", "gate_id", "portfolio_id", "selected_match_ids",
    "q_min_delete_match_id", "q_min_delete_code",
}
ROLE_REQUIRED = {
    "gate_id", "portfolio_id", "issue", "fold", "year", "issue_instance", "match_id", "selection_rank",
    "q_weight3", "q_weight1", "q_weight0",
}
OUTCOME_FIELDS = (
    "match_id", "result_code", "winning_sp", "winning_sp_source", "settlement_quality", "has_trusted_settlement",
)
SETTLEMENT_FIELDS = (
    "issue", "fold", "year", "issue_instance", "config_id", "config_role", "gate_id", "top_k_id",
    "allocator_id", "allocator_family", "allocator_interpretation", "seed", "seed_role", "ticket_M",
    "ticket_mechanism", "frozen_selection_status", "settlement_status", "selected_identity_count",
    "selected_portfolio_ids", "planned_draw_count", "planned_stake_yuan", "full_control_stake_yuan",
    "capital_utilization_vs_exact_full", "hit_ticket_count", "coverage_hit", "gross_pre_tax_yuan", "tax_yuan",
    "after_tax_gross_yuan", "pre_tax_net_yuan", "tax_adjusted_net_yuan", "no_tax_roi", "tax_adjusted_roi",
    "unique_match_count", "total_leg_slots", "overlap_leg_slots", "max_match_exposure",
    "effective_independent_match_count", "max_pairwise_jaccard", "max_q_delete_exposure",
    "gross_top_identity_share", "outcome_gap_count", "taxable_hit_ticket_count", "non_taxable_hit_ticket_count",
)
TICKET_FIELDS = (
    "issue", "fold", "year", "issue_instance", "config_id", "allocator_id", "seed", "portfolio_id",
    "winning_ticket_gross_yuan", "winning_ticket_count", "per_ticket_tax_yuan", "tax_yuan", "tax_rule",
)
SUMMARY_FIELDS = (
    "scope", "scope_value", "config_id", "config_role", "gate_id", "top_k_id", "allocator_id",
    "allocator_family", "allocator_interpretation", "seed", "seed_role", "ticket_M", "ticket_mechanism",
    "frozen_available_issue_count", "frozen_no_bet_issue_count", "settled_issue_count",
    "unavailable_outcome_issue_count", "planned_draw_count", "stake_yuan", "full_control_stake_yuan",
    "capital_utilization_vs_exact_full", "hit_ticket_count", "coverage_hits", "coverage_hit_rate",
    "gross_pre_tax_yuan", "tax_yuan", "after_tax_gross_yuan", "pre_tax_net_yuan", "tax_adjusted_net_yuan",
    "no_tax_roi", "tax_adjusted_roi", "max_drawdown_yuan", "longest_miss_streak", "gross_top_issue_share",
    "gross_issue_hhi", "gross_top_identity_share", "largest_issue_gross_yuan", "ex_largest_issue_no_tax_roi",
    "ex_largest_issue_tax_adjusted_roi", "mean_effective_independent_match_count", "max_match_exposure",
    "max_pairwise_jaccard", "max_q_delete_exposure",
)
EFFECT_FIELDS = (
    "scope", "scope_value", "effect", "config_id", "allocator_id", "seed", "baseline_config_id",
    "baseline_allocator_id", "baseline_seed", "support_issue_count", "candidate_issue_count", "stake_yuan",
    "baseline_stake_yuan", "full_reference_stake_yuan", "no_tax_roi", "baseline_no_tax_roi",
    "no_tax_roi_delta", "tax_adjusted_roi", "baseline_tax_adjusted_roi", "tax_adjusted_roi_delta",
    "gross_pre_tax_yuan_delta", "tax_yuan_delta", "coverage_hit_rate_delta", "gross_top_issue_share_delta",
    "gross_issue_hhi_delta", "matched_support_rule",
)
BOOTSTRAP_FIELDS = (
    "effect", "config_id", "allocator_id", "seed", "support_issue_count", "replicates", "metric",
    "point_estimate", "ci95_low", "ci95_high", "one_sided_positive_p", "two_sided_sign_p",
    "primary_family_size", "bonferroni_two_sided_p", "fwer_alpha", "passes_fwer_positive",
)
COMPARISON_FIELDS = (
    "comparison_id", "effect", "config_id", "allocator_id", "seed", "is_primary_economic_comparison",
    "support_issue_count", "all_no_tax_roi_delta", "all_tax_adjusted_roi_delta", "all_bootstrap_ci95_low",
    "all_bootstrap_ci95_high", "bonferroni_two_sided_p", "tax_bootstrap_ci95_low",
    "tax_bootstrap_ci95_high", "tax_bonferroni_two_sided_p", "fwer_alpha", "all_seed_persistence_group",
    "classification",
)
TAX_RECON_FIELDS = (
    "config_id", "allocator_id", "seed", "ticket_ledger_hit_ticket_count", "ticket_ledger_taxable_ticket_count",
    "ticket_ledger_tax_yuan", "issue_ledger_tax_yuan", "difference_yuan", "tax_rule",
)
SOURCE_FIELDS = ("source", "role", "identity", "sha256", "rows", "join_status")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def decompressed_digest(path: Path) -> tuple[str, int]:
    digest, size = hashlib.sha256(), 0
    with gzip.open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def decimal(value: object, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise RuntimeError(f"invalid {label}: {value!r}") from error
    if not result.is_finite():
        raise RuntimeError(f"non-finite {label}: {value!r}")
    return result


def money(value: Decimal | None) -> str:
    return "" if value is None else format(value.quantize(MONEY_QUANTUM), "f")


def ratio(value: Decimal | float | None) -> str:
    if value is None:
        return ""
    return f"{float(value):.12f}"


def verified_manifest(path: Path, expected_manifest: str) -> dict[str, str]:
    manifest_path = path / "SHA256SUMS.json"
    if not manifest_path.is_file() or sha256(manifest_path) != expected_manifest:
        raise RuntimeError(f"unaccepted manifest: {path}")
    declared = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = {
        item.name: sha256(item)
        for item in path.iterdir()
        if item.is_file() and item.name != manifest_path.name
    }
    if not isinstance(declared, dict) or declared != actual:
        raise RuntimeError(f"manifest coverage drift: {path}")
    return declared


def write_csv(path: Path, fields: tuple[str, ...], rows: Iterable[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n", extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def gzip_writer(path: Path, fields: tuple[str, ...]):
    raw = path.open("wb")
    zipped = gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0)
    text = io.TextIOWrapper(zipped, newline="", encoding="utf-8")
    writer = csv.DictWriter(text, fieldnames=fields, lineterminator="\n", extrasaction="raise")
    writer.writeheader()
    return raw, zipped, text, writer


def close_gzip(handles) -> None:
    raw, zipped, text, _writer = handles
    text.flush()
    text.detach()
    zipped.close()
    raw.close()


def write_gzip_csv(path: Path, fields: tuple[str, ...], rows: Iterable[dict[str, object]]) -> None:
    handles = gzip_writer(path, fields)
    try:
        handles[-1].writerows(rows)
    finally:
        close_gzip(handles)


def stable_uniform(*parts: object) -> float:
    token = "|".join(str(part) for part in parts).encode("utf-8")
    value = int.from_bytes(hashlib.sha256(token).digest()[:8], "big")
    return (value + 0.5) / 2**64


def ticket_tax(ticket_gross: Decimal) -> Decimal:
    """Tax exactly an individual winning ticket; never pool prizes first."""
    return ticket_gross * TAX_RATE if ticket_gross >= TAX_THRESHOLD else Decimal(0)


def allocator_interpretation(plan: dict[str, str]) -> str:
    allocator = plan["allocator_id"]
    if allocator in {"Q_DELETE_EXPOSURE_CAP_1", "Q_DELETE_EXPOSURE_CAP_2"} and plan["config_id"].startswith("PRIMARY_"):
        return "PRIMARY_IDENTIFIABLE_Q_DELETE_DIVERSIFICATION"
    if allocator in {"Q_DELETE_EXPOSURE_CAP_1", "Q_DELETE_EXPOSURE_CAP_2", "Q_DELETE_EXPOSURE_CAP_4"} and plan["config_id"].startswith("SECONDARY_"):
        return "SECONDARY_DESCRIPTIVE_SMALL_SUPPORT"
    if allocator in {"Q_DELETE_EXPOSURE_CAP_4", "Q_DELETE_EXPOSURE_CAP_8", "MATCH_EXPOSURE_CAP_4", "JACCARD_CAP_075", "JACCARD_CAP_100", "JOINT_M4_J100_Q4"}:
        return "IDENTITY_EQUIVALENT_OR_CAP_FRONTIER_CONTROL"
    if plan.get("selection_status", plan.get("frozen_selection_status")) != "AVAILABLE":
        return "STRUCTURAL_NO_BET_CAP_CONTROL"
    if allocator == "CONCENTRATED_TOP_SCORE":
        return "CONCENTRATED_CONTROL"
    return "STRUCTURAL_CAP_FRONTIER_CONTROL"


@dataclass(frozen=True)
class Identity:
    key: tuple[str, str]
    row: dict[str, str]
    roles: tuple[dict[str, str], ...]
    truth_index: int | None
    payout_per_ticket: Decimal | None
    outcome_gap_count: int


@dataclass
class TaxAudit:
    hit_tickets: int = 0
    taxable_tickets: int = 0
    tax_yuan: Decimal = Decimal(0)

    def add(self, per_ticket_tax: Decimal, count: int) -> None:
        self.hit_tickets += count
        if per_ticket_tax:
            self.taxable_tickets += count
            self.tax_yuan += per_ticket_tax * count


def validate_inputs() -> dict[str, str]:
    freeze = verified_manifest(FREEZE, FREEZE_MANIFEST)
    content = json.loads((FREEZE / "CONTENT_IDENTITY.json").read_text(encoding="utf-8"))
    card = json.loads((FREEZE / "gate_a_card.json").read_text(encoding="utf-8"))
    if card.get("contract") != CONTRACT or card.get("stage") != "GATE_A_OUTCOME_UNEXPOSED_COMPLETE_ISSUE_DIVERSIFIED_ALLOCATION_FREEZE":
        raise RuntimeError("unexpected Gate-A contract")
    if content.get("contract_version") != "bj133-gate-a-content-v1":
        raise RuntimeError("unexpected Gate-A content identity contract")
    if content["gzip_payloads"]["candidate_identity_catalog.csv.gz"]["canonical_decompressed_sha256"] != decompressed_digest(FREEZE / "candidate_identity_catalog.csv.gz")[0]:
        raise RuntimeError("Gate-A identity portable digest drift")
    if content["gzip_payloads"]["candidate_role_vectors.csv.gz"]["canonical_decompressed_sha256"] != decompressed_digest(FREEZE / "candidate_role_vectors.csv.gz")[0]:
        raise RuntimeError("Gate-A role portable digest drift")
    outcome = verified_manifest(OUTCOME_SOURCE, OUTCOME_MANIFEST)
    if outcome.get("canonical_outcome_join.csv") != OUTCOME_PAYLOAD:
        raise RuntimeError("canonical final-SP payload drift")
    return {
        "gate_a_manifest_sha256": FREEZE_MANIFEST,
        "gate_a_content_identity_sha256": freeze["CONTENT_IDENTITY.json"],
        "gate_a_plan_sha256": freeze["allocation_plan.csv"],
        "gate_a_identity_payload_sha256": freeze["candidate_identity_catalog.csv.gz"],
        "gate_a_role_payload_sha256": freeze["candidate_role_vectors.csv.gz"],
        "outcome_manifest_sha256": OUTCOME_MANIFEST,
        "canonical_outcome_join_sha256": OUTCOME_PAYLOAD,
    }


def load_outcomes() -> dict[str, dict[str, str]]:
    with (OUTCOME_SOURCE / "canonical_outcome_join.csv").open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != OUTCOME_FIELDS:
            raise RuntimeError("canonical outcome schema drift")
        rows = list(reader)
    outcomes = {row["match_id"]: row for row in rows}
    if len(rows) != len(outcomes):
        raise RuntimeError("duplicate canonical outcome match id")
    for row in outcomes.values():
        if (row["result_code"] not in CODES or row["settlement_quality"] != "trusted"
                or row["has_trusted_settlement"] != "1" or decimal(row["winning_sp"], "winning SP") <= 0):
            raise RuntimeError("untrusted canonical outcome")
    return outcomes


def load_plans() -> list[dict[str, str]]:
    with (FREEZE / "allocation_plan.csv").open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != PLAN_FIELDS:
            raise RuntimeError("Gate-A allocation-plan schema drift")
        plans = list(reader)
    if len(plans) != 20_880:
        raise RuntimeError(f"Gate-A plan denominator drift: {len(plans)}")
    keys = {(row["config_id"], row["allocator_id"], row["issue_instance"]) for row in plans}
    if len(keys) != len(plans):
        raise RuntimeError("Gate-A allocation-plan uniqueness drift")
    return plans


def load_identities(outcomes: dict[str, dict[str, str]]) -> dict[tuple[str, str], Identity]:
    role_map: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    with gzip.open(FREEZE / "candidate_role_vectors.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not ROLE_REQUIRED <= set(reader.fieldnames or ()):
            raise RuntimeError("Gate-A role schema lacks required columns")
        for row in reader:
            role_map[(row["gate_id"], row["portfolio_id"])].append(row)
    rows: dict[tuple[str, str], dict[str, str]] = {}
    with gzip.open(FREEZE / "candidate_identity_catalog.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not IDENTITY_REQUIRED <= set(reader.fieldnames or ()):
            raise RuntimeError("Gate-A identity schema lacks required columns")
        for row in reader:
            key = row["gate_id"], row["portfolio_id"]
            if key in rows:
                raise RuntimeError("duplicate Gate-A identity")
            rows[key] = row
    if len(rows) != 15_390 or sum(len(values) for values in role_map.values()) != 107_730:
        raise RuntimeError("Gate-A candidate denominator drift")
    identities: dict[tuple[str, str], Identity] = {}
    for key, row in rows.items():
        roles = tuple(sorted(role_map.get(key, []), key=lambda value: int(value["selection_rank"])))
        if len(roles) != N or [int(value["selection_rank"]) for value in roles] != list(range(1, N + 1)):
            raise RuntimeError(f"invalid N7 role geometry: {key}")
        if "|".join(value["match_id"] for value in roles) != row["selected_match_ids"]:
            raise RuntimeError(f"identity/role mismatch: {key}")
        truth, product, gap_count = 0, Decimal(1), 0
        for role in roles:
            outcome = outcomes.get(role["match_id"])
            if outcome is None:
                gap_count += 1
                continue
            truth = truth * 3 + CODES.index(outcome["result_code"])
            product *= decimal(outcome["winning_sp"], "winning SP")
        identities[key] = Identity(
            key=key,
            row=row,
            roles=roles,
            truth_index=None if gap_count else truth,
            payout_per_ticket=None if gap_count else UNIT_STAKE * PAYOUT_FACTOR * product,
            outcome_gap_count=gap_count,
        )
    return identities


def q_weights(identity: Identity) -> list[float]:
    weights = [1.0]
    for role in identity.roles:
        vector = [float(role[f"q_weight{code}"]) for code in CODES]
        if any(value <= 0 or not math.isfinite(value) for value in vector) or abs(sum(vector) - 1.0) > 1e-8:
            raise RuntimeError(f"invalid Q probability vector: {identity.key}")
        weights = [prior * value for prior in weights for value in vector]
    if len(weights) != FULL_K or abs(sum(weights) - 1.0) > 1e-8:
        raise RuntimeError("Q ticket-space normalization drift")
    return weights


def weighted_without_replacement_rank(identity: Identity, seed: int) -> int:
    if identity.truth_index is None:
        raise RuntimeError("cannot sample an identity missing canonical outcomes")
    weights = q_weights(identity)
    truth = identity.truth_index
    truth_key = -math.log(max(stable_uniform("bj133", "Q_WOR", seed, identity.key[0], identity.key[1], truth), 1e-18)) / weights[truth]
    rank = 1
    for ordinal, weight in enumerate(weights):
        if ordinal == truth:
            continue
        key = -math.log(max(stable_uniform("bj133", "Q_WOR", seed, identity.key[0], identity.key[1], ordinal), 1e-18)) / weight
        if key < truth_key:
            rank += 1
    return rank


def expanded_plans(plans: list[dict[str, str]]) -> Iterator[dict[str, str]]:
    for plan in plans:
        if plan["ticket_mechanism"] == "EXACT_K4_FULL":
            yield {**plan, "seed": "NA", "seed_role": "CONTROL"}
        else:
            for seed in ("133001", "133002", "133003"):
                yield {**plan, "seed": seed, "seed_role": "PRIMARY" if seed == "133001" else "SENSITIVITY"}


def plan_key(plan: dict[str, str]) -> tuple[str, str, str]:
    return plan["config_id"], plan["allocator_id"], plan["seed"]


def outcome_status(plan: dict[str, str], selected: list[Identity]) -> str:
    if plan["selection_status"] != "AVAILABLE":
        return "NO_BET_GATE_A"
    if not selected:
        raise RuntimeError("available Gate-A plan has no selected identities")
    return "UNAVAILABLE_CANONICAL_OUTCOME" if any(identity.outcome_gap_count for identity in selected) else "SETTLED"


def settle_plan(
    plan: dict[str, str],
    identities: dict[tuple[str, str], Identity],
    rank_cache: dict[tuple[tuple[str, str], int], int],
    ticket_writer: csv.DictWriter,
    audit: TaxAudit,
) -> dict[str, object]:
    portfolio_ids = tuple(value for value in plan["selected_portfolio_ids"].split("|") if value)
    selected = [identities[(plan["gate_id"], portfolio_id)] for portfolio_id in portfolio_ids]
    status = outcome_status(plan, selected)
    common = {
        "issue": plan["issue"], "fold": plan["fold"], "year": plan["year"], "issue_instance": plan["issue_instance"],
        "config_id": plan["config_id"], "config_role": plan["config_role"], "gate_id": plan["gate_id"],
        "top_k_id": plan["top_k_id"], "allocator_id": plan["allocator_id"], "allocator_family": plan["allocator_family"],
        "allocator_interpretation": allocator_interpretation(plan), "seed": plan["seed"], "seed_role": plan["seed_role"],
        "ticket_M": plan["ticket_M"], "ticket_mechanism": plan["ticket_mechanism"],
        "frozen_selection_status": plan["selection_status"], "settlement_status": status,
        "selected_identity_count": len(selected), "selected_portfolio_ids": plan["selected_portfolio_ids"],
        "full_control_stake_yuan": decimal(plan["full_control_stake_yuan"], "full control stake"),
        "unique_match_count": int(plan["unique_match_count"]), "total_leg_slots": int(plan["total_leg_slots"]),
        "overlap_leg_slots": int(plan["overlap_leg_slots"]), "max_match_exposure": int(plan["max_match_exposure"]),
        "effective_independent_match_count": float(plan["effective_independent_match_count"]),
        "max_pairwise_jaccard": float(plan["max_pairwise_jaccard"]), "max_q_delete_exposure": int(plan["max_q_delete_exposure"]),
    }
    if status != "SETTLED":
        return {
            **common, "planned_draw_count": 0, "planned_stake_yuan": Decimal(0), "capital_utilization_vs_exact_full": None,
            "hit_ticket_count": 0, "coverage_hit": 0, "gross_pre_tax_yuan": Decimal(0), "tax_yuan": Decimal(0),
            "after_tax_gross_yuan": Decimal(0), "pre_tax_net_yuan": Decimal(0), "tax_adjusted_net_yuan": Decimal(0),
            "no_tax_roi": None, "tax_adjusted_roi": None, "gross_top_identity_share": None,
            "outcome_gap_count": sum(identity.outcome_gap_count for identity in selected), "taxable_hit_ticket_count": 0,
            "non_taxable_hit_ticket_count": 0,
        }
    hit_count, gross, tax = 0, Decimal(0), Decimal(0)
    individual_gross: list[Decimal] = []
    ticket_m = int(plan["ticket_M"])
    for identity in selected:
        if identity.payout_per_ticket is None:
            raise RuntimeError("settled identity lacks ticket payout")
        if plan["ticket_mechanism"] == "EXACT_K4_FULL":
            hit = 1
        else:
            cache_key = identity.key, int(plan["seed"])
            if cache_key not in rank_cache:
                rank_cache[cache_key] = weighted_without_replacement_rank(identity, int(plan["seed"]))
            hit = int(rank_cache[cache_key] <= ticket_m)
        if not hit:
            individual_gross.append(Decimal(0))
            continue
        # Persist and aggregate one canonical ticket-level monetary amount so
        # the visible ticket ledger, the policy ledger, and tax reconciliation
        # agree exactly at the declared ¥0.000001 precision.
        per_ticket_gross = identity.payout_per_ticket.quantize(MONEY_QUANTUM)
        per_ticket_tax = ticket_tax(per_ticket_gross).quantize(MONEY_QUANTUM)
        hit_count += 1
        gross += per_ticket_gross
        tax += per_ticket_tax
        individual_gross.append(per_ticket_gross)
        audit.add(per_ticket_tax, 1)
        ticket_writer.writerow({
            "issue": plan["issue"], "fold": plan["fold"], "year": plan["year"], "issue_instance": plan["issue_instance"],
            "config_id": plan["config_id"], "allocator_id": plan["allocator_id"], "seed": plan["seed"],
            "portfolio_id": identity.key[1], "winning_ticket_gross_yuan": money(per_ticket_gross),
            "winning_ticket_count": 1, "per_ticket_tax_yuan": money(per_ticket_tax), "tax_yuan": money(per_ticket_tax),
            "tax_rule": "20pct_if_each_ticket_gross_gte_10000_no_aggregate_pooling",
        })
    draws = len(selected) * ticket_m
    stake = UNIT_STAKE * draws
    pre_tax_net, tax_net = gross - stake, gross - tax - stake
    taxable = sum(1 for value in individual_gross if value and ticket_tax(value))
    return {
        **common, "planned_draw_count": draws, "planned_stake_yuan": stake,
        "capital_utilization_vs_exact_full": Decimal(0) if not common["full_control_stake_yuan"] else stake / common["full_control_stake_yuan"],
        "hit_ticket_count": hit_count, "coverage_hit": int(bool(hit_count)), "gross_pre_tax_yuan": gross, "tax_yuan": tax,
        "after_tax_gross_yuan": gross - tax, "pre_tax_net_yuan": pre_tax_net, "tax_adjusted_net_yuan": tax_net,
        "no_tax_roi": pre_tax_net / stake if stake else None, "tax_adjusted_roi": tax_net / stake if stake else None,
        "gross_top_identity_share": max(individual_gross, default=Decimal(0)) / gross if gross else None, "outcome_gap_count": 0,
        "taxable_hit_ticket_count": taxable, "non_taxable_hit_ticket_count": hit_count - taxable,
    }


def serializable(row: dict[str, object]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in row.items():
        if isinstance(value, Decimal):
            result[key] = ratio(value) if any(token in key for token in ("roi", "share", "hhi", "utilization", "rate")) else money(value)
        elif isinstance(value, float):
            result[key] = ratio(value)
        else:
            result[key] = value
    return result


@dataclass
class Metric:
    meta: dict[str, object]
    ordered: list[dict[str, object]]

    def summary(self, scope: str, value: str) -> dict[str, object]:
        rows = [row for row in self.ordered if row["settlement_status"] == "SETTLED"]
        no_bet = sum(row["settlement_status"] == "NO_BET_GATE_A" for row in self.ordered)
        unavailable = sum(row["settlement_status"] == "UNAVAILABLE_CANONICAL_OUTCOME" for row in self.ordered)
        stake = sum((row["planned_stake_yuan"] for row in rows), Decimal(0))
        full_stake = sum((row["full_control_stake_yuan"] for row in rows), Decimal(0))
        gross = sum((row["gross_pre_tax_yuan"] for row in rows), Decimal(0))
        tax = sum((row["tax_yuan"] for row in rows), Decimal(0))
        pre_tax_net = sum((row["pre_tax_net_yuan"] for row in rows), Decimal(0))
        tax_net = sum((row["tax_adjusted_net_yuan"] for row in rows), Decimal(0))
        hits = sum(int(row["hit_ticket_count"]) for row in rows)
        coverage = sum(int(row["coverage_hit"]) for row in rows)
        issue_gross = [row["gross_pre_tax_yuan"] for row in rows]
        identity_share = [row["gross_top_identity_share"] for row in rows if row["gross_top_identity_share"] is not None]
        max_gross = max(issue_gross, default=Decimal(0))
        largest = next((row for row in rows if row["gross_pre_tax_yuan"] == max_gross), None)
        ex_rows = [row for row in rows if row is not largest]
        ex_stake = sum((row["planned_stake_yuan"] for row in ex_rows), Decimal(0))
        ex_pre_tax = sum((row["pre_tax_net_yuan"] for row in ex_rows), Decimal(0))
        ex_tax_net = sum((row["tax_adjusted_net_yuan"] for row in ex_rows), Decimal(0))
        cumulative, peak, max_drawdown, miss_streak, longest_miss = Decimal(0), Decimal(0), Decimal(0), 0, 0
        for row in rows:
            cumulative += row["tax_adjusted_net_yuan"]
            peak = max(peak, cumulative)
            max_drawdown = max(max_drawdown, peak - cumulative)
            miss_streak = 0 if int(row["coverage_hit"]) else miss_streak + 1
            longest_miss = max(longest_miss, miss_streak)
        return {
            "scope": scope, "scope_value": value, **self.meta,
            "frozen_available_issue_count": len(rows), "frozen_no_bet_issue_count": no_bet,
            "settled_issue_count": len(rows), "unavailable_outcome_issue_count": unavailable,
            "planned_draw_count": sum(int(row["planned_draw_count"]) for row in rows), "stake_yuan": stake,
            "full_control_stake_yuan": full_stake, "capital_utilization_vs_exact_full": stake / full_stake if full_stake else None,
            "hit_ticket_count": hits, "coverage_hits": coverage, "coverage_hit_rate": Decimal(coverage) / len(rows) if rows else None,
            "gross_pre_tax_yuan": gross, "tax_yuan": tax, "after_tax_gross_yuan": gross - tax,
            "pre_tax_net_yuan": pre_tax_net, "tax_adjusted_net_yuan": tax_net,
            "no_tax_roi": pre_tax_net / stake if stake else None, "tax_adjusted_roi": tax_net / stake if stake else None,
            "max_drawdown_yuan": max_drawdown, "longest_miss_streak": longest_miss,
            "gross_top_issue_share": max_gross / gross if gross else None,
            "gross_issue_hhi": sum((value / gross) ** 2 for value in issue_gross) if gross else None,
            "gross_top_identity_share": max(identity_share, default=None), "largest_issue_gross_yuan": max_gross,
            "ex_largest_issue_no_tax_roi": ex_pre_tax / ex_stake if ex_stake else None,
            "ex_largest_issue_tax_adjusted_roi": ex_tax_net / ex_stake if ex_stake else None,
            "mean_effective_independent_match_count": sum((Decimal(str(row["effective_independent_match_count"])) for row in rows), Decimal(0)) / len(rows) if rows else None,
            "max_match_exposure": max((int(row["max_match_exposure"]) for row in rows), default=0),
            "max_pairwise_jaccard": max((float(row["max_pairwise_jaccard"]) for row in rows), default=0.0),
            "max_q_delete_exposure": max((int(row["max_q_delete_exposure"]) for row in rows), default=0),
        }


def metric_meta(plan: dict[str, str]) -> dict[str, object]:
    return {
        "config_id": plan["config_id"], "config_role": plan["config_role"], "gate_id": plan["gate_id"],
        "top_k_id": plan["top_k_id"], "allocator_id": plan["allocator_id"], "allocator_family": plan["allocator_family"],
        "allocator_interpretation": allocator_interpretation(plan), "seed": plan["seed"], "seed_role": plan["seed_role"],
        "ticket_M": plan["ticket_M"], "ticket_mechanism": plan["ticket_mechanism"],
    }


def metrics_for(rows: list[dict[str, object]]) -> tuple[list[dict[str, object]], dict[tuple[str, str, str], list[dict[str, object]]]]:
    policy_rows: dict[tuple[str, str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        policy_rows[(str(row["config_id"]), str(row["allocator_id"]), str(row["seed"]))].append(row)
    summaries: list[dict[str, object]] = []
    for key, values in sorted(policy_rows.items()):
        values.sort(key=lambda row: (str(row["year"]), str(row["issue"]), str(row["fold"])))
        summaries.append(Metric(metric_meta(values[0]), values).summary("ALL", "ALL"))
        for year in sorted({str(row["year"]) for row in values}):
            summaries.append(Metric(metric_meta(values[0]), [row for row in values if row["year"] == year]).summary("YEAR", year))
        for fold in sorted({str(row["fold"]) for row in values}):
            summaries.append(Metric(metric_meta(values[0]), [row for row in values if row["fold"] == fold]).summary("FOLD", fold))
        for omit_year in sorted({str(row["year"]) for row in values}):
            summaries.append(Metric(metric_meta(values[0]), [row for row in values if row["year"] != omit_year]).summary("LEAVE_ONE_YEAR_OUT", omit_year))
    return summaries, policy_rows


def matched_rows(left: list[dict[str, object]], right: list[dict[str, object]], scope: str, value: str) -> tuple[list[tuple[dict[str, object], dict[str, object]]], int]:
    def retain(row: dict[str, object]) -> bool:
        return row["settlement_status"] == "SETTLED" and (scope == "ALL" or (row["year"] == value if scope == "YEAR" else row["fold"] == value if scope == "FOLD" else row["year"] != value))
    left_map = {str(row["issue_instance"]): row for row in left if retain(row)}
    right_map = {str(row["issue_instance"]): row for row in right if retain(row)}
    if len(left_map) != sum(retain(row) for row in left) or len(right_map) != sum(retain(row) for row in right):
        raise RuntimeError("non-unique complete issue within policy")
    pairs = [(left_map[key], right_map[key]) for key in sorted(left_map.keys() & right_map.keys())]
    return pairs, len(left_map | right_map)


def effect_row(
    effect: str,
    candidate: list[dict[str, object]],
    baseline: list[dict[str, object]],
    scope: str,
    value: str,
    baseline_config_id: str,
    baseline_allocator_id: str,
    baseline_seed: str,
) -> tuple[dict[str, object], list[tuple[dict[str, object], dict[str, object]]]]:
    pairs, candidate_issue_count = matched_rows(candidate, baseline, scope, value)
    left_stake = sum((left["planned_stake_yuan"] for left, _right in pairs), Decimal(0))
    right_stake = sum((right["planned_stake_yuan"] for _left, right in pairs), Decimal(0))
    left_pre = sum((left["pre_tax_net_yuan"] for left, _right in pairs), Decimal(0))
    right_pre = sum((right["pre_tax_net_yuan"] for _left, right in pairs), Decimal(0))
    left_tax = sum((left["tax_adjusted_net_yuan"] for left, _right in pairs), Decimal(0))
    right_tax = sum((right["tax_adjusted_net_yuan"] for _left, right in pairs), Decimal(0))
    left_gross = sum((left["gross_pre_tax_yuan"] for left, _right in pairs), Decimal(0))
    right_gross = sum((right["gross_pre_tax_yuan"] for _left, right in pairs), Decimal(0))
    left_tax_yuan = sum((left["tax_yuan"] for left, _right in pairs), Decimal(0))
    right_tax_yuan = sum((right["tax_yuan"] for _left, right in pairs), Decimal(0))
    left_cov = sum(int(left["coverage_hit"]) for left, _right in pairs)
    right_cov = sum(int(right["coverage_hit"]) for _left, right in pairs)
    def hhi(values: list[Decimal]) -> Decimal | None:
        total = sum(values, Decimal(0))
        return sum((value / total) ** 2 for value in values) if total else None
    left_hhi = hhi([left["gross_pre_tax_yuan"] for left, _right in pairs])
    right_hhi = hhi([right["gross_pre_tax_yuan"] for _left, right in pairs])
    left_share = max((left["gross_pre_tax_yuan"] for left, _right in pairs), default=Decimal(0)) / left_gross if left_gross else None
    right_share = max((right["gross_pre_tax_yuan"] for _left, right in pairs), default=Decimal(0)) / right_gross if right_gross else None
    return ({
        "scope": scope, "scope_value": value, "effect": effect, "config_id": candidate[0]["config_id"],
        "allocator_id": candidate[0]["allocator_id"], "seed": candidate[0]["seed"],
        "baseline_config_id": baseline_config_id, "baseline_allocator_id": baseline_allocator_id,
        "baseline_seed": baseline_seed, "support_issue_count": len(pairs), "candidate_issue_count": candidate_issue_count,
        "stake_yuan": left_stake, "baseline_stake_yuan": right_stake,
        "full_reference_stake_yuan": sum((left["full_control_stake_yuan"] for left, _right in pairs), Decimal(0)),
        "no_tax_roi": left_pre / left_stake if left_stake else None,
        "baseline_no_tax_roi": right_pre / right_stake if right_stake else None,
        "no_tax_roi_delta": (left_pre / left_stake) - (right_pre / right_stake) if left_stake and right_stake else None,
        "tax_adjusted_roi": left_tax / left_stake if left_stake else None,
        "baseline_tax_adjusted_roi": right_tax / right_stake if right_stake else None,
        "tax_adjusted_roi_delta": (left_tax / left_stake) - (right_tax / right_stake) if left_stake and right_stake else None,
        "gross_pre_tax_yuan_delta": left_gross - right_gross, "tax_yuan_delta": left_tax_yuan - right_tax_yuan,
        "coverage_hit_rate_delta": Decimal(left_cov - right_cov) / len(pairs) if pairs else None,
        "gross_top_issue_share_delta": (left_share - right_share) if left_share is not None and right_share is not None else None,
        "gross_issue_hhi_delta": (left_hhi - right_hhi) if left_hhi is not None and right_hhi is not None else None,
        "matched_support_rule": "complete issue/fold with both frozen plans SETTLED; no partial or cross-segment substitution",
    }, pairs)


def quantile(values: list[float], probability: float) -> float:
    if not values:
        return float("nan")
    position = (len(values) - 1) * probability
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return values[lower]
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def bootstrap(
    effect: dict[str, object],
    pairs: list[tuple[dict[str, object], dict[str, object]]],
    seed_label: str,
) -> list[dict[str, object]]:
    if not pairs:
        return []
    rng_seed = int(hashlib.sha256(seed_label.encode("utf-8")).hexdigest()[:16], 16)
    rng = random.Random(rng_seed)
    results: dict[str, list[float]] = {"no_tax_roi_delta": [], "tax_adjusted_roi_delta": []}
    for _replicate in range(BOOTSTRAP_REPLICATES):
        drawn = [pairs[rng.randrange(len(pairs))] for _ in range(len(pairs))]
        left_stake = sum((left["planned_stake_yuan"] for left, _right in drawn), Decimal(0))
        right_stake = sum((right["planned_stake_yuan"] for _left, right in drawn), Decimal(0))
        for metric, field in (("no_tax_roi_delta", "pre_tax_net_yuan"), ("tax_adjusted_roi_delta", "tax_adjusted_net_yuan")):
            left = sum((left[field] for left, _right in drawn), Decimal(0)) / left_stake
            right = sum((right[field] for _left, right in drawn), Decimal(0)) / right_stake
            results[metric].append(float(left - right))
    output = []
    for metric, values in results.items():
        values.sort()
        point = float(effect[metric]) if effect[metric] is not None else float("nan")
        positive = sum(value <= 0 for value in values) / len(values)
        negative = sum(value >= 0 for value in values) / len(values)
        output.append({
            "effect": effect["effect"], "config_id": effect["config_id"], "allocator_id": effect["allocator_id"],
            "seed": effect["seed"], "support_issue_count": len(pairs), "replicates": BOOTSTRAP_REPLICATES,
            "metric": metric, "point_estimate": point, "ci95_low": quantile(values, 0.025), "ci95_high": quantile(values, 0.975),
            "one_sided_positive_p": positive, "two_sided_sign_p": min(1.0, 2.0 * min(positive, negative)),
        })
    return output


def build_effects(policy_rows: dict[tuple[str, str, str], list[dict[str, object]]]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    effects: list[dict[str, object]] = []
    bootstrap_rows: list[dict[str, object]] = []
    scopes = [("ALL", "ALL")]
    years = sorted({str(row["year"]) for values in policy_rows.values() for row in values})
    folds = sorted({str(row["fold"]) for values in policy_rows.values() for row in values})
    scopes.extend(("YEAR", value) for value in years)
    scopes.extend(("FOLD", value) for value in folds)
    scopes.extend(("LEAVE_ONE_YEAR_OUT", value) for value in years)
    for config in ("PRIMARY_NO_GATE_K4_M64", "PRIMARY_NO_GATE_K4_M128"):
        full_config = "ECONOMIC_CONTROL_NO_GATE_K4_FULL"
        for allocator in ("Q_DELETE_EXPOSURE_CAP_1", "Q_DELETE_EXPOSURE_CAP_2"):
            for seed in ("133001", "133002", "133003"):
                candidate = policy_rows[(config, allocator, seed)]
                concentrated = policy_rows[(config, "CONCENTRATED_TOP_SCORE", seed)]
                full = policy_rows[(full_config, allocator, "NA")]
                for scope, value in scopes:
                    row, pairs = effect_row("ALLOCATOR_MINUS_CONCENTRATED", candidate, concentrated, scope, value, config, "CONCENTRATED_TOP_SCORE", seed)
                    effects.append(row)
                    if scope == "ALL":
                        bootstrap_rows.extend(bootstrap(row, pairs, f"bj133|{config}|{allocator}|{seed}|concentrated"))
                    row, pairs = effect_row("ALLOCATOR_MINUS_FULL_CAPITAL_NORMALIZED", candidate, full, scope, value, full_config, allocator, "NA")
                    effects.append(row)
                    if scope == "ALL":
                        bootstrap_rows.extend(bootstrap(row, pairs, f"bj133|{config}|{allocator}|{seed}|full"))
    return effects, bootstrap_rows


def comparison_diagnostics(effects: list[dict[str, object]], bootstraps: list[dict[str, object]]) -> tuple[list[dict[str, object]], dict[str, object]]:
    primary = [row for row in effects if row["scope"] == "ALL"]
    family_size = len(primary) * 2
    bootstrap_index = {(row["effect"], row["config_id"], row["allocator_id"], row["seed"], row["metric"]): row for row in bootstraps}
    output: list[dict[str, object]] = []
    persistence: dict[tuple[str, str, str], list[dict[str, object]]] = defaultdict(list)
    for row in primary:
        boot = bootstrap_index[(row["effect"], row["config_id"], row["allocator_id"], row["seed"], "no_tax_roi_delta")]
        boot_tax = bootstrap_index[(row["effect"], row["config_id"], row["allocator_id"], row["seed"], "tax_adjusted_roi_delta")]
        p = float(boot["two_sided_sign_p"])
        tax_p = float(boot_tax["two_sided_sign_p"])
        output.append({
            "comparison_id": "|".join(str(row[name]) for name in ("effect", "config_id", "allocator_id", "seed")),
            "effect": row["effect"], "config_id": row["config_id"], "allocator_id": row["allocator_id"], "seed": row["seed"],
            "is_primary_economic_comparison": "TRUE", "support_issue_count": row["support_issue_count"],
            "all_no_tax_roi_delta": row["no_tax_roi_delta"], "all_tax_adjusted_roi_delta": row["tax_adjusted_roi_delta"],
            "all_bootstrap_ci95_low": boot["ci95_low"], "all_bootstrap_ci95_high": boot["ci95_high"],
            "bonferroni_two_sided_p": min(1.0, p * family_size),
            "tax_bootstrap_ci95_low": boot_tax["ci95_low"], "tax_bootstrap_ci95_high": boot_tax["ci95_high"],
            "tax_bonferroni_two_sided_p": min(1.0, tax_p * family_size), "fwer_alpha": 0.05,
            "all_seed_persistence_group": f"{row['effect']}|{row['config_id']}|{row['allocator_id']}",
            "classification": "PRIMARY_IDENTIFIABLE_EFFECT; strict EV required before any promotion if durable positive",
        })
        persistence[(str(row["effect"]), str(row["config_id"]), str(row["allocator_id"]))].append(row)
    robust = []
    for key, values in persistence.items():
        if {str(row["seed"]) for row in values} != {"133001", "133002", "133003"}:
            continue
        global_positive = all(float(row["no_tax_roi_delta"]) > 0 and float(row["tax_adjusted_roi_delta"]) > 0 for row in values)
        if not global_positive:
            continue
        same = [row for row in effects if (row["effect"], row["config_id"], row["allocator_id"]) == key]
        chronological = [row for row in same if row["scope"] in {"YEAR", "FOLD", "LEAVE_ONE_YEAR_OUT"}]
        matching_diag = [row for row in output if (row["effect"], row["config_id"], row["allocator_id"]) == key]
        fwer_positive = matching_diag and all(
            float(row["bonferroni_two_sided_p"]) < 0.05
            and float(row["tax_bonferroni_two_sided_p"]) < 0.05
            and float(row["all_bootstrap_ci95_low"]) > 0
            and float(row["tax_bootstrap_ci95_low"]) > 0
            for row in matching_diag
        )
        if chronological and fwer_positive and all(float(row["no_tax_roi_delta"]) > 0 and float(row["tax_adjusted_roi_delta"]) > 0 for row in chronological):
            robust.append(key)
    decision = {
        "decision": "POSITIVE_REQUIRES_STRICT_INDEPENDENT_EV" if robust else "NO_PROMOTION",
        "promotion_authorized": False,
        "strict_independent_ev_required": bool(robust),
        "primary_effect_comparisons": len(primary),
        "primary_metric_tests_for_bonferroni": family_size,
        "strict_ev_candidates": ["|".join(key) for key in sorted(robust)],
        "rule": "A candidate must have positive no-tax and ticket-tax-adjusted deltas in every frozen seed, ALL/YEAR/FOLD/LOYO view, and Bonferroni-adjusted all-scope issue-bootstrap support before it can request strict independent EV. No result promotes purchase, production, or betting.",
    }
    for row in bootstraps:
        row["primary_family_size"] = family_size
        row["bonferroni_two_sided_p"] = min(1.0, float(row["two_sided_sign_p"]) * family_size)
        row["fwer_alpha"] = 0.05
        row["passes_fwer_positive"] = int(float(row["ci95_low"]) > 0 and float(row["bonferroni_two_sided_p"]) < 0.05)
    return output, decision


def validate_full_alignment(plans: list[dict[str, str]]) -> None:
    index = {(row["config_id"], row["allocator_id"], row["issue_instance"]): row for row in plans}
    for config in ("PRIMARY_NO_GATE_K4_M64", "PRIMARY_NO_GATE_K4_M128"):
        for allocator in {row["allocator_id"] for row in plans}:
            for issue_instance in {row["issue_instance"] for row in plans if row["config_id"] == config}:
                sampled = index[(config, allocator, issue_instance)]
                full = index[("ECONOMIC_CONTROL_NO_GATE_K4_FULL", allocator, issue_instance)]
                if sampled["selected_portfolio_ids"] != full["selected_portfolio_ids"] or sampled["selection_status"] != full["selection_status"]:
                    raise RuntimeError("sampled/FULL frozen identity sets drift")


def build(output: Path) -> dict[str, object]:
    if output.exists():
        raise RuntimeError(f"refusing immutable overwrite: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".bj133_gate_b_", dir=output.parent))
    try:
        provenance = validate_inputs()
        outcomes = load_outcomes()
        plans = load_plans()
        validate_full_alignment(plans)
        identities = load_identities(outcomes)
        rank_cache: dict[tuple[tuple[str, str], int], int] = {}
        rows: list[dict[str, object]] = []
        tax_audit: dict[tuple[str, str, str], TaxAudit] = defaultdict(TaxAudit)
        ticket_handles = gzip_writer(stage / "winning_ticket_tax_ledger.csv.gz", TICKET_FIELDS)
        try:
            ticket_writer = ticket_handles[-1]
            for plan in expanded_plans(plans):
                key = plan_key(plan)
                rows.append(settle_plan(plan, identities, rank_cache, ticket_writer, tax_audit[key]))
        finally:
            close_gzip(ticket_handles)
        if len(rows) != 52_200:
            raise RuntimeError(f"expanded settlement denominator drift: {len(rows)}")
        rows.sort(key=lambda row: (str(row["year"]), str(row["issue"]), str(row["fold"]), str(row["config_id"]), str(row["allocator_id"]), str(row["seed"])))
        write_gzip_csv(stage / "issue_allocator_settlement.csv.gz", SETTLEMENT_FIELDS, (serializable(row) for row in rows))
        summaries, policy_rows = metrics_for(rows)
        write_csv(stage / "allocator_frontier_summary.csv", SUMMARY_FIELDS, (serializable(row) for row in summaries))
        effects, bootstraps = build_effects(policy_rows)
        write_gzip_csv(stage / "matched_effects.csv.gz", EFFECT_FIELDS, (serializable(row) for row in effects))
        comparison_rows, decision = comparison_diagnostics(effects, bootstraps)
        write_csv(stage / "issue_bootstrap_diagnostics.csv", BOOTSTRAP_FIELDS, (serializable(row) for row in bootstraps))
        write_csv(stage / "multiple_comparison_diagnostics.csv", COMPARISON_FIELDS, (serializable(row) for row in comparison_rows))
        reconciliation = []
        summary_index = {(row["scope"], row["scope_value"], row["config_id"], row["allocator_id"], row["seed"]): row for row in summaries}
        for key, audit in sorted(tax_audit.items()):
            issue_tax = summary_index[("ALL", "ALL", *key)]["tax_yuan"]
            difference = audit.tax_yuan - issue_tax
            if abs(difference) > Decimal("0.000001"):
                raise RuntimeError(f"ticket-tax reconciliation drift for {key}: {difference}")
            reconciliation.append({
                "config_id": key[0], "allocator_id": key[1], "seed": key[2],
                "ticket_ledger_hit_ticket_count": audit.hit_tickets, "ticket_ledger_taxable_ticket_count": audit.taxable_tickets,
                "ticket_ledger_tax_yuan": audit.tax_yuan, "issue_ledger_tax_yuan": issue_tax, "difference_yuan": difference,
                "tax_rule": "20pct_if_each_ticket_gross_gte_10000_no_aggregate_pooling",
            })
        write_csv(stage / "ticket_tax_reconciliation.csv", TAX_RECON_FIELDS, (serializable(row) for row in reconciliation))
        write_csv(stage / "source_census.csv", SOURCE_FIELDS, [
            {"source": "bj133_gate_a_preoutcome_v1", "role": "accepted immutable complete-issue allocation/ticket freeze", "identity": "SHA256SUMS.json", "sha256": FREEZE_MANIFEST, "rows": 20_880, "join_status": "all frozen allocator rows retained; no selection or cap is recomputed"},
            {"source": "bj95_gate_b_outcome_settlement_v2r8", "role": "canonical trusted final-SP outcome truth", "identity": "canonical_outcome_join.csv", "sha256": OUTCOME_PAYLOAD, "rows": len(outcomes), "join_status": "trusted result/final-SP only; gaps retain zero stake"},
        ])
        (stage / "decision.json").write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        card = {
            "issue": 133,
            "contract": CONTRACT,
            "runner_version": VERSION,
            "stage": "GATE_B_ONE_SHOT_COMPLETE_ISSUE_OUTCOME_SETTLEMENT",
            "provenance": provenance,
            "input_boundary": "Only immutable Gate-A allocation/candidate/Q-role inputs and the canonical trusted final-SP outcome payload are read. No candidate selection, cap, ticket budget, or upstream #137 result is recomputed or used as an economic edge.",
            "scope": "historical paper research only; no purchase, production, betting, or promotion authority.",
            "sampling": "Q_INFORMED_WOR_DISTINCT uses deterministic exponential-race weighted sampling without replacement over the 3^7 ticket space, keyed by frozen gate/portfolio identity and frozen seed. EXACT_K4_FULL covers all 2187 sequences once. There are no duplicate selected tickets in the sampled arms.",
            "tax": "Tax is secondary to no_tax_roi and is applied per individual winning ticket: 20% iff that one ticket's gross is at least ¥10,000. No issue, identity, arm, policy, draw count, or portfolio aggregate is used to cross the tax threshold. winning_ticket_tax_ledger.csv.gz and ticket_tax_reconciliation.csv make this auditable.",
            "comparisons": "Primary effects are Q-delete exposure cap 1/2 minus CONCENTRATED_TOP_SCORE on exact complete-issue matched support at M64/M128 and the same allocator minus its exact-K4 FULL capital-normalized ROI reference. FULL raw stake is preserved separately; it is not a literal equal-ticket-budget comparator. Secondary ESP300_GM290 cap 1/2/4 rows are descriptive only.",
            "frontier": "All frozen cap rows are retained. Match/Jaccard/joint structural no-bets and identity-equivalent cap rows are controls, not independent strategies; their inability to diversify stems from the frozen six-shared-leg construction.",
            "metrics": "Pre-tax no_tax_roi precedes tax-adjusted ROI. Complete-issue participation, capital utilization, payout concentration, ex-largest issue, drawdown, YEAR/FOLD/LOYO, deterministic issue bootstrap, and a 24-comparison Bonferroni diagnostic are included.",
            "decision": decision,
        }
        (stage / "settlement_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        shutil.copy2(__file__, stage / "settlement_runner.py")
        (stage / "README.md").write_text(
            "# #133 Gate B — diversified N7 allocation\n\n"
            "One-shot canonical outcome settlement of the accepted Gate-A allocator freeze. "
            "Tax is computed per winning ticket, never after pooling issue or policy receipts. "
            "Replay with `python3 settlement_runner.py --output <new-dir>`; staging is under `results/`, never `/tmp`.\n",
            encoding="utf-8",
        )
        compressed = ("issue_allocator_settlement.csv.gz", "matched_effects.csv.gz", "winning_ticket_tax_ledger.csv.gz")
        content = {
            "contract_version": "bj133-gate-b-portable-content-v1",
            "gzip_payloads": {name: {"canonical_decompressed_sha256": decompressed_digest(stage / name)[0], "canonical_decompressed_bytes": decompressed_digest(stage / name)[1]} for name in compressed},
            "non_compressed_controls": {item.name: sha256(item) for item in sorted(stage.iterdir()) if item.is_file() and item.name not in compressed},
        }
        (stage / "CONTENT_IDENTITY.json").write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest = {item.name: sha256(item) for item in sorted(stage.iterdir()) if item.is_file()}
        (stage / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(stage, output)
        return {
            "manifest_sha256": sha256(output / "SHA256SUMS.json"),
            "content_identity_sha256": sha256(output / "CONTENT_IDENTITY.json"),
            "settlement_rows": len(rows), "summary_rows": len(summaries), "matched_effect_rows": len(effects),
            "decision": decision,
        }
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(json.dumps(build(args.output.resolve()), sort_keys=True))


if __name__ == "__main__":
    main()
