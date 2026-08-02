#!/usr/bin/env python3
"""One-shot #151 settlement of the accepted fixed #137 candidate.

The numerical engine is copied, hash-bound #148 settlement code.  This wrapper
adapts only the immutable #151 Gate-A schema, preserving all frozen
NO_GATE/K4 identities, Q vectors, M points, seeds, and draw plans.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import gzip
import hashlib
import importlib.util
import json
import math
import os
import random
import shutil
import sqlite3
import sys
import tempfile
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path


CONTRACT = "BJ-HIST-N7-CANDIDATE-REPRO-001"
VERSION = "bj151-gate-b-v1-fixed-candidate-dense-surface"
FREEZE_MANIFEST = "3605278bd6067fc7aa279a0625f4c4cab91603d8a1490c8608381e8fca997ac6"
OUTCOME_MANIFEST = "fbbd3b53bd86f4bb0caff8f2587933cd6b0e4e7d04fb0f709bac934ec2a705cc"
OUTCOME_PAYLOAD = "13d709d253c31519734dbf0447e6961ac8a6060772975d7461741224e5251a89"
BROADER_MANIFEST = "a60389f27f0373ea03300db5edf28aebb3a0e567e47e78ade860094413756467"


def repository_root() -> Path:
    for candidate in (Path(__file__).resolve().parent, *Path(__file__).resolve().parents):
        if (candidate / ".git").exists() and (candidate / "scripts").is_dir():
            return candidate
    raise RuntimeError("repository root unavailable")


ROOT = repository_root()
FREEZE = ROOT / "results" / "bj151_gate_a_preoutcome_v1"
OUTCOME_SOURCE = ROOT / "results" / "bj95_gate_b_outcome_settlement_v2r8"
BROADER = ROOT / "results" / "bj148_gate_b_outcome_settlement_v1"
OUTPUT = ROOT / "results" / "bj151_gate_b_outcome_settlement_v1"


def engine_path() -> Path:
    embedded = Path(__file__).with_name("shared_engine.py")
    return embedded if embedded.is_file() else ROOT / "scripts" / "settle_bj148_dense_m_grid_gate_b.py"


def engine():
    spec = importlib.util.spec_from_file_location("bj151_shared_engine", engine_path())
    if not spec or not spec.loader:
        raise RuntimeError("shared settlement engine unavailable")
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    value.OUTCOME_SOURCE = OUTCOME_SOURCE
    value.OUTCOME_MANIFEST = OUTCOME_MANIFEST
    value.OUTCOME_PAYLOAD = OUTCOME_PAYLOAD
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_inputs(e) -> dict[str, str]:
    freeze = e.verified_bundle(FREEZE, FREEZE_MANIFEST)
    card = json.loads((FREEZE / "gate_a_card.json").read_text(encoding="utf-8"))
    content = json.loads((FREEZE / "CONTENT_IDENTITY.json").read_text(encoding="utf-8"))
    if card.get("contract") != CONTRACT or card.get("stage") != "GATE_A_OUTCOME_UNEXPOSED_FIXED_CANDIDATE_DENSE_M_FREEZE":
        raise RuntimeError("unexpected #151 Gate-A contract")
    if content.get("contract_version") != "bj151-gate-a-content-v1":
        raise RuntimeError("unexpected #151 Gate-A content contract")
    for name in ("candidate_identities.csv.gz", "candidate_role_vectors.csv.gz"):
        expected = content.get("gzip_payloads", {}).get(name, {}).get("canonical_decompressed_sha256")
        if expected != e.decompressed_digest(FREEZE / name)[0]:
            raise RuntimeError(f"Gate-A portable gzip digest drift: {name}")
    outcome = e.verified_bundle(OUTCOME_SOURCE, OUTCOME_MANIFEST)
    if outcome.get("canonical_outcome_join.csv") != OUTCOME_PAYLOAD:
        raise RuntimeError("canonical outcome payload drift")
    broader = e.verified_bundle(BROADER, BROADER_MANIFEST)
    if "m_grid_surface_summary.csv" not in broader:
        raise RuntimeError("#148 broader-pool surface unavailable")
    return {
        "gate_a_manifest_sha256": FREEZE_MANIFEST,
        "gate_a_content_identity_sha256": freeze["CONTENT_IDENTITY.json"],
        "gate_a_sampling_plan_sha256": freeze["sampling_plan.csv"],
        "gate_a_cohort_sha256": freeze["candidate_cohort.csv"],
        "gate_a_identity_sha256": freeze["candidate_identities.csv.gz"],
        "gate_a_role_sha256": freeze["candidate_role_vectors.csv.gz"],
        "canonical_outcome_manifest_sha256": OUTCOME_MANIFEST,
        "canonical_outcome_join_sha256": OUTCOME_PAYLOAD,
        "bj148_broader_settlement_manifest_sha256": BROADER_MANIFEST,
        "bj148_broader_surface_sha256": broader["m_grid_surface_summary.csv"],
        "shared_engine_sha256": sha256(engine_path()),
    }


def load_freeze(e):
    with (FREEZE / "candidate_cohort.csv").open(newline="", encoding="utf-8") as handle:
        raw_cohort = list(csv.DictReader(handle))
    if len(raw_cohort) != 348 or Counter(row["selection_status"] for row in raw_cohort) != {"AVAILABLE": 339, "NO_BET_SOURCE_K4_INSUFFICIENT_IDENTITIES": 9}:
        raise RuntimeError("Gate-A fixed-candidate cohort drift")
    cohort = [{**row, "common_support_status": "AVAILABLE" if row["selection_status"] == "AVAILABLE" else "NO_BET_GATE_A"} for row in raw_cohort]
    with (FREEZE / "dense_m_grid.csv").open(newline="", encoding="utf-8") as handle:
        m_grid = [int(row["M"]) for row in csv.DictReader(handle)]
    if len(m_grid) != 58 or m_grid[-1] != e.FULL_TICKETS or len(set(m_grid)) != 58:
        raise RuntimeError("Gate-A dense M grid drift")
    with (FREEZE / "sampling_plan.csv").open(newline="", encoding="utf-8") as handle:
        plans = list(csv.DictReader(handle))
    if len(plans) != 119_364 or len({row["plan_id"] for row in plans}) != len(plans):
        raise RuntimeError("Gate-A sampling-plan drift")
    plan_by_issue: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in plans:
        plan_by_issue[row["issue_instance"]].append(row)
    if any(len(rows) != 343 for rows in plan_by_issue.values()) or set(plan_by_issue) != {row["issue_instance"] for row in cohort}:
        raise RuntimeError("Gate-A per-issue plan surface drift")
    with gzip.open(FREEZE / "candidate_identities.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        identity_rows = list(csv.DictReader(handle))
    with gzip.open(FREEZE / "candidate_role_vectors.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        role_rows = list(csv.DictReader(handle))
    if len(identity_rows) != 1356 or len(role_rows) != 9492:
        raise RuntimeError("Gate-A fixed-candidate identity/role drift")
    role_map: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in role_rows:
        role_map[(row["issue_instance"], row["portfolio_id"])].append(row)
    outcomes = e.load_outcomes()
    by_issue: dict[str, list[object]] = defaultdict(list)
    for row in identity_rows:
        key = row["issue_instance"], row["portfolio_id"]
        roles = tuple(sorted(role_map.get(key, []), key=lambda value: int(value["selection_rank"])))
        if len(roles) != e.N or [int(value["selection_rank"]) for value in roles] != list(range(1, e.N + 1)):
            raise RuntimeError(f"invalid frozen role geometry: {key}")
        if "|".join(value["match_id"] for value in roles) != row["selected_match_ids"]:
            raise RuntimeError(f"identity/role mismatch: {key}")
        truth, product, gaps = 0, Decimal(1), 0
        for role in roles:
            outcome = outcomes.get(role["match_id"])
            if outcome is None:
                gaps += 1
                continue
            truth = truth * 3 + e.CODES.index(outcome["result_code"])
            product *= e.decimal(outcome["winning_sp"], "winning SP")
        by_issue[row["issue_instance"]].append(e.Identity(row["portfolio_id"], row["issue_instance"], roles, None if gaps else truth, None if gaps else e.UNIT_STAKE * e.PAYOUT_FACTOR * product, gaps))
    available = {row["issue_instance"] for row in cohort if row["common_support_status"] == "AVAILABLE"}
    if set(by_issue) != available or any(len(rows) != 4 for rows in by_issue.values()):
        raise RuntimeError("fixed candidate membership no longer matches K4 freeze")
    return cohort, by_issue, m_grid, plan_by_issue


def candidate_add_identity(e, acc, identity, m_values, seeds) -> None:
    if identity.truth_index is None or identity.payout_per_ticket is None:
        raise RuntimeError("available identity lacks trusted outcome")
    weights = e.q_weights(identity)
    per_ticket_gross = identity.payout_per_ticket.quantize(e.MONEY_QUANTUM)
    per_ticket_tax = e.ticket_tax(per_ticket_gross).quantize(e.MONEY_QUANTUM)
    signature = "|".join(role["match_id"] for role in identity.roles)
    for seed in seeds:
        wr = historical_wr_profile(weights, identity.truth_index, int(seed), signature, m_values)
        rank = historical_wor_rank(weights, identity.truth_index, int(seed), signature)
        for m_value in m_values:
            for role, mechanism, values in (("PRIMARY_WR_NATURAL_BASELINE", "Q_INFORMED_WR_DUPLICATE_STAKE", wr[m_value]), ("SENSITIVITY_WOR_FIXED_CANDIDATE", "Q_INFORMED_WOR_DISTINCT", (int(rank <= m_value), m_value, 0, 0))):
                hit, unique, duplicates, groups = values
                entry = acc[(role, mechanism, m_value, seed)]
                gross, tax = per_ticket_gross * hit, per_ticket_tax * hit
                entry["unique"] += unique
                entry["duplicates"] += duplicates
                entry["duplicate_groups"] += groups
                entry["hits"] += hit
                entry["taxable"] += hit if per_ticket_tax else 0
                entry["gross"] += gross
                entry["tax"] += tax
                entry["top_identity_gross"] = max(entry["top_identity_gross"], gross)
                if hit:
                    entry["ticket_rows"].append((identity.portfolio_id, per_ticket_gross, hit, per_ticket_tax, tax))
    full = acc[("FULL_ECONOMIC_CONTROL", "FULL_ENUMERATED", e.FULL_TICKETS, "NA")]
    full["unique"] += e.FULL_TICKETS
    full["hits"] += 1
    full["taxable"] += int(bool(per_ticket_tax))
    full["gross"] += per_ticket_gross
    full["tax"] += per_ticket_tax
    full["top_identity_gross"] = max(full["top_identity_gross"], per_ticket_gross)
    full["ticket_rows"].append((identity.portfolio_id, per_ticket_gross, 1, per_ticket_tax, per_ticket_tax))


def stable_uniform(*parts: object) -> float:
    """The accepted #137 Gate-B hash sampler, preserved exactly."""
    token = "|".join(str(part) for part in parts).encode("utf-8")
    value = int.from_bytes(hashlib.sha256(token).digest()[:8], "big")
    return (value + 0.5) / (2 ** 64)


def historical_wr_profile(weights: list[float], truth: int, seed: int, signature: str, m_values: list[int]) -> dict[int, tuple[int, int, int, int]]:
    cumulative, total = [], 0.0
    for weight in weights:
        total += weight
        cumulative.append(total)
    if abs(total - 1.0) > 1e-8:
        raise RuntimeError("#137 WR cumulative weight drift")
    thresholds, counts, output = set(m_values), defaultdict(int), {}
    hits = unique = groups = 0
    for draw in range(1, max(m_values) + 1):
        ticket = bisect.bisect_left(cumulative, stable_uniform("bj137", "WR", seed, signature, draw - 1))
        if ticket == len(cumulative):
            ticket -= 1
        prior = counts[ticket]
        counts[ticket] = prior + 1
        unique += prior == 0
        groups += prior == 1
        hits += ticket == truth
        if draw in thresholds:
            output[draw] = (hits, unique, draw - unique, groups)
    if set(output) != thresholds:
        raise RuntimeError("#137 WR profile missed frozen M point")
    return output


def historical_wor_rank(weights: list[float], truth: int, seed: int, signature: str) -> int:
    target = -math.log(max(stable_uniform("bj137", "WOR", seed, signature, truth), 1e-18)) / weights[truth]
    return 1 + sum(-math.log(max(stable_uniform("bj137", "WOR", seed, signature, ordinal), 1e-18)) / weight < target for ordinal, weight in enumerate(weights) if ordinal != truth)


def broader_comparison(e, summaries: list[dict[str, object]]) -> tuple[tuple[str, ...], list[dict[str, object]]]:
    fields = ("sampling_role", "ticket_mechanism", "M", "candidate_seed_count", "candidate_settled_issue_count_mean", "candidate_no_tax_roi_mean", "candidate_no_tax_roi_min", "candidate_tax_adjusted_roi_mean", "broader_sampling_role", "broader_seed_count", "broader_settled_issue_count_mean", "broader_no_tax_roi_mean", "broader_no_tax_roi_min", "broader_tax_adjusted_roi_mean", "comparison_rule")
    with (BROADER / "m_grid_surface_summary.csv").open(newline="", encoding="utf-8") as handle:
        broader_rows = list(csv.DictReader(handle))
    candidate_rows = [row for row in summaries if row["scope"] == "ALL"]
    grouped: dict[tuple[str, str, str], list[dict[str, object]]] = defaultdict(list)
    wider: dict[tuple[str, str, str], list[dict[str, str]]] = defaultdict(list)
    for row in candidate_rows:
        grouped[(str(row["sampling_role"]), str(row["ticket_mechanism"]), str(row["M"]))].append(row)
    for row in broader_rows:
        if row["scope"] == "ALL":
            wider[(row["sampling_role"], row["ticket_mechanism"], row["M"])].append(row)
    output = []
    for key in sorted(grouped, key=lambda value: (value[0], int(value[2]), value[1])):
        candidate = grouped[key]
        broader_role = "SENSITIVITY_WOR_DISTINCT" if key[0] == "SENSITIVITY_WOR_FIXED_CANDIDATE" else key[0]
        broad = wider.get((broader_role, key[1], key[2]), [])
        def mean(rows, field):
            return sum(Decimal(str(row[field])) for row in rows) / len(rows) if rows else None
        def minimum(rows, field):
            return min((Decimal(str(row[field])) for row in rows), default=None)
        output.append({"sampling_role": key[0], "ticket_mechanism": key[1], "M": key[2], "candidate_seed_count": len(candidate), "candidate_settled_issue_count_mean": mean(candidate, "settled_issue_count"), "candidate_no_tax_roi_mean": mean(candidate, "no_tax_roi"), "candidate_no_tax_roi_min": minimum(candidate, "no_tax_roi"), "candidate_tax_adjusted_roi_mean": mean(candidate, "tax_adjusted_roi"), "broader_sampling_role": broader_role, "broader_seed_count": len(broad), "broader_settled_issue_count_mean": mean(broad, "settled_issue_count"), "broader_no_tax_roi_mean": mean(broad, "no_tax_roi"), "broader_no_tax_roi_min": minimum(broad, "no_tax_roi"), "broader_tax_adjusted_roi_mean": mean(broad, "tax_adjusted_roi"), "comparison_rule": "descriptive side-by-side only: fixed #137 K4 and #148 broader pool have different frozen identities, seeds and outcome-completeness supports; no causal or matched delta is asserted"})
    return fields, output


def decision(summaries: list[dict[str, object]]) -> dict[str, object]:
    reference = [row for row in summaries if row["scope"] == "ALL" and row["sampling_role"] == "SENSITIVITY_WOR_FIXED_CANDIDATE" and int(row["M"]) == 64]
    if len(reference) != 3:
        raise RuntimeError("missing fixed #137 reference point")
    return {"decision": "FIXED_CANDIDATE_REPRODUCTION_ONLY", "promotion_authorized": False, "historical_reference": "#137 NO_GATE/K4/Q_INFORMED_WOR_DISTINCT/M64", "reference_no_tax_roi_by_seed": {str(row["seed"]): str(row["no_tax_roi"]) for row in reference}, "rule": "This is a fixed-candidate historical reproduction, not an independent validation or a new parameter search. Pre-tax ROI is primary and tax is secondary. Any apparent positive needs a separate strict independent EV; no purchase, production, betting or promotion is authorized."}


def database_rows(connection: sqlite3.Connection, key: tuple[str, str, int, str]) -> list[dict[str, str]]:
    cursor = connection.execute("SELECT payload FROM issue_rows WHERE role=? AND mechanism=? AND m_value=? AND seed=? ORDER BY year_num, issue_num", key)
    return [json.loads(row[0]) for row in cursor]


def streaming_summaries(e, connection: sqlite3.Connection) -> tuple[list[dict[str, object]], list[tuple[str, str, int, str]]]:
    keys = [tuple(row) for row in connection.execute("SELECT DISTINCT role, mechanism, m_value, seed FROM issue_rows ORDER BY role, m_value, seed")]
    if len(keys) != 343:
        raise RuntimeError("streamed configuration surface drift")
    summaries: list[dict[str, object]] = []
    for key in keys:
        values = database_rows(connection, key)
        if len(values) != 348:
            raise RuntimeError(f"streamed issue denominator drift: {key}")
        for scope, scope_value, scoped in e.grouped_scopes(values):
            summaries.append(e.summary(scope, scope_value, scoped))
    summaries.sort(key=lambda row: (str(row["sampling_role"]), int(row["M"]), str(row["seed"]), str(row["scope"]), str(row["scope_value"])))
    return summaries, keys


def streaming_bootstrap(e, connection: sqlite3.Connection, keys: list[tuple[str, str, int, str]]) -> list[dict[str, object]]:
    full = database_rows(connection, ("FULL_ECONOMIC_CONTROL", "FULL_ENUMERATED", e.FULL_TICKETS, "NA"))
    output: list[dict[str, object]] = []
    for key in keys:
        role, mechanism, m_value, seed = key
        if role != "PRIMARY_WR_NATURAL_BASELINE":
            continue
        values = database_rows(connection, key)
        if [row["issue_instance"] for row in values] != [row["issue_instance"] for row in full]:
            raise RuntimeError("WR/FULL streamed bootstrap support drift")
        n = len(values)
        for metric in ("pre_tax_net_yuan", "tax_adjusted_net_yuan"):
            point = sum(float(row[metric]) for row in values) / sum(float(row["planned_stake_yuan"]) for row in values) - sum(float(row[metric]) for row in full) / sum(float(row["planned_stake_yuan"]) for row in full)
            rng = random.Random(e.seed_value(CONTRACT, "ISSUE_BOOTSTRAP", role, mechanism, m_value, seed, metric))
            samples, positive, negative = [], 0, 0
            for _ in range(e.BOOTSTRAP_REPLICATES):
                sample_net = sample_stake = full_net = full_stake = 0.0
                for _draw in range(n):
                    index = rng.randrange(n)
                    sample_net += float(values[index][metric])
                    sample_stake += float(values[index]["planned_stake_yuan"])
                    full_net += float(full[index][metric])
                    full_stake += float(full[index]["planned_stake_yuan"])
                delta = sample_net / sample_stake - full_net / full_stake
                samples.append(delta)
                positive += delta >= 0.0
                negative += delta <= 0.0
            samples.sort()
            output.append({"sampling_role": role, "ticket_mechanism": mechanism, "seed": seed, "M": m_value, "baseline_role": "FULL_ECONOMIC_CONTROL", "baseline_M": e.FULL_TICKETS, "support_issue_count": n, "replicates": e.BOOTSTRAP_REPLICATES, "metric": "no_tax_roi_delta" if metric == "pre_tax_net_yuan" else "tax_adjusted_roi_delta", "point_estimate": point, "ci95_low": samples[math.floor(0.025 * e.BOOTSTRAP_REPLICATES)], "ci95_high": samples[math.ceil(0.975 * e.BOOTSTRAP_REPLICATES) - 1], "one_sided_positive_p": (1 + negative) / (1 + e.BOOTSTRAP_REPLICATES), "two_sided_sign_p": min(1.0, 2 * min((1 + positive) / (1 + e.BOOTSTRAP_REPLICATES), (1 + negative) / (1 + e.BOOTSTRAP_REPLICATES)))})
    if len(output) != 342:
        raise RuntimeError("streamed bootstrap surface drift")
    return output


def build(output: Path) -> dict[str, object]:
    if output.exists():
        raise RuntimeError(f"refusing immutable overwrite: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".bj151_gate_b_", dir=output.parent))
    try:
        e = engine()
        provenance = validate_inputs(e)
        cohort, identities_by_issue, m_grid, plan_by_issue = load_freeze(e)
        e.add_identity = lambda acc, identity, m_values, seeds: candidate_add_identity(e, acc, identity, m_values, seeds)
        audits = defaultdict(e.TicketAudit)
        status_counts: Counter[str] = Counter()
        database_path = stage / "issue_settlement_index.sqlite"
        connection = sqlite3.connect(database_path)
        connection.execute("PRAGMA journal_mode=OFF")
        connection.execute("PRAGMA synchronous=OFF")
        connection.execute("CREATE TABLE issue_rows (role TEXT NOT NULL, mechanism TEXT NOT NULL, m_value INTEGER NOT NULL, seed TEXT NOT NULL, year_num INTEGER NOT NULL, issue_num INTEGER NOT NULL, payload TEXT NOT NULL)")
        connection.execute("CREATE INDEX issue_rows_config ON issue_rows (role, mechanism, m_value, seed, year_num, issue_num)")
        handles = e.gzip_writer(stage / "winning_ticket_tax_ledger.csv.gz", e.TICKET_FIELDS)
        issue_handles = e.gzip_writer(stage / "issue_m_grid_settlement.csv.gz", e.ISSUE_FIELDS)
        try:
            ticket_writer, issue_writer = handles[-1], issue_handles[-1]
            for sample in cohort:
                issue_rows = e.settle_issue(sample, plan_by_issue[sample["issue_instance"]], identities_by_issue.get(sample["issue_instance"], []), m_grid, audits, ticket_writer)
                if len(issue_rows) != 343:
                    raise RuntimeError("streamed issue surface drift")
                for row in issue_rows:
                    serialized = e.serializable(row)
                    issue_writer.writerow(serialized)
                    status_counts[str(row["settlement_status"])] += 1
                    connection.execute("INSERT INTO issue_rows VALUES (?, ?, ?, ?, ?, ?, ?)", (str(row["sampling_role"]), str(row["ticket_mechanism"]), int(row["M"]), str(row["seed"]), int(row["year"]), int(row["issue"]), json.dumps(serialized, sort_keys=True, separators=(",", ":"))))
        finally:
            e.close_gzip(handles)
            e.close_gzip(issue_handles)
        connection.commit()
        row_count = connection.execute("SELECT COUNT(*) FROM issue_rows").fetchone()[0]
        if row_count != 119_364:
            raise RuntimeError("Gate-B issue-settlement denominator drift")
        summaries, keys = streaming_summaries(e, connection)
        e.write_csv(stage / "m_grid_surface_summary.csv", e.SUMMARY_FIELDS, (e.serializable(row) for row in summaries))
        deltas = e.full_deltas(summaries)
        e.write_csv(stage / "full_control_deltas.csv", e.DELTA_FIELDS, (e.serializable(row) for row in deltas))
        bootstrap = streaming_bootstrap(e, connection, keys)
        e.write_csv(stage / "issue_bootstrap_full_deltas.csv", e.BOOTSTRAP_FIELDS, (e.serializable(row) for row in bootstrap))
        fields, comparison = broader_comparison(e, summaries)
        e.write_csv(stage / "candidate_vs_broader_pool_m_curve.csv", fields, (e.serializable(row) for row in comparison))
        all_summary = {(str(row["sampling_role"]), str(row["ticket_mechanism"]), int(row["M"]), str(row["seed"])): row for row in summaries if row["scope"] == "ALL"}
        reconciliation = []
        for key, audit in sorted(audits.items()):
            issue_tax = Decimal(all_summary[key]["tax_yuan"])
            difference = audit.tax - issue_tax
            if abs(difference) > e.MONEY_QUANTUM:
                raise RuntimeError(f"per-ticket tax reconciliation drift: {key}: {difference}")
            reconciliation.append({"sampling_role": key[0], "ticket_mechanism": key[1], "seed": key[3], "M": key[2], "ticket_ledger_hit_ticket_count": audit.hits, "ticket_ledger_taxable_ticket_count": audit.taxable, "ticket_ledger_tax_yuan": audit.tax, "issue_ledger_tax_yuan": issue_tax, "difference_yuan": difference, "tax_rule": "20pct_if_each_ticket_gross_gte_10000_no_aggregate_pooling"})
        e.write_csv(stage / "ticket_tax_reconciliation.csv", e.TAX_RECON_FIELDS, (e.serializable(row) for row in reconciliation))
        final = decision(summaries)
        (stage / "decision.json").write_text(json.dumps(final, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        denominator = 343
        settled, unavailable, no_bet = (status_counts["SETTLED"] // denominator, status_counts["UNAVAILABLE_CANONICAL_OUTCOME"] // denominator, status_counts["NO_BET_GATE_A"] // denominator)
        if settled + unavailable + no_bet != 348:
            raise RuntimeError("outcome completeness denominator drift")
        e.write_csv(stage / "source_census.csv", e.SOURCE_FIELDS, [
            {"source": "bj151_gate_a_preoutcome_v1", "role": "accepted immutable fixed #137 NO_GATE/K4 candidate, Q vectors and dense-M plans", "identity": "SHA256SUMS.json", "sha256": FREEZE_MANIFEST, "rows": row_count, "join_status": "all frozen issue/arm/M/seed rows retained; no candidate, vector, M, seed, stake or sampler rule recomputed"},
            {"source": "bj95_gate_b_outcome_settlement_v2r8", "role": "canonical trusted final-SP truth only", "identity": "canonical_outcome_join.csv", "sha256": OUTCOME_PAYLOAD, "rows": 46802, "join_status": "complete issue settlement only; no pre-outcome selection input changed"},
            {"source": "bj148_gate_b_outcome_settlement_v1", "role": "accepted broader-pool descriptive M-curve comparator", "identity": "SHA256SUMS.json", "sha256": BROADER_MANIFEST, "rows": len(comparison), "join_status": "side-by-side only; not used to alter #151 candidate or derive a matched causal delta"},
        ])
        card = {"issue": 151, "contract": CONTRACT, "runner_version": VERSION, "stage": "GATE_B_ONE_SHOT_FIXED_CANDIDATE_DENSE_M_SETTLEMENT", "provenance": provenance, "input_boundary": "Reads only accepted #151 Gate-A fixed candidate/plans, canonical final-SP outcomes, and accepted #148 settled aggregate curve for descriptive side-by-side reporting. No candidate identity, Q vector, M, seed, stake, sampler or selection rule is recomputed. An issue missing any canonical role outcome remains unavailable at zero executed stake; no partial or substitute settlement is used.", "streaming": "Issue rows are written once. A stage-local SQLite index provides bounded-memory summaries and bootstrap, then is omitted after its published CSV/gzip controls are materialized; no /tmp path is used.", "sampling": "WR is primary and retains each independent duplicate draw as its own ¥2 ticket; WOR is the fixed #137-candidate sensitivity; FULL is exact enumeration.", "tax": "Tax is secondary and assessed per individual winning ticket only: 20% iff that ticket gross is at least ¥10,000. No issue/policy/identity aggregation can create tax.", "metrics": "Pre-tax ROI primary; outputs include candidate, same-K4 FULL and candidate-minus-FULL, dense M surface, seed/YEAR/FOLD/LOYO/bootstrap, concentration, largest issue, stake distribution, duplicate/coverage and #148 side-by-side curve.", "decision": final, "outcome_completeness": {"frozen_complete_issue_rows": 348, "frozen_available_issue_rows": 339, "settled_complete_issue_rows": settled, "unavailable_canonical_outcome_issue_rows": unavailable, "source_no_bet_issue_rows": no_bet, "rule": "Complete issue settlement only; unavailable rows have zero executed stake and remain in every M/seed/arm denominator."}, "denominator": {"issue_settlement_rows": row_count, "surface_summary_rows": len(summaries), "full_delta_rows": len(deltas), "primary_wr_bootstrap_rows": len(bootstrap), "ticket_tax_reconciliation_rows": len(reconciliation), "broader_pool_comparison_rows": len(comparison)}, "scope": "historical paper research only; no purchase, production, betting, or promotion authority."}
        (stage / "settlement_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        shutil.copy2(__file__, stage / "settlement_runner.py")
        shutil.copy2(engine_path(), stage / "shared_engine.py")
        connection.close()
        database_path.unlink()
        (stage / "README.md").write_text("# #151 Gate B — fixed #137 candidate dense-M settlement\n\nOne-shot settlement of the accepted fixed candidate. WR is primary, WOR is the historical candidate sensitivity, and FULL is exact. Tax is per winning ticket. `candidate_vs_broader_pool_m_curve.csv` is descriptive only, not a matched effect. Replay with `python3 settlement_runner.py --output <new-dir>`; staging is beside the output, never in `/tmp`.\n", encoding="utf-8")
        compressed = ("issue_m_grid_settlement.csv.gz", "winning_ticket_tax_ledger.csv.gz")
        content = {"contract_version": "bj151-gate-b-portable-content-v1", "gzip_payloads": {name: {"canonical_decompressed_sha256": e.decompressed_digest(stage / name)[0], "canonical_decompressed_bytes": e.decompressed_digest(stage / name)[1]} for name in compressed}, "non_compressed_controls": {item.name: sha256(item) for item in sorted(stage.iterdir()) if item.is_file() and item.name not in compressed}}
        (stage / "CONTENT_IDENTITY.json").write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest = {item.name: sha256(item) for item in sorted(stage.iterdir()) if item.is_file()}
        (stage / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(stage, output)
        return {"manifest_sha256": sha256(output / "SHA256SUMS.json"), "content_identity_sha256": sha256(output / "CONTENT_IDENTITY.json"), "issue_rows": row_count, "summary_rows": len(summaries), "delta_rows": len(deltas), "bootstrap_rows": len(bootstrap), "comparison_rows": len(comparison), "decision": final}
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
