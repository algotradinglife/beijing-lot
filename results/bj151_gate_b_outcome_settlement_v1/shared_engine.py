#!/usr/bin/env python3
"""One-shot Gate-B settlement for #148's immutable dense M-grid freeze.

The computation is deliberately issue-streamed: it expands the frozen WR/WOR
plans from Gate A without loading a ticket ledger for every draw.  Final SP
and results are read only from the canonical trusted settlement bundle.
"""
from __future__ import annotations

import argparse
import bisect
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
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path


CONTRACT = "BJ-HIST-N7-M-GRID-001"
VERSION = "bj148-gate-b-v1-ticket-tax-dense-surface"
FREEZE_MANIFEST = "fd4a0f4dc0ab5ef97f3c260a082515aa7874a60a1ac1e5e0ecd865fdb1eeafd6"
OUTCOME_MANIFEST = "fbbd3b53bd86f4bb0caff8f2587933cd6b0e4e7d04fb0f709bac934ec2a705cc"
OUTCOME_PAYLOAD = "13d709d253c31519734dbf0447e6961ac8a6060772975d7461741224e5251a89"
CODES = ("3", "1", "0")
N, FULL_TICKETS = 7, 2187
UNIT_STAKE, PAYOUT_FACTOR = Decimal("2"), Decimal("0.65")
TAX_RATE, TAX_THRESHOLD = Decimal("0.20"), Decimal("10000")
MONEY_QUANTUM = Decimal("0.000001")
BOOTSTRAP_REPLICATES = 1000
getcontext().prec = 80

OUTCOME_FIELDS = ("match_id", "result_code", "winning_sp", "winning_sp_source", "settlement_quality", "has_trusted_settlement")
ISSUE_FIELDS = (
    "issue", "fold", "year", "issue_instance", "sampling_role", "ticket_mechanism", "seed", "seed_role", "M",
    "frozen_selection_status", "settlement_status", "candidate_identity_count", "planned_draw_count", "planned_stake_yuan",
    "frozen_planned_draw_count", "frozen_planned_stake_yuan", "full_control_stake_yuan", "frozen_full_control_stake_yuan",
    "capital_utilization_vs_full", "unique_ticket_draw_count", "duplicate_ticket_draw_count",
    "duplicate_ticket_draw_group_count", "unique_ticket_coverage", "duplicate_ticket_ratio", "hit_ticket_count",
    "coverage_hit", "gross_pre_tax_yuan", "tax_yuan", "after_tax_gross_yuan", "pre_tax_net_yuan",
    "tax_adjusted_net_yuan", "no_tax_roi", "tax_adjusted_roi", "gross_top_identity_share", "outcome_gap_count",
    "taxable_hit_ticket_count", "non_taxable_hit_ticket_count",
)
TICKET_FIELDS = (
    "issue", "fold", "year", "issue_instance", "sampling_role", "ticket_mechanism", "seed", "M", "portfolio_id",
    "winning_ticket_gross_yuan", "winning_ticket_count", "per_ticket_tax_yuan", "tax_yuan", "tax_rule",
)
SUMMARY_FIELDS = (
    "scope", "scope_value", "sampling_role", "ticket_mechanism", "seed", "M", "frozen_issue_count",
    "frozen_available_issue_count", "frozen_no_bet_issue_count", "settled_issue_count", "unavailable_outcome_issue_count",
    "planned_draw_count", "stake_yuan", "full_control_stake_yuan", "capital_utilization_vs_full", "stake_mean_yuan",
    "stake_p50_yuan", "stake_p90_yuan", "stake_p95_yuan", "stake_max_yuan", "unique_ticket_draw_count",
    "duplicate_ticket_draw_count", "duplicate_ticket_draw_group_count", "unique_ticket_coverage", "duplicate_ticket_ratio",
    "hit_ticket_count", "coverage_hits", "coverage_hit_rate", "gross_pre_tax_yuan", "tax_yuan", "after_tax_gross_yuan",
    "pre_tax_net_yuan", "tax_adjusted_net_yuan", "no_tax_roi", "tax_adjusted_roi", "gross_top_issue_share",
    "gross_issue_hhi", "gross_top_identity_share", "largest_issue_gross_yuan", "max_drawdown_yuan", "longest_miss_streak",
)
DELTA_FIELDS = (
    "scope", "scope_value", "sampling_role", "ticket_mechanism", "seed", "M", "baseline_role", "baseline_mechanism",
    "baseline_M", "support_issue_count", "stake_yuan", "full_stake_yuan", "stake_yuan_delta", "no_tax_roi",
    "full_no_tax_roi", "no_tax_roi_delta", "tax_adjusted_roi", "full_tax_adjusted_roi", "tax_adjusted_roi_delta",
    "coverage_hit_rate", "full_coverage_hit_rate", "coverage_hit_rate_delta", "unique_ticket_coverage",
    "full_unique_ticket_coverage", "unique_ticket_coverage_delta", "duplicate_ticket_ratio", "full_duplicate_ticket_ratio",
    "duplicate_ticket_ratio_delta", "comparison_rule",
)
BOOTSTRAP_FIELDS = (
    "sampling_role", "ticket_mechanism", "seed", "M", "baseline_role", "baseline_M", "support_issue_count", "replicates",
    "metric", "point_estimate", "ci95_low", "ci95_high", "one_sided_positive_p", "two_sided_sign_p",
)
TAX_RECON_FIELDS = (
    "sampling_role", "ticket_mechanism", "seed", "M", "ticket_ledger_hit_ticket_count", "ticket_ledger_taxable_ticket_count",
    "ticket_ledger_tax_yuan", "issue_ledger_tax_yuan", "difference_yuan", "tax_rule",
)
SOURCE_FIELDS = ("source", "role", "identity", "sha256", "rows", "join_status")


def repository_root() -> Path:
    for candidate in (Path(__file__).resolve().parent, *Path(__file__).resolve().parents):
        if (candidate / ".git").exists() and (candidate / "scripts").is_dir():
            return candidate
    raise RuntimeError("repository root unavailable")


ROOT = repository_root()
FREEZE = ROOT / "results" / "bj148_gate_a_preoutcome_v1"
OUTCOME_SOURCE = ROOT / "results" / "bj95_gate_b_outcome_settlement_v2r8"
OUTPUT = ROOT / "results" / "bj148_gate_b_outcome_settlement_v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def decompressed_digest(path: Path) -> tuple[str, int]:
    digest, count = hashlib.sha256(), 0
    with gzip.open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
            count += len(block)
    return digest.hexdigest(), count


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
    return "" if value is None else f"{float(value):.12f}"


def verified_bundle(path: Path, expected_manifest: str) -> dict[str, str]:
    manifest_path = path / "SHA256SUMS.json"
    if not manifest_path.is_file() or sha256(manifest_path) != expected_manifest:
        raise RuntimeError(f"unaccepted manifest: {path}")
    declared = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = {item.name: sha256(item) for item in path.iterdir() if item.is_file() and item.name != manifest_path.name}
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
    raw, zipped, text, _ = handles
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


def seed_value(*parts: object) -> int:
    payload = "|".join(map(str, parts)).encode("utf-8")
    return int.from_bytes(hashlib.sha256(payload).digest()[:16], "big")


def ticket_tax(ticket_gross: Decimal) -> Decimal:
    """Apply tax per individual ticket; never pool by issue or policy."""
    return ticket_gross * TAX_RATE if ticket_gross >= TAX_THRESHOLD else Decimal(0)


def percentile(values: list[Decimal], quantile: float) -> Decimal:
    if not values or not 0.0 <= quantile <= 1.0:
        raise RuntimeError("invalid quantile inputs")
    ordered = sorted(values)
    return ordered[math.ceil(len(ordered) * quantile) - 1]


@dataclass(frozen=True)
class Identity:
    portfolio_id: str
    issue_instance: str
    roles: tuple[dict[str, str], ...]
    truth_index: int | None
    payout_per_ticket: Decimal | None
    outcome_gap_count: int


@dataclass
class TicketAudit:
    hits: int = 0
    taxable: int = 0
    tax: Decimal = Decimal(0)

    def add(self, per_ticket_tax: Decimal, hit_count: int) -> None:
        self.hits += hit_count
        if per_ticket_tax:
            self.taxable += hit_count
            self.tax += per_ticket_tax * hit_count


def validate_inputs() -> dict[str, str]:
    freeze = verified_bundle(FREEZE, FREEZE_MANIFEST)
    card = json.loads((FREEZE / "gate_a_card.json").read_text(encoding="utf-8"))
    content = json.loads((FREEZE / "CONTENT_IDENTITY.json").read_text(encoding="utf-8"))
    if card.get("contract") != CONTRACT or card.get("stage") != "GATE_A_OUTCOME_UNEXPOSED_DENSE_M_GRID_COMMON_SUPPORT_FREEZE":
        raise RuntimeError("unexpected #148 Gate-A contract")
    if content.get("contract_version") != "bj148-gate-a-content-v1":
        raise RuntimeError("unexpected #148 Gate-A content contract")
    for name in ("common_support_identities.csv.gz", "common_support_role_vectors.csv.gz"):
        expected = content.get("gzip_payloads", {}).get(name, {}).get("canonical_decompressed_sha256")
        if expected != decompressed_digest(FREEZE / name)[0]:
            raise RuntimeError(f"Gate-A portable gzip digest drift: {name}")
    outcome = verified_bundle(OUTCOME_SOURCE, OUTCOME_MANIFEST)
    if outcome.get("canonical_outcome_join.csv") != OUTCOME_PAYLOAD:
        raise RuntimeError("canonical outcome payload drift")
    return {
        "gate_a_manifest_sha256": FREEZE_MANIFEST,
        "gate_a_content_identity_sha256": freeze["CONTENT_IDENTITY.json"],
        "gate_a_sampling_plan_sha256": freeze["sampling_plan.csv"],
        "gate_a_cohort_sha256": freeze["common_support_cohort.csv"],
        "gate_a_identity_sha256": freeze["common_support_identities.csv.gz"],
        "gate_a_role_sha256": freeze["common_support_role_vectors.csv.gz"],
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
    if len(outcomes) != len(rows):
        raise RuntimeError("duplicate final-SP outcome match id")
    for row in outcomes.values():
        if row["result_code"] not in CODES or row["settlement_quality"] != "trusted" or row["has_trusted_settlement"] != "1" or decimal(row["winning_sp"], "winning SP") <= 0:
            raise RuntimeError("untrusted canonical final-SP outcome")
    return outcomes


def load_freeze() -> tuple[list[dict[str, str]], dict[str, list[Identity]], list[int]]:
    with (FREEZE / "common_support_cohort.csv").open(newline="", encoding="utf-8") as handle:
        cohort = list(csv.DictReader(handle))
    if len(cohort) != 348 or sum(row["common_support_status"] == "AVAILABLE" for row in cohort) != 343:
        raise RuntimeError("Gate-A cohort denominator drift")
    with (FREEZE / "dense_m_grid.csv").open(newline="", encoding="utf-8") as handle:
        grid = list(csv.DictReader(handle))
    m_grid = [int(row["M"]) for row in grid]
    if len(m_grid) != 58 or m_grid[-1] != FULL_TICKETS or len(set(m_grid)) != len(m_grid):
        raise RuntimeError("Gate-A dense M-grid drift")
    with (FREEZE / "sampling_plan.csv").open(newline="", encoding="utf-8") as handle:
        plans = list(csv.DictReader(handle))
    if len(plans) != 119_364 or len({row["plan_id"] for row in plans}) != len(plans):
        raise RuntimeError("Gate-A sampling-plan denominator drift")
    plans_by_issue: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in plans:
        plans_by_issue[row["issue_instance"]].append(row)
    if set(plans_by_issue) != {row["issue_instance"] for row in cohort} or any(len(rows) != 343 for rows in plans_by_issue.values()):
        raise RuntimeError("Gate-A issue-plan surface drift")
    with gzip.open(FREEZE / "common_support_role_vectors.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        role_rows = list(csv.DictReader(handle))
    with gzip.open(FREEZE / "common_support_identities.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        identity_rows = list(csv.DictReader(handle))
    if len(identity_rows) != 8_550 or len(role_rows) != 59_850:
        raise RuntimeError("Gate-A identity/role denominator drift")
    role_map: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in role_rows:
        role_map[(row["issue_instance"], row["portfolio_id"])].append(row)
    outcomes = load_outcomes()
    by_issue: dict[str, list[Identity]] = defaultdict(list)
    for row in identity_rows:
        key = row["issue_instance"], row["portfolio_id"]
        roles = tuple(sorted(role_map.get(key, []), key=lambda value: int(value["selection_rank"])))
        if len(roles) != N or [int(value["selection_rank"]) for value in roles] != list(range(1, N + 1)):
            raise RuntimeError(f"invalid frozen N7 role geometry: {key}")
        if "|".join(value["match_id"] for value in roles) != row["selected_match_ids"]:
            raise RuntimeError(f"identity/role mismatch: {key}")
        truth, product, gaps = 0, Decimal(1), 0
        for role in roles:
            outcome = outcomes.get(role["match_id"])
            if outcome is None:
                gaps += 1
                continue
            truth = truth * 3 + CODES.index(outcome["result_code"])
            product *= decimal(outcome["winning_sp"], "winning SP")
        by_issue[row["issue_instance"]].append(Identity(
            portfolio_id=row["portfolio_id"], issue_instance=row["issue_instance"], roles=roles,
            truth_index=None if gaps else truth, payout_per_ticket=None if gaps else UNIT_STAKE * PAYOUT_FACTOR * product,
            outcome_gap_count=gaps,
        ))
    if sum(len(rows) for rows in by_issue.values()) != 8_550 or set(by_issue) != {row["issue_instance"] for row in cohort if row["common_support_status"] == "AVAILABLE"}:
        raise RuntimeError("common-support identity membership drift")
    return cohort, by_issue, m_grid


def q_weights(identity: Identity) -> list[float]:
    weights = [1.0]
    for role in identity.roles:
        vector = [float(role[f"q_weight{code}"]) for code in CODES]
        if any(value <= 0.0 or not math.isfinite(value) for value in vector) or abs(sum(vector) - 1.0) > 1e-8:
            raise RuntimeError(f"invalid Q vector: {identity.portfolio_id}")
        weights = [prefix * value for prefix in weights for value in vector]
    if len(weights) != FULL_TICKETS or abs(sum(weights) - 1.0) > 1e-8:
        raise RuntimeError("N7 Q ticket-space normalization drift")
    return weights


def wr_profile(weights: list[float], truth: int, seed: str, identity: Identity, m_values: list[int]) -> dict[int, tuple[int, int, int, int]]:
    cumulative, total = [], 0.0
    for weight in weights:
        total += weight
        cumulative.append(total)
    if abs(total - 1.0) > 1e-8:
        raise RuntimeError("WR Q cumulative normalization drift")
    rng = random.Random(seed_value(CONTRACT, "WR", seed, identity.issue_instance, identity.portfolio_id))
    thresholds = set(m_values)
    counts: dict[int, int] = defaultdict(int)
    hits = unique = duplicate_groups = 0
    output: dict[int, tuple[int, int, int, int]] = {}
    for draw in range(1, max(m_values) + 1):
        ticket = bisect.bisect_left(cumulative, rng.random())
        if ticket >= FULL_TICKETS:
            ticket = FULL_TICKETS - 1
        prior = counts[ticket]
        counts[ticket] = prior + 1
        if prior == 0:
            unique += 1
        elif prior == 1:
            duplicate_groups += 1
        if ticket == truth:
            hits += 1
        if draw in thresholds:
            output[draw] = hits, unique, draw - unique, duplicate_groups
    if set(output) != thresholds:
        raise RuntimeError("WR profile missed frozen M point")
    return output


def wor_truth_rank(weights: list[float], truth: int, seed: str, identity: Identity) -> int:
    rng = random.Random(seed_value(CONTRACT, "WOR", seed, identity.issue_instance, identity.portfolio_id))
    scores = [-math.log(max(rng.random(), 1e-18)) / weight for weight in weights]
    return 1 + sum(score < scores[truth] for ordinal, score in enumerate(scores) if ordinal != truth)


def add_identity(acc: dict[tuple[str, str, int, str], dict[str, object]], identity: Identity, m_values: list[int], seeds: tuple[str, ...]) -> None:
    if identity.truth_index is None or identity.payout_per_ticket is None:
        raise RuntimeError("available identity lacks trusted outcome")
    weights = q_weights(identity)
    per_ticket_gross = identity.payout_per_ticket.quantize(MONEY_QUANTUM)
    per_ticket_tax = ticket_tax(per_ticket_gross).quantize(MONEY_QUANTUM)
    for seed in seeds:
        wr = wr_profile(weights, identity.truth_index, seed, identity, m_values)
        rank = wor_truth_rank(weights, identity.truth_index, seed, identity)
        for m_value in m_values:
            for role, mechanism, values in (
                ("PRIMARY_WR_NATURAL_BASELINE", "Q_INFORMED_WR_DUPLICATE_STAKE", wr[m_value]),
                ("SENSITIVITY_WOR_DISTINCT", "Q_INFORMED_WOR_DISTINCT", (int(rank <= m_value), m_value, 0, 0)),
            ):
                hit, unique, duplicates, groups = values
                entry = acc[(role, mechanism, m_value, seed)]
                gross = per_ticket_gross * hit
                tax = per_ticket_tax * hit
                entry["unique"] = int(entry["unique"]) + unique
                entry["duplicates"] = int(entry["duplicates"]) + duplicates
                entry["duplicate_groups"] = int(entry["duplicate_groups"]) + groups
                entry["hits"] = int(entry["hits"]) + hit
                entry["taxable"] = int(entry["taxable"]) + (hit if per_ticket_tax else 0)
                entry["gross"] = Decimal(entry["gross"]) + gross
                entry["tax"] = Decimal(entry["tax"]) + tax
                entry["top_identity_gross"] = max(Decimal(entry["top_identity_gross"]), gross)
                if hit:
                    entry["ticket_rows"].append((identity.portfolio_id, per_ticket_gross, hit, per_ticket_tax, tax))
    full = acc[("FULL_ECONOMIC_CONTROL", "FULL_ENUMERATED", FULL_TICKETS, "NA")]
    full["unique"] = int(full["unique"]) + FULL_TICKETS
    full["hits"] = int(full["hits"]) + 1
    full["taxable"] = int(full["taxable"]) + int(bool(per_ticket_tax))
    full["gross"] = Decimal(full["gross"]) + per_ticket_gross
    full["tax"] = Decimal(full["tax"]) + per_ticket_tax
    full["top_identity_gross"] = max(Decimal(full["top_identity_gross"]), per_ticket_gross)
    full["ticket_rows"].append((identity.portfolio_id, per_ticket_gross, 1, per_ticket_tax, per_ticket_tax))


def fresh_accumulator(plans: list[dict[str, str]]) -> dict[tuple[str, str, int, str], dict[str, object]]:
    result: dict[tuple[str, str, int, str], dict[str, object]] = {}
    for plan in plans:
        key = plan["sampling_role"], plan["ticket_mechanism"], int(plan["M"]), plan["seed"]
        if key in result:
            raise RuntimeError("duplicate frozen plan key within issue")
        result[key] = {"unique": 0, "duplicates": 0, "duplicate_groups": 0, "hits": 0, "taxable": 0, "gross": Decimal(0), "tax": Decimal(0), "top_identity_gross": Decimal(0), "ticket_rows": []}
    if len(result) != 343:
        raise RuntimeError("incomplete frozen per-issue M surface")
    return result


def settle_issue(sample: dict[str, str], plans: list[dict[str, str]], identities: list[Identity], m_values: list[int], audits: dict[tuple[str, str, int, str], TicketAudit], ticket_writer: csv.DictWriter) -> list[dict[str, object]]:
    acc = fresh_accumulator(plans)
    available = sample["common_support_status"] == "AVAILABLE"
    outcome_gaps = sum(identity.outcome_gap_count for identity in identities)
    if available:
        if len(identities) != int(sample["selected_identity_count"]):
            raise RuntimeError("available common-support issue has identity membership drift")
        if not outcome_gaps:
            seeds = tuple(sorted({row["seed"] for row in plans if row["seed"] != "NA"}))
            add_values = [m for m in m_values if m != FULL_TICKETS]
            for identity in identities:
                add_identity(acc, identity, add_values, seeds)
    elif identities:
        raise RuntimeError("no-bet issue unexpectedly has common-support identities")
    frozen_full_stake = Decimal(int(sample["full_issue_stake_yuan"]))
    settlement_status = "SETTLED" if available and not outcome_gaps else ("UNAVAILABLE_CANONICAL_OUTCOME" if available else "NO_BET_GATE_A")
    rows: list[dict[str, object]] = []
    for plan in plans:
        key = plan["sampling_role"], plan["ticket_mechanism"], int(plan["M"]), plan["seed"]
        values = acc[key]
        count = int(plan["candidate_identity_count"])
        frozen_draws = count * int(plan["M"]) if available else 0
        frozen_stake = UNIT_STAKE * frozen_draws
        if frozen_draws != int(plan["planned_draw_count"]) or frozen_stake != Decimal(plan["planned_stake_yuan"]):
            raise RuntimeError("settlement recomputation drifts from frozen draw/stake plan")
        draws = frozen_draws if settlement_status == "SETTLED" else 0
        stake = frozen_stake if settlement_status == "SETTLED" else Decimal(0)
        full_stake = frozen_full_stake if settlement_status == "SETTLED" else Decimal(0)
        gross, tax = Decimal(values["gross"]), Decimal(values["tax"])
        audit = audits[key]
        for portfolio_id, ticket_gross, hit, per_ticket_tax, ticket_tax_amount in values["ticket_rows"]:
            audit.add(per_ticket_tax, hit)
            ticket_writer.writerow({
                "issue": plan["issue"], "fold": plan["fold"], "year": plan["year"], "issue_instance": plan["issue_instance"],
                "sampling_role": plan["sampling_role"], "ticket_mechanism": plan["ticket_mechanism"], "seed": plan["seed"], "M": plan["M"],
                "portfolio_id": portfolio_id, "winning_ticket_gross_yuan": money(ticket_gross), "winning_ticket_count": hit,
                "per_ticket_tax_yuan": money(per_ticket_tax), "tax_yuan": money(ticket_tax_amount),
                "tax_rule": "20pct_if_each_ticket_gross_gte_10000_no_aggregate_pooling",
            })
        unique = int(values["unique"])
        duplicates = int(values["duplicates"])
        rows.append({
            "issue": plan["issue"], "fold": plan["fold"], "year": plan["year"], "issue_instance": plan["issue_instance"],
            "sampling_role": plan["sampling_role"], "ticket_mechanism": plan["ticket_mechanism"], "seed": plan["seed"], "seed_role": plan["seed_role"], "M": plan["M"],
            "frozen_selection_status": plan["selection_status"], "settlement_status": settlement_status, "candidate_identity_count": count,
            "planned_draw_count": draws, "planned_stake_yuan": stake, "frozen_planned_draw_count": frozen_draws, "frozen_planned_stake_yuan": frozen_stake,
            "full_control_stake_yuan": full_stake, "frozen_full_control_stake_yuan": frozen_full_stake,
            "capital_utilization_vs_full": stake / full_stake if full_stake else None, "unique_ticket_draw_count": unique,
            "duplicate_ticket_draw_count": duplicates, "duplicate_ticket_draw_group_count": int(values["duplicate_groups"]),
            "unique_ticket_coverage": Decimal(unique) / draws if draws else None, "duplicate_ticket_ratio": Decimal(duplicates) / draws if draws else None,
            "hit_ticket_count": int(values["hits"]), "coverage_hit": int(bool(values["hits"])), "gross_pre_tax_yuan": gross,
            "tax_yuan": tax, "after_tax_gross_yuan": gross - tax, "pre_tax_net_yuan": gross - stake,
            "tax_adjusted_net_yuan": gross - tax - stake, "no_tax_roi": (gross - stake) / stake if stake else None,
            "tax_adjusted_roi": (gross - tax - stake) / stake if stake else None,
            "gross_top_identity_share": Decimal(values["top_identity_gross"]) / gross if gross else None, "outcome_gap_count": outcome_gaps,
            "taxable_hit_ticket_count": int(values["taxable"]), "non_taxable_hit_ticket_count": int(values["hits"]) - int(values["taxable"]),
        })
    return rows


def serializable(row: dict[str, object]) -> dict[str, object]:
    output: dict[str, object] = {}
    for key, value in row.items():
        if isinstance(value, Decimal):
            output[key] = ratio(value) if any(token in key for token in ("roi", "share", "ratio", "coverage", "utilization", "rate", "hhi")) else money(value)
        elif isinstance(value, float):
            output[key] = ratio(value)
        else:
            output[key] = value
    return output


def config_key(row: dict[str, object]) -> tuple[str, str, int, str]:
    return str(row["sampling_role"]), str(row["ticket_mechanism"]), int(row["M"]), str(row["seed"])


def grouped_scopes(rows: list[dict[str, object]]) -> Iterable[tuple[str, str, list[dict[str, object]]]]:
    yield "ALL", "ALL", rows
    for scope, field in (("YEAR", "year"), ("FOLD", "fold")):
        for value in sorted({str(row[field]) for row in rows}):
            yield scope, value, [row for row in rows if str(row[field]) == value]
    for year in sorted({str(row["year"]) for row in rows}):
        yield "LEAVE_ONE_YEAR_OUT", year, [row for row in rows if str(row["year"]) != year]


def summary(scope: str, scope_value: str, rows: list[dict[str, object]]) -> dict[str, object]:
    if not rows or len({config_key(row) for row in rows}) != 1:
        raise RuntimeError("summary scope mixes frozen configurations")
    settled = [row for row in rows if row["settlement_status"] == "SETTLED"]
    stakes = [Decimal(row["planned_stake_yuan"]) for row in rows]
    stake = sum(stakes, Decimal(0))
    full_stake = sum((Decimal(row["full_control_stake_yuan"]) for row in rows), Decimal(0))
    gross = sum((Decimal(row["gross_pre_tax_yuan"]) for row in rows), Decimal(0))
    tax = sum((Decimal(row["tax_yuan"]) for row in rows), Decimal(0))
    pre_net = sum((Decimal(row["pre_tax_net_yuan"]) for row in rows), Decimal(0))
    tax_net = sum((Decimal(row["tax_adjusted_net_yuan"]) for row in rows), Decimal(0))
    unique = sum(int(row["unique_ticket_draw_count"]) for row in rows)
    duplicates = sum(int(row["duplicate_ticket_draw_count"]) for row in rows)
    hits = sum(int(row["hit_ticket_count"]) for row in rows)
    coverage = sum(int(row["coverage_hit"]) for row in rows)
    issue_gross = [Decimal(row["gross_pre_tax_yuan"]) for row in rows]
    cumulative = peak = drawdown = Decimal(0)
    misses = longest_miss = 0
    for row in sorted(rows, key=lambda item: (int(str(item["year"])), int(str(item["issue"])) )):
        cumulative += Decimal(row["tax_adjusted_net_yuan"])
        peak = max(peak, cumulative)
        drawdown = max(drawdown, peak - cumulative)
        if int(row["coverage_hit"]):
            misses = 0
        else:
            misses += 1
            longest_miss = max(longest_miss, misses)
    first = rows[0]
    return {
        "scope": scope, "scope_value": scope_value, "sampling_role": first["sampling_role"], "ticket_mechanism": first["ticket_mechanism"], "seed": first["seed"], "M": first["M"],
        "frozen_issue_count": len(rows), "frozen_available_issue_count": sum(row["frozen_selection_status"] == "AVAILABLE" for row in rows), "frozen_no_bet_issue_count": sum(row["frozen_selection_status"] != "AVAILABLE" for row in rows),
        "settled_issue_count": len(settled), "unavailable_outcome_issue_count": sum(row["settlement_status"] == "UNAVAILABLE_CANONICAL_OUTCOME" for row in rows),
        "planned_draw_count": sum(int(row["planned_draw_count"]) for row in rows), "stake_yuan": stake, "full_control_stake_yuan": full_stake,
        "capital_utilization_vs_full": stake / full_stake if full_stake else None, "stake_mean_yuan": stake / len(rows), "stake_p50_yuan": percentile(stakes, 0.50), "stake_p90_yuan": percentile(stakes, 0.90), "stake_p95_yuan": percentile(stakes, 0.95), "stake_max_yuan": max(stakes),
        "unique_ticket_draw_count": unique, "duplicate_ticket_draw_count": duplicates, "duplicate_ticket_draw_group_count": sum(int(row["duplicate_ticket_draw_group_count"]) for row in rows),
        "unique_ticket_coverage": Decimal(unique) / sum(int(row["planned_draw_count"]) for row in rows) if stake else None, "duplicate_ticket_ratio": Decimal(duplicates) / sum(int(row["planned_draw_count"]) for row in rows) if stake else None,
        "hit_ticket_count": hits, "coverage_hits": coverage, "coverage_hit_rate": Decimal(coverage) / len(rows), "gross_pre_tax_yuan": gross, "tax_yuan": tax, "after_tax_gross_yuan": gross - tax,
        "pre_tax_net_yuan": pre_net, "tax_adjusted_net_yuan": tax_net, "no_tax_roi": pre_net / stake if stake else None, "tax_adjusted_roi": tax_net / stake if stake else None,
        "gross_top_issue_share": max(issue_gross, default=Decimal(0)) / gross if gross else None, "gross_issue_hhi": sum((item / gross) ** 2 for item in issue_gross) if gross else None,
        "gross_top_identity_share": max((Decimal(row["gross_top_identity_share"]) for row in rows if row["gross_top_identity_share"] is not None), default=None), "largest_issue_gross_yuan": max(issue_gross, default=Decimal(0)),
        "max_drawdown_yuan": drawdown, "longest_miss_streak": longest_miss,
    }


def build_summaries(rows: list[dict[str, object]]) -> tuple[list[dict[str, object]], dict[tuple[str, str, str, int, str], list[dict[str, object]]]]:
    groups: dict[tuple[str, str, int, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        groups[config_key(row)].append(row)
    if len(groups) != 343 or any(len(values) != 348 for values in groups.values()):
        raise RuntimeError("full frozen configuration surface was not settled")
    output: list[dict[str, object]] = []
    for values in groups.values():
        for scope, scope_value, scoped in grouped_scopes(values):
            output.append(summary(scope, scope_value, scoped))
    output.sort(key=lambda row: (str(row["sampling_role"]), int(row["M"]), str(row["seed"]), str(row["scope"]), str(row["scope_value"])))
    return output, groups


def full_deltas(summaries: list[dict[str, object]]) -> list[dict[str, object]]:
    index = {(str(row["scope"]), str(row["scope_value"]), *config_key(row)): row for row in summaries}
    output: list[dict[str, object]] = []
    for row in summaries:
        if row["sampling_role"] == "FULL_ECONOMIC_CONTROL":
            continue
        baseline = index[(str(row["scope"]), str(row["scope_value"]), "FULL_ECONOMIC_CONTROL", "FULL_ENUMERATED", FULL_TICKETS, "NA")]
        def difference(name: str) -> Decimal | None:
            a, b = row[name], baseline[name]
            return Decimal(a) - Decimal(b) if a is not None and b is not None else None
        output.append({
            "scope": row["scope"], "scope_value": row["scope_value"], "sampling_role": row["sampling_role"], "ticket_mechanism": row["ticket_mechanism"], "seed": row["seed"], "M": row["M"],
            "baseline_role": baseline["sampling_role"], "baseline_mechanism": baseline["ticket_mechanism"], "baseline_M": baseline["M"], "support_issue_count": row["settled_issue_count"],
            "stake_yuan": row["stake_yuan"], "full_stake_yuan": baseline["stake_yuan"], "stake_yuan_delta": Decimal(row["stake_yuan"]) - Decimal(baseline["stake_yuan"]),
            "no_tax_roi": row["no_tax_roi"], "full_no_tax_roi": baseline["no_tax_roi"], "no_tax_roi_delta": difference("no_tax_roi"),
            "tax_adjusted_roi": row["tax_adjusted_roi"], "full_tax_adjusted_roi": baseline["tax_adjusted_roi"], "tax_adjusted_roi_delta": difference("tax_adjusted_roi"),
            "coverage_hit_rate": row["coverage_hit_rate"], "full_coverage_hit_rate": baseline["coverage_hit_rate"], "coverage_hit_rate_delta": difference("coverage_hit_rate"),
            "unique_ticket_coverage": row["unique_ticket_coverage"], "full_unique_ticket_coverage": baseline["unique_ticket_coverage"], "unique_ticket_coverage_delta": difference("unique_ticket_coverage"),
            "duplicate_ticket_ratio": row["duplicate_ticket_ratio"], "full_duplicate_ticket_ratio": baseline["duplicate_ticket_ratio"], "duplicate_ticket_ratio_delta": difference("duplicate_ticket_ratio"),
            "comparison_rule": "same complete issue/fold common-support cohort versus exact M=2187 FULL control; raw stake is intentionally not equalized",
        })
    return output


def bootstrap_deltas(groups: dict[tuple[str, str, int, str], list[dict[str, object]]]) -> list[dict[str, object]]:
    full = groups[("FULL_ECONOMIC_CONTROL", "FULL_ENUMERATED", FULL_TICKETS, "NA")]
    output: list[dict[str, object]] = []
    for key, values in sorted(groups.items()):
        role, mechanism, m_value, seed = key
        if role != "PRIMARY_WR_NATURAL_BASELINE":
            continue
        if [row["issue_instance"] for row in values] != [row["issue_instance"] for row in full]:
            raise RuntimeError("WR/FULL bootstrap support identity drift")
        n = len(values)
        point = []
        for metric in ("pre_tax_net_yuan", "tax_adjusted_net_yuan"):
            sample_net = sum((float(row[metric]) for row in values), 0.0)
            sample_stake = sum((float(row["planned_stake_yuan"]) for row in values), 0.0)
            full_net = sum((float(row[metric]) for row in full), 0.0)
            full_stake = sum((float(row["planned_stake_yuan"]) for row in full), 0.0)
            point_value = sample_net / sample_stake - full_net / full_stake
            rng = random.Random(seed_value(CONTRACT, "ISSUE_BOOTSTRAP", role, mechanism, m_value, seed, metric))
            values_boot = []
            positive = negative = 0
            for _ in range(BOOTSTRAP_REPLICATES):
                snet = sstake = fnet = fstake = 0.0
                for _draw in range(n):
                    index = rng.randrange(n)
                    snet += float(values[index][metric]); sstake += float(values[index]["planned_stake_yuan"])
                    fnet += float(full[index][metric]); fstake += float(full[index]["planned_stake_yuan"])
                delta = snet / sstake - fnet / fstake
                values_boot.append(delta)
                positive += delta >= 0.0
                negative += delta <= 0.0
            ordered = sorted(values_boot)
            output.append({
                "sampling_role": role, "ticket_mechanism": mechanism, "seed": seed, "M": m_value, "baseline_role": "FULL_ECONOMIC_CONTROL", "baseline_M": FULL_TICKETS,
                "support_issue_count": n, "replicates": BOOTSTRAP_REPLICATES,
                "metric": "no_tax_roi_delta" if metric == "pre_tax_net_yuan" else "tax_adjusted_roi_delta", "point_estimate": point_value,
                "ci95_low": ordered[math.floor(0.025 * BOOTSTRAP_REPLICATES)], "ci95_high": ordered[math.ceil(0.975 * BOOTSTRAP_REPLICATES) - 1],
                "one_sided_positive_p": (1 + negative) / (1 + BOOTSTRAP_REPLICATES), "two_sided_sign_p": min(1.0, 2 * min((1 + positive) / (1 + BOOTSTRAP_REPLICATES), (1 + negative) / (1 + BOOTSTRAP_REPLICATES))),
            })
    if len(output) != 57 * 3 * 2:
        raise RuntimeError("primary WR bootstrap surface drift")
    return output


def decision_from_surface(summaries: list[dict[str, object]]) -> dict[str, object]:
    primary = [row for row in summaries if row["sampling_role"] == "PRIMARY_WR_NATURAL_BASELINE"]
    stable: list[int] = []
    for m_value in sorted({int(row["M"]) for row in primary}):
        rows = [row for row in primary if int(row["M"]) == m_value]
        all_seed = [row for row in rows if row["scope"] == "ALL"]
        chronological = [row for row in rows if row["scope"] in {"YEAR", "FOLD", "LEAVE_ONE_YEAR_OUT"}]
        if len(all_seed) == 3 and len(chronological) == 3 * 21 and all(row["no_tax_roi"] is not None and Decimal(row["no_tax_roi"]) > 0 for row in all_seed + chronological):
            stable.append(m_value)
    return {
        "decision": "DESCRIPTIVE_SURFACE_ONLY",
        "promotion_authorized": False,
        "recommended_M_interval": stable if stable else [],
        "recommendation": "NO_STABLE_SWEET_SPOT" if not stable else "DESCRIPTIVE_INTERVAL_REQUIRES_STRICT_INDEPENDENT_EV",
        "rule": "A reported M interval requires positive pre-tax ROI in all three WR seeds and every YEAR/FOLD/LOYO view. Regardless of this descriptive screen, no result authorizes purchase, production, betting, or promotion; any candidate requires separate strict independent EV and validation.",
    }


def build(output: Path) -> dict[str, object]:
    if output.exists():
        raise RuntimeError(f"refusing immutable overwrite: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".bj148_gate_b_", dir=output.parent))
    try:
        provenance = validate_inputs()
        cohort, identities_by_issue, m_grid = load_freeze()
        plan_by_issue: dict[str, list[dict[str, str]]] = defaultdict(list)
        with (FREEZE / "sampling_plan.csv").open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                plan_by_issue[row["issue_instance"]].append(row)
        audits: dict[tuple[str, str, int, str], TicketAudit] = defaultdict(TicketAudit)
        rows: list[dict[str, object]] = []
        ticket_handles = gzip_writer(stage / "winning_ticket_tax_ledger.csv.gz", TICKET_FIELDS)
        try:
            writer = ticket_handles[-1]
            for sample in cohort:
                rows.extend(settle_issue(sample, plan_by_issue[sample["issue_instance"]], identities_by_issue.get(sample["issue_instance"], []), m_grid, audits, writer))
        finally:
            close_gzip(ticket_handles)
        if len(rows) != 119_364:
            raise RuntimeError("Gate-B issue-settlement denominator drift")
        rows.sort(key=lambda row: (int(str(row["year"])), int(str(row["issue"])), str(row["sampling_role"]), int(str(row["M"])), str(row["seed"])))
        write_gzip_csv(stage / "issue_m_grid_settlement.csv.gz", ISSUE_FIELDS, (serializable(row) for row in rows))
        summaries, groups = build_summaries(rows)
        write_csv(stage / "m_grid_surface_summary.csv", SUMMARY_FIELDS, (serializable(row) for row in summaries))
        deltas = full_deltas(summaries)
        write_csv(stage / "full_control_deltas.csv", DELTA_FIELDS, (serializable(row) for row in deltas))
        bootstrap = bootstrap_deltas(groups)
        write_csv(stage / "issue_bootstrap_full_deltas.csv", BOOTSTRAP_FIELDS, (serializable(row) for row in bootstrap))
        all_summary = {(str(row["sampling_role"]), str(row["ticket_mechanism"]), int(row["M"]), str(row["seed"])): row for row in summaries if row["scope"] == "ALL"}
        recon_rows = []
        for key, audit in sorted(audits.items()):
            issue_tax = Decimal(all_summary[key]["tax_yuan"])
            difference = audit.tax - issue_tax
            if abs(difference) > MONEY_QUANTUM:
                raise RuntimeError(f"per-ticket tax reconciliation drift: {key}: {difference}")
            recon_rows.append({
                "sampling_role": key[0], "ticket_mechanism": key[1], "seed": key[3], "M": key[2],
                "ticket_ledger_hit_ticket_count": audit.hits, "ticket_ledger_taxable_ticket_count": audit.taxable,
                "ticket_ledger_tax_yuan": audit.tax, "issue_ledger_tax_yuan": issue_tax, "difference_yuan": difference,
                "tax_rule": "20pct_if_each_ticket_gross_gte_10000_no_aggregate_pooling",
            })
        write_csv(stage / "ticket_tax_reconciliation.csv", TAX_RECON_FIELDS, (serializable(row) for row in recon_rows))
        decision = decision_from_surface(summaries)
        (stage / "decision.json").write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        write_csv(stage / "source_census.csv", SOURCE_FIELDS, [
            {"source": "bj148_gate_a_preoutcome_v1", "role": "accepted immutable complete-issue common-support, Q-role, dense-M and WR/WOR/FULL plan freeze", "identity": "SHA256SUMS.json", "sha256": FREEZE_MANIFEST, "rows": 119364, "join_status": "all frozen issue/arm/M/seed rows retained; no candidate, probability, M, seed, stake or sampler rule recomputed"},
            {"source": "bj95_gate_b_outcome_settlement_v2r8", "role": "canonical trusted final-SP truth for the already-frozen N7 role match IDs", "identity": "canonical_outcome_join.csv", "sha256": OUTCOME_PAYLOAD, "rows": 46802, "join_status": "trusted result and final SP only; no pre-outcome selection input changed"},
        ])
        status_counts = Counter(str(row["settlement_status"]) for row in rows)
        settled_issues = status_counts["SETTLED"] // 343
        unavailable_issues = status_counts["UNAVAILABLE_CANONICAL_OUTCOME"] // 343
        no_bet_issues = status_counts["NO_BET_GATE_A"] // 343
        if (settled_issues, unavailable_issues, no_bet_issues) != (187, 156, 5):
            raise RuntimeError("canonical outcome availability denominator drift")
        card = {
            "issue": 148, "contract": CONTRACT, "runner_version": VERSION, "stage": "GATE_B_ONE_SHOT_DENSE_M_GRID_OUTCOME_SETTLEMENT", "provenance": provenance,
            "input_boundary": "Only the accepted immutable #148 Gate-A common-support/Q-role/dense-plan package and the canonical trusted final-SP outcome payload are read. No candidate selection, probability calibration, M grid, seed, stake cap, or ticket plan is recomputed. A frozen issue with any missing canonical outcome is retained as UNAVAILABLE_CANONICAL_OUTCOME at zero executed stake; it is never partially settled or replaced.",
            "sampling": "WR is primary: each independent Q-weighted draw remains a separate ¥2 ticket, including exact duplicates. WOR remains sensitivity. M=2187 is exact FULL enumeration.",
            "tax": "Tax is secondary and per individual winning ticket only: 20% iff that ticket gross is at least ¥10,000. Issue, identity, arm, policy and aggregate receipts never cross the tax threshold. The winning-ticket ledger and reconciliation make this auditable.",
            "metrics": "Pre-tax ROI is primary. The full M surface reports tax reference, complete-issue hit/coverage, per-issue stake distribution, total stake/capital utilization, unique/duplicate curves, matched FULL deltas, YEAR/FOLD/LOYO summaries, and deterministic issue-bootstrap FULL deltas for all WR M/seed points.",
            "decision": decision, "scope": "historical paper research only; no purchase, production, betting, or promotion authority.",
            "outcome_completeness": {"frozen_complete_issue_rows": 348, "frozen_available_issue_rows": 343, "settled_complete_issue_rows": settled_issues, "unavailable_canonical_outcome_issue_rows": unavailable_issues, "source_no_bet_issue_rows": no_bet_issues, "rule": "Complete issue settlement only; unavailable rows have zero executed stake and remain in every M/seed/arm denominator."},
            "denominator": {"issue_settlement_rows": len(rows), "surface_summary_rows": len(summaries), "full_delta_rows": len(deltas), "primary_wr_bootstrap_rows": len(bootstrap), "ticket_tax_reconciliation_rows": len(recon_rows)},
        }
        (stage / "settlement_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        shutil.copy2(__file__, stage / "settlement_runner.py")
        (stage / "README.md").write_text(
            "# #148 Gate B — dense N7 M-grid settlement\n\n"
            "One-shot outcome settlement of the accepted Gate-A surface. WR is primary, WOR sensitivity, and FULL is an exact control. Tax is evaluated per winning ticket and never after pooling. Replay with `python3 settlement_runner.py --output <new-dir>`; staging is under `results/`, never `/tmp`.\n",
            encoding="utf-8",
        )
        compressed = ("issue_m_grid_settlement.csv.gz", "winning_ticket_tax_ledger.csv.gz")
        content = {
            "contract_version": "bj148-gate-b-portable-content-v1",
            "gzip_payloads": {name: {"canonical_decompressed_sha256": decompressed_digest(stage / name)[0], "canonical_decompressed_bytes": decompressed_digest(stage / name)[1]} for name in compressed},
            "non_compressed_controls": {item.name: sha256(item) for item in sorted(stage.iterdir()) if item.is_file() and item.name not in compressed},
        }
        (stage / "CONTENT_IDENTITY.json").write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest = {item.name: sha256(item) for item in sorted(stage.iterdir()) if item.is_file()}
        (stage / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(stage, output)
        return {"manifest_sha256": sha256(output / "SHA256SUMS.json"), "content_identity_sha256": sha256(output / "CONTENT_IDENTITY.json"), "issue_rows": len(rows), "summary_rows": len(summaries), "delta_rows": len(deltas), "bootstrap_rows": len(bootstrap), "decision": decision}
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
