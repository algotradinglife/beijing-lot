#!/usr/bin/env python3
"""Settle #170's fixed selector x allocation stack on one paired issue cohort.

The nine cells, identities, role vectors and support are read only from the
accepted #170 Gate-A v2 package.  A selector issue is settled only when every
one of its frozen identities has a trusted canonical outcome; the controlling
THREE_WAY_ALL row settles all nine cells only when all three selector policies
are available.  Missing outcomes therefore create nine zero-execution rows,
never fake losing stake or a partially comparable selector.
"""
from __future__ import annotations

import argparse
import array
import csv
import gzip
import hashlib
import importlib.util
import io
import json
import math
import os
import random
import shutil
import statistics
import struct
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Sequence


CONTRACT = "BJ-HIST-N7-SELECTOR-ALLOCATOR-STACK-001"
VERSION = "bj170-gate-b-v1"
STAKE_PER_TICKET = 2.0
PAYOUT_FACTOR = 0.65
TAX_RATE = 0.20
TAX_LINE_YUAN = 10_000.0
BOOTSTRAP_REPLICATES = 20_000
BOOTSTRAP_SEED = 170_177
CODE_ORD = {"3": 0, "1": 1, "0": 2}

EXPECTED_GATE_A_MANIFEST = "bb60ac5638d29674ad8c1c05f1ffe3ab9cdf12acb70ebdae6cea679743136d87"
EXPECTED_GATE_A_CONTENT = "adc4d0f96628c784149da998a20e8830cde26db4001fe457eaf9ca4b7bb74223"
EXPECTED_BJ167_MANIFEST = "b3fa02f5cc2722932ff55fffb0bd9672508f6e78104cfb2458ad81c826f3b313"
EXPECTED_BJ167_CONTENT = "bfe29083b74d5d212555c261e888d6f5d4d5fd163b56e1876944d1f5d04aa5c7"
EXPECTED_OUTCOME_MANIFEST = "fbbd3b53bd86f4bb0caff8f2587933cd6b0e4e7d04fb0f709bac934ec2a705cc"
EXPECTED_OUTCOME_PAYLOAD = "13d709d253c31519734dbf0447e6961ac8a6060772975d7461741224e5251a89"
EXPECTED_ALLOCATOR_SHA256 = "5f8f5d75dd15758e62dd2a05f7b674cb12824b38ccba35cfee772e8904a8bd93"

SELECTOR_ALIASES = ("BEST_FULL", "Q_SOURCE", "MODEL_SOURCE")
ARM_ALIASES = ("FULL_ENUMERATED", "Q_TOP_MASS_M192", "MODEL_CAP1_M512")
ARM_M = {"FULL_ENUMERATED": 2187, "Q_TOP_MASS_M192": 192, "MODEL_CAP1_M512": 512}
ARM_SPEC = {
    "FULL_ENUMERATED": ("NA", "FULL_ENUMERATED", None),
    "Q_TOP_MASS_M192": ("Q_WEIGHT", "DETERMINISTIC_TOP_MASS", None),
    "MODEL_CAP1_M512": ("MODEL_P_CAL", "CAPPED_REPEAT", 1),
}


def repo_root() -> Path:
    for candidate in (Path(__file__).resolve().parent, *Path(__file__).resolve().parents):
        if (candidate / ".git").exists() and (candidate / "results").is_dir():
            return candidate
    raise RuntimeError("repository root unavailable")


ROOT = repo_root()
GATE_A = ROOT / "results" / "bj170_gate_a_preoutcome_v2"
BJ167 = ROOT / "results" / "bj167_gate_b_strategy_atlas_v3r1_postscreen_exact_identity_v1"
OUTCOME_DIR = ROOT / "results" / "bj95_gate_b_outcome_settlement_v2r8"
OUTCOME_PATH = OUTCOME_DIR / "canonical_outcome_join.csv"
DEFAULT_OUTPUT = ROOT / "results" / "bj170_gate_b_selector_allocator_stack_v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def verify_package(directory: Path, expected_manifest: str, expected_content: str | None = None) -> dict[str, str]:
    manifest_path = directory / "SHA256SUMS.json"
    if sha256_file(manifest_path) != expected_manifest:
        raise RuntimeError(f"manifest drift: {directory.name}")
    if expected_content is not None and sha256_file(directory / "CONTENT_IDENTITY.json") != expected_content:
        raise RuntimeError(f"content identity drift: {directory.name}")
    declared = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual_names = sorted(path.name for path in directory.iterdir() if path.is_file() and path.name != "SHA256SUMS.json")
    if sorted(declared) != actual_names:
        raise RuntimeError(f"manifest coverage drift: {directory.name}")
    for name, digest in declared.items():
        if sha256_file(directory / name) != digest:
            raise RuntimeError(f"payload drift: {directory.name}/{name}")
    return declared


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_gzip(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fields: Sequence[str], rows: Iterable[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n", extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def write_gzip(path: Path, fields: Sequence[str], rows: Iterable[dict[str, object]]) -> None:
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            text = io.TextIOWrapper(zipped, encoding="utf-8", newline="")
            writer = csv.DictWriter(text, fieldnames=fields, lineterminator="\n", extrasaction="raise")
            writer.writeheader()
            writer.writerows(rows)
            text.flush()
            text.detach()


def fmt_money(value: float) -> str:
    return f"{value:.6f}"


def fmt_ratio(value: float | None) -> str:
    return "" if value is None else f"{value:.12f}"


def safe_ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def numeric_bridge_delta(actual: str, expected: str, tolerance: float) -> float:
    """Accept only documented serialization noise in a numeric source bridge."""
    delta = float(actual) - float(expected)
    if abs(delta) > tolerance:
        raise RuntimeError(
            f"numeric source bridge drift: actual={actual} expected={expected} delta={delta}"
        )
    return delta


def load_gate_a_module():
    path = GATE_A / "freeze_runner.py"
    spec = importlib.util.spec_from_file_location("bj170_gate_a_frozen_runner", path)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError("Gate-A runner loader unavailable")
    spec.loader.exec_module(module)
    return module


def load_outcomes() -> dict[str, dict[str, object]]:
    rows = read_csv(OUTCOME_PATH)
    outcomes: dict[str, dict[str, object]] = {}
    for row in rows:
        if row["settlement_quality"] != "trusted" or row["has_trusted_settlement"] != "1":
            raise RuntimeError("canonical outcome contains an untrusted row")
        if row["result_code"] not in CODE_ORD or float(row["winning_sp"]) <= 0:
            raise RuntimeError("canonical outcome contains an invalid result/SP")
        outcomes[row["match_id"]] = {
            "truth_code": CODE_ORD[row["result_code"]],
            "winning_sp": float(row["winning_sp"]),
            "source": row["winning_sp_source"],
        }
    return outcomes


def load_frozen_data() -> dict[str, object]:
    identities = read_gzip(GATE_A / "identity_freeze.csv.gz")
    roles = read_gzip(GATE_A / "role_vector_freeze.csv.gz")
    digests = read_gzip(GATE_A / "identity_allocation_digest.csv.gz")
    participation = read_csv(GATE_A / "selector_issue_participation.csv")
    support_membership = read_csv(GATE_A / "support_issue_membership.csv")
    selectors = read_csv(GATE_A / "selector_registry.csv")
    allocations = read_csv(GATE_A / "allocation_registry.csv")
    if len(identities) != 1779 or len(roles) != len(identities) * 7 or len(digests) != len(identities) * 3:
        raise RuntimeError("Gate-A denominator drift")
    common_issues = {
        row["issue_instance"] for row in support_membership if row["support_view_id"] == "THREE_WAY_ALL"
    }
    if len(common_issues) != 177:
        raise RuntimeError(f"THREE_WAY_ALL support drift: {len(common_issues)}")
    return {
        "identities": identities,
        "roles": roles,
        "digests": digests,
        "participation": participation,
        "common_issues": common_issues,
        "selectors": selectors,
        "allocations": allocations,
    }


def policy_status(identity_rows: Sequence[dict[str, object]]) -> str:
    if not identity_rows:
        return "NO_BET_FROZEN"
    return "SETTLED" if all(bool(row["outcome_available"]) for row in identity_rows) else "UNAVAILABLE_CANONICAL_OUTCOME"


def common_policy_status(statuses: dict[str, str]) -> str:
    """Fail closed for the complete selector-by-issue comparison policy."""
    if set(statuses) != set(SELECTOR_ALIASES):
        raise RuntimeError(f"incomplete selector policy status: {sorted(statuses)}")
    return (
        "SETTLED_COMMON"
        if all(status == "SETTLED" for status in statuses.values())
        else "UNAVAILABLE_COMMON_OUTCOME"
    )


def ticket_settlement(
    counts: Sequence[int], truth_ordinal: int, payout_yuan: float, available: bool
) -> dict[str, float | int]:
    """Settle independent tickets with the frozen per-ticket tax contract."""
    hit = int(counts[truth_ordinal]) if available else 0
    gross = payout_yuan * hit if available else 0.0
    tax = payout_yuan * TAX_RATE * hit if available and payout_yuan >= TAX_LINE_YUAN else 0.0
    return {
        "hit_ticket_count": hit,
        "coverage_hit": int(hit > 0),
        "gross_yuan": gross,
        "tax_yuan": tax,
        "tax_line_exposure_yuan": (
            payout_yuan * hit if available and payout_yuan >= TAX_LINE_YUAN else 0.0
        ),
        "tax_line_hit_ticket_count": (
            hit if available and payout_yuan >= TAX_LINE_YUAN else 0
        ),
    }


def counts_fingerprint(counts: Sequence[int]) -> str:
    return hashlib.sha256(json.dumps(tuple(int(value) for value in counts), separators=(",", ":")).encode("utf-8")).hexdigest()


def settle_identities(frozen: dict[str, object], outcomes: dict[str, dict[str, object]]) -> tuple[list[dict[str, object]], dict[tuple[str, str, str], list[dict[str, object]]]]:
    gate = load_gate_a_module()
    if gate.EXPECTED_ALLOCATOR_SHA256 != EXPECTED_ALLOCATOR_SHA256:
        raise RuntimeError("Gate-A allocator binding drift")
    allocator = gate.FrozenAllocator()
    role_by_key: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for role in frozen["roles"]:
        role_by_key[(role["selector_alias"], role["issue_instance"], role["portfolio_id"])].append(role)
    digest_by_key = {
        (row["selector_alias"], row["issue_instance"], row["portfolio_id"], row["allocation_arm"]): row
        for row in frozen["digests"]
    }
    full_counts = (1,) * 2187
    result: list[dict[str, object]] = []
    by_policy: dict[tuple[str, str, str], list[dict[str, object]]] = defaultdict(list)
    for identity in frozen["identities"]:
        key = (identity["selector_alias"], identity["issue_instance"], identity["portfolio_id"])
        roles = sorted(role_by_key[key], key=lambda row: int(row["selection_rank"]))
        mids = identity["selected_match_ids"].split("|")
        if len(roles) != 7 or [row["match_id"] for row in roles] != mids:
            raise RuntimeError(f"identity/role mismatch: {key}")
        missing = tuple(mid for mid in mids if mid not in outcomes)
        available = not missing
        truth = -1
        payout = 0.0
        if available:
            truth_codes = [int(outcomes[mid]["truth_code"]) for mid in mids]
            truth = sum(code * (3 ** (6 - index)) for index, code in enumerate(truth_codes))
            payout = STAKE_PER_TICKET * PAYOUT_FACTOR * math.prod(float(outcomes[mid]["winning_sp"]) for mid in mids)
        cached_weights: dict[str, tuple[float, ...]] = {}
        for arm in ARM_ALIASES:
            source, mechanism, cap = ARM_SPEC[arm]
            if arm == "FULL_ENUMERATED":
                counts = full_counts
            else:
                weights = cached_weights.setdefault(source, gate.role_product_weights(roles, source))
                counts = allocator.allocate(weights, mechanism, ARM_M[arm], cap)
            expected_digest = digest_by_key[key + (arm,)]
            fingerprint = counts_fingerprint(counts)
            if fingerprint != expected_digest["counts_sha256"]:
                raise RuntimeError(f"Gate-A allocation digest mismatch: {key}/{arm}")
            economics = ticket_settlement(counts, truth, payout, available)
            unique = sum(value > 0 for value in counts)
            duplicate = sum(max(value - 1, 0) for value in counts)
            if unique != int(expected_digest["unique_ticket_count"]) or duplicate != int(expected_digest["duplicate_ticket_count"]):
                raise RuntimeError(f"Gate-A allocation census mismatch: {key}/{arm}")
            record = {
                "selector_alias": identity["selector_alias"],
                "selector_id": identity["selector_id"],
                "issue": identity["issue"],
                "year": identity["year"],
                "fold": identity["fold"],
                "issue_instance": identity["issue_instance"],
                "portfolio_id": identity["portfolio_id"],
                "allocation_arm": arm,
                "outcome_available": available,
                "missing_match_ids": missing,
                "truth_ordinal": truth,
                "payout_yuan": payout,
                "planned_ticket_count": ARM_M[arm],
                "planned_stake_yuan": ARM_M[arm] * STAKE_PER_TICKET,
                "unique_ticket_count": unique,
                "duplicate_ticket_count": duplicate,
                **economics,
                "counts_sha256": fingerprint,
            }
            result.append(record)
            by_policy[(identity["selector_alias"], identity["issue_instance"], arm)].append(record)
    return result, by_policy


def sum_records(records: Sequence[dict[str, object]], execute: bool) -> dict[str, float]:
    if not execute:
        return {
            "executed_identity_count": 0.0, "ticket_count": 0.0, "stake_yuan": 0.0,
            "gross_yuan": 0.0, "tax_yuan": 0.0, "hit_ticket_count": 0.0,
            "coverage_hits": 0.0, "unique_ticket_count": 0.0, "duplicate_ticket_count": 0.0,
            "tax_line_exposure_yuan": 0.0, "tax_line_hit_ticket_count": 0.0,
        }
    return {
        "executed_identity_count": float(len(records)),
        "ticket_count": float(sum(int(row["unique_ticket_count"]) + int(row["duplicate_ticket_count"]) for row in records)),
        "stake_yuan": sum(float(row["planned_stake_yuan"]) for row in records),
        "gross_yuan": sum(float(row["gross_yuan"]) for row in records),
        "tax_yuan": sum(float(row["tax_yuan"]) for row in records),
        "hit_ticket_count": float(sum(int(row["hit_ticket_count"]) for row in records)),
        "coverage_hits": float(sum(int(row["coverage_hit"]) for row in records)),
        "unique_ticket_count": float(sum(int(row["unique_ticket_count"]) for row in records)),
        "duplicate_ticket_count": float(sum(int(row["duplicate_ticket_count"]) for row in records)),
        "tax_line_exposure_yuan": sum(float(row["tax_line_exposure_yuan"]) for row in records),
        "tax_line_hit_ticket_count": float(sum(int(row["tax_line_hit_ticket_count"]) for row in records)),
    }


def load_expected_source_rows() -> dict[tuple[str, str], dict[str, str]]:
    selector_id_by_alias = {
        row["selector_alias"]: row["selector_id"] for row in read_csv(GATE_A / "selector_registry.csv")
    }
    expected: dict[tuple[str, str], dict[str, str]] = {}
    with gzip.open(BJ167 / "chart_source_selector_full_surface_v3r1.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            for alias, selector_id in selector_id_by_alias.items():
                if row["selector_id"] == selector_id:
                    expected[(alias, "FULL_ENUMERATED")] = row
    with gzip.open(BJ167 / "chart_source_full_dense_m_curve_v3r1.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["selector_id"] == selector_id_by_alias["Q_SOURCE"] and row["weight_source"] == "Q_WEIGHT" and row["mechanism"] == "DETERMINISTIC_TOP_MASS" and row["M"] == "192":
                expected[("Q_SOURCE", "Q_TOP_MASS_M192")] = row
            if row["selector_id"] == selector_id_by_alias["MODEL_SOURCE"] and row["weight_source"] == "MODEL_P_CAL" and row["mechanism"] == "CAPPED_REPEAT" and row["cap"] == "1" and row["M"] == "512":
                expected[("MODEL_SOURCE", "MODEL_CAP1_M512")] = row
    required = {
        ("BEST_FULL", "FULL_ENUMERATED"),
        ("Q_SOURCE", "FULL_ENUMERATED"),
        ("Q_SOURCE", "Q_TOP_MASS_M192"),
        ("MODEL_SOURCE", "FULL_ENUMERATED"),
        ("MODEL_SOURCE", "MODEL_CAP1_M512"),
    }
    if set(expected) != required:
        raise RuntimeError(f"#167 source bridge rows incomplete: {set(expected)}")
    return expected


def reproduce_source_rows(
    frozen: dict[str, object], by_policy: dict[tuple[str, str, str], list[dict[str, object]]]
) -> list[dict[str, object]]:
    expected = load_expected_source_rows()
    participation = {
        (row["selector_alias"], row["issue_instance"]): row for row in frozen["participation"]
    }
    selector_issues = {
        alias: sorted(issue for selector, issue in participation if selector == alias)
        for alias in SELECTOR_ALIASES
    }
    total_identity = {
        alias: sum(int(participation[(alias, issue)]["selected_identity_count"]) for issue in selector_issues[alias])
        for alias in SELECTOR_ALIASES
    }
    rows: list[dict[str, object]] = []
    for key, source in sorted(expected.items()):
        alias, arm = key
        aggregate = defaultdict(float)
        settled = unavailable = no_bet = 0
        for issue in selector_issues[alias]:
            records = by_policy.get((alias, issue, arm), [])
            status = policy_status(records)
            if status == "SETTLED":
                settled += 1
                for field, value in sum_records(records, True).items():
                    aggregate[field] += value
            elif status == "NO_BET_FROZEN":
                no_bet += 1
            else:
                unavailable += 1
        stake = aggregate["stake_yuan"]
        gross = aggregate["gross_yuan"]
        tax = aggregate["tax_yuan"]
        roi = safe_ratio(gross - stake, stake)
        tax_roi = safe_ratio(gross - tax - stake, stake)
        coverage = safe_ratio(aggregate["coverage_hits"], float(total_identity[alias]))
        ticket_hit = safe_ratio(aggregate["hit_ticket_count"], aggregate["ticket_count"])
        actual = {
            "stake_yuan": fmt_money(stake),
            "gross_pre_tax_yuan": fmt_money(gross),
            "no_tax_roi": fmt_ratio(roi),
            "tax_adjusted_roi": fmt_ratio(tax_roi),
            "coverage_hit_rate": fmt_ratio(coverage),
            "ticket_hit_rate": fmt_ratio(ticket_hit),
        }
        comparisons = {
            "stake_yuan": (actual["stake_yuan"], source["stake_yuan"], 5e-7),
            "gross_pre_tax_yuan": (actual["gross_pre_tax_yuan"], source["gross_pre_tax_yuan"], 5e-7),
            "no_tax_roi": (actual["no_tax_roi"], source["no_tax_roi"], 1e-10),
            "coverage_hit_rate": (actual["coverage_hit_rate"], source["coverage_hit_rate"], 1e-10),
            "ticket_hit_rate": (actual["ticket_hit_rate"], source["ticket_hit_rate"], 1e-10),
        }
        if "tax_adjusted_roi" in source:
            comparisons["tax_adjusted_roi"] = (
                actual["tax_adjusted_roi"],
                source["tax_adjusted_roi"],
                1e-10,
            )
        deltas = {}
        for field, (actual_value, expected_value, tolerance) in comparisons.items():
            try:
                delta = numeric_bridge_delta(actual_value, expected_value, tolerance)
            except RuntimeError as error:
                raise RuntimeError(f"#167 source reproduction drift {alias}/{arm}/{field}: {error}") from error
            deltas[field] = delta
        if "selector_policy_count" in source and (
            int(source["selector_policy_count"]) != len(selector_issues[alias])
            or int(source["settled_policy_count"]) != settled
            or int(source["unavailable_policy_count"]) != unavailable
            or int(source["no_bet_policy_count"]) != no_bet
        ):
            raise RuntimeError(f"#167 source policy census drift: {alias}/{arm}")
        rows.append({
            "selector_alias": alias,
            "selector_id": source["selector_id"],
            "allocation_arm": arm,
            "source_file": "chart_source_selector_full_surface_v3r1.csv.gz" if arm == "FULL_ENUMERATED" else "chart_source_full_dense_m_curve_v3r1.csv.gz",
            "selector_policy_count": len(selector_issues[alias]),
            "settled_policy_count": settled,
            "unavailable_policy_count": unavailable,
            "no_bet_policy_count": no_bet,
            "expected_stake_yuan": source["stake_yuan"],
            "actual_stake_yuan": actual["stake_yuan"],
            "expected_gross_yuan": source["gross_pre_tax_yuan"],
            "actual_gross_yuan": actual["gross_pre_tax_yuan"],
            "expected_no_tax_roi": source["no_tax_roi"],
            "actual_no_tax_roi": actual["no_tax_roi"],
            "roi_delta": f"{deltas['no_tax_roi']:.15f}",
            "expected_tax_adjusted_roi": source.get("tax_adjusted_roi", ""),
            "actual_tax_adjusted_roi": actual["tax_adjusted_roi"],
            "expected_coverage_hit_rate": source["coverage_hit_rate"],
            "actual_coverage_hit_rate": actual["coverage_hit_rate"],
            "expected_ticket_hit_rate": source["ticket_hit_rate"],
            "actual_ticket_hit_rate": actual["ticket_hit_rate"],
            "reproduction_status": "PASS",
        })
    return rows


def build_common_contributions(
    frozen: dict[str, object], by_policy: dict[tuple[str, str, str], list[dict[str, object]]]
) -> tuple[list[dict[str, object]], list[str]]:
    participation = {
        (row["selector_alias"], row["issue_instance"]): row for row in frozen["participation"]
    }
    role_rows = frozen["roles"]
    first_kickoff = defaultdict(list)
    for role in role_rows:
        if role["issue_instance"] in frozen["common_issues"] and role["kickoff_ts"]:
            first_kickoff[role["issue_instance"]].append(role["kickoff_ts"])
    issue_order = sorted(
        frozen["common_issues"],
        key=lambda issue: (not first_kickoff[issue], min(first_kickoff[issue]) if first_kickoff[issue] else "", issue),
    )
    rows: list[dict[str, object]] = []
    for issue_index, issue in enumerate(issue_order):
        statuses = {
            alias: policy_status(by_policy.get((alias, issue, "FULL_ENUMERATED"), []))
            for alias in SELECTOR_ALIASES
        }
        common_status = common_policy_status(statuses)
        common_settled = common_status == "SETTLED_COMMON"
        missing = sorted({
            match_id
            for alias in SELECTOR_ALIASES
            for record in by_policy.get((alias, issue, "FULL_ENUMERATED"), [])
            for match_id in record["missing_match_ids"]
        })
        representative = participation[("BEST_FULL", issue)]
        for alias in SELECTOR_ALIASES:
            planned_identity = int(participation[(alias, issue)]["selected_identity_count"])
            for arm in ARM_ALIASES:
                records = by_policy[(alias, issue, arm)]
                aggregate = sum_records(records, common_settled)
                stake = aggregate["stake_yuan"]
                gross = aggregate["gross_yuan"]
                tax = aggregate["tax_yuan"]
                rows.append({
                    "issue_index": issue_index,
                    "issue": representative["issue"],
                    "year": representative["year"],
                    "fold": representative["fold"],
                    "issue_instance": issue,
                    "first_kickoff_ts": min(first_kickoff[issue]) if first_kickoff[issue] else "",
                    "selector_alias": alias,
                    "allocation_arm": arm,
                    "common_policy_status": common_status,
                    "selector_policy_statuses_json": json.dumps(statuses, sort_keys=True, separators=(",", ":")),
                    "missing_match_ids": "|".join(missing),
                    "planned_identity_count": planned_identity,
                    "executed_identity_count": int(aggregate["executed_identity_count"]),
                    "planned_ticket_count": planned_identity * ARM_M[arm],
                    "executed_ticket_count": int(aggregate["ticket_count"]),
                    "planned_stake_yuan": fmt_money(planned_identity * ARM_M[arm] * STAKE_PER_TICKET),
                    "stake_yuan": fmt_money(stake),
                    "gross_pre_tax_yuan": fmt_money(gross),
                    "tax_yuan": fmt_money(tax),
                    "pre_tax_net_yuan": fmt_money(gross - stake),
                    "tax_adjusted_net_yuan": fmt_money(gross - tax - stake),
                    "unique_ticket_count": int(aggregate["unique_ticket_count"]),
                    "duplicate_ticket_count": int(aggregate["duplicate_ticket_count"]),
                    "hit_ticket_count": int(aggregate["hit_ticket_count"]),
                    "coverage_hits": int(aggregate["coverage_hits"]),
                    "tax_line_exposure_yuan": fmt_money(aggregate["tax_line_exposure_yuan"]),
                    "tax_line_hit_ticket_count": int(aggregate["tax_line_hit_ticket_count"]),
                })
    if len(rows) != 177 * 9:
        raise RuntimeError(f"common contribution denominator drift: {len(rows)}")
    return rows, issue_order


def metric_totals(records: Sequence[dict[str, object]]) -> dict[str, float]:
    numeric = (
        "planned_identity_count", "executed_identity_count", "planned_ticket_count", "executed_ticket_count",
        "planned_stake_yuan", "stake_yuan", "gross_pre_tax_yuan", "tax_yuan", "pre_tax_net_yuan",
        "tax_adjusted_net_yuan", "unique_ticket_count", "duplicate_ticket_count", "hit_ticket_count",
        "coverage_hits", "tax_line_exposure_yuan", "tax_line_hit_ticket_count",
    )
    return {field: sum(float(row[field]) for row in records) for field in numeric}


def risk_metrics(records: Sequence[dict[str, object]]) -> dict[str, object]:
    settled = [row for row in records if float(row["stake_yuan"]) > 0]
    gross_total = sum(float(row["gross_pre_tax_yuan"]) for row in settled)
    issue_hhi = sum((float(row["gross_pre_tax_yuan"]) / gross_total) ** 2 for row in settled) if gross_total else 0.0
    top_issue = max(settled, key=lambda row: float(row["gross_pre_tax_yuan"]), default=None)
    year_net = defaultdict(float); year_stake = defaultdict(float); year_gross = defaultdict(float)
    for row in settled:
        year_net[row["year"]] += float(row["pre_tax_net_yuan"])
        year_stake[row["year"]] += float(row["stake_yuan"])
        year_gross[row["year"]] += float(row["gross_pre_tax_yuan"])
    top_year = max(year_gross, key=year_gross.get, default="")
    cumulative = peak = drawdown = 0.0
    miss = longest_miss = 0
    for row in settled:
        cumulative += float(row["pre_tax_net_yuan"])
        peak = max(peak, cumulative)
        drawdown = max(drawdown, peak - cumulative)
        if int(row["hit_ticket_count"]) > 0:
            miss = 0
        else:
            miss += 1; longest_miss = max(longest_miss, miss)
    total_net = sum(float(row["pre_tax_net_yuan"]) for row in settled)
    total_stake = sum(float(row["stake_yuan"]) for row in settled)
    ex_issue_roi = None
    if top_issue is not None:
        ex_issue_roi = safe_ratio(total_net - float(top_issue["pre_tax_net_yuan"]), total_stake - float(top_issue["stake_yuan"]))
    ex_year_roi = None
    if top_year:
        ex_year_roi = safe_ratio(total_net - year_net[top_year], total_stake - year_stake[top_year])
    largest_positive = max(settled, key=lambda row: float(row["pre_tax_net_yuan"]), default=None)
    largest_loss = min(settled, key=lambda row: float(row["pre_tax_net_yuan"]), default=None)
    return {
        "gross_issue_hhi": issue_hhi,
        "gross_top_issue_share": safe_ratio(float(top_issue["gross_pre_tax_yuan"]), gross_total) if top_issue else None,
        "gross_top_issue": top_issue["issue_instance"] if top_issue else "",
        "gross_top_year_share": safe_ratio(year_gross[top_year], gross_total) if top_year else None,
        "gross_top_year": top_year,
        "drawdown_no_tax_yuan": drawdown,
        "longest_miss_streak": longest_miss,
        "ex_largest_gross_issue_roi": ex_issue_roi,
        "ex_largest_gross_year_roi": ex_year_roi,
        "largest_positive_issue": largest_positive["issue_instance"] if largest_positive else "",
        "largest_positive_issue_net_yuan": float(largest_positive["pre_tax_net_yuan"]) if largest_positive else 0.0,
        "largest_loss_issue": largest_loss["issue_instance"] if largest_loss else "",
        "largest_loss_issue_net_yuan": float(largest_loss["pre_tax_net_yuan"]) if largest_loss else 0.0,
    }


def summarize_cells(contributions: Sequence[dict[str, object]]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    by_cell: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in contributions:
        by_cell[(row["selector_alias"], row["allocation_arm"])].append(row)
    totals = {key: metric_totals(rows) for key, rows in by_cell.items()}
    rows: list[dict[str, object]] = []
    risks: list[dict[str, object]] = []
    for alias in SELECTOR_ALIASES:
        full = totals[(alias, "FULL_ENUMERATED")]
        full_roi = safe_ratio(full["pre_tax_net_yuan"], full["stake_yuan"])
        full_tax_roi = safe_ratio(full["tax_adjusted_net_yuan"], full["stake_yuan"])
        for arm in ARM_ALIASES:
            cell = totals[(alias, arm)]
            roi = safe_ratio(cell["pre_tax_net_yuan"], cell["stake_yuan"])
            tax_roi = safe_ratio(cell["tax_adjusted_net_yuan"], cell["stake_yuan"])
            cell_rows = by_cell[(alias, arm)]
            settled_issue_count = sum(float(row["stake_yuan"]) > 0 for row in cell_rows)
            row = {
                "selector_alias": alias,
                "allocation_arm": arm,
                "frozen_issue_count": 177,
                "settled_common_issue_count": settled_issue_count,
                "unavailable_common_issue_count": 177 - settled_issue_count,
                "planned_identity_count": int(cell["planned_identity_count"]),
                "executed_identity_count": int(cell["executed_identity_count"]),
                "executed_ticket_count": int(cell["executed_ticket_count"]),
                "stake_yuan": fmt_money(cell["stake_yuan"]),
                "gross_pre_tax_yuan": fmt_money(cell["gross_pre_tax_yuan"]),
                "tax_yuan": fmt_money(cell["tax_yuan"]),
                "pre_tax_net_yuan": fmt_money(cell["pre_tax_net_yuan"]),
                "tax_adjusted_net_yuan": fmt_money(cell["tax_adjusted_net_yuan"]),
                "no_tax_roi": fmt_ratio(roi),
                "tax_adjusted_roi": fmt_ratio(tax_roi),
                "matched_full_no_tax_roi": fmt_ratio(full_roi),
                "matched_full_tax_adjusted_roi": fmt_ratio(full_tax_roi),
                "matched_full_lift": fmt_ratio(roi - full_roi if roi is not None and full_roi is not None else None),
                "capital_utilization_vs_full": fmt_ratio(safe_ratio(cell["stake_yuan"], full["stake_yuan"])),
                "gross_return_retention_vs_full": fmt_ratio(safe_ratio(cell["gross_pre_tax_yuan"], full["gross_pre_tax_yuan"])),
                "coverage_hit_rate_executed": fmt_ratio(safe_ratio(cell["coverage_hits"], cell["executed_identity_count"])),
                "coverage_hit_rate_frozen": fmt_ratio(safe_ratio(cell["coverage_hits"], cell["planned_identity_count"])),
                "ticket_hit_rate": fmt_ratio(safe_ratio(cell["hit_ticket_count"], cell["executed_ticket_count"])),
                "unique_ticket_coverage": fmt_ratio(safe_ratio(cell["unique_ticket_count"], cell["executed_ticket_count"])),
                "duplicate_ticket_ratio": fmt_ratio(safe_ratio(cell["duplicate_ticket_count"], cell["executed_ticket_count"])),
                "tax_line_exposure_yuan": fmt_money(cell["tax_line_exposure_yuan"]),
                "tax_line_hit_ticket_count": int(cell["tax_line_hit_ticket_count"]),
                "seed_scope": "DETERMINISTIC",
                "seed_count": 0,
                "seed_dispersion_status": "NOT_APPLICABLE_DETERMINISTIC_ARM",
            }
            rows.append(row)
            risk = risk_metrics(cell_rows)
            risks.append({"selector_alias": alias, "allocation_arm": arm, **{
                key: fmt_money(value) if key.endswith("_yuan") and isinstance(value, float) else fmt_ratio(value) if key.endswith("_roi") or key.endswith("_share") or key.endswith("_hhi") else value
                for key, value in risk.items()
            }})
    return rows, risks


def build_draw_matrix(path: Path, issue_count: int) -> tuple[array.array, dict[str, object]]:
    rng = random.Random(BOOTSTRAP_SEED)
    draws = array.array("H", (rng.randrange(issue_count) for _ in range(BOOTSTRAP_REPLICATES * issue_count)))
    raw = draws.tobytes()
    if sys.byteorder != "little":
        copy = array.array("H", draws); copy.byteswap(); raw = copy.tobytes()
    with path.open("wb") as handle:
        with gzip.GzipFile(filename="", mode="wb", fileobj=handle, mtime=0) as zipped:
            zipped.write(raw)
    metadata = {
        "generator": "random.Random(seed).randrange(issue_count), row-major replicate × issue draw",
        "seed": BOOTSTRAP_SEED,
        "replicates": BOOTSTRAP_REPLICATES,
        "issue_count": issue_count,
        "dtype": "uint16_le",
        "uncompressed_bytes": len(raw),
        "uncompressed_sha256": hashlib.sha256(raw).hexdigest(),
        "compressed_sha256": sha256_file(path),
    }
    return draws, metadata


def quantile(values: Sequence[float], probability: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(probability * len(ordered))))
    return ordered[index]


def summarize_samples(values: Sequence[float]) -> dict[str, object]:
    return {
        "ci95_low": fmt_ratio(quantile(values, 0.025)),
        "ci95_high": fmt_ratio(quantile(values, 0.975)),
        "positive_fraction": fmt_ratio(sum(value > 0 for value in values) / len(values)),
        "mean": fmt_ratio(statistics.fmean(values)),
        "sd": fmt_ratio(statistics.stdev(values)),
    }


def bootstrap_all(
    contributions: Sequence[dict[str, object]], issue_order: Sequence[str], draws: array.array
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    keys = [(selector, arm) for selector in SELECTOR_ALIASES for arm in ARM_ALIASES]
    by_cell_issue = {(row["selector_alias"], row["allocation_arm"], row["issue_instance"]): row for row in contributions}
    nets = {key: [float(by_cell_issue[key + (issue,)]["pre_tax_net_yuan"]) for issue in issue_order] for key in keys}
    tax_nets = {key: [float(by_cell_issue[key + (issue,)]["tax_adjusted_net_yuan"]) for issue in issue_order] for key in keys}
    stakes = {key: [float(by_cell_issue[key + (issue,)]["stake_yuan"]) for issue in issue_order] for key in keys}
    samples = {key: [] for key in keys}; tax_samples = {key: [] for key in keys}
    n = len(issue_order)
    for replicate in range(BOOTSTRAP_REPLICATES):
        start = replicate * n
        indices = draws[start:start + n]
        for key in keys:
            stake = sum(stakes[key][index] for index in indices)
            if not stake:
                raise RuntimeError("zero-stake common bootstrap replicate")
            samples[key].append(sum(nets[key][index] for index in indices) / stake)
            tax_samples[key].append(sum(tax_nets[key][index] for index in indices) / stake)
    absolute_rows = []
    for key in keys:
        full_key = (key[0], "FULL_ENUMERATED")
        lift_samples = [left - right for left, right in zip(samples[key], samples[full_key])]
        point = safe_ratio(sum(nets[key]), sum(stakes[key]))
        full_point = safe_ratio(sum(nets[full_key]), sum(stakes[full_key]))
        absolute_rows.append({
            "selector_alias": key[0], "allocation_arm": key[1],
            "replicates": BOOTSTRAP_REPLICATES,
            "candidate_point_roi": fmt_ratio(point),
            **{f"candidate_{name}": value for name, value in summarize_samples(samples[key]).items()},
            **{f"tax_adjusted_{name}": value for name, value in summarize_samples(tax_samples[key]).items()},
            "matched_full_point_roi": fmt_ratio(full_point),
            "paired_lift_point": fmt_ratio(point - full_point if point is not None and full_point is not None else None),
            **{f"paired_lift_{name}": value for name, value in summarize_samples(lift_samples).items()},
            "bootstrap_unit": "frozen issue_instance; all 177 rows including 36 fail-closed zero-execution rows",
            "draw_matrix_seed": BOOTSTRAP_SEED,
        })
    allocation_rows = []
    for selector in SELECTOR_ALIASES:
        for sleeve in ARM_ALIASES[1:]:
            key = (selector, sleeve); full_key = (selector, "FULL_ENUMERATED")
            values = [left - right for left, right in zip(samples[key], samples[full_key])]
            point = sum(nets[key]) / sum(stakes[key]) - sum(nets[full_key]) / sum(stakes[full_key])
            allocation_rows.append({
                "selector_alias": selector, "sleeve_arm": sleeve,
                "allocation_lift_point": fmt_ratio(point),
                **{f"allocation_lift_{name}": value for name, value in summarize_samples(values).items()},
                "replicates": BOOTSTRAP_REPLICATES,
            })
    selector_rows = []
    for left_index in range(len(SELECTOR_ALIASES)):
        for right_index in range(left_index + 1, len(SELECTOR_ALIASES)):
            left = SELECTOR_ALIASES[left_index]; right = SELECTOR_ALIASES[right_index]
            for arm in ARM_ALIASES:
                left_key=(left,arm); right_key=(right,arm)
                values=[a-b for a,b in zip(samples[left_key],samples[right_key])]
                point=sum(nets[left_key])/sum(stakes[left_key])-sum(nets[right_key])/sum(stakes[right_key])
                selector_rows.append({
                    "left_selector_alias": left, "right_selector_alias": right, "allocation_arm": arm,
                    "selector_lift_point": fmt_ratio(point),
                    **{f"selector_lift_{name}": value for name, value in summarize_samples(values).items()},
                    "replicates": BOOTSTRAP_REPLICATES,
                })
    interaction_rows = []
    for source, sleeve in (("Q_SOURCE", "Q_TOP_MASS_M192"), ("MODEL_SOURCE", "MODEL_CAP1_M512")):
        best_sleeve=("BEST_FULL",sleeve); best_full=("BEST_FULL","FULL_ENUMERATED")
        source_sleeve=(source,sleeve); source_full=(source,"FULL_ENUMERATED")
        values=[(a-b)-(c-d) for a,b,c,d in zip(samples[best_sleeve],samples[best_full],samples[source_sleeve],samples[source_full])]
        point=(sum(nets[best_sleeve])/sum(stakes[best_sleeve])-sum(nets[best_full])/sum(stakes[best_full]))-(sum(nets[source_sleeve])/sum(stakes[source_sleeve])-sum(nets[source_full])/sum(stakes[source_full]))
        interaction_rows.append({
            "source_selector_alias": source, "sleeve_arm": sleeve,
            "formula": "[(BEST+sleeve)-BEST_FULL]-[(SOURCE+sleeve)-SOURCE_FULL]",
            "interaction_point": fmt_ratio(point),
            **{f"interaction_{name}": value for name, value in summarize_samples(values).items()},
            "replicates": BOOTSTRAP_REPLICATES,
        })
    return absolute_rows, allocation_rows, selector_rows, interaction_rows


def stability_rows(contributions: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    by_cell: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in contributions: by_cell[(row["selector_alias"], row["allocation_arm"])].append(row)
    years = sorted({row["year"] for row in contributions})
    folds = sorted({row["fold"] for row in contributions})
    output = []
    for key, records in sorted(by_cell.items()):
        full_records = by_cell[(key[0], "FULL_ENUMERATED")]
        definitions = []
        for year in years:
            definitions.append(("YEAR", year, lambda row, year=year: row["year"] == year))
        for fold in folds:
            definitions.append(("FOLD", fold, lambda row, fold=fold: row["fold"] == fold))
        for year in years:
            definitions.append(("LOYO", f"EX_{year}", lambda row, year=year: row["year"] != year))
        for split_type, split, predicate in definitions:
            selected=[row for row in records if predicate(row)]; full=[row for row in full_records if predicate(row)]
            totals=metric_totals(selected); ft=metric_totals(full)
            roi=safe_ratio(totals["pre_tax_net_yuan"],totals["stake_yuan"]); froi=safe_ratio(ft["pre_tax_net_yuan"],ft["stake_yuan"])
            output.append({
                "selector_alias": key[0], "allocation_arm": key[1], "split_type": split_type, "split": split,
                "frozen_issue_count": len(selected), "settled_issue_count": sum(float(row["stake_yuan"])>0 for row in selected),
                "stake_yuan": fmt_money(totals["stake_yuan"]), "no_tax_roi": fmt_ratio(roi),
                "matched_full_no_tax_roi": fmt_ratio(froi), "matched_full_lift": fmt_ratio(roi-froi if roi is not None and froi is not None else None),
            })
    return output


def svg_bar_chart(path: Path, title: str, labels: Sequence[str], series: Sequence[tuple[str, Sequence[float], str]], y_label: str) -> None:
    width, height = 1200, 620; left, right, top, bottom = 100, 40, 70, 150
    values=[value for _,vals,_ in series for value in vals]
    low=min(0.0,min(values)); high=max(0.0,max(values)); span=max(high-low,0.01)
    plot_w=width-left-right; plot_h=height-top-bottom
    def y(value): return top+(high-value)/span*plot_h
    zero=y(0.0); group_w=plot_w/len(labels); bar_w=min(45,group_w/(len(series)+1))
    lines=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
           '<rect width="100%" height="100%" fill="white"/>',f'<text x="{width/2}" y="35" text-anchor="middle" font-size="22" font-family="sans-serif">{title}</text>',
           f'<line x1="{left}" y1="{zero:.2f}" x2="{width-right}" y2="{zero:.2f}" stroke="#333"/>',
           f'<text x="20" y="{top+plot_h/2}" transform="rotate(-90 20 {top+plot_h/2})" text-anchor="middle" font-size="14" font-family="sans-serif">{y_label}</text>']
    for group_index,label in enumerate(labels):
        center=left+(group_index+0.5)*group_w
        lines.append(f'<text x="{center:.2f}" y="{height-bottom+35}" text-anchor="middle" font-size="12" font-family="sans-serif">{label}</text>')
        for series_index,(name,vals,color) in enumerate(series):
            value=vals[group_index]; x=center+(series_index-(len(series)-1)/2)*bar_w-bar_w*.42; yy=y(value); h=abs(zero-yy)
            lines.append(f'<rect x="{x:.2f}" y="{min(zero,yy):.2f}" width="{bar_w*.84:.2f}" height="{h:.2f}" fill="{color}"/>')
            lines.append(f'<text x="{x+bar_w*.42:.2f}" y="{(yy-6 if value>=0 else yy+16):.2f}" text-anchor="middle" font-size="10" font-family="sans-serif">{value:.1%}</text>')
    legend_x=left
    for index,(name,_,color) in enumerate(series):
        x=legend_x+index*260; lines.append(f'<rect x="{x}" y="{height-45}" width="16" height="16" fill="{color}"/><text x="{x+22}" y="{height-32}" font-size="13" font-family="sans-serif">{name}</text>')
    lines.append('</svg>')
    path.write_text("\n".join(lines)+"\n",encoding="utf-8")


def choose_disposition(metrics: Sequence[dict[str, object]], interactions: Sequence[dict[str, object]], risks: Sequence[dict[str, object]]) -> dict[str, str]:
    lookup={(row["selector_alias"],row["allocation_arm"]):row for row in metrics}
    best_full=float(lookup[("BEST_FULL","FULL_ENUMERATED")]["no_tax_roi"])
    best_q=float(lookup[("BEST_FULL","Q_TOP_MASS_M192")]["no_tax_roi"])
    best_model=float(lookup[("BEST_FULL","MODEL_CAP1_M512")]["no_tax_roi"])
    positive=[arm for arm,value in (("Q_TOP_MASS_M192",best_q),("MODEL_CAP1_M512",best_model)) if value>0]
    lifts={arm:float(lookup[("BEST_FULL",arm)]["matched_full_lift"]) for arm in ARM_ALIASES[1:]}
    if all(value <= 0 for value in lifts.values()):
        return {"decision":"SELECTION_ONLY","inheritance_panel":"BEST_FULL × FULL_ENUMERATED","rationale":"Both fixed sleeves have non-positive matched lift on controlling common support; the frozen -9.47% native selection baseline is not demoted."}
    interaction={row["sleeve_arm"]:float(row["interaction_point"]) for row in interactions}
    source_lift={
        "Q_TOP_MASS_M192":float(lookup[("Q_SOURCE","Q_TOP_MASS_M192")]["matched_full_lift"]),
        "MODEL_CAP1_M512":float(lookup[("MODEL_SOURCE","MODEL_CAP1_M512")]["matched_full_lift"]),
    }
    confined=[arm for arm in ARM_ALIASES[1:] if lifts[arm] <= 0 and source_lift[arm] > 0]
    if confined and all(lifts[arm] <= 0 or interaction[arm] < 0 for arm in ARM_ALIASES[1:]):
        return {"decision":"ALLOCATOR_CONTEXT_ONLY","inheritance_panel":"BEST_FULL × FULL_ENUMERATED; source sleeves diagnostic only","rationale":"Sleeve value is confined to its source-selector context; strong-selector stacking does not preserve the source lift."}
    # A positive transfer or mixed interaction without a prespecified
    # material-robustness threshold is kept inconclusive until strict EV/PI.
    return {"decision":"INCONCLUSIVE_SUPPORT","inheritance_panel":"BEST_FULL × FULL_ENUMERATED controlling; positive sleeve diagnostic pending strict EV","rationale":f"At least one BEST_FULL sleeve has positive matched lift, but the same-history post-selection design and interaction/concentration evidence do not independently establish STACKS. Absolute-positive cells: {','.join(positive) if positive else 'none'}."}


def package_identity(stage: Path, controls: dict[str, object]) -> tuple[str, str]:
    names=sorted(path.name for path in stage.iterdir() if path.is_file() and path.name not in {"CONTENT_IDENTITY.json","SHA256SUMS.json"})
    content={"contract_version":VERSION,"controls":controls,"payloads":{name:sha256_file(stage/name) for name in names}}
    (stage/"CONTENT_IDENTITY.json").write_text(json.dumps(content,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    sums={path.name:sha256_file(path) for path in stage.iterdir() if path.is_file() and path.name!="SHA256SUMS.json"}
    (stage/"SHA256SUMS.json").write_text(json.dumps(sums,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return sha256_file(stage/"SHA256SUMS.json"),sha256_file(stage/"CONTENT_IDENTITY.json")


def build(output: Path = DEFAULT_OUTPUT) -> dict[str, object]:
    gate_a_manifest=verify_package(GATE_A,EXPECTED_GATE_A_MANIFEST,EXPECTED_GATE_A_CONTENT)
    bj167_manifest=verify_package(BJ167,EXPECTED_BJ167_MANIFEST,EXPECTED_BJ167_CONTENT)
    outcome_manifest=verify_package(OUTCOME_DIR,EXPECTED_OUTCOME_MANIFEST)
    if outcome_manifest.get("canonical_outcome_join.csv") != EXPECTED_OUTCOME_PAYLOAD:
        raise RuntimeError("canonical outcome payload binding drift")
    if output.exists(): raise RuntimeError(f"refusing to replace immutable output: {output}")
    output.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix=f".{output.name}.stage-",dir=output.parent))
    try:
        frozen=load_frozen_data(); outcomes=load_outcomes()
        settlements,by_policy=settle_identities(frozen,outcomes)
        reproduction=reproduce_source_rows(frozen,by_policy)
        contributions,issue_order=build_common_contributions(frozen,by_policy)
        metrics,risks=summarize_cells(contributions)
        draws,draw_meta=build_draw_matrix(stage/"bootstrap_draw_matrix.uint16.gz",len(issue_order))
        absolute_boot,allocation_lifts,selector_lifts,interactions=bootstrap_all(contributions,issue_order,draws)
        stability=stability_rows(contributions)
        disposition=choose_disposition(metrics,interactions,risks)
        metric_lookup={(r["selector_alias"],r["allocation_arm"]):r for r in metrics}
        absolute_positive=[f"{s}/{a}" for (s,a),r in metric_lookup.items() if float(r["no_tax_roi"])>0]

        write_csv(stage/"source_row_reproduction.csv",tuple(reproduction[0]),reproduction)
        write_gzip(stage/"three_way_issue_contributions.csv.gz",tuple(contributions[0]),contributions)
        write_csv(stage/"nine_cell_primary.csv",tuple(metrics[0]),metrics)
        write_csv(stage/"nine_cell_bootstrap_20000.csv",tuple(absolute_boot[0]),absolute_boot)
        write_csv(stage/"allocation_sleeve_lift.csv",tuple(allocation_lifts[0]),allocation_lifts)
        write_csv(stage/"selector_lift_fixed_arm.csv",tuple(selector_lifts[0]),selector_lifts)
        write_csv(stage/"interaction_decomposition.csv",tuple(interactions[0]),interactions)
        write_csv(stage/"risk_diagnostics.csv",tuple(risks[0]),risks)
        write_csv(stage/"stability_year_fold_loyo.csv",tuple(stability[0]),stability)
        write_csv(stage/"chart_source_roi_lift.csv",tuple(metrics[0]),metrics)
        support_rows=[]
        statuses=defaultdict(int)
        for issue in issue_order:
            record=next(row for row in contributions if row["issue_instance"]==issue)
            statuses[record["common_policy_status"]]+=1
        support_rows=[
            {"support_stage":"GATE_A_PREOUTCOME","issue_count":177,"definition":"THREE_WAY_ALL frozen issue intersection","support_hash":"d4b6bed20db88c9f153c7ecff2a02dcc050f511fa0475b75b8fa8118c6f61be7"},
            {"support_stage":"GATE_B_SETTLED_COMMON","issue_count":statuses["SETTLED_COMMON"],"definition":"all three selector policies have complete trusted outcomes","support_hash":canonical_hash([issue for issue in issue_order if next(row for row in contributions if row["issue_instance"]==issue)["common_policy_status"]=="SETTLED_COMMON"])},
            {"support_stage":"GATE_B_UNAVAILABLE_COMMON","issue_count":statuses["UNAVAILABLE_COMMON_OUTCOME"],"definition":"at least one selector policy lacks a canonical outcome; all nine cells execute zero stake","support_hash":canonical_hash([issue for issue in issue_order if next(row for row in contributions if row["issue_instance"]==issue)["common_policy_status"]=="UNAVAILABLE_COMMON_OUTCOME"])},
        ]
        write_csv(stage/"chart_source_support_overlap.csv",tuple(support_rows[0]),support_rows)
        write_csv(stage/"chart_source_interaction.csv",tuple(interactions[0]),interactions)
        write_csv(stage/"chart_source_stability.csv",tuple(stability[0]),stability)
        (stage/"bootstrap_draw_matrix.json").write_text(json.dumps(draw_meta,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        seed_rows=[{"selector_alias":s,"allocation_arm":a,"seed_scope":"DETERMINISTIC","seed_count":0,"dispersion_status":"NOT_APPLICABLE_DETERMINISTIC_ARM","reason":"All three frozen allocation arms are deterministic; issue-cluster bootstrap captures historical issue uncertainty."} for s in SELECTOR_ALIASES for a in ARM_ALIASES]
        write_csv(stage/"seed_dispersion.csv",tuple(seed_rows[0]),seed_rows)

        labels=["FULL","Q/M192","MODEL/M512"]
        series=[]
        colors={"BEST_FULL":"#2563eb","Q_SOURCE":"#f59e0b","MODEL_SOURCE":"#10b981"}
        for selector in SELECTOR_ALIASES:
            series.append((selector,[float(metric_lookup[(selector,arm)]["no_tax_roi"]) for arm in ARM_ALIASES],colors[selector]))
        svg_bar_chart(stage/"roi_lift_grouped.svg","#170 THREE_WAY_ALL pre-tax ROI",labels,series,"Pre-tax ROI")
        svg_bar_chart(stage/"interaction_attribution.svg","#170 allocation lift and interaction",["Q/M192","MODEL/M512"],[
            ("BEST matched lift",[float(metric_lookup[("BEST_FULL",arm)]["matched_full_lift"]) for arm in ARM_ALIASES[1:]],"#2563eb"),
            ("SOURCE matched lift",[float(metric_lookup[(source,arm)]["matched_full_lift"]) for source,arm in (("Q_SOURCE","Q_TOP_MASS_M192"),("MODEL_SOURCE","MODEL_CAP1_M512"))],"#f59e0b"),
            ("interaction",[float(row["interaction_point"]) for row in interactions],"#dc2626"),
        ],"ROI difference")
        svg_bar_chart(stage/"support_overlap.svg","#170 common support",["Frozen","Settled","Unavailable"],[("Issue count / 177",[177/177,statuses["SETTLED_COMMON"]/177,statuses["UNAVAILABLE_COMMON_OUTCOME"]/177],"#6366f1")],"Fraction of frozen issues")

        report=(
            "# #170 Gate B — selector × allocation stacking bridge\n\n"
            f"Controlling support: 177 frozen THREE_WAY_ALL issues; {statuses['SETTLED_COMMON']} settle all nine cells and {statuses['UNAVAILABLE_COMMON_OUTCOME']} fail closed with zero execution.\n\n"
            "## Nine-cell result\n\n"
            "| Selector | Arm | Stake | Gross | Pre-tax ROI | Tax-adjusted ROI | Matched FULL lift |\n|---|---|---:|---:|---:|---:|---:|\n"+
            "".join(f"| {row['selector_alias']} | {row['allocation_arm']} | ¥{float(row['stake_yuan']):,.0f} | ¥{float(row['gross_pre_tax_yuan']):,.0f} | {float(row['no_tax_roi']):+.2%} | {float(row['tax_adjusted_roi']):+.2%} | {float(row['matched_full_lift']):+.2%} |\n" for row in metrics)+
            "\n## Interaction\n\n"+
            "".join(f"- {row['sleeve_arm']}: interaction {float(row['interaction_point']):+.2%}, 95% CI [{float(row['interaction_ci95_low']):+.2%}, {float(row['interaction_ci95_high']):+.2%}].\n" for row in interactions)+
            f"\n## Disposition\n\n**{disposition['decision']}** — {disposition['rationale']}\n\n#134 inheritance panel: `{disposition['inheritance_panel']}`. The native -9.47% BEST_FULL selection baseline is not demoted by any negative transfer result.\n\n"
            f"Absolute-positive common-support cells: {', '.join(absolute_positive) if absolute_positive else 'none'}. "
            f"Strict independent EV required before PI terminal review: {'YES' if absolute_positive else 'NO'}.\n\n"
            "This is same-history post-selection transfer research, not independent promotion evidence. No purchase, execution, betting or production authority is granted.\n"
        )
        (stage/"REPORT.md").write_text(report,encoding="utf-8")
        (stage/"README.md").write_text("# #170 Gate-B immutable package\n\nSee `REPORT.md` for the controlling result. All monetary settlement is per independent ¥2 ticket; tax is applied per winning ticket whose payout is at least ¥10,000, without pooling.\n",encoding="utf-8")
        source_binding={
            "gate_a":{"manifest_sha256":EXPECTED_GATE_A_MANIFEST,"content_identity_sha256":EXPECTED_GATE_A_CONTENT,"payload_count":len(gate_a_manifest)},
            "bj167_terminal":{"manifest_sha256":EXPECTED_BJ167_MANIFEST,"content_identity_sha256":EXPECTED_BJ167_CONTENT,"payload_count":len(bj167_manifest)},
            "outcome_package":{"manifest_sha256":EXPECTED_OUTCOME_MANIFEST,"canonical_outcome_join_sha256":EXPECTED_OUTCOME_PAYLOAD,"payload_count":len(outcome_manifest)},
            "allocator_sha256":EXPECTED_ALLOCATOR_SHA256,
            "gate_a_merge":"29d34610bae2d3ed0bf68bdba1a339edfd54152b",
        }
        (stage/"source_binding.json").write_text(json.dumps(source_binding,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        card={
            "issue":170,"contract":CONTRACT,"version":VERSION,"stage":"GATE_B_ONE_SHOT_CANONICAL_SETTLEMENT",
            "primary_support":{"frozen_issue_count":177,"settled_common_issue_count":statuses["SETTLED_COMMON"],"unavailable_common_issue_count":statuses["UNAVAILABLE_COMMON_OUTCOME"],"support_hash":"d4b6bed20db88c9f153c7ecff2a02dcc050f511fa0475b75b8fa8118c6f61be7"},
            "surface":{"selector_count":3,"allocation_arm_count":3,"cell_count":9,"new_parameter_scan":False},
            "source_row_reproduction":{"row_count":len(reproduction),"all_pass":all(row["reproduction_status"]=="PASS" for row in reproduction)},
            "bootstrap":draw_meta,"economics":{"primary":"pre-tax ROI","secondary":"tax-adjusted ROI","stake":"¥2 per independent ticket","tax":"20% per winning ticket when that ticket payout >= ¥10,000; no pooling"},
            "decision":disposition,"absolute_positive_cells":absolute_positive,
            "strict_independent_ev_required":bool(absolute_positive),
            "promotion_boundary":"same-history post-selection transfer study; no point estimate alone grants production/purchase/betting authority",
            "source_binding":source_binding,
        }
        (stage/"settlement_card.json").write_text(json.dumps(card,indent=2,sort_keys=True)+"\n",encoding="utf-8")
        shutil.copy2(Path(__file__).resolve(),stage/"settlement_runner.py")
        controls={"gate_a_manifest":EXPECTED_GATE_A_MANIFEST,"outcome_manifest":EXPECTED_OUTCOME_MANIFEST,"source_reproduction_sha256":sha256_file(stage/"source_row_reproduction.csv"),"contributions_sha256":sha256_file(stage/"three_way_issue_contributions.csv.gz"),"nine_cell_sha256":sha256_file(stage/"nine_cell_primary.csv"),"bootstrap_matrix_sha256":draw_meta["compressed_sha256"],"decision":disposition,"absolute_positive_cells":absolute_positive}
        manifest_sha,content_sha=package_identity(stage,controls)
        os.replace(stage,output)
        return {"output":str(output),"manifest_sha256":manifest_sha,"content_identity_sha256":content_sha,"settled_common_issues":statuses["SETTLED_COMMON"],"absolute_positive_cells":absolute_positive,"decision":disposition}
    except BaseException:
        if stage.exists(): shutil.rmtree(stage)
        raise


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--output",type=Path,default=DEFAULT_OUTPUT); args=parser.parse_args()
    output=args.output if args.output.is_absolute() else ROOT/args.output
    print(json.dumps(build(output.resolve()),indent=2,sort_keys=True))


if __name__ == "__main__": main()
