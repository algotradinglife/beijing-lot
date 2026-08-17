#!/usr/bin/env python3
"""One-shot canonical Gate-B settlement for #127's accepted matched N7 freeze.

The program may read outcomes only after manifest-verifying the accepted Gate-A
v2 package.  It never regenerates a threshold, candidate, companion, seven-leg
set, deletion code, ticket count, or stake after that outcome boundary.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import os
import shutil
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path


def repo_root(anchor: Path) -> Path:
    for candidate in (anchor.resolve().parent, *anchor.resolve().parents):
        if (candidate / ".git").exists():
            return candidate
    raise RuntimeError("repository root unavailable")


ROOT = repo_root(Path(__file__))
FREEZE = ROOT / "results" / "bj127_gate_a_preoutcome_v2"
OUTCOME_SOURCE = ROOT / "results" / "bj95_gate_b_outcome_settlement_v2r8"
OUT = ROOT / "results" / "bj127_gate_b_outcome_settlement_v1"

CONTRACT = "BJ-HIST-PRUNE-ONE-GLOBAL-N7-001"
RUNNER_VERSION = "bj127-gateb-v1"
EXPECTED_FREEZE_MANIFEST = "a8eeb50204bb9a2d69578538e28943a432bea11083661a63b950a5ab5a2481da"
EXPECTED_OUTCOME_MANIFEST = "fbbd3b53bd86f4bb0caff8f2587933cd6b0e4e7d04fb0f709bac934ec2a705cc"
EXPECTED_OUTCOME_PAYLOAD = "13d709d253c31519734dbf0447e6961ac8a6060772975d7461741224e5251a89"
EXPECTED_FRONTIERS = 204_361
EXPECTED_NO_BET = 23_931
EXPECTED_IDENTITIES = 90_215
EXPECTED_ROLE_ROWS = 631_505
EXPECTED_VARIANTS = 9
FULL_K, PRUNE_K = 2_187, 1_458
FACTOR, UNIT_STAKE = Decimal("0.65"), Decimal("2")
TAX_RATE, TAX_THRESHOLD = Decimal("0.20"), Decimal("10000")
Q = Decimal("0.000001")
CODES = ("3", "1", "0")
getcontext().prec = 128

FRONTIER_FIELDS = (
    "issue", "fold", "year", "pool_id", "segment_index", "pool_disposition",
    "eligible_match_count", "pool_match_count", "first_kickoff_ts", "last_kickoff_ts",
    "window_hours", "terminal_remainder", "variant_id", "arm", "portfolio_id",
    "deletion_candidate_match_id", "deletion_candidate_p_min", "selected_match_ids",
    "selected_n", "gm_e_sp", "deleted_match_id", "deleted_code", "deleted_probability",
    "formula_k", "stake_yuan", "matched_full_k", "matched_full_stake_yuan",
    "stake_reduction_fraction", "disposition", "reason", "descriptor_sha256",
)
ROLE_FIELDS = (
    "variant_id", "portfolio_id", "issue", "fold", "year", "pool_id", "match_id",
    "match_idx", "selection_rank", "e_sp", "p_min", "p3", "p1", "p0",
    "is_deletion_candidate", "is_global_deleted_code_match", "global_deleted_code",
    "global_deleted_probability", "full_allowed_codes", "prune_allowed_codes",
)
OUTCOME_FIELDS = (
    "match_id", "result_code", "winning_sp", "winning_sp_source",
    "settlement_quality", "has_trusted_settlement",
)
SETTLEMENT_FIELDS = FRONTIER_FIELDS + (
    "settlement_status", "outcome_gap_count", "coverage_hit", "omitted_code_occurred",
    "truth_sequence", "final_winning_sp_product", "gross_pre_tax_yuan",
    "issue_policy_gross_yuan", "tax_yuan", "after_tax_gross_yuan",
    "pre_tax_net_yuan", "tax_adjusted_net_yuan", "winning_sp_sources",
)
SUMMARY_FIELDS = (
    "scope", "scope_value", "variant_id", "e_sp_min", "gm_e_sp_min", "low_p_max", "arm",
    "frontier_rows", "gate_a_available", "no_bet_gate_a", "unavailable_canonical_outcome",
    "settled", "settled_portfolio_identities", "total_tickets", "stake_yuan", "coverage_hits",
    "coverage_hit_rate", "coverage_miss_rate", "omitted_code_occurrences", "omitted_code_rate",
    "gross_pre_tax_yuan", "pre_tax_net_yuan", "no_tax_roi", "tax_yuan", "tax_drag_yuan",
    "tax_drag_roi_points", "after_tax_gross_yuan", "tax_adjusted_net_yuan", "tax_adjusted_roi",
    "max_drawdown_yuan", "longest_miss_streak", "best_payout_portfolio_id",
    "best_payout_gross_yuan", "ex_best_payout_net_yuan", "ex_best_payout_roi", "best_net_issue",
    "ex_best_issue_net_yuan", "ex_best_issue_roi", "positive_net_top_issue_share",
    "gross_top_issue_share", "settled_issue_count", "settled_pool_count",
)
DELTA_FIELDS = (
    "variant_id", "portfolio_id", "issue", "fold", "year", "pool_id", "first_kickoff_ts",
    "deletion_candidate_match_id", "deleted_match_id", "deleted_code", "omitted_code_occurred",
    "full_coverage_hit", "prune_coverage_hit", "full_tickets", "prune_tickets", "full_stake_yuan",
    "prune_stake_yuan", "stake_saved_yuan", "full_gross_pre_tax_yuan", "prune_gross_pre_tax_yuan",
    "full_pre_tax_net_yuan", "prune_pre_tax_net_yuan", "full_tax_yuan", "prune_tax_yuan",
    "full_tax_adjusted_net_yuan", "prune_tax_adjusted_net_yuan", "full_minus_prune_net_yuan",
)
POLICY_COMPARISON_FIELDS = (
    "scope", "scope_value", "variant_id", "e_sp_min", "gm_e_sp_min", "low_p_max",
    "full_settled", "prune_settled", "full_coverage_hit_rate", "prune_coverage_hit_rate",
    "omitted_code_rate", "full_stake_yuan", "prune_stake_yuan", "stake_saved_yuan",
    "full_no_tax_roi", "prune_no_tax_roi", "no_tax_roi_delta_prune_minus_full",
    "full_tax_adjusted_roi", "prune_tax_adjusted_roi", "tax_adjusted_roi_delta_prune_minus_full",
    "full_tax_yuan", "prune_tax_yuan", "full_max_drawdown_yuan", "prune_max_drawdown_yuan",
    "full_longest_miss_streak", "prune_longest_miss_streak",
)


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
        raise RuntimeError(f"invalid decimal {label}: {value!r}") from error
    if not result.is_finite():
        raise RuntimeError(f"non-finite decimal {label}: {value!r}")
    return result


def money(value: Decimal) -> str:
    return format(value.quantize(Q), "f")


def ratio(value: Decimal | None) -> str:
    return "" if value is None else format(value, ".12f")


def manifest(bundle: Path, expected: str) -> dict[str, str]:
    path = bundle / "SHA256SUMS.json"
    if sha256(path) != expected:
        raise RuntimeError(f"unaccepted manifest: {bundle}")
    declared = json.loads(path.read_text(encoding="utf-8"))
    actual = {item.name: sha256(item) for item in bundle.iterdir() if item.is_file() and item.name != path.name}
    if not isinstance(declared, dict) or declared != actual:
        raise RuntimeError(f"manifest coverage drift: {bundle}")
    return declared


def validate_inputs() -> dict[str, str]:
    freeze = manifest(FREEZE, EXPECTED_FREEZE_MANIFEST)
    card = json.loads((FREEZE / "gate_a_card.json").read_text(encoding="utf-8"))
    if (card.get("contract") != CONTRACT or card.get("stage") != "GATE_A_OUTCOME_UNEXPOSED_MATCHED_FREEZE"
            or card.get("denominator") != {"native_issues": 344, "native_pools": 2659,
                                            "frontier_rows": EXPECTED_FRONTIERS,
                                            "portfolio_identities": EXPECTED_IDENTITIES,
                                            "role_rows": EXPECTED_ROLE_ROWS}):
        raise RuntimeError("unaccepted Gate-A contract/cardinality")
    if len(card.get("variants", {})) != EXPECTED_VARIANTS:
        raise RuntimeError("Gate-A threshold-grid drift")
    outcome = manifest(OUTCOME_SOURCE, EXPECTED_OUTCOME_MANIFEST)
    if outcome.get("canonical_outcome_join.csv") != EXPECTED_OUTCOME_PAYLOAD:
        raise RuntimeError("canonical outcome payload drift")
    return {"gate_a_manifest_sha256": EXPECTED_FREEZE_MANIFEST,
            "gate_a_content_identity_sha256": freeze["CONTENT_IDENTITY.json"],
            "outcome_source_manifest_sha256": EXPECTED_OUTCOME_MANIFEST,
            "canonical_outcome_payload_sha256": EXPECTED_OUTCOME_PAYLOAD}


def load_outcomes() -> dict[str, dict[str, str]]:
    with (OUTCOME_SOURCE / "canonical_outcome_join.csv").open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != OUTCOME_FIELDS:
            raise RuntimeError("canonical outcome schema drift")
        rows = list(reader)
    outcomes = {row["match_id"]: row for row in rows}
    if len(outcomes) != len(rows):
        raise RuntimeError("duplicate canonical outcome id")
    for row in outcomes.values():
        if (row["result_code"] not in CODES or row["settlement_quality"] != "trusted"
                or row["has_trusted_settlement"] != "1" or dec(row["winning_sp"], "winning SP") <= 0):
            raise RuntimeError(f"untrusted canonical outcome: {row['match_id']}")
    return outcomes


def gzip_writer(path: Path, fields: tuple[str, ...]):
    raw = path.open("wb")
    zipped = gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0)
    text = io.TextIOWrapper(zipped, encoding="utf-8", newline="")
    writer = csv.DictWriter(text, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    return raw, zipped, text, writer


def close_gzip(handles) -> None:
    raw, zipped, text, _ = handles
    text.flush(); text.detach(); zipped.close(); raw.close()


def role_groups() -> object:
    """Yield the exact seven frozen role rows per portfolio without a large in-memory join."""
    with gzip.open(FREEZE / "portfolio_role_assignments.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != ROLE_FIELDS:
            raise RuntimeError("Gate-A role schema drift")
        current: tuple[str, str] | None = None
        rows: list[dict[str, str]] = []
        for row in reader:
            key = row["variant_id"], row["portfolio_id"]
            if current is not None and key != current:
                yield current, rows
                rows = []
            current = key
            rows.append(row)
        if current is not None:
            yield current, rows


def validate_roles(frontier: dict[str, str], roles: list[dict[str, str]]) -> None:
    if len(roles) != 7 or [int(row["selection_rank"]) for row in roles] != list(range(1, 8)):
        raise RuntimeError("frozen role cardinality/order drift")
    key = frontier["variant_id"], frontier["portfolio_id"]
    if any((row["variant_id"], row["portfolio_id"]) != key for row in roles):
        raise RuntimeError("frontier/role key drift")
    if any(row[field] != frontier[field] for row in roles for field in ("issue", "fold", "year", "pool_id")):
        raise RuntimeError("frontier/role provenance drift")
    if ";".join(row["match_id"] for row in roles) != frontier["selected_match_ids"]:
        raise RuntimeError("frozen selected-match identity drift")
    deleted = [row for row in roles if row["is_global_deleted_code_match"] == "1"]
    if len(deleted) != 1 or deleted[0]["match_id"] != frontier["deleted_match_id"]:
        raise RuntimeError("frozen deleted-match drift")
    if deleted[0]["global_deleted_code"] != frontier["deleted_code"]:
        raise RuntimeError("frozen deleted-code drift")
    if any(row["full_allowed_codes"] != "310" for row in roles):
        raise RuntimeError("FULL coverage geometry drift")
    for row in roles:
        expected = "".join(code for code in CODES if not (row is deleted[0] and code == frontier["deleted_code"]))
        if row["prune_allowed_codes"] != expected:
            raise RuntimeError("PRUNE coverage geometry drift")


def settlement(frontier: dict[str, str], roles: list[dict[str, str]] | None,
               outcomes: dict[str, dict[str, str]]) -> dict[str, object]:
    if frontier["arm"] == "NO_BET_CONTROL":
        if frontier["disposition"] != "NO_BET" or roles is not None or int(frontier["formula_k"]):
            raise RuntimeError("NO_BET gate geometry drift")
        return {"status": "NO_BET_GATE_A", "gap": 0, "hit": "", "omitted": "", "truth": "",
                "product": Decimal(0), "gross": Decimal(0), "sources": ""}
    if frontier["disposition"] != "AVAILABLE" or roles is None or int(frontier["selected_n"]) != 7:
        raise RuntimeError("available frontier geometry drift")
    validate_roles(frontier, roles)
    expected_k = FULL_K if frontier["arm"] == "MATCHED_FULL_N7" else PRUNE_K
    allowed = "full_allowed_codes" if frontier["arm"] == "MATCHED_FULL_N7" else "prune_allowed_codes"
    if (frontier["arm"] not in {"MATCHED_FULL_N7", "PRUNE_ONE_GLOBAL_N7"}
            or int(frontier["formula_k"]) != expected_k
            or dec(frontier["stake_yuan"], "frozen stake") != UNIT_STAKE * expected_k):
        raise RuntimeError("matched ticket/stake drift")
    missing = [row["match_id"] for row in roles if row["match_id"] not in outcomes]
    if missing:
        return {"status": "UNAVAILABLE_CANONICAL_OUTCOME", "gap": len(missing), "hit": "", "omitted": "",
                "truth": "", "product": Decimal(0), "gross": Decimal(0), "sources": ""}
    truth, product, sources = [], Decimal(1), set()
    hit = True
    for role in roles:
        outcome = outcomes[role["match_id"]]
        truth.append(outcome["result_code"])
        product *= dec(outcome["winning_sp"], "winning SP")
        sources.add(outcome["winning_sp_source"])
        hit = hit and outcome["result_code"] in role[allowed]
    deleted = next(row for row in roles if row["is_global_deleted_code_match"] == "1")
    omitted = "YES" if outcomes[deleted["match_id"]]["result_code"] == frontier["deleted_code"] else "NO"
    gross = UNIT_STAKE * FACTOR * product if hit else Decimal(0)
    return {"status": "SETTLED", "gap": 0, "hit": "YES" if hit else "NO", "omitted": omitted,
            "truth": "".join(truth), "product": product, "gross": gross, "sources": ";".join(sorted(sources))}


def bucket_key(row: dict[str, str]) -> tuple[str, str, str]:
    return row["issue"], row["variant_id"], row["arm"]


def allocated_tax(gross: Decimal, bucket_gross: Decimal) -> Decimal:
    if gross < 0 or bucket_gross < 0:
        raise RuntimeError("negative gross cannot be taxed")
    return gross * TAX_RATE if bucket_gross >= TAX_THRESHOLD else Decimal(0)


def variant_parts(variant: str) -> tuple[str, str, str]:
    parts = variant.split("_")
    if len(parts) != 3 or not parts[0].startswith("ESP") or not parts[1].startswith("GM") or not parts[2].startswith("LOWP"):
        raise RuntimeError(f"invalid variant id: {variant}")
    return ratio(Decimal(parts[0][3:]) / 100), ratio(Decimal(parts[1][2:]) / 100), ratio(Decimal(parts[2][4:]) / 100)


@dataclass
class Metric:
    variant_id: str
    arm: str
    scope: str
    scope_value: str
    rows: int = 0; available: int = 0; no_bet: int = 0; unavailable: int = 0; settled: int = 0
    tickets: int = 0; stake: Decimal = Decimal(0); gross: Decimal = Decimal(0); tax: Decimal = Decimal(0)
    after_tax: Decimal = Decimal(0); net: Decimal = Decimal(0); hits: int = 0; omitted: int = 0
    best_gross: Decimal = Decimal(-1); best_net: Decimal = Decimal(0); best_stake: Decimal = Decimal(0); best_portfolio: str = ""
    issue_net: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    issue_stake: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    issue_gross: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    pools: set[str] = field(default_factory=set)
    timeline: list[tuple[str, str, str, Decimal, bool]] = field(default_factory=list)

    def add(self, row: dict[str, str]) -> None:
        self.rows += 1
        if row["disposition"] == "AVAILABLE": self.available += 1
        status = row["settlement_status"]
        if status == "NO_BET_GATE_A": self.no_bet += 1; return
        if status == "UNAVAILABLE_CANONICAL_OUTCOME": self.unavailable += 1; return
        if status != "SETTLED": raise RuntimeError(f"unknown settlement status: {status}")
        self.settled += 1; self.tickets += int(row["formula_k"]); self.pools.add(row["pool_id"])
        stake, gross, tax, after_tax, net = (dec(row[field], field) for field in (
            "stake_yuan", "gross_pre_tax_yuan", "tax_yuan", "after_tax_gross_yuan", "tax_adjusted_net_yuan"))
        self.stake += stake; self.gross += gross; self.tax += tax; self.after_tax += after_tax; self.net += net
        self.hits += row["coverage_hit"] == "YES"
        self.omitted += row["omitted_code_occurred"] == "YES"
        self.timeline.append((row["first_kickoff_ts"], row["pool_id"], row["portfolio_id"], net, row["coverage_hit"] == "YES"))
        if gross > self.best_gross:
            self.best_gross, self.best_net, self.best_stake, self.best_portfolio = gross, net, stake, row["portfolio_id"]
        self.issue_net[row["issue"]] += net; self.issue_stake[row["issue"]] += stake; self.issue_gross[row["issue"]] += gross

    def output(self) -> dict[str, object]:
        cumulative = peak = drawdown = Decimal(0); streak = longest = 0
        for _, _, _, net, hit in sorted(self.timeline):
            cumulative += net; peak = max(peak, cumulative); drawdown = max(drawdown, peak - cumulative)
            streak = 0 if hit else streak + 1; longest = max(longest, streak)
        best_issue = max(self.issue_net, key=self.issue_net.get, default="")
        best_issue_net, best_issue_stake = self.issue_net.get(best_issue, Decimal(0)), self.issue_stake.get(best_issue, Decimal(0))
        positive = [max(Decimal(0), value) for value in self.issue_net.values()]
        positive_total, gross_total = sum(positive, Decimal(0)), sum(self.issue_gross.values(), Decimal(0))
        e_sp, gm, low_p = variant_parts(self.variant_id)
        pre_net = self.gross - self.stake
        no_tax_roi = pre_net / self.stake if self.stake else None
        tax_roi = self.net / self.stake if self.stake else None
        return {"scope": self.scope, "scope_value": self.scope_value, "variant_id": self.variant_id,
                "e_sp_min": e_sp, "gm_e_sp_min": gm, "low_p_max": low_p, "arm": self.arm,
                "frontier_rows": self.rows, "gate_a_available": self.available, "no_bet_gate_a": self.no_bet,
                "unavailable_canonical_outcome": self.unavailable, "settled": self.settled,
                "settled_portfolio_identities": self.settled, "total_tickets": self.tickets, "stake_yuan": money(self.stake),
                "coverage_hits": self.hits, "coverage_hit_rate": ratio(Decimal(self.hits) / self.settled) if self.settled else "",
                "coverage_miss_rate": ratio(Decimal(self.settled-self.hits) / self.settled) if self.settled else "",
                "omitted_code_occurrences": self.omitted, "omitted_code_rate": ratio(Decimal(self.omitted) / self.settled) if self.settled else "",
                "gross_pre_tax_yuan": money(self.gross), "pre_tax_net_yuan": money(pre_net), "no_tax_roi": ratio(no_tax_roi),
                "tax_yuan": money(self.tax), "tax_drag_yuan": money(self.tax), "tax_drag_roi_points": ratio(self.tax / self.stake) if self.stake else "",
                "after_tax_gross_yuan": money(self.after_tax), "tax_adjusted_net_yuan": money(self.net), "tax_adjusted_roi": ratio(tax_roi),
                "max_drawdown_yuan": money(drawdown), "longest_miss_streak": longest,
                "best_payout_portfolio_id": self.best_portfolio, "best_payout_gross_yuan": money(max(self.best_gross, Decimal(0))),
                "ex_best_payout_net_yuan": money(self.net-self.best_net), "ex_best_payout_roi": ratio((self.net-self.best_net)/(self.stake-self.best_stake)) if self.stake > self.best_stake else "",
                "best_net_issue": best_issue, "ex_best_issue_net_yuan": money(self.net-best_issue_net),
                "ex_best_issue_roi": ratio((self.net-best_issue_net)/(self.stake-best_issue_stake)) if self.stake > best_issue_stake else "",
                "positive_net_top_issue_share": ratio(max(positive, default=Decimal(0))/positive_total) if positive_total else "",
                "gross_top_issue_share": ratio(max(self.issue_gross.values(), default=Decimal(0))/gross_total) if gross_total else "",
                "settled_issue_count": len(self.issue_net), "settled_pool_count": len(self.pools)}


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)


def summary(path: Path) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    all_metrics: dict[tuple[str, str], Metric] = {}
    year_metrics: dict[tuple[str, str, str], Metric] = {}
    fold_metrics: dict[tuple[str, str, str], Metric] = {}
    years: set[str] = set()
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            key = row["variant_id"], row["arm"]; years.add(row["year"])
            all_metrics.setdefault(key, Metric(*key, "ALL", "ALL")).add(row)
            year_metrics.setdefault((row["year"], *key), Metric(*key, "YEAR", row["year"])).add(row)
            fold_metrics.setdefault((row["fold"], *key), Metric(*key, "FOLD", row["fold"])).add(row)
    all_rows = [metric.output() for _, metric in sorted(all_metrics.items())]
    robust = [metric.output() for _, metric in sorted(year_metrics.items())] + [metric.output() for _, metric in sorted(fold_metrics.items())]
    for omitted in sorted(years):
        loyo: dict[tuple[str, str], Metric] = {}
        with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row["year"] == omitted: continue
                key = row["variant_id"], row["arm"]
                loyo.setdefault(key, Metric(*key, "LEAVE_ONE_YEAR_OUT", omitted)).add(row)
        robust.extend(metric.output() for _, metric in sorted(loyo.items()))
    return all_rows, robust


def comparisons(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    by_key = {(row["scope"], row["scope_value"], row["variant_id"], row["arm"]): row for row in rows}
    result = []
    for (scope, value, variant, arm), full in sorted(by_key.items()):
        if arm != "MATCHED_FULL_N7": continue
        prune = by_key[(scope, value, variant, "PRUNE_ONE_GLOBAL_N7")]
        def value_of(row: dict[str, object], field: str) -> Decimal: return dec(row[field], field)
        result.append({"scope": scope, "scope_value": value, "variant_id": variant,
                       "e_sp_min": full["e_sp_min"], "gm_e_sp_min": full["gm_e_sp_min"], "low_p_max": full["low_p_max"],
                       "full_settled": full["settled"], "prune_settled": prune["settled"],
                       "full_coverage_hit_rate": full["coverage_hit_rate"], "prune_coverage_hit_rate": prune["coverage_hit_rate"],
                       "omitted_code_rate": prune["omitted_code_rate"], "full_stake_yuan": full["stake_yuan"], "prune_stake_yuan": prune["stake_yuan"],
                       "stake_saved_yuan": money(value_of(full, "stake_yuan")-value_of(prune, "stake_yuan")),
                       "full_no_tax_roi": full["no_tax_roi"], "prune_no_tax_roi": prune["no_tax_roi"],
                       "no_tax_roi_delta_prune_minus_full": ratio(value_of(prune, "no_tax_roi")-value_of(full, "no_tax_roi")) if full["no_tax_roi"] else "",
                       "full_tax_adjusted_roi": full["tax_adjusted_roi"], "prune_tax_adjusted_roi": prune["tax_adjusted_roi"],
                       "tax_adjusted_roi_delta_prune_minus_full": ratio(value_of(prune, "tax_adjusted_roi")-value_of(full, "tax_adjusted_roi")) if full["tax_adjusted_roi"] else "",
                       "full_tax_yuan": full["tax_yuan"], "prune_tax_yuan": prune["tax_yuan"],
                       "full_max_drawdown_yuan": full["max_drawdown_yuan"], "prune_max_drawdown_yuan": prune["max_drawdown_yuan"],
                       "full_longest_miss_streak": full["longest_miss_streak"], "prune_longest_miss_streak": prune["longest_miss_streak"]})
    return result


def write_deltas(path: Path, settlement_path: Path) -> None:
    pending: dict[tuple[str, str], dict[str, str]] = {}
    rows: list[dict[str, object]] = []
    with gzip.open(settlement_path, "rt", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["settlement_status"] != "SETTLED": continue
            key = row["variant_id"], row["portfolio_id"]
            if row["arm"] == "MATCHED_FULL_N7": pending[key] = row; continue
            if row["arm"] != "PRUNE_ONE_GLOBAL_N7" or key not in pending: raise RuntimeError("matched pair ordering drift")
            full = pending.pop(key)
            if any(full[field] != row[field] for field in ("issue", "fold", "year", "pool_id", "selected_match_ids", "deleted_match_id", "deleted_code")):
                raise RuntimeError("same-seven matched pair drift")
            rows.append({"variant_id": row["variant_id"], "portfolio_id": row["portfolio_id"], "issue": row["issue"], "fold": row["fold"], "year": row["year"], "pool_id": row["pool_id"], "first_kickoff_ts": row["first_kickoff_ts"], "deletion_candidate_match_id": row["deletion_candidate_match_id"], "deleted_match_id": row["deleted_match_id"], "deleted_code": row["deleted_code"], "omitted_code_occurred": row["omitted_code_occurred"], "full_coverage_hit": full["coverage_hit"], "prune_coverage_hit": row["coverage_hit"], "full_tickets": full["formula_k"], "prune_tickets": row["formula_k"], "full_stake_yuan": full["stake_yuan"], "prune_stake_yuan": row["stake_yuan"], "stake_saved_yuan": money(dec(full["stake_yuan"], "full stake")-dec(row["stake_yuan"], "prune stake")), "full_gross_pre_tax_yuan": full["gross_pre_tax_yuan"], "prune_gross_pre_tax_yuan": row["gross_pre_tax_yuan"], "full_pre_tax_net_yuan": full["pre_tax_net_yuan"], "prune_pre_tax_net_yuan": row["pre_tax_net_yuan"], "full_tax_yuan": full["tax_yuan"], "prune_tax_yuan": row["tax_yuan"], "full_tax_adjusted_net_yuan": full["tax_adjusted_net_yuan"], "prune_tax_adjusted_net_yuan": row["tax_adjusted_net_yuan"], "full_minus_prune_net_yuan": money(dec(full["tax_adjusted_net_yuan"], "full net")-dec(row["tax_adjusted_net_yuan"], "prune net"))})
    if pending: raise RuntimeError("unpaired FULL rows")
    write_csv(path, DELTA_FIELDS, rows)


def build(output: Path) -> dict[str, object]:
    if output.exists(): raise RuntimeError(f"refusing immutable overwrite: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".bj127_gateb_", dir=output.parent))
    try:
        provenance, outcomes = validate_inputs(), load_outcomes()
        pre_tax = stage / "_pre_tax.csv"; bucket_gross: dict[tuple[str, str, str], Decimal] = defaultdict(Decimal)
        roles = role_groups(); next_roles = next(roles, None); pending_roles: list[dict[str, str]] | None = None
        total = no_bet = identities = role_rows = 0; variants, pools = set(), set()
        with gzip.open(FREEZE / "matched_frontier.csv.gz", "rt", newline="", encoding="utf-8") as source, pre_tax.open("w", newline="", encoding="utf-8") as target:
            reader = csv.DictReader(source)
            if tuple(reader.fieldnames or ()) != FRONTIER_FIELDS: raise RuntimeError("Gate-A frontier schema drift")
            writer = csv.DictWriter(target, fieldnames=FRONTIER_FIELDS + ("settlement_status", "outcome_gap_count", "coverage_hit", "omitted_code_occurred", "truth_sequence", "final_winning_sp_product", "gross_pre_tax_yuan", "winning_sp_sources"), lineterminator="\n"); writer.writeheader()
            for frontier in reader:
                arm = frontier["arm"]; role_set = None
                if arm == "MATCHED_FULL_N7":
                    if next_roles is None: raise RuntimeError("missing frozen role group")
                    key, role_set = next_roles
                    if key != (frontier["variant_id"], frontier["portfolio_id"]): raise RuntimeError("role/frontier ordering drift")
                    pending_roles = role_set; next_roles = next(roles, None); identities += 1; role_rows += len(role_set)
                elif arm == "PRUNE_ONE_GLOBAL_N7":
                    role_set, pending_roles = pending_roles, None
                    if role_set is None: raise RuntimeError("PRUNE without matched FULL role group")
                elif arm == "NO_BET_CONTROL":
                    no_bet += 1
                else: raise RuntimeError(f"unknown frozen arm: {arm}")
                result = settlement(frontier, role_set, outcomes)
                writer.writerow({**frontier, "settlement_status": result["status"], "outcome_gap_count": result["gap"], "coverage_hit": result["hit"], "omitted_code_occurred": result["omitted"], "truth_sequence": result["truth"], "final_winning_sp_product": money(result["product"]), "gross_pre_tax_yuan": money(result["gross"]), "winning_sp_sources": result["sources"]})
                if result["status"] == "SETTLED": bucket_gross[bucket_key(frontier)] += result["gross"]
                total += 1; variants.add(frontier["variant_id"]); pools.add(frontier["pool_id"])
        if next_roles is not None or pending_roles is not None or (total, no_bet, identities, role_rows, len(variants), len(pools)) != (EXPECTED_FRONTIERS, EXPECTED_NO_BET, EXPECTED_IDENTITIES, EXPECTED_ROLE_ROWS, EXPECTED_VARIANTS, 2659):
            raise RuntimeError("frozen denominator/cardinality drift")
        handles = gzip_writer(stage / "portfolio_settlement.csv.gz", SETTLEMENT_FIELDS); writer = handles[-1]
        with pre_tax.open(newline="", encoding="utf-8") as source:
            for row in csv.DictReader(source):
                gross = dec(row["gross_pre_tax_yuan"], "gross"); tax = allocated_tax(gross, bucket_gross[bucket_key(row)])
                after_tax = gross-tax; stake = dec(row["stake_yuan"], "stake") if row["settlement_status"] == "SETTLED" else Decimal(0)
                if row["settlement_status"] != "SETTLED": row["stake_yuan"] = money(Decimal(0))
                writer.writerow({**row, "issue_policy_gross_yuan": money(bucket_gross[bucket_key(row)]), "tax_yuan": money(tax), "after_tax_gross_yuan": money(after_tax), "pre_tax_net_yuan": money(gross-stake), "tax_adjusted_net_yuan": money(after_tax-stake)})
        close_gzip(handles); pre_tax.unlink()
        all_rows, robustness = summary(stage / "portfolio_settlement.csv.gz")
        compare_all, compare_robust = comparisons(all_rows), comparisons(robustness)
        write_csv(stage / "arm_comparison.csv", SUMMARY_FIELDS, all_rows)
        write_csv(stage / "robustness_summary.csv", SUMMARY_FIELDS, robustness)
        write_csv(stage / "threshold_curves.csv", POLICY_COMPARISON_FIELDS, compare_all + compare_robust)
        write_deltas(stage / "matched_pair_deltas.csv", stage / "portfolio_settlement.csv.gz")
        positives = [row for row in all_rows if row["tax_adjusted_roi"] and dec(row["tax_adjusted_roi"], "ROI") > 0]
        decision = {"decision": "POSITIVE_REQUIRES_STRICT_INDEPENDENT_EV" if positives else "NO_PROMOTION", "positive_all_rows": len(positives), "strict_independent_ev_required": bool(positives), "promotion_authorized": False, "rule": "Positive historical ROI requires strict independent EV; a negative or non-promotable finding receives light review."}
        (stage / "decision.json").write_text(json.dumps(decision, indent=2, sort_keys=True)+"\n", encoding="utf-8")
        card = {"issue": 127, "contract": CONTRACT, "runner_version": RUNNER_VERSION, "stage": "GATE_B_MATCHED_CANONICAL_OUTCOME_SETTLEMENT", "provenance": provenance, "frozen_matrix": {"frontier_rows": EXPECTED_FRONTIERS, "no_bet_rows": EXPECTED_NO_BET, "portfolio_identities": EXPECTED_IDENTITIES, "role_rows": EXPECTED_ROLE_ROWS, "variants": EXPECTED_VARIANTS}, "settlement_rule": "Hit iff every canonical result code is in the frozen arm's allowed codes; gross=2*0.65*product(canonical final winning SP) once on hit, else zero; final SP is uncapped.", "tax_rule": "Each variant/arm is a distinct paper policy. Aggregate its gross by native issue; when issue-policy gross >=10000, apply 20% tax to every winning portfolio gross in that bucket.", "availability_rule": "Every Gate-A row is retained. NO_BET_GATE_A and UNAVAILABLE_CANONICAL_OUTCOME both receive zero realized stake and are never replaced.", "chronology_rule": "Drawdown and miss streak sort first_kickoff_ts, pool_id, portfolio_id.", "scope": "historical research only; no purchase, production, or promotion authorization"}
        (stage / "settlement_card.json").write_text(json.dumps(card, indent=2, sort_keys=True)+"\n", encoding="utf-8")
        shutil.copyfile(__file__, stage / "settlement_runner.py")
        (stage / "README.md").write_text("# #127 Gate B\n\nCanonical one-shot settlement of the accepted matched FULL/prune v2 freeze. Run `python settlement_runner.py --output <new-dir>` from a compatible checkout.\n", encoding="utf-8")
        def uncompressed(path: Path) -> tuple[str, int]:
            digest, size = hashlib.sha256(), 0
            with gzip.open(path, "rb") as handle:
                for block in iter(lambda: handle.read(1 << 20), b""): digest.update(block); size += len(block)
            return digest.hexdigest(), size
        digest, size = uncompressed(stage / "portfolio_settlement.csv.gz")
        content = {"contract_version": "bj127-gateb-portable-content-v1", "gzip_payloads": {"portfolio_settlement.csv.gz": {"canonical_decompressed_sha256": digest, "canonical_decompressed_bytes": size}}, "non_compressed_controls": {item.name: sha256(item) for item in sorted(stage.iterdir()) if item.is_file() and item.name != "portfolio_settlement.csv.gz"}}
        (stage / "CONTENT_IDENTITY.json").write_text(json.dumps(content, indent=2, sort_keys=True)+"\n", encoding="utf-8")
        sums = {item.name: sha256(item) for item in sorted(stage.iterdir()) if item.is_file()}
        (stage / "SHA256SUMS.json").write_text(json.dumps(sums, indent=2, sort_keys=True)+"\n", encoding="utf-8")
        os.replace(stage, output)
        return {"manifest_sha256": sha256(output / "SHA256SUMS.json"), "content_identity_sha256": sha256(output / "CONTENT_IDENTITY.json"), "decision": decision, "all_rows": len(all_rows)}
    except Exception:
        shutil.rmtree(stage, ignore_errors=True); raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--output", type=Path, default=OUT)
    print(json.dumps(build(parser.parse_args().output.resolve()), sort_keys=True))


if __name__ == "__main__": main()
