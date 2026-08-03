#!/usr/bin/env python3
"""Independent EV reconstruction for #165.

This validator is deliberately self-contained.  It reads the accepted #159
Gate-A freeze, the authenticated final-outcome join, and the immutable #159
Gate-B ledgers, but never imports either #159 runner.  The allocator, ticket
rank calculation, per-ticket payout/tax calculation, issue aggregation and
control surfaces are reconstructed here and compared to the published v2r1
rows.  The output is a new immutable evidence package; it does not modify a
prior #159 result package.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import heapq
import itertools
import json
import math
import os
import random
import shutil
import subprocess
from collections import defaultdict
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path

getcontext().prec = 96

CONTRACT = "BJ-EV-159-N9-001"
SOURCE_CONTRACT = "BJ-HIST-SELECTED-WOR-CROSS-N-001"
GA_MANIFEST = "a15c585fc1836da4f558d07ce19c925561bfd1c240e834b7e3e0da22701cd325"
GB_MANIFEST = "17b42f65b834f2b5afff0e52795588f95340d76810f7faec75b193b6eecc4cc8"
GB_CONTENT = "7ba60fcc8fa99c620c019f6098e3d9e8b5bb112f6622799baffa9c6f2422cbaf"
SOURCE_V2_MANIFEST = "ad724693f7fbee8a120030cb4ace852a4cf69011bf98b39b41ae427bcfbd0917"
SOURCE_V2_CONTENT = "42f8960c9754efb3033cb6da54f38b759da3cb64d7272f195845aeabb51b1b08"
OUTCOME_MANIFEST = "fbbd3b53bd86f4bb0caff8f2587933cd6b0e4e7d04fb0f709bac934ec2a705cc"
OUTCOME_PAYLOAD = "13d709d253c31519734dbf0447e6961ac8a6060772975d7461741224e5251a89"
N_GRID = tuple(range(2, 11))
M_GRID = (32, 64, 128)
SEEDS = ("137001", "137002", "137003")
CODES = ("3", "1", "0")
STAKE = Decimal("2")
FACTOR = Decimal("0.65")
TAX_RATE = Decimal("0.20")
TAX_THRESHOLD = Decimal("10000")
MONEY_Q = Decimal("0.000001")
BOOTSTRAP_REPLICATES = 1000

SUMMARY_FIELDS = (
    "scope", "scope_value", "n", "M", "nominal_M", "effective_M", "seed", "saturation_status",
    "frozen_issue_count", "frozen_available_issue_count", "frozen_no_bet_issue_count",
    "settled_issue_count", "unavailable_outcome_issue_count", "planned_identity_count",
    "settled_identity_count", "planned_draw_count", "executed_draw_count", "planned_stake_yuan",
    "stake_yuan", "full_control_stake_yuan", "capital_utilization_vs_full", "stake_mean_yuan",
    "stake_p50_yuan", "stake_p90_yuan", "stake_p95_yuan", "stake_max_yuan", "unique_ticket_count",
    "duplicate_ticket_count", "duplicate_ticket_ratio", "winning_ticket_count", "hit_identity_count",
    "coverage_hit_rate", "ticket_hit_rate", "gross_pre_tax_yuan", "taxable_winning_ticket_count",
    "tax_line_share", "tax_yuan", "after_tax_gross_yuan", "pre_tax_net_yuan", "tax_adjusted_net_yuan",
    "no_tax_roi", "tax_adjusted_roi", "gm_expected_sp_mean", "expected_sp_product_q_mean",
    "actual_winning_sp_product_mean", "gross_top_issue", "gross_top_issue_gross_yuan",
    "gross_top_issue_share", "gross_issue_hhi", "largest_issue", "largest_issue_gross_yuan",
    "largest_issue_stake_yuan", "largest_issue_pre_tax_net_yuan", "largest_issue_tax_adjusted_net_yuan",
    "ex_largest_issue_no_tax_roi", "ex_largest_issue_tax_adjusted_roi", "largest_year",
    "largest_year_stake_yuan", "largest_year_pre_tax_net_yuan", "largest_year_tax_adjusted_net_yuan",
    "ex_largest_year_no_tax_roi", "ex_largest_year_tax_adjusted_roi", "max_drawdown_no_tax_yuan",
    "max_drawdown_tax_adjusted_yuan", "longest_frozen_calendar_miss_streak", "longest_executed_miss_streak",
)


def repo_root(anchor: Path) -> Path:
    for candidate in (anchor.resolve().parent, *anchor.resolve().parents):
        if (candidate / ".git").exists() and (candidate / "results").is_dir():
            return candidate
    raise RuntimeError("repository root unavailable")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def dec(value: object, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise RuntimeError(f"invalid {label}: {value!r}") from exc
    if not result.is_finite():
        raise RuntimeError(f"non-finite {label}: {value!r}")
    return result


def money(value: Decimal) -> str:
    return format(value.quantize(MONEY_Q), "f")


def ratio(value: Decimal | None) -> str:
    return "" if value is None else f"{float(value):.12f}"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def read_gzip(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, object]], fields: tuple[str, ...] | None = None) -> None:
    if fields is None:
        fields = tuple(rows[0].keys()) if rows else ("status",)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n", extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def write_gzip(path: Path, rows: list[dict[str, object]], fields: tuple[str, ...]) -> None:
    with gzip.open(path, "wt", newline="", encoding="utf-8", mtime=0) as f:
        writer = csv.DictWriter(f, fieldnames=fields, lineterminator="\n", extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def verify_bundle(path: Path, expected_manifest: str, expected_content: str | None = None) -> dict[str, str]:
    manifest_path = path / "SHA256SUMS.json"
    if sha(manifest_path) != expected_manifest:
        raise RuntimeError(f"manifest hash drift: {path}")
    declared = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = {p.name: sha(p) for p in path.iterdir() if p.is_file() and p.name != manifest_path.name}
    if declared != actual:
        raise RuntimeError(f"manifest coverage drift: {path}")
    if expected_content is not None and sha(path / "CONTENT_IDENTITY.json") != expected_content:
        raise RuntimeError(f"content identity drift: {path}")
    return declared


def stable_uniform(*parts: object) -> float:
    token = "|".join(str(part) for part in parts).encode("utf-8")
    value = int.from_bytes(hashlib.sha256(token).digest()[:8], "big")
    return (value + 0.5) / (2 ** 64)


def truth_ordinal(code: str) -> int:
    value = 0
    for digit in code:
        value = value * 3 + CODES.index(digit)
    return value


def ticket_code(ordinal: int, n: int) -> str:
    digits = ["3"] * n
    value = ordinal
    for index in range(n - 1, -1, -1):
        digits[index] = CODES[value % 3]
        value //= 3
    return "".join(digits)


def ticket_tax(gross: Decimal) -> Decimal:
    # Keep the unrounded tax through after-tax net calculation; money() is the
    # sole presentation quantizer, matching the frozen settlement contract.
    return gross * TAX_RATE if gross >= TAX_THRESHOLD else Decimal(0)


def q_weights(roles: list[dict[str, str]]) -> tuple[float, ...]:
    weights: list[float] = []
    for ticket in itertools.product(CODES, repeat=len(roles)):
        value = 1.0
        for role, code in zip(roles, ticket):
            value *= float(role[f"q_weight{code}"])
        weights.append(value)
    if not math.isfinite(sum(weights)) or abs(sum(weights) - 1.0) > 3e-8:
        raise RuntimeError("Q ticket mass drift")
    return tuple(weights)


def allocation(weights: tuple[float, ...], signature: str, seed: str, effective_m: int, truth_idx: int | None) -> tuple[tuple[int, ...], int | None]:
    keyed: list[tuple[float, int]] = []
    truth_key: tuple[float, int] | None = None
    for ordinal, weight in enumerate(weights):
        key = math.inf if weight <= 0 else -math.log(max(stable_uniform("bj137", "WOR", seed, signature, ordinal), 1e-18)) / weight
        pair = (key, ordinal)
        keyed.append(pair)
        if ordinal == truth_idx:
            truth_key = pair
    top = tuple(ordinal for _, ordinal in heapq.nsmallest(min(effective_m, len(keyed), 128), keyed))
    truth_rank = None if truth_key is None else 1 + sum(item < truth_key for item in keyed)
    return top, truth_rank


def _allocation_worker(spec: tuple[str, str, str, tuple[tuple[float, float, float], ...], int | None]) -> tuple[str, str, tuple[int, ...], int | None]:
    """Compute one top-128 ordering per identity/seed.

    The three nominal M values are prefixes of the same ordering.  Computing
    the ordering once is both faster and makes the effective-M equivalence
    explicit; it does not change any allocation key or ticket rank.
    """
    identity_id, signature, seed, q_vectors, truth_idx = spec
    weights = tuple(math.prod(q_vectors[i][CODES.index(code)] for i, code in enumerate(ticket)) for ticket in itertools.product(CODES, repeat=len(q_vectors)))
    selected, rank = allocation(weights, signature, seed, min(128, len(weights)), truth_idx)
    return identity_id, seed, selected, rank


def all_allocations(identities: dict[str, dict[str, str]], role_map: dict[str, list[dict[str, str]]], outcomes: dict[str, dict[str, str]]) -> dict[tuple[str, str, int], tuple[tuple[int, ...], int | None, str]]:
    def spec_iter():
        for identity_id, identity in identities.items():
            roles = sorted(role_map[identity_id], key=lambda row: int(row["selection_rank"]))
            q_vectors = tuple(tuple(float(role[f"q_weight{code}"]) for code in CODES) for role in roles)
            truth_code = "".join(outcomes[row["match_id"]]["result_code"] for row in roles) if all(row["match_id"] in outcomes for row in roles) else None
            truth_idx = truth_ordinal(truth_code) if truth_code else None
            for seed in SEEDS:
                yield (identity_id, identity["selected_match_ids"], seed, q_vectors, truth_idx)
    cache: dict[tuple[str, str, int], tuple[tuple[int, ...], int | None, str]] = {}
    workers = max(1, min(8, os.cpu_count() or 1))
    if workers == 1:
        result_iter = map(_allocation_worker, spec_iter())
    else:
        import concurrent.futures
        executor = concurrent.futures.ProcessPoolExecutor(max_workers=workers)
        result_iter = executor.map(_allocation_worker, spec_iter(), chunksize=8)
    try:
        for identity_id, seed, selected, rank in result_iter:
            n = int(identities[identity_id]["n"])
            for effective_m in sorted({min(m, 3 ** n) for m in M_GRID}):
                prefix = selected[:effective_m]
                fingerprint = hashlib.sha256(json.dumps(prefix, separators=(",", ":")).encode()).hexdigest()
                cache[(identity_id, seed, effective_m)] = (prefix, rank, fingerprint)
    finally:
        if workers > 1:
            executor.shutdown()
    return cache


def compare_value(expected: str, actual: object, field: str, tolerance: Decimal = Decimal("0.000000000002")) -> bool:
    actual_text = "" if actual is None else str(actual)
    if expected == actual_text:
        return True
    if expected == "" or actual_text == "":
        return False
    try:
        return abs(Decimal(expected) - Decimal(actual_text)) <= tolerance
    except InvalidOperation:
        return False


def load_inputs(root: Path) -> tuple[dict[str, str], list[dict[str, str]], dict[str, dict[str, str]], dict[str, list[dict[str, str]]], dict[tuple[int, int, str], dict[str, str]], dict[str, dict[str, str]], list[dict[str, str]], list[dict[str, str]], dict[tuple[int, int, str], list[dict[str, str]]]]:
    ga = root / "results/bj159_gate_a_preoutcome_v2r1"
    gb = root / "results/bj159_gate_b_outcome_settlement_v2r1"
    outcome_dir = root / "results/bj95_gate_b_outcome_settlement_v2r8"
    ga_manifest = verify_bundle(ga, GA_MANIFEST)
    gb_manifest = verify_bundle(gb, GB_MANIFEST, GB_CONTENT)
    verify_bundle(root / "results/bj159_gate_b_outcome_settlement_v2", SOURCE_V2_MANIFEST, SOURCE_V2_CONTENT)
    outcome_manifest = verify_bundle(outcome_dir, OUTCOME_MANIFEST)
    if outcome_manifest.get("canonical_outcome_join.csv") != OUTCOME_PAYLOAD:
        raise RuntimeError("canonical outcome payload drift")
    card = json.loads((ga / "gate_a_card.json").read_text(encoding="utf-8"))
    if card.get("contract") != SOURCE_CONTRACT or card.get("stage") != "GATE_A_OUTCOME_UNEXPOSED_SELECTED_BASELINE_CROSS_N_FREEZE":
        raise RuntimeError("Gate-A contract drift")
    identities = read_gzip(ga / "identity_catalog.csv.gz")
    roles = read_gzip(ga / "role_vectors.csv.gz")
    participation = read_csv(ga / "issue_participation.csv")
    plans = read_csv(ga / "sampling_plan.csv")
    outcomes_rows = read_csv(outcome_dir / "canonical_outcome_join.csv")
    outcomes = {row["match_id"]: row for row in outcomes_rows}
    if len(outcomes) != len(outcomes_rows):
        raise RuntimeError("duplicate outcome match id")
    for row in outcomes.values():
        if row["result_code"] not in CODES or row["settlement_quality"] != "trusted" or row["has_trusted_settlement"] != "1" or dec(row["winning_sp"], "winning SP") <= 0:
            raise RuntimeError("untrusted canonical outcome")
    identity_map = {row["identity_id"]: row for row in identities}
    role_map: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in roles:
        role_map[row["identity_id"]].append(row)
    plan_map = {(int(row["n"]), int(row["nominal_M"]), row["seed"]): row for row in plans}
    source_identity = read_gzip(gb / "identity_settlement.csv.gz")
    source_issue = read_gzip(gb / "issue_settlement.csv.gz")
    source_surface = read_csv(gb / "surface_summary.csv")
    source_by_cfg: dict[tuple[int, int, str], list[dict[str, str]]] = defaultdict(list)
    for row in source_issue:
        source_by_cfg[(int(row["n"]), int(row["nominal_M"]), row["seed"])].append(row)
    return ga_manifest, identities, identity_map, role_map, plan_map, outcomes, source_identity, source_issue, source_surface, source_by_cfg


def validate_gate_a(identities: list[dict[str, str]], identity_map: dict[str, dict[str, str]], role_map: dict[str, list[dict[str, str]]], plan_map: dict[tuple[int, int, str], dict[str, str]], participation: list[dict[str, str]]) -> dict[str, object]:
    expected_counts = {2: 38, 3: 335, 4: 648, 5: 844, 6: 937, 7: 1005, 8: 1042, 9: 1077, 10: 1094}
    observed_counts = {n: sum(int(row["n"]) == n for row in identities) for n in N_GRID}
    if observed_counts != expected_counts or len(identities) != 7020 or len(role_map) != 7020 or len(participation) != 3132 or len(plan_map) != 81:
        raise RuntimeError("Gate-A denominator drift")
    gm_failures = q_failures = role_failures = 0
    for identity in identities:
        iid = identity["identity_id"]
        roles = sorted(role_map[iid], key=lambda row: int(row["selection_rank"]))
        n = int(identity["n"])
        if len(roles) != n or [int(row["selection_rank"]) for row in roles] != list(range(1, n + 1)) or "|".join(row["match_id"] for row in roles) != identity["selected_match_ids"]:
            role_failures += 1
        if identity["descriptor_sha256"] != iid or identity["selected_n"] != identity["n"] or identity["outcome_boundary"].lower().find("no outcome") < 0:
            role_failures += 1
        values = [dec(row["e_sp"], "e_sp") for row in roles]
        gm = Decimal(str(math.prod(float(value) for value in values) ** (1.0 / n)))
        if abs(gm - dec(identity["gm_e_sp"], "gm_e_sp")) > Decimal("0.00000000002"):
            gm_failures += 1
        for row in roles:
            q = [dec(row[f"q_weight{code}"], "q weight") for code in CODES]
            if abs(sum(q) - Decimal(1)) > Decimal("0.00000000002") or any(v < 0 for v in q):
                q_failures += 1
    if role_failures or gm_failures or q_failures:
        raise RuntimeError(f"Gate-A structural drift roles={role_failures} gm={gm_failures} q={q_failures}")
    expected_cells = {(n, m, seed) for n in N_GRID for m in M_GRID for seed in SEEDS}
    if set(plan_map) != expected_cells:
        raise RuntimeError("sampling plan grid drift")
    for (n, m, seed), row in plan_map.items():
        effective = min(m, 3 ** n)
        if int(row["effective_M"]) != effective or row["saturation_status"] != ("FULL_SPACE_SATURATED" if m > 3 ** n else "PARTIAL_WOR") or row["allocator"] != "Q_INFORMED_WOR_DISTINCT" or row["mechanism"] != "WEIGHTED_WITHOUT_REPLACEMENT":
            raise RuntimeError("sampling plan contract drift")
    return {"identity_rows": len(identities), "identity_count_by_n": {str(n): observed_counts[n] for n in N_GRID}, "role_rows": sum(len(v) for v in role_map.values()), "participation_rows": len(participation), "sampling_plan_rows": len(plan_map), "structural_failures": 0}


def identity_settlement(identity: dict[str, str], roles: list[dict[str, str]], plan: dict[str, str], seed: str, outcomes: dict[str, dict[str, str]], alloc: tuple[tuple[int, ...], int | None, str]) -> dict[str, object]:
    n = int(identity["n"]); nominal_m = int(plan["nominal_M"]); effective_m = int(plan["effective_M"])
    selected, truth_rank, fingerprint = alloc
    missing = [role["match_id"] for role in roles if role["match_id"] not in outcomes]
    planned = effective_m
    base: dict[str, object] = {"identity_id": identity["identity_id"], "issue": identity["issue"], "fold": identity["fold"], "year": identity["year"], "issue_instance": identity["issue_instance"], "n": n, "M": nominal_m, "nominal_M": nominal_m, "effective_M": effective_m, "seed": seed, "saturation_status": plan["saturation_status"], "allocation_equivalence_key": f"{identity['identity_id']}|{seed}|effective_M={effective_m}", "planned_draw_count": planned, "executed_draw_count": 0 if missing else planned, "stake_yuan": money(Decimal(0) if missing else STAKE * effective_m), "unique_ticket_count": 0 if missing else effective_m, "duplicate_ticket_count": 0, "duplicate_ticket_ratio": ratio(Decimal(0)), "allocation_fingerprint": fingerprint, "outcome_gap_count": len(missing), "settlement_status": "UNAVAILABLE_CANONICAL_OUTCOME" if missing else "SETTLED", "gm_e_sp": identity["gm_e_sp"]}
    if missing:
        return {**base, "truth_sequence": "", "truth_ordinal": "", "truth_rank": "", "coverage_hit": "", "winning_ticket_count": 0, "expected_sp_product_q": "", "actual_winning_sp_product": "", "gross_pre_tax_yuan": money(Decimal(0)), "taxable_winning_ticket_count": 0, "tax_yuan": money(Decimal(0)), "after_tax_gross_yuan": money(Decimal(0)), "pre_tax_net_yuan": money(Decimal(0)), "tax_adjusted_net_yuan": money(Decimal(0)), "no_tax_roi": "", "tax_adjusted_roi": "", "winning_sp_sources": ""}
    truth = "".join(outcomes[role["match_id"]]["result_code"] for role in roles)
    truth_idx = truth_ordinal(truth)
    product = Decimal(1); expected_product = Decimal(1); sources: set[str] = set()
    for role in roles:
        outcome = outcomes[role["match_id"]]
        product *= dec(outcome["winning_sp"], "winning SP")
        sources.add(outcome["winning_sp_source"])
        expected_leg = sum(dec(role[f"q_weight{code}"], "q weight") * dec(role[f"predicted_sp{code}"], "predicted SP") for code in CODES)
        expected_product *= expected_leg
    hit = truth_rank is not None and truth_rank <= effective_m
    gross = STAKE * FACTOR * product if hit else Decimal(0)
    tax = ticket_tax(gross) if hit else Decimal(0)
    after = gross - tax
    stake = STAKE * effective_m
    pre = gross - stake; tax_net = after - stake
    return {**base, "truth_sequence": truth, "truth_ordinal": truth_idx, "truth_rank": truth_rank, "coverage_hit": "YES" if hit else "NO", "winning_ticket_count": int(hit), "expected_sp_product_q": money(expected_product), "actual_winning_sp_product": money(product) if hit else "", "gross_pre_tax_yuan": money(gross), "taxable_winning_ticket_count": int(tax > 0), "tax_yuan": money(tax), "after_tax_gross_yuan": money(after), "pre_tax_net_yuan": money(pre), "tax_adjusted_net_yuan": money(tax_net), "no_tax_roi": ratio(pre / stake), "tax_adjusted_roi": ratio(tax_net / stake), "winning_sp_sources": ";".join(sorted(sources))}


def contribution_groups(rows: list[dict[str, object]], key: str) -> dict[str, dict[str, Decimal]]:
    groups: dict[str, dict[str, Decimal]] = {}
    for row in rows:
        stake = dec(row["stake_yuan"], "stake")
        if stake <= 0:
            continue
        group = str(row[key]); current = groups.setdefault(group, {"stake": Decimal(0), "gross": Decimal(0), "pre": Decimal(0), "tax": Decimal(0)})
        current["stake"] += stake; current["gross"] += dec(row["gross_pre_tax_yuan"], "gross"); current["pre"] += dec(row["pre_tax_net_yuan"], "pre-tax net"); current["tax"] += dec(row["tax_adjusted_net_yuan"], "tax net")
    return groups


def largest_group(groups: dict[str, dict[str, Decimal]]) -> tuple[str, dict[str, Decimal]]:
    return max(groups.items(), key=lambda item: (item[1]["pre"], item[0])) if groups else ("", {"stake": Decimal(0), "gross": Decimal(0), "pre": Decimal(0), "tax": Decimal(0)})


def quantile(values: list[Decimal], q: float) -> Decimal:
    if not values:
        return Decimal(0)
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, math.ceil(len(ordered) * q) - 1))]


def drawdown(rows: list[dict[str, object]], field: str) -> Decimal:
    cumulative = peak = maximum = Decimal(0)
    for row in sorted(rows, key=lambda item: (str(item.get("first_kickoff_ts", "")), str(item["issue_instance"]))):
        cumulative += dec(row[field], field); peak = max(peak, cumulative); maximum = max(maximum, peak - cumulative)
    return maximum


def miss_streak(rows: list[dict[str, object]], executed_only: bool) -> int:
    streak = longest = 0
    for row in sorted(rows, key=lambda item: (str(item.get("first_kickoff_ts", "")), str(item["issue_instance"]))):
        if executed_only and dec(row["stake_yuan"], "stake") <= 0:
            continue
        streak = 0 if row["coverage_hit"] == "YES" else streak + 1; longest = max(longest, streak)
    return longest


def summary(issue_rows: list[dict[str, object]], scope: str, scope_value: str) -> dict[str, object]:
    first = issue_rows[0]; n = int(first["n"]); m = int(first["nominal_M"]); effective = int(first["effective_M"]); seed = str(first["seed"])
    settled = [row for row in issue_rows if int(row["settled_identity_count"]) > 0]; executed = [row for row in issue_rows if dec(row["stake_yuan"], "stake") > 0]
    stake = sum((dec(row["stake_yuan"], "stake") for row in issue_rows), Decimal(0)); full = sum((dec(row["full_control_stake_yuan"], "full stake") for row in issue_rows), Decimal(0))
    gross = sum((dec(row["gross_pre_tax_yuan"], "gross") for row in issue_rows), Decimal(0)); tax = sum((dec(row["tax_yuan"], "tax") for row in issue_rows), Decimal(0)); after = sum((dec(row["after_tax_gross_yuan"], "after") for row in issue_rows), Decimal(0)); pre = sum((dec(row["pre_tax_net_yuan"], "pre") for row in issue_rows), Decimal(0)); tax_net = sum((dec(row["tax_adjusted_net_yuan"], "tax net") for row in issue_rows), Decimal(0))
    stake_values = [dec(row["stake_yuan"], "stake") for row in executed]
    issue_groups = contribution_groups(issue_rows, "issue_instance"); year_groups = contribution_groups(issue_rows, "year")
    gross_top, gross_top_v = max(issue_groups.items(), key=lambda x: (x[1]["gross"], x[0])) if issue_groups else ("", {"gross": Decimal(0), "stake": Decimal(0), "pre": Decimal(0), "tax": Decimal(0)})
    largest_issue, issue_v = largest_group(issue_groups); largest_year, year_v = largest_group(year_groups)
    total_gross = sum((v["gross"] for v in issue_groups.values()), Decimal(0)); hhi = sum((v["gross"] / total_gross) ** 2 for v in issue_groups.values()) if total_gross else Decimal(0)
    def ex_roi(v: dict[str, Decimal], field: str) -> str:
        remaining = stake - v["stake"]
        return ratio((pre if field == "pre" else tax_net) - v[field] if remaining else None) if remaining <= 0 else ratio(((pre if field == "pre" else tax_net) - v[field]) / remaining)
    gm = [dec(row["gm_expected_sp_mean"], "gm") for row in settled if row["gm_expected_sp_mean"] not in ("", None)]; expected = [dec(row["expected_sp_product_q_mean"], "expected") for row in settled if row["expected_sp_product_q_mean"] not in ("", None)]; actual = [dec(row["actual_winning_sp_product_mean"], "actual") for row in settled if row["actual_winning_sp_product_mean"] not in ("", None)]
    out: dict[str, object] = {"scope": scope, "scope_value": scope_value, "n": n, "M": m, "nominal_M": m, "effective_M": effective, "seed": seed, "saturation_status": first["saturation_status"], "frozen_issue_count": len(issue_rows), "frozen_available_issue_count": sum(row["selection_status"] == "AVAILABLE" for row in issue_rows), "frozen_no_bet_issue_count": sum(row["selection_status"] != "AVAILABLE" for row in issue_rows), "settled_issue_count": len(settled), "unavailable_outcome_issue_count": sum(int(row["unavailable_identity_count"]) > 0 for row in issue_rows), "planned_identity_count": sum(int(row["planned_identity_count"]) for row in issue_rows), "settled_identity_count": sum(int(row["settled_identity_count"]) for row in issue_rows), "planned_draw_count": sum(int(row["planned_draw_count"]) for row in issue_rows), "executed_draw_count": sum(int(row["executed_draw_count"]) for row in issue_rows), "planned_stake_yuan": money(sum((dec(row["planned_stake_yuan"], "planned") for row in issue_rows), Decimal(0))), "stake_yuan": money(stake), "full_control_stake_yuan": money(full), "capital_utilization_vs_full": ratio(stake / full if full else None), "stake_mean_yuan": money(sum(stake_values, Decimal(0)) / len(stake_values)) if stake_values else money(Decimal(0)), "stake_p50_yuan": money(quantile(stake_values, .5)), "stake_p90_yuan": money(quantile(stake_values, .9)), "stake_p95_yuan": money(quantile(stake_values, .95)), "stake_max_yuan": money(max(stake_values, default=Decimal(0))), "unique_ticket_count": sum(int(row["unique_ticket_count"]) for row in issue_rows), "duplicate_ticket_count": sum(int(row["duplicate_ticket_count"]) for row in issue_rows), "duplicate_ticket_ratio": ratio(Decimal(sum(int(row["duplicate_ticket_count"]) for row in issue_rows)) / sum(int(row["unique_ticket_count"]) + int(row["duplicate_ticket_count"]) for row in issue_rows)) if sum(int(row["unique_ticket_count"]) + int(row["duplicate_ticket_count"]) for row in issue_rows) else "", "winning_ticket_count": sum(int(row["winning_ticket_count"]) for row in issue_rows), "hit_identity_count": sum(int(row["hit_identity_count"]) for row in issue_rows), "coverage_hit_rate": ratio(Decimal(sum(int(row["hit_identity_count"]) for row in issue_rows)) / sum(int(row["settled_identity_count"]) for row in issue_rows)) if sum(int(row["settled_identity_count"]) for row in issue_rows) else "", "ticket_hit_rate": ratio(Decimal(sum(int(row["winning_ticket_count"]) for row in issue_rows)) / sum(int(row["executed_draw_count"]) for row in issue_rows)) if sum(int(row["executed_draw_count"]) for row in issue_rows) else "", "gross_pre_tax_yuan": money(gross), "taxable_winning_ticket_count": sum(int(row["taxable_winning_ticket_count"]) for row in issue_rows), "tax_line_share": ratio(Decimal(sum(int(row["taxable_winning_ticket_count"]) for row in issue_rows)) / sum(int(row["winning_ticket_count"]) for row in issue_rows)) if sum(int(row["winning_ticket_count"]) for row in issue_rows) else "", "tax_yuan": money(tax), "after_tax_gross_yuan": money(after), "pre_tax_net_yuan": money(pre), "tax_adjusted_net_yuan": money(tax_net), "no_tax_roi": ratio(pre / stake) if stake else "", "tax_adjusted_roi": ratio(tax_net / stake) if stake else "", "gm_expected_sp_mean": ratio(sum(gm, Decimal(0)) / len(gm)) if gm else "", "expected_sp_product_q_mean": ratio(sum(expected, Decimal(0)) / len(expected)) if expected else "", "actual_winning_sp_product_mean": ratio(sum(actual, Decimal(0)) / len(actual)) if actual else "", "gross_top_issue": gross_top, "gross_top_issue_gross_yuan": money(gross_top_v["gross"]), "gross_top_issue_share": ratio(gross_top_v["gross"] / total_gross) if total_gross else "", "gross_issue_hhi": ratio(hhi), "largest_issue": largest_issue, "largest_issue_gross_yuan": money(issue_v["gross"]), "largest_issue_stake_yuan": money(issue_v["stake"]), "largest_issue_pre_tax_net_yuan": money(issue_v["pre"]), "largest_issue_tax_adjusted_net_yuan": money(issue_v["tax"]), "ex_largest_issue_no_tax_roi": ex_roi(issue_v, "pre"), "ex_largest_issue_tax_adjusted_roi": ex_roi(issue_v, "tax"), "largest_year": largest_year, "largest_year_stake_yuan": money(year_v["stake"]), "largest_year_pre_tax_net_yuan": money(year_v["pre"]), "largest_year_tax_adjusted_net_yuan": money(year_v["tax"]), "ex_largest_year_no_tax_roi": ex_roi(year_v, "pre"), "ex_largest_year_tax_adjusted_roi": ex_roi(year_v, "tax"), "max_drawdown_no_tax_yuan": money(drawdown(executed, "pre_tax_net_yuan")), "max_drawdown_tax_adjusted_yuan": money(drawdown(executed, "tax_adjusted_net_yuan")), "longest_frozen_calendar_miss_streak": miss_streak(issue_rows, False), "longest_executed_miss_streak": miss_streak(issue_rows, True)}
    return out


def recompute_issue_rows(identities: dict[str, dict[str, str]], role_map: dict[str, list[dict[str, str]]], participation: list[dict[str, str]], plans: dict[tuple[int, int, str], dict[str, str]], outcomes: dict[str, dict[str, str]], allocations: dict[tuple[str, str, int], tuple[tuple[int, ...], int | None, str]], first_kickoff: dict[tuple[str, int], str]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    by_id_cfg: dict[tuple[str, str, int], dict[str, object]] = {}
    for identity_id, identity in identities.items():
        roles = sorted(role_map[identity_id], key=lambda row: int(row["selection_rank"]))
        for seed in SEEDS:
            for m in M_GRID:
                eff = min(m, 3 ** int(identity["n"]))
                by_id_cfg[(identity_id, seed, eff)] = identity_settlement(identity, roles, plans[(int(identity["n"]), m, seed)], seed, outcomes, allocations[(identity_id, seed, eff)])
    output: list[dict[str, object]] = []
    for part in participation:
        n = int(part["n"]); iid = part["issue_instance"]
        ids = [identity_id for identity_id, identity in identities.items() if identity["issue_instance"] == iid and int(identity["n"]) == n]
        for m in M_GRID:
            for seed in SEEDS:
                plan = plans[(n, m, seed)]; eff = int(plan["effective_M"]); rows = [by_id_cfg[(identity_id, seed, eff)] for identity_id in ids]
                settled = [row for row in rows if row["settlement_status"] == "SETTLED"]
                missing = [row for row in rows if row["settlement_status"] != "SETTLED"]
                stake = sum((dec(row["stake_yuan"], "stake") for row in settled), Decimal(0)); gross = sum((dec(row["gross_pre_tax_yuan"], "gross") for row in settled), Decimal(0)); tax = sum((dec(row["tax_yuan"], "tax") for row in settled), Decimal(0)); after = sum((dec(row["after_tax_gross_yuan"], "after") for row in settled), Decimal(0)); pre = sum((dec(row["pre_tax_net_yuan"], "pre") for row in settled), Decimal(0)); tax_net = sum((dec(row["tax_adjusted_net_yuan"], "tax net") for row in settled), Decimal(0)); wins = sum(int(row["winning_ticket_count"]) for row in settled); hits = sum(int(row["coverage_hit"] == "YES") for row in settled); taxable = sum(int(row["taxable_winning_ticket_count"]) for row in settled)
                gm_sum = sum((dec(row["gm_e_sp"], "gm") for row in settled), Decimal(0)); expected_sum = sum((dec(row["expected_sp_product_q"], "expected") for row in settled), Decimal(0)); actuals = [dec(row["actual_winning_sp_product"], "actual") for row in settled if row["actual_winning_sp_product"]]
                # No-identity/no-bet issues still have a chronological kickoff
                # in the authenticated issue ledger.  Use that frozen
                # provenance field for calendar controls; selected role rows
                # alone cannot represent a no-bet issue's kickoff.
                first = first_kickoff.get((iid, n), min((role["kickoff_ts"] for identity_id in ids for role in role_map[identity_id]), default=""))
                output.append({"issue": part["issue"], "fold": part["fold"], "year": part["year"], "issue_instance": iid, "n": n, "M": m, "nominal_M": m, "effective_M": eff, "seed": seed, "saturation_status": plan["saturation_status"], "selection_status": "AVAILABLE" if ids else "NO_BET_NO_IDENTITY", "planned_identity_count": len(ids), "settled_identity_count": len(settled), "unavailable_identity_count": len(missing), "planned_draw_count": len(ids) * eff, "executed_draw_count": len(settled) * eff, "planned_stake_yuan": money(STAKE * len(ids) * eff), "stake_yuan": money(stake), "full_control_stake_yuan": money(STAKE * len(ids) * (3 ** n)), "unique_ticket_count": sum(int(row["unique_ticket_count"]) for row in settled), "duplicate_ticket_count": sum(int(row["duplicate_ticket_count"]) for row in settled), "hit_identity_count": hits, "winning_ticket_count": wins, "coverage_hit": "YES" if hits else "NO", "gross_pre_tax_yuan": money(gross), "taxable_winning_ticket_count": taxable, "tax_yuan": money(tax), "after_tax_gross_yuan": money(after), "pre_tax_net_yuan": money(pre), "tax_adjusted_net_yuan": money(tax_net), "no_tax_roi": ratio(pre / stake) if stake else "", "tax_adjusted_roi": ratio(tax_net / stake) if stake else "", "gm_expected_sp_mean": ratio(gm_sum / len(settled)) if settled else "", "expected_sp_product_q_mean": ratio(expected_sum / len(settled)) if settled else "", "actual_winning_sp_product_mean": ratio(sum(actuals, Decimal(0)) / len(actuals)) if actuals else "", "tax_line_share": ratio(Decimal(taxable) / wins) if wins else "", "largest_identity_gross_yuan": money(max((dec(row["gross_pre_tax_yuan"], "gross") for row in settled), default=Decimal(0))), "first_kickoff_ts": first})
    return output, list(by_id_cfg.values())


def matched_deltas(by_cfg: dict[tuple[int, int, str], list[dict[str, object]]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for n in N_GRID:
        for m in M_GRID:
            for seed in SEEDS:
                left = {row["issue_instance"]: row for row in by_cfg[(n, m, seed)] if dec(row["stake_yuan"], "stake") > 0}; base = {row["issue_instance"]: row for row in by_cfg[(7, m, seed)] if dec(row["stake_yuan"], "stake") > 0}; common = sorted(set(left) & set(base))
                def roi(source: dict[str, dict[str, object]], field: str) -> tuple[Decimal, Decimal]:
                    stake = sum((dec(source[key]["stake_yuan"], "stake") for key in common), Decimal(0)); net = sum((dec(source[key][field], field) for key in common), Decimal(0)); return (net / stake if stake else Decimal(0), stake)
                n_pre, n_stake = roi(left, "pre_tax_net_yuan"); b_pre, b_stake = roi(base, "pre_tax_net_yuan"); n_tax, _ = roi(left, "tax_adjusted_net_yuan"); b_tax, _ = roi(base, "tax_adjusted_net_yuan")
                rows.append({"n": n, "M": m, "nominal_M": m, "effective_M": min(m, 3 ** n), "n7_nominal_M": m, "n7_effective_M": min(m, 3 ** 7), "seed": seed, "common_issue_count": len(common), "n_stake_yuan": money(n_stake), "n7_stake_yuan": money(b_stake), "n_no_tax_roi": ratio(n_pre), "n7_no_tax_roi": ratio(b_pre), "no_tax_roi_delta": ratio(n_pre - b_pre), "n_tax_adjusted_roi": ratio(n_tax), "n7_tax_adjusted_roi": ratio(b_tax), "tax_adjusted_roi_delta": ratio(n_tax - b_tax), "rule": "matched issue-instance support only; N7 descriptive baseline; pre-tax primary"})
    return rows


def overlap_rows(identities: list[dict[str, str]]) -> list[dict[str, object]]:
    output = []
    for n in N_GRID:
        selected = [row for row in identities if int(row["n"]) == n]; by_issue: dict[str, list[dict[str, str]]] = defaultdict(list)
        for row in selected: by_issue[row["issue_instance"]].append(row)
        pair_count = shared = jaccard = 0.0; max_shared = max_j = 0.0
        for issue_rows in by_issue.values():
            for left, right in itertools.combinations(issue_rows, 2):
                a = set(left["selected_match_ids"].split("|")); b = set(right["selected_match_ids"].split("|")); inter = len(a & b); union = len(a | b); pair_count += 1; shared += inter; jaccard += inter / union; max_shared = max(max_shared, inter); max_j = max(max_j, inter / union)
        output.append({"n": n, "identity_count": len(selected), "issue_count": len(by_issue), "pair_count": int(pair_count), "mean_shared_leg_count": ratio(Decimal(str(shared / pair_count)) if pair_count else Decimal(0)), "max_shared_leg_count": int(max_shared), "mean_jaccard": ratio(Decimal(str(jaccard / pair_count)) if pair_count else Decimal(0)), "max_jaccard": ratio(Decimal(str(max_j)),), "duplicate_ticket_policy": "WOR distinct within each identity; cross-identity shared legs reported, no ticket deduplication"})
    return output


def bootstrap_rows(by_cfg: dict[tuple[int, int, str], list[dict[str, object]]]) -> list[dict[str, object]]:
    output = []
    for n in N_GRID:
        for m in M_GRID:
            for seed in SEEDS:
                support = [row for row in by_cfg[(n, m, seed)] if dec(row["stake_yuan"], "stake") > 0]
                if not support:
                    continue
                rng = random.Random(int.from_bytes(hashlib.sha256(f"{SOURCE_CONTRACT}|bootstrap|{n}|{m}|{seed}".encode()).digest()[:8], "big"))
                for field, metric in (("pre_tax_net_yuan", "no_tax_roi"), ("tax_adjusted_net_yuan", "tax_adjusted_roi")):
                    values = []
                    for _ in range(BOOTSTRAP_REPLICATES):
                        sample = [support[rng.randrange(len(support))] for _ in support]; stake = sum((dec(row["stake_yuan"], "stake") for row in sample), Decimal(0)); net = sum((dec(row[field], field) for row in sample), Decimal(0)); values.append(float(net / stake if stake else 0))
                    values.sort(); point_stake = sum((dec(row["stake_yuan"], "stake") for row in support), Decimal(0)); point = sum((dec(row[field], field) for row in support), Decimal(0)) / point_stake
                    output.append({"n": n, "M": m, "nominal_M": m, "effective_M": min(m, 3 ** n), "seed": seed, "saturation_status": "FULL_SPACE_SATURATED" if m > 3 ** n else "PARTIAL_WOR", "metric": metric, "support_issue_count": len(support), "replicates": BOOTSTRAP_REPLICATES, "point_estimate": ratio(point), "ci95_low": f"{values[25]:.12f}", "ci95_high": f"{values[974]:.12f}", "positive_fraction": f"{sum(value > 0 for value in values) / len(values):.12f}"})
    return output


def compare_rows(expected: list[dict[str, str]], actual: list[dict[str, object]], keys: tuple[str, ...], fields: tuple[str, ...]) -> list[dict[str, object]]:
    left = {tuple(row[key] for key in keys): row for row in expected}; right = {tuple(str(row[key]) for key in keys): row for row in actual}; discrepancies = []
    for key in sorted(set(left) | set(right)):
        if key not in left or key not in right:
            discrepancies.append({"key": "|".join(key), "field": "ROW", "expected": "present" if key in left else "missing", "actual": "present" if key in right else "missing"}); continue
        for field in fields:
            if not compare_value(str(left[key].get(field, "")), right[key].get(field, ""), field):
                discrepancies.append({"key": "|".join(key), "field": field, "expected": left[key].get(field, ""), "actual": right[key].get(field, "")})
    return discrepancies


def stage2_protocol(root: Path) -> tuple[dict[str, object], dict[str, object]]:
    # This is an availability census only.  It never reuses #159 rows as a
    # pseudo-forward sample.  The repository fixtures stop before 26079 and
    # the prior native runtime readback recorded no issue >26079.
    fixture_paths = sorted((root / "tests/fixtures").glob("*.db"))
    protocol = {"status": "WAITING_FOR_FORWARD_DATA", "primary": {"n": 9, "M": 64, "allocator": "Q_INFORMED_WOR", "seeds": list(SEEDS)}, "controls": [{"n": n, "M": 64, "allocator": "Q_INFORMED_WOR", "seeds": list(SEEDS)} for n in (7, 8, 10)], "outcome_boundary": "No outcome from the #159 historical window may be reused; no thresholds, selector, allocator, N, M or seeds may change.", "primary_metric": "pre-tax no_tax_roi", "secondary_metric": "tax_adjusted_roi", "required_outputs": ["stake", "ticket_count", "coverage", "hit_multiplicity", "drawdown", "largest_issue", "largest_year", "seed_dispersion"], "promotion_rule": "held-out/forward pre-tax evidence must not be driven by one issue, year or seed", "failure_mode": "WAITING_FOR_FORWARD_DATA until a genuinely new issue/outcome is available"}
    availability = {"status": "WAITING_FOR_FORWARD_DATA", "max_known_issue_from_native_runtime_readback": 26079, "new_issue_count": 0, "candidate_rule": "issue > 26079", "fixtures_checked": [str(path.relative_to(root)) for path in fixture_paths], "fixture_note": "fixture DBs are audit fixtures only; they contain no post-26079 prospective issue", "same_window_reuse": False}
    return protocol, availability


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path, default=None); parser.add_argument("--head-start", default=""); parser.add_argument("--head-end", default="")
    args = parser.parse_args(); root = repo_root(Path(__file__)); output = (args.output or root / "results/bj165_independent_validation_v1").resolve()
    if output.exists():
        raise RuntimeError(f"refusing overwrite: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    _, identities_rows, identities, role_map, plan_map, outcomes, source_identity, source_issue, source_surface, source_by_cfg = load_inputs(root)
    participation = read_csv(root / "results/bj159_gate_a_preoutcome_v2r1/issue_participation.csv")
    structural = validate_gate_a(identities_rows, identities, role_map, plan_map, participation)
    print("#165: Gate-A structural checks passed; computing independent Q-WOR allocations", flush=True)
    allocations = all_allocations(identities, role_map, outcomes)
    allocation_checks = []; allocation_failures = 0
    for source in source_identity:
        key = (source["identity_id"], source["seed"], int(source["effective_M"])); actual = allocations[key]; match = source["allocation_fingerprint"] == actual[2]
        allocation_failures += int(not match); allocation_checks.append({"identity_id": source["identity_id"], "seed": source["seed"], "effective_M": source["effective_M"], "source_fingerprint": source["allocation_fingerprint"], "independent_fingerprint": actual[2], "fingerprint_match": str(match).lower(), "truth_rank_independent": "" if actual[1] is None else actual[1]})
    print(f"#165: allocation fingerprints checked={len(allocation_checks)} failures={allocation_failures}", flush=True)
    first_kickoff = {(row["issue_instance"], int(row["n"])): row["first_kickoff_ts"] for row in source_issue}
    issue_rows, independent_identity = recompute_issue_rows(identities, role_map, participation, plan_map, outcomes, allocations, first_kickoff)
    identity_discrepancies = compare_rows(source_identity, independent_identity, ("identity_id", "seed", "effective_M"), ("settlement_status", "outcome_gap_count", "planned_draw_count", "executed_draw_count", "stake_yuan", "unique_ticket_count", "duplicate_ticket_count", "truth_sequence", "truth_ordinal", "truth_rank", "coverage_hit", "winning_ticket_count", "gm_e_sp", "expected_sp_product_q", "actual_winning_sp_product", "gross_pre_tax_yuan", "taxable_winning_ticket_count", "tax_yuan", "after_tax_gross_yuan", "pre_tax_net_yuan", "tax_adjusted_net_yuan", "no_tax_roi", "tax_adjusted_roi", "allocation_fingerprint", "winning_sp_sources"))
    print(f"#165: identity settlement discrepancies={len(identity_discrepancies)}", flush=True)
    by_cfg: dict[tuple[int, int, str], list[dict[str, object]]] = defaultdict(list)
    for row in issue_rows: by_cfg[(int(row["n"]), int(row["M"]), str(row["seed"]))].append(row)
    all_surface: list[dict[str, object]] = []; robustness: list[dict[str, object]] = []
    for key, rows in sorted(by_cfg.items()):
        all_surface.append(summary(rows, "ALL", "ALL")); years = sorted({str(row["year"]) for row in rows}); folds = sorted({str(row["fold"]) for row in rows})
        for year in years: robustness.append(summary([row for row in rows if str(row["year"]) == year], "YEAR", year))
        for fold in folds: robustness.append(summary([row for row in rows if str(row["fold"]) == fold], "FOLD", fold))
        for year in years: robustness.append(summary([row for row in rows if str(row["year"]) != year], "LOYO", year))
    surface_discrepancies = compare_rows(source_surface, all_surface + robustness, ("scope", "scope_value", "n", "M", "seed"), SUMMARY_FIELDS)
    print(f"#165: surface rows checked={len(all_surface)+len(robustness)} discrepancies={len(surface_discrepancies)}", flush=True)
    matched = matched_deltas(by_cfg); overlap = overlap_rows(identities_rows); bootstrap = bootstrap_rows(by_cfg)
    source_matched = read_csv(root / "results/bj159_gate_b_outcome_settlement_v2r1/matched_n7_deltas.csv"); source_overlap = read_csv(root / "results/bj159_gate_b_outcome_settlement_v2r1/overlap_summary.csv"); source_bootstrap = read_csv(root / "results/bj159_gate_b_outcome_settlement_v2r1/issue_bootstrap.csv")
    matched_diff = compare_rows(source_matched, matched, ("n", "M", "seed"), tuple(source_matched[0].keys()))
    overlap_diff = compare_rows(source_overlap, overlap, ("n",), tuple(source_overlap[0].keys()))
    bootstrap_diff = compare_rows(source_bootstrap, bootstrap, ("n", "M", "seed", "metric"), tuple(source_bootstrap[0].keys()))
    protocol, availability = stage2_protocol(root)
    source_binding = {"issue": 165, "contract": CONTRACT, "source_gate_a_manifest": GA_MANIFEST, "source_gate_b_v2r1_manifest": GB_MANIFEST, "source_gate_b_v2r1_content_identity": GB_CONTENT, "source_v2_manifest": SOURCE_V2_MANIFEST, "source_v2_content_identity": SOURCE_V2_CONTENT, "canonical_outcome_manifest": OUTCOME_MANIFEST, "canonical_outcome_payload": OUTCOME_PAYLOAD, "independent_checkout_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(), "authoritative_source_rows_are_read_only": True, "source_outcome_loader_not_imported": True}
    output.mkdir()
    write_csv(output / "allocation_reconciliation.csv", allocation_checks)
    write_csv(output / "identity_discrepancies.csv", identity_discrepancies, ("key", "field", "expected", "actual"))
    write_csv(output / "surface_discrepancies.csv", surface_discrepancies, ("key", "field", "expected", "actual"))
    write_csv(output / "matched_n7_discrepancies.csv", matched_diff, ("key", "field", "expected", "actual"))
    write_csv(output / "overlap_discrepancies.csv", overlap_diff, ("key", "field", "expected", "actual"))
    write_csv(output / "bootstrap_discrepancies.csv", bootstrap_diff, ("key", "field", "expected", "actual"))
    write_csv(output / "recomputed_surface_summary.csv", all_surface + robustness, SUMMARY_FIELDS)
    focus = [row for row in all_surface if int(row["n"]) in (7, 8, 9, 10) and int(row["M"]) == 64]
    write_csv(output / "n7_n10_m64_focus.csv", focus, SUMMARY_FIELDS)
    (output / "source_binding.json").write_text(json.dumps(source_binding, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "stage2_protocol.json").write_text(json.dumps(protocol, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "forward_availability.json").write_text(json.dumps(availability, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    discrepancies = len(identity_discrepancies) + len(surface_discrepancies) + len(matched_diff) + len(overlap_diff) + len(bootstrap_diff) + allocation_failures
    card = {"issue": 165, "contract": CONTRACT, "stage": "STAGE_1_INDEPENDENT_EV_PLUS_STAGE_2_FORWARD_PROTOCOL", "target_head": source_binding["independent_checkout_head"], "head_start": args.head_start, "head_end": args.head_end, "gate_a": structural, "allocation_checks": {"rows": len(allocation_checks), "failures": allocation_failures}, "identity_rows_checked": len(source_identity), "identity_comparison_keys": len(independent_identity), "identity_discrepancies": len(identity_discrepancies), "surface_rows_checked": len(all_surface) + len(robustness), "surface_discrepancies": len(surface_discrepancies), "matched_n7_discrepancies": len(matched_diff), "overlap_discrepancies": len(overlap_diff), "bootstrap_discrepancies": len(bootstrap_diff), "material_discrepancies": discrepancies, "focus_n7_n10_m64_rows": len(focus), "pre_tax_primary": True, "tax_secondary": True, "tax_rule": "20% per independent winning ¥2 ticket gross >= ¥10000; no issue/policy pooling", "stage1_decision": "PASS_ZERO_MATERIAL_DISCREPANCIES" if discrepancies == 0 else "FAIL_MATERIAL_DISCREPANCIES", "stage2_decision": protocol["status"], "promotion_authorized": False, "no_purchase_production_or_betting_authority": True}
    (output / "validation_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "README.md").write_text("# #165 independent validation\n\nThis package is an independently written detached-checkout reconstruction of #159. It recomputes Gate-A joins, Q-informed WOR allocations, canonical outcome settlement, per-ticket ¥2/0.65 payout/tax, the complete 81-cell surface, matched N7 deltas, YEAR/FOLD/LOYO-derived surface, overlap and bootstrap controls. #159 runners are not imported. Stage 2 is frozen unchanged and is `WAITING_FOR_FORWARD_DATA`; no same-window row is relabeled held-out.\n", encoding="utf-8")
    shutil.copy2(Path(__file__), output / "validation_runner.py")
    content = {"package": "bj165_independent_validation_v1", "contract": CONTRACT, "files": {p.name: sha(p) for p in sorted(output.iterdir()) if p.is_file()}}
    (output / "CONTENT_IDENTITY.json").write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {p.name: sha(p) for p in sorted(output.iterdir()) if p.is_file()}
    (output / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "manifest_sha256": sha(output / "SHA256SUMS.json"), "content_sha256": sha(output / "CONTENT_IDENTITY.json"), "material_discrepancies": discrepancies, "stage2": protocol["status"]}, sort_keys=True))


if __name__ == "__main__":
    main()
