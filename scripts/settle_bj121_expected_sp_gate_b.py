#!/usr/bin/env python3
"""One-shot canonical Gate-B settlement for #121's accepted v3 freeze.

The selector is deliberately absent from this program: it reads the immutable
Gate-A frontier and frozen role assignments verbatim, joins one authenticated
final-SP truth payload, applies the 0.65 payout factor once per covered
portfolio, and taxes each counterfactual policy at native issue level.
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
import shutil
import sqlite3
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path

getcontext().prec = 80

CONTRACT = "BJ-HIST-EXPECTED-SP-LOWP-001"
GATE_A_MANIFEST = "acef123c062c4deafd637941ea4ebe5cb165078dfdf0bd1998cc2b6e00446eee"
GATE_A_CONTENT = "9dd4eaeefd9aa76ec976108469bfdd4ae230bc6129c7c4574191d8bf9e9f1a76"
OUTCOME_MANIFEST = "fbbd3b53bd86f4bb0caff8f2587933cd6b0e4e7d04fb0f709bac934ec2a705cc"
OUTCOME_PAYLOAD = "13d709d253c31519734dbf0447e6961ac8a6060772975d7461741224e5251a89"
FACTOR = Decimal("0.65")
UNIT_STAKE = Decimal("2")
TAX_RATE = Decimal("0.20")
TAX_THRESHOLD = Decimal("10000")
MONEY_Q = Decimal("0.000001")

ROOT = Path(__file__).resolve().parents[1]
FREEZE = ROOT / "results" / "bj121_gate_a_preoutcome_v3"
CANONICAL = ROOT / "results" / "bj95_gate_b_outcome_settlement_v2r8"
OUT = ROOT / "results" / "bj121_gate_b_outcome_settlement_v1"

FRONTIER_FIELDS = (
    "issue", "fold", "year", "pool_id", "segment_index", "pool_disposition",
    "eligible_match_count", "pool_match_count", "first_kickoff_ts", "last_kickoff_ts",
    "window_hours", "terminal_remainder", "variant_id", "arm", "candidate_match_count",
    "selected_n", "selected_match_ids", "role_codes", "full_legs", "double_legs",
    "single_legs", "gm_e_sp", "expected_portfolio_mass", "formula_k", "stake_yuan",
    "g_be_pre_tax", "disposition", "reason", "descriptor_sha256",
)
ASSIGNMENT_FIELDS = (
    "variant_id", "arm", "issue", "fold", "year", "pool_id", "match_id",
    "match_idx", "selection_rank", "role", "allowed_codes", "omitted_codes", "p3",
    "p1", "p0", "p_min", "p_max", "argmin_code", "argmax_code", "e_sp", "q3",
    "q1", "q0",
)
OUTCOME_FIELDS = (
    "match_id", "result_code", "winning_sp", "winning_sp_source", "settlement_quality",
    "has_trusted_settlement",
)
SETTLEMENT_FIELDS = (
    "issue", "fold", "year", "pool_id", "segment_index", "first_kickoff_ts", "variant_id",
    "arm", "gate_a_disposition", "settlement_status", "candidate_match_count", "selected_n",
    "outcome_gap_count", "formula_k", "active_k", "stake_yuan", "full_legs", "double_legs",
    "single_legs", "expected_portfolio_mass", "coverage_hit", "omitted_outcome_count",
    "truth_sequence", "final_winning_sp_product", "gross_pre_tax_yuan", "tax_bucket_gross_yuan",
    "tax_yuan", "after_tax_gross_yuan", "tax_adjusted_net_yuan", "winning_sp_sources",
    "descriptor_sha256",
)
SUMMARY_FIELDS = (
    "scope", "scope_value", "variant_id", "arm", "frontier_rows", "candidate_matches",
    "gate_a_available", "settled", "outcome_unavailable", "no_bet_gate_a", "total_k",
    "stake_yuan", "coverage_hits", "coverage_hit_rate", "mean_expected_coverage",
    "gross_pre_tax_yuan", "tax_yuan", "after_tax_gross_yuan", "tax_adjusted_net_yuan",
    "tax_adjusted_roi", "max_drawdown_yuan", "longest_losing_streak", "best_payout_pool_id",
    "best_payout_gross_yuan", "ex_best_payout_net_yuan", "ex_best_payout_roi", "best_net_issue",
    "ex_best_issue_net_yuan", "ex_best_issue_roi", "positive_net_top_issue_share",
    "coverage_miss_pool_count", "top_failure_issue", "top_failure_issue_share", "control_arm", "control_gross_pre_tax_yuan",
    "gross_retention_vs_control", "net_vs_control_yuan",
)
CONCENTRATION_FIELDS = (
    "variant_id", "arm", "settled", "coverage_miss_pool_count", "best_payout_pool_id",
    "best_payout_gross_yuan", "best_net_issue", "positive_net_top_issue_share",
    "top_failure_issue", "top_failure_issue_share",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def verified_manifest(directory: Path, expected: str) -> dict[str, str]:
    manifest_path = directory / "SHA256SUMS.json"
    if sha256(manifest_path) != expected:
        raise RuntimeError(f"unaccepted manifest: {directory}")
    declared = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = {item.name: sha256(item) for item in directory.iterdir()
              if item.is_file() and item.name != "SHA256SUMS.json"}
    if not isinstance(declared, dict) or declared != actual:
        raise RuntimeError(f"manifest coverage drift: {directory}")
    return declared


def decimal(value: object, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise RuntimeError(f"invalid decimal {label}: {value!r}") from error
    if not result.is_finite():
        raise RuntimeError(f"non-finite decimal {label}: {value!r}")
    return result


def money(value: Decimal) -> str:
    return format(value.quantize(MONEY_Q), "f")


def ratio(value: Decimal | None) -> str:
    return "" if value is None else format(value, ".12f")


def gzip_reader(path: Path, fields: tuple[str, ...]):
    handle = gzip.open(path, "rt", newline="", encoding="utf-8")
    reader = csv.DictReader(handle)
    if tuple(reader.fieldnames or ()) != fields:
        handle.close()
        raise RuntimeError(f"schema drift: {path}")
    return handle, reader


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def validate_inputs() -> dict[str, str]:
    gate_a = verified_manifest(FREEZE, GATE_A_MANIFEST)
    if gate_a.get("CONTENT_IDENTITY.json") != GATE_A_CONTENT:
        raise RuntimeError("Gate-A content identity drift")
    card = json.loads((FREEZE / "gate_a_card.json").read_text(encoding="utf-8"))
    if card.get("contract") != CONTRACT or card.get("stage") != "GATE_A_OUTCOME_UNEXPOSED_FREEZE":
        raise RuntimeError("unexpected Gate-A contract")
    canonical = verified_manifest(CANONICAL, OUTCOME_MANIFEST)
    if canonical.get("canonical_outcome_join.csv") != OUTCOME_PAYLOAD:
        raise RuntimeError("canonical outcome payload drift")
    return {
        "gate_a_manifest_sha256": GATE_A_MANIFEST,
        "gate_a_content_identity_sha256": GATE_A_CONTENT,
        "canonical_outcome_manifest_sha256": OUTCOME_MANIFEST,
        "canonical_outcome_payload_sha256": OUTCOME_PAYLOAD,
    }


def load_outcomes() -> dict[str, dict[str, str]]:
    with (CANONICAL / "canonical_outcome_join.csv").open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != OUTCOME_FIELDS:
            raise RuntimeError("canonical outcome schema drift")
        rows = list(reader)
    outcomes: dict[str, dict[str, str]] = {}
    for row in rows:
        if (row["match_id"] in outcomes or row["result_code"] not in {"3", "1", "0"}
                or decimal(row["winning_sp"], "winning_sp") <= 0
                or row["settlement_quality"] != "trusted" or row["has_trusted_settlement"] != "1"):
            raise RuntimeError(f"untrusted canonical outcome: {row['match_id']}")
        outcomes[row["match_id"]] = row
    return outcomes


def assignment_key(row: dict[str, str]) -> tuple[str, str, str]:
    return row["variant_id"], row["arm"], row["pool_id"]


class AssignmentStream:
    """Read Gate-A assignment groups in their frozen write order without an OOM join."""

    def __init__(self) -> None:
        self.handle, self.reader = gzip_reader(FREEZE / "candidate_assignments.csv.gz", ASSIGNMENT_FIELDS)
        self.pending = next(self.reader, None)
        self.count = 0

    def group(self, key: tuple[str, str, str], selected_n: int) -> list[dict[str, str]]:
        # Gate A iterates variant -> pool -> arm, which is not lexical arm
        # order.  ``selected_n`` supplies the exact cardinality assertion
        # without inventing an alternative order in Gate B.
        if selected_n == 0:
            if self.pending is not None and assignment_key(self.pending) == key:
                raise RuntimeError("unselected frontier unexpectedly has frozen roles")
            return []
        if self.pending is None or assignment_key(self.pending) != key:
            raise RuntimeError("available frontier is missing its frozen role group")
        rows: list[dict[str, str]] = []
        while self.pending is not None and assignment_key(self.pending) == key:
            rows.append(self.pending)
            self.count += 1
            self.pending = next(self.reader, None)
        return rows

    def close(self) -> None:
        if self.pending is not None:
            raise RuntimeError("unconsumed frozen assignments")
        self.handle.close()


def geometry(frontier: dict[str, str], roles: list[dict[str, str]], outcomes: dict[str, dict[str, str]]) -> dict[str, object]:
    selected_n = int(frontier["selected_n"])
    formula_k = int(frontier["formula_k"])
    frozen_stake = decimal(frontier["stake_yuan"], "frozen stake")
    if frontier["disposition"] != "AVAILABLE":
        if selected_n or formula_k or frozen_stake or roles:
            raise RuntimeError("Gate-A no-bet geometry drift")
        return {"status": "NO_BET_GATE_A", "active_k": 0, "stake": Decimal(0), "hit": "NO",
                "omitted": 0, "truth": "", "product": Decimal(0), "gross": Decimal(0),
                "gap_count": 0, "sources": ""}
    if len(roles) != selected_n or selected_n not in {4, 7}:
        raise RuntimeError("available frontier lacks exact frozen roles")
    roles.sort(key=lambda row: int(row["selection_rank"]))
    if [row["selection_rank"] for row in roles] != [str(i) for i in range(1, selected_n + 1)]:
        raise RuntimeError("frozen role ranks drift")
    expected_k = 1
    for role in roles:
        allowed = role["allowed_codes"]
        if not allowed or any(code not in "310" for code in allowed):
            raise RuntimeError("invalid frozen allowed codes")
        expected_k *= len(allowed)
    if expected_k != formula_k or frozen_stake != UNIT_STAKE * formula_k:
        raise RuntimeError("frozen K/stake drift")
    missing = [role for role in roles if role["match_id"] not in outcomes]
    if missing:
        return {"status": "UNAVAILABLE_CANONICAL_OUTCOME", "active_k": 0, "stake": Decimal(0), "hit": "NO",
                "omitted": 0, "truth": "", "product": Decimal(0), "gross": Decimal(0),
                "gap_count": len(missing), "sources": ""}
    product = Decimal(1)
    truth: list[str] = []
    sources: set[str] = set()
    hit = True
    omitted = 0
    for role in roles:
        outcome = outcomes[role["match_id"]]
        code = outcome["result_code"]
        truth.append(code)
        product *= decimal(outcome["winning_sp"], "winning_sp")
        sources.add(outcome["winning_sp_source"])
        hit = hit and code in role["allowed_codes"]
        omitted += int(code in role["omitted_codes"])
    gross = UNIT_STAKE * FACTOR * product if hit else Decimal(0)
    return {"status": "SETTLED", "active_k": formula_k, "stake": frozen_stake,
            "hit": "YES" if hit else "NO", "omitted": omitted, "truth": "".join(truth),
            "product": product, "gross": gross, "gap_count": 0, "sources": ";".join(sorted(sources))}


def tax_key(row: dict[str, str]) -> tuple[str, str, str]:
    return row["issue"], row["variant_id"], row["arm"]


def control_for(arm: str) -> str:
    if arm.endswith("_N4"):
        return "UNFILTERED_FULL_N4"
    if arm.endswith("_N7"):
        return "UNFILTERED_FULL_N7"
    if arm.endswith("_DYNAMIC_4_7"):
        return "UNFILTERED_FULL_DYNAMIC_4_7"
    return ""


@dataclass
class Metric:
    variant: str
    arm: str
    scope: str
    scope_value: str
    rows: int = 0
    candidates: int = 0
    available: int = 0
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
    expected_n: int = 0
    payout_rows: list[tuple[str, str, Decimal, Decimal, Decimal, str]] = field(default_factory=list)
    issue_net: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    issue_stake: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    failures: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def add(self, row: sqlite3.Row) -> None:
        self.rows += 1
        self.candidates += int(row["candidate_match_count"])
        if row["gate_a_disposition"] == "AVAILABLE":
            self.available += 1
        status = row["settlement_status"]
        if status == "NO_BET_GATE_A":
            self.no_bet += 1
            return
        if status == "UNAVAILABLE_CANONICAL_OUTCOME":
            self.unavailable += 1
            self.failures[row["issue"]] += 1
            return
        self.settled += 1
        stake = decimal(row["stake_yuan"], "stake")
        gross = decimal(row["gross_pre_tax_yuan"], "gross")
        tax = decimal(row["tax_yuan"], "tax")
        after_tax = decimal(row["after_tax_gross_yuan"], "after_tax")
        net = decimal(row["tax_adjusted_net_yuan"], "net")
        self.k += int(row["active_k"]); self.stake += stake; self.gross += gross
        self.tax += tax; self.after_tax += after_tax; self.net += net
        self.hits += int(row["coverage_hit"] == "YES")
        self.expected += decimal(row["expected_portfolio_mass"], "expected coverage")
        self.expected_n += 1
        if row["coverage_hit"] != "YES": self.failures[row["issue"]] += 1
        self.issue_net[row["issue"]] += net; self.issue_stake[row["issue"]] += stake
        self.payout_rows.append((row["first_kickoff_ts"], row["pool_id"], gross, net, stake, row["coverage_hit"]))

    def output(self) -> dict[str, object]:
        ordered = sorted(self.payout_rows)
        cumulative = peak = drawdown = Decimal(0)
        current_streak = longest = 0
        best_pool = ""; best_gross = Decimal(0); best_net = Decimal(0); best_stake = Decimal(0)
        for _, pool, gross, net, stake, hit in ordered:
            cumulative += net; peak = max(peak, cumulative); drawdown = max(drawdown, peak - cumulative)
            current_streak = 0 if hit == "YES" else current_streak + 1; longest = max(longest, current_streak)
            if gross > best_gross:
                best_pool, best_gross, best_net, best_stake = pool, gross, net, stake
        best_issue = max(self.issue_net, key=self.issue_net.get, default="")
        best_issue_net = self.issue_net.get(best_issue, Decimal(0))
        best_issue_stake = self.issue_stake.get(best_issue, Decimal(0))
        positive_total = sum((max(Decimal(0), value) for value in self.issue_net.values()), Decimal(0))
        total_failures = sum(self.failures.values())
        return {
            "scope": self.scope, "scope_value": self.scope_value, "variant_id": self.variant, "arm": self.arm,
            "frontier_rows": self.rows, "candidate_matches": self.candidates, "gate_a_available": self.available,
            "settled": self.settled, "outcome_unavailable": self.unavailable, "no_bet_gate_a": self.no_bet,
            "total_k": self.k, "stake_yuan": money(self.stake), "coverage_hits": self.hits,
            "coverage_hit_rate": ratio(Decimal(self.hits) / self.settled) if self.settled else "",
            "mean_expected_coverage": ratio(self.expected / self.expected_n) if self.expected_n else "",
            "gross_pre_tax_yuan": money(self.gross), "tax_yuan": money(self.tax),
            "after_tax_gross_yuan": money(self.after_tax), "tax_adjusted_net_yuan": money(self.net),
            "tax_adjusted_roi": ratio(self.net / self.stake) if self.stake else "",
            "max_drawdown_yuan": money(drawdown), "longest_losing_streak": longest,
            "best_payout_pool_id": best_pool, "best_payout_gross_yuan": money(best_gross),
            "ex_best_payout_net_yuan": money(self.net - best_net),
            "ex_best_payout_roi": ratio((self.net - best_net) / (self.stake - best_stake)) if self.stake > best_stake else "",
            "best_net_issue": best_issue, "ex_best_issue_net_yuan": money(self.net - best_issue_net),
            "ex_best_issue_roi": ratio((self.net - best_issue_net) / (self.stake - best_issue_stake)) if self.stake > best_issue_stake else "",
            "positive_net_top_issue_share": ratio(max((max(Decimal(0), value) for value in self.issue_net.values()), default=Decimal(0)) / positive_total) if positive_total else "",
            "top_failure_issue_share": ratio(Decimal(max(self.failures.values(), default=0)) / total_failures) if total_failures else "",
            "coverage_miss_pool_count": self.settled - self.hits,
            "top_failure_issue": max(self.failures, key=self.failures.get, default=""),
            "control_arm": control_for(self.arm), "control_gross_pre_tax_yuan": "", "gross_retention_vs_control": "", "net_vs_control_yuan": "",
        }


def metric_rows(database: Path, where: str = "", parameters: tuple[str, ...] = (), scope: str = "ALL", scope_value: str = "ALL") -> list[dict[str, object]]:
    connection = sqlite3.connect(database); connection.row_factory = sqlite3.Row
    try:
        # The host's shared /tmp is intentionally not an artifact dependency.
        # Keep any SQLite ordering workspace in process memory; the frozen
        # 311k-row matrix is bounded and this avoids an opaque disk spill.
        connection.execute("PRAGMA temp_store=MEMORY")
        query = "SELECT * FROM settlements"
        if where:
            query += " WHERE " + where
        query += " ORDER BY variant_id, arm, first_kickoff_ts, issue, pool_id"
        metrics: dict[tuple[str, str], Metric] = {}
        for row in connection.execute(query, parameters):
            key = row["variant_id"], row["arm"]
            metrics.setdefault(key, Metric(*key, scope, scope_value)).add(row)
        outputs = [metric.output() for _, metric in sorted(metrics.items())]
        controls = {(row["scope"], row["scope_value"], row["variant_id"], row["arm"]): row for row in outputs}
        for row in outputs:
            control = controls.get((row["scope"], row["scope_value"], row["variant_id"], row["control_arm"]))
            if control:
                control_gross = decimal(control["gross_pre_tax_yuan"], "control gross")
                row["control_gross_pre_tax_yuan"] = money(control_gross)
                row["gross_retention_vs_control"] = ratio(decimal(row["gross_pre_tax_yuan"], "gross") / control_gross) if control_gross else ""
                row["net_vs_control_yuan"] = money(decimal(row["tax_adjusted_net_yuan"], "net") - decimal(control["tax_adjusted_net_yuan"], "control net"))
        return outputs
    finally:
        connection.close()


def summary_slices(database: Path) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    all_rows = metric_rows(database)
    connection = sqlite3.connect(database)
    try:
        years = [row[0] for row in connection.execute("SELECT DISTINCT year FROM settlements ORDER BY year")]
        folds = [row[0] for row in connection.execute("SELECT DISTINCT fold FROM settlements ORDER BY fold")]
    finally:
        connection.close()
    annual = []
    for year in years:
        annual.extend(metric_rows(database, "year=?", (year,), "YEAR", year))
    fold = []
    for item in folds:
        fold.extend(metric_rows(database, "fold=?", (item,), "FOLD", item))
    loyo = []
    for year in years:
        loyo.extend(metric_rows(database, "year!=?", (year,), "LEAVE_ONE_YEAR_OUT", year))
    return all_rows, annual, fold, loyo


def decision(all_rows: list[dict[str, object]], annual: list[dict[str, object]], loyo: list[dict[str, object]]) -> dict[str, object]:
    candidates: list[dict[str, object]] = []
    for row in all_rows:
        required = ("tax_adjusted_roi", "ex_best_payout_roi", "ex_best_issue_roi")
        if (row["arm"].startswith("UNFILTERED") or row["arm"] == "NO_BET_CONTROL"
                or any(not row[name] for name in required)):
            continue
        if not (Decimal(str(row["tax_adjusted_roi"])) > 0 and Decimal(str(row["ex_best_payout_roi"])) > 0 and Decimal(str(row["ex_best_issue_roi"])) > 0):
            continue
        slices = [item for item in [*annual, *loyo] if item["variant_id"] == row["variant_id"] and item["arm"] == row["arm"]]
        if slices and all(item["tax_adjusted_roi"] and Decimal(str(item["tax_adjusted_roi"])) > 0 for item in slices):
            candidates.append(row)
    return {
        "terminal_disposition": "NO_PROMOTION" if not candidates else "STRICT_INDEPENDENT_EV_REQUIRED",
        "positive_candidate_count": len(candidates),
        "candidate_ids": [f"{row['variant_id']}:{row['arm']}" for row in candidates],
        "rule": "A positive row is not promoted. It must be positive after issue-level tax, exclude-best-payout and exclude-best-issue, and in every frozen annual and LOYO slice; any survivor requires strict independent EV.",
    }


def settle(output: Path) -> dict[str, object]:
    if output.exists(): raise RuntimeError(f"refusing immutable overwrite: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".bj121_gateb_", dir=output.parent))
    try:
        provenance = validate_inputs(); outcomes = load_outcomes(); assignments = AssignmentStream()
        pre_tax = stage / "_pre_tax.csv"; gross_by_bucket: dict[tuple[str, str, str], Decimal] = defaultdict(Decimal)
        counts: dict[str, int] = defaultdict(int); total_frontiers = 0; total_assignments = 0
        with pre_tax.open("w", newline="", encoding="utf-8") as handle:
            fields = tuple(field for field in SETTLEMENT_FIELDS if field not in {"tax_bucket_gross_yuan", "tax_yuan", "after_tax_gross_yuan", "tax_adjusted_net_yuan"})
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n"); writer.writeheader()
            frontier_handle, frontiers = gzip_reader(FREEZE / "portfolio_frontier.csv.gz", FRONTIER_FIELDS)
            try:
                for frontier in frontiers:
                    key = (frontier["variant_id"], frontier["arm"], frontier["pool_id"])
                    roles = assignments.group(key, int(frontier["selected_n"]))
                    settlement = geometry(frontier, roles, outcomes)
                    total_frontiers += 1; total_assignments += len(roles); counts[str(settlement["status"])] += 1
                    if settlement["status"] == "SETTLED": gross_by_bucket[tax_key(frontier)] += settlement["gross"]  # type: ignore[operator]
                    writer.writerow({
                        "issue": frontier["issue"], "fold": frontier["fold"], "year": frontier["year"], "pool_id": frontier["pool_id"],
                        "segment_index": frontier["segment_index"], "first_kickoff_ts": frontier["first_kickoff_ts"],
                        "variant_id": frontier["variant_id"], "arm": frontier["arm"], "gate_a_disposition": frontier["disposition"],
                        "settlement_status": settlement["status"], "candidate_match_count": frontier["candidate_match_count"],
                        "selected_n": frontier["selected_n"], "outcome_gap_count": settlement["gap_count"], "formula_k": frontier["formula_k"],
                        "active_k": settlement["active_k"], "stake_yuan": money(settlement["stake"]), "full_legs": frontier["full_legs"],
                        "double_legs": frontier["double_legs"], "single_legs": frontier["single_legs"],
                        "expected_portfolio_mass": frontier["expected_portfolio_mass"] or "0", "coverage_hit": settlement["hit"],
                        "omitted_outcome_count": settlement["omitted"], "truth_sequence": settlement["truth"],
                        # Keep the full Decimal product in the receipt.  Gross is
                        # rounded for currency reporting only, so a six-decimal
                        # product would make an otherwise exact one-factor
                        # replay appear off by a micro-yuan.
                        "final_winning_sp_product": format(settlement["product"], "f"), "gross_pre_tax_yuan": money(settlement["gross"]),
                        "winning_sp_sources": settlement["sources"], "descriptor_sha256": frontier["descriptor_sha256"],
                    })
            finally:
                frontier_handle.close(); assignments.close()
        if total_frontiers != 311_103 or total_assignments != 1_324_602:
            raise RuntimeError(f"frozen cardinality drift: {total_frontiers}/{total_assignments}")
        with pre_tax.open(newline="", encoding="utf-8") as source:
            raw = (stage / "portfolio_settlement.csv.gz").open("wb")
            zipped = gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0)
            text = io.TextIOWrapper(zipped, newline="", encoding="utf-8")
            reader = csv.DictReader(source); writer = csv.DictWriter(text, fieldnames=SETTLEMENT_FIELDS, lineterminator="\n"); writer.writeheader()
            for row in reader:
                gross = decimal(row["gross_pre_tax_yuan"], "gross")
                bucket_total = gross_by_bucket[tax_key(row)]
                tax = gross * TAX_RATE if bucket_total >= TAX_THRESHOLD else Decimal(0)
                after_tax = gross - tax; net = after_tax - decimal(row["stake_yuan"], "stake")
                writer.writerow({**row, "tax_bucket_gross_yuan": money(bucket_total), "tax_yuan": money(tax),
                                 "after_tax_gross_yuan": money(after_tax), "tax_adjusted_net_yuan": money(net)})
            text.flush(); text.detach(); zipped.close(); raw.close()
        if sum(counts.values()) != total_frontiers: raise RuntimeError("status denominator drift")
        database = stage / "_metrics.sqlite"
        connection = sqlite3.connect(database)
        try:
            connection.execute("PRAGMA temp_store=MEMORY")
            with gzip.open(stage / "portfolio_settlement.csv.gz", "rt", newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                if tuple(reader.fieldnames or ()) != SETTLEMENT_FIELDS: raise RuntimeError("settlement schema drift")
                connection.execute("CREATE TABLE settlements (" + ",".join(f'\"{field}\" TEXT NOT NULL' for field in SETTLEMENT_FIELDS) + ")")
                placeholders = ",".join("?" for _ in SETTLEMENT_FIELDS)
                connection.executemany("INSERT INTO settlements VALUES (" + placeholders + ")", ([row[field] for field in SETTLEMENT_FIELDS] for row in reader))
                connection.execute("CREATE INDEX order_by_policy ON settlements(variant_id, arm, first_kickoff_ts, issue, pool_id)")
                connection.execute("CREATE INDEX year_order ON settlements(year, variant_id, arm, first_kickoff_ts, issue, pool_id)")
                connection.execute("CREATE INDEX fold_order ON settlements(fold, variant_id, arm, first_kickoff_ts, issue, pool_id)")
                connection.commit()
        finally:
            connection.close()
        all_rows, annual, fold, loyo = summary_slices(database)
        write_csv(stage / "frontier_summary.csv", SUMMARY_FIELDS, all_rows)
        write_csv(stage / "annual_summary.csv", SUMMARY_FIELDS, annual)
        write_csv(stage / "fold_summary.csv", SUMMARY_FIELDS, fold)
        write_csv(stage / "leave_one_year_out_summary.csv", SUMMARY_FIELDS, loyo)
        concentration = [{field: row[field] for field in CONCENTRATION_FIELDS} for row in all_rows]
        write_csv(stage / "pool_failure_concentration.csv", CONCENTRATION_FIELDS, concentration)
        decision_card = decision(all_rows, annual, loyo)
        (stage / "decision.json").write_text(json.dumps(decision_card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        shutil.copyfile(CANONICAL / "canonical_outcome_join.csv", stage / "canonical_outcome_join.csv")
        shutil.copyfile(__file__, stage / "settlement_runner.py")
        card = {
            "issue": 121, "contract": CONTRACT, "stage": "GATE_B_ONE_SHOT_CANONICAL_OUTCOME_SETTLEMENT",
            "provenance": provenance, "input_freeze": str(FREEZE.relative_to(ROOT)),
            "canonical_outcome_source": str((CANONICAL / "canonical_outcome_join.csv").relative_to(ROOT)),
            "row_counts": {"frontier_rows": total_frontiers, "assignment_rows": total_assignments, **dict(sorted(counts.items()))},
            "settlement_rule": "For each settled frozen portfolio, hit iff every final result is in the frozen allowed set; gross=2*0.65*product(final winning SP) on hit and 0 otherwise. K/stake are frozen outputs, never eligibility filters.",
            "tax_rule": "Each (variant, arm) is a separate paper policy. Aggregate gross prizes by native issue before tax. A bucket at least 10000 yuan pays 20% of every gross prize in that bucket.",
            "availability_rule": "Every Gate-A row remains in denominator. Selected portfolios with absent canonical outcomes are UNAVAILABLE_CANONICAL_OUTCOME with zero stake and no alternate truth source.",
            "terminal_disposition": decision_card["terminal_disposition"],
            "scope": "historical paper-only research; no purchase, production, or promotion recommendation.",
        }
        (stage / "settlement_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (stage / "README.md").write_text("# #121 Gate B\n\nCanonical frozen-matrix outcome settlement. Run `python settlement_runner.py --output <empty-dir>` from a compatible checkout.\n", encoding="utf-8")
        pre_tax.unlink(); database.unlink()
        manifest = {item.name: sha256(item) for item in sorted(stage.iterdir()) if item.is_file()}
        (stage / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(stage, output)
        return {"manifest_sha256": sha256(output / "SHA256SUMS.json"), "status_counts": dict(sorted(counts.items())), **decision_card}
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    print(json.dumps(settle(args.output.resolve()), sort_keys=True))


if __name__ == "__main__":
    main()
