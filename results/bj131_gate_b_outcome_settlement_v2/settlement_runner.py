#!/usr/bin/env python3
"""One-shot canonical Gate-B settlement for #131's accepted soft-cover freeze.

The accepted Gate-A v3 package fixes every selected seven, omitted code, seed,
and nested omitted-slab prefix.  This program reads that package and the
accepted canonical outcome join only.  It never reselects portfolios or tunes
the sleeve grid after outcomes are opened.
"""
from __future__ import annotations

import argparse
import csv
import errno
import gzip
import hashlib
import io
import json
import os
import shutil
import sqlite3
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
FREEZE = ROOT / "results" / "bj131_gate_a_preoutcome_v3"
OUTCOME_SOURCE = ROOT / "results" / "bj95_gate_b_outcome_settlement_v2r8"
OUT = ROOT / "results" / "bj131_gate_b_outcome_settlement_v2"

CONTRACT = "BJ-HIST-SOFT-COVER-N7-001"
RUNNER_VERSION = "bj131-gateb-v2"
EXPECTED_FREEZE_MANIFEST = "79d722a7919afb03916d0be57dd72c51c5ef2174fbf6b27cea2042ed6a65e53c"
EXPECTED_OUTCOME_MANIFEST = "fbbd3b53bd86f4bb0caff8f2587933cd6b0e4e7d04fb0f709bac934ec2a705cc"
EXPECTED_OUTCOME_PAYLOAD = "13d709d253c31519734dbf0447e6961ac8a6060772975d7461741224e5251a89"
ACTIVE, NO_BET, SEEDS, SLEEVES, SLAB = 90_215, 23_931, 3, 7, 729
FACTOR, UNIT, TAX_RATE, TAX_THRESHOLD = Decimal("0.65"), Decimal("2"), Decimal("0.20"), Decimal("10000")
CODES = ("3", "1", "0")
Q = Decimal("0.000001")
getcontext().prec = 128

BASE_FIELDS = (
    "issue", "fold", "year", "pool_id", "segment_index", "pool_disposition",
    "eligible_match_count", "pool_match_count", "first_kickoff_ts", "last_kickoff_ts",
    "window_hours", "terminal_remainder", "variant_id", "portfolio_id", "selected_match_ids",
    "deleted_match_id", "deleted_code", "deleted_probability", "descriptor_sha256",
)
ACTIVE_FIELDS = BASE_FIELDS + ("hard_prune_k", "hard_prune_stake_yuan", "full_k", "full_stake_yuan")
ORDER_FIELDS = ("variant_id", "portfolio_id", "seed_role", "seed", "ticket_order_scheme",
                "ticket_order_multiplier", "ticket_order_offset", "ticket_order_commitment")
NO_BET_FIELDS = BASE_FIELDS + ("reason",)
MATRIX_FIELDS = ("seed_role", "seed", "sleeve_label", "sleeve_fraction_nominal", "slab_tickets",
                 "sleeve_tickets", "formula_k", "stake_yuan", "stake_retention_vs_full",
                 "ticket_order_scheme", "expected_active_rows", "expected_no_bet_rows")
OUTCOME_FIELDS = ("match_id", "result_code", "winning_sp", "winning_sp_source", "settlement_quality", "has_trusted_settlement")
SETTLEMENT_FIELDS = BASE_FIELDS + (
    "seed_role", "seed", "sleeve_label", "sleeve_fraction_nominal", "sleeve_tickets", "formula_k",
    "stake_yuan", "settlement_status", "outcome_gap_count", "coverage_hit", "omitted_code_occurred",
    "omitted_slab_lex_index", "omitted_slab_rank", "truth_sequence", "final_winning_sp_product",
    "gross_pre_tax_yuan", "issue_policy_gross_yuan", "tax_yuan", "after_tax_gross_yuan",
    "pre_tax_net_yuan", "tax_adjusted_net_yuan", "winning_sp_sources", "reason",
)
SUMMARY_FIELDS = (
    "scope", "scope_value", "variant_id", "seed_role", "seed", "sleeve_label", "sleeve_fraction_nominal",
    "frontier_rows", "gate_a_available", "no_bet_gate_a", "unavailable_canonical_outcome", "settled",
    "stake_yuan", "gross_pre_tax_yuan", "pre_tax_net_yuan", "no_tax_roi", "tax_yuan", "after_tax_gross_yuan",
    "tax_adjusted_net_yuan", "tax_adjusted_roi", "coverage_hits", "coverage_hit_rate", "coverage_miss_rate",
    "omitted_code_occurrences", "omitted_code_rate", "settled_issue_count", "settled_pool_count",
    "max_drawdown_yuan", "longest_miss_streak", "best_payout_portfolio_id", "best_payout_gross_yuan",
    "ex_best_payout_net_yuan", "ex_best_payout_roi", "best_net_issue", "ex_best_issue_net_yuan",
    "ex_best_issue_roi", "positive_net_top_issue_share", "gross_top_issue_share",
)
CURVE_FIELDS = (
    "scope", "scope_value", "variant_id", "seed_role", "seed", "sleeve_label", "sleeve_fraction_nominal",
    "settled", "stake_yuan", "gross_pre_tax_yuan", "stake_retention_vs_full", "gross_retention_vs_full",
    "no_tax_roi", "tax_adjusted_roi", "no_tax_roi_delta_vs_full", "tax_adjusted_roi_delta_vs_full",
    "no_tax_roi_delta_vs_hard_prune", "tax_adjusted_roi_delta_vs_hard_prune", "coverage_hit_rate",
    "omitted_code_rate", "max_drawdown_yuan", "ex_best_payout_roi", "ex_best_issue_roi",
)
DELTA_FIELDS = (
    "variant_id", "portfolio_id", "issue", "fold", "year", "pool_id", "first_kickoff_ts", "seed_role", "seed",
    "sleeve_label", "sleeve_fraction_nominal", "settlement_status", "omitted_code_occurred", "coverage_hit",
    "full_coverage_hit", "hard_prune_coverage_hit", "formula_k", "stake_yuan", "full_stake_yuan",
    "hard_prune_stake_yuan", "gross_pre_tax_yuan", "full_gross_pre_tax_yuan", "hard_prune_gross_pre_tax_yuan",
    "tax_adjusted_net_yuan", "full_tax_adjusted_net_yuan", "hard_prune_tax_adjusted_net_yuan",
    "tax_net_delta_vs_full", "tax_net_delta_vs_hard_prune",
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
    if declared != actual:
        raise RuntimeError(f"manifest coverage drift: {bundle}")
    return declared


def validate_inputs() -> dict[str, str]:
    freeze = manifest(FREEZE, EXPECTED_FREEZE_MANIFEST)
    card = json.loads((FREEZE / "gate_a_card.json").read_text(encoding="utf-8"))
    denominator = card.get("denominator", {})
    if (card.get("contract") != CONTRACT or card.get("stage") != "GATE_A_OUTCOME_UNEXPOSED_SOFT_COVER_FREEZE"
            or denominator.get("active_base_rows") != ACTIVE or denominator.get("no_bet_base_rows") != NO_BET
            or denominator.get("seed_count") != SEEDS or denominator.get("sleeve_count") != SLEEVES
            or denominator.get("logical_active_matrix_rows") != ACTIVE * SEEDS * SLEEVES
            or denominator.get("logical_no_bet_matrix_rows") != NO_BET * SEEDS * SLEEVES):
        raise RuntimeError("unaccepted Gate-A contract/cardinality")
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
                or row["has_trusted_settlement"] != "1" or dec(row["winning_sp"], "winning_sp") <= 0):
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


def matrix() -> list[dict[str, str]]:
    with (FREEZE / "sleeve_matrix.csv").open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != MATRIX_FIELDS:
            raise RuntimeError("sleeve-matrix schema drift")
        rows = list(reader)
    if len(rows) != SEEDS * SLEEVES:
        raise RuntimeError("sleeve-matrix cardinality drift")
    labels = {row["sleeve_label"] for row in rows}
    if labels != {"S00_HARD_PRUNE", "S05_SOFT_COVER", "S10_SOFT_COVER", "S20_SOFT_COVER", "S33_SOFT_COVER", "S50_SOFT_COVER", "S100_FULL"}:
        raise RuntimeError("sleeve labels drift")
    if any(int(row["slab_tickets"]) != SLAB or int(row["formula_k"]) != 1458 + int(row["sleeve_tickets"]) for row in rows):
        raise RuntimeError("sleeve geometry drift")
    return rows


def orders() -> dict[tuple[str, str, str], dict[str, str]]:
    result: dict[tuple[str, str, str], dict[str, str]] = {}
    with gzip.open(FREEZE / "portfolio_seed_order.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != ORDER_FIELDS:
            raise RuntimeError("seed-order schema drift")
        for row in reader:
            key = row["variant_id"], row["portfolio_id"], row["seed"]
            if key in result or int(row["ticket_order_multiplier"]) % 3 == 0 or not 0 <= int(row["ticket_order_offset"]) < SLAB:
                raise RuntimeError("seed-order geometry drift")
            result[key] = row
    if len(result) != ACTIVE * SEEDS:
        raise RuntimeError("seed-order cardinality drift")
    return result


def active_rows():
    with gzip.open(FREEZE / "portfolio_base.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != ACTIVE_FIELDS:
            raise RuntimeError("active-base schema drift")
        for row in reader:
            if int(row["hard_prune_k"]) != 1458 or int(row["full_k"]) != 2187:
                raise RuntimeError("base ticket geometry drift")
            yield row


def no_bet_rows():
    with gzip.open(FREEZE / "no_bet_control.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != NO_BET_FIELDS:
            raise RuntimeError("no-bet schema drift")
        yield from reader


def outcome_geometry(base: dict[str, str], outcomes: dict[str, dict[str, str]]) -> dict[str, object]:
    match_ids = base["selected_match_ids"].split(";")
    if len(match_ids) != 7 or len(set(match_ids)) != 7 or base["deleted_match_id"] not in match_ids or base["deleted_code"] not in CODES:
        raise RuntimeError("frozen seven/deletion geometry drift")
    missing = [match_id for match_id in match_ids if match_id not in outcomes]
    if missing:
        return {"status": "UNAVAILABLE_CANONICAL_OUTCOME", "gap": len(missing), "truth": "", "product": Decimal(0),
                "sources": "", "omitted": "", "lex": "", "rank_inputs": None}
    truth, product, sources, digits = [], Decimal(1), set(), []
    for match_id in match_ids:
        row = outcomes[match_id]
        code = row["result_code"]
        truth.append(code); product *= dec(row["winning_sp"], "winning_sp"); sources.add(row["winning_sp_source"])
        if match_id != base["deleted_match_id"]:
            digits.append(CODES.index(code))
    omitted = outcomes[base["deleted_match_id"]]["result_code"] == base["deleted_code"]
    lex = 0
    for digit in digits:
        lex = lex * 3 + digit
    if not 0 <= lex < SLAB:
        raise RuntimeError("omitted-slab lex geometry drift")
    return {"status": "SETTLED", "gap": 0, "truth": "".join(truth), "product": product,
            "sources": ";".join(sorted(sources)), "omitted": "YES" if omitted else "NO", "lex": lex, "rank_inputs": True}


def event_rows(outcomes: dict[str, dict[str, str]], order_map: dict[tuple[str, str, str], dict[str, str]], matrix_rows: list[dict[str, str]]):
    by_seed: dict[str, list[dict[str, str]]] = defaultdict(list)
    for item in matrix_rows:
        by_seed[item["seed"]].append(item)
    for rows in by_seed.values():
        rows.sort(key=lambda row: int(row["sleeve_tickets"]))
    total = 0
    for base in active_rows():
        total += 1
        geometry = outcome_geometry(base, outcomes)
        for seed, sleeves in by_seed.items():
            order = order_map[(base["variant_id"], base["portfolio_id"], seed)]
            rank = ""
            if geometry["status"] == "SETTLED" and geometry["omitted"] == "YES":
                rank = str((int(order["ticket_order_multiplier"]) * int(geometry["lex"]) + int(order["ticket_order_offset"])) % SLAB)
            for sleeve in sleeves:
                added = int(sleeve["sleeve_tickets"])
                hit = geometry["status"] == "SETTLED" and (geometry["omitted"] == "NO" or int(rank) < added)
                gross = UNIT * FACTOR * geometry["product"] if hit else Decimal(0)
                yield {**base, "seed_role": sleeve["seed_role"], "seed": seed, "sleeve_label": sleeve["sleeve_label"],
                       "sleeve_fraction_nominal": sleeve["sleeve_fraction_nominal"], "sleeve_tickets": sleeve["sleeve_tickets"],
                       "formula_k": sleeve["formula_k"], "stake_yuan": sleeve["stake_yuan"], "settlement_status": geometry["status"],
                       "outcome_gap_count": str(geometry["gap"]), "coverage_hit": "YES" if hit else ("NO" if geometry["status"] == "SETTLED" else ""),
                       "omitted_code_occurred": geometry["omitted"], "omitted_slab_lex_index": str(geometry["lex"]),
                       "omitted_slab_rank": rank, "truth_sequence": geometry["truth"], "final_winning_sp_product": money(geometry["product"]),
                       "gross_pre_tax_yuan": money(gross), "winning_sp_sources": geometry["sources"], "reason": ""}
    if total != ACTIVE:
        raise RuntimeError("active-base denominator drift")


def no_bet_events(matrix_rows: list[dict[str, str]]):
    base_rows = list(no_bet_rows())
    if len(base_rows) != NO_BET:
        raise RuntimeError("no-bet denominator drift")
    for base in base_rows:
        for sleeve in matrix_rows:
            yield {**base, "seed_role": sleeve["seed_role"], "seed": sleeve["seed"], "sleeve_label": sleeve["sleeve_label"],
                   "sleeve_fraction_nominal": sleeve["sleeve_fraction_nominal"], "sleeve_tickets": sleeve["sleeve_tickets"],
                   "formula_k": "0", "stake_yuan": "0.000000", "settlement_status": "NO_BET_GATE_A",
                   "outcome_gap_count": "0", "coverage_hit": "", "omitted_code_occurred": "", "omitted_slab_lex_index": "",
                   "omitted_slab_rank": "", "truth_sequence": "", "final_winning_sp_product": "0.000000",
                   "gross_pre_tax_yuan": "0.000000", "winning_sp_sources": "", "reason": base["reason"]}


def bucket_key(row: dict[str, str]) -> tuple[str, str, str, str]:
    return row["issue"], row["variant_id"], row["seed"], row["sleeve_label"]


def tax_for(gross: Decimal, bucket_gross: Decimal) -> Decimal:
    return gross * TAX_RATE if bucket_gross >= TAX_THRESHOLD else Decimal(0)


@dataclass
class Metric:
    variant: str; seed_role: str; seed: str; sleeve: str; fraction: str; scope: str; value: str
    rows: int = 0; available: int = 0; no_bet: int = 0; unavailable: int = 0; settled: int = 0; hits: int = 0; omitted: int = 0
    stake: Decimal = Decimal(0); gross: Decimal = Decimal(0); tax: Decimal = Decimal(0); net: Decimal = Decimal(0)
    issue_net: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal)); issue_stake: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal)); issue_gross: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal)); pools: set[str] = field(default_factory=set)
    def add(self, row: dict[str, str]) -> None:
        self.rows += 1; status = row["settlement_status"]
        if row["portfolio_id"]: self.available += 1
        if status == "NO_BET_GATE_A": self.no_bet += 1; return
        if status == "UNAVAILABLE_CANONICAL_OUTCOME": self.unavailable += 1; return
        if status != "SETTLED": raise RuntimeError(f"unknown settlement status {status}")
        self.settled += 1; self.hits += row["coverage_hit"] == "YES"; self.omitted += row["omitted_code_occurred"] == "YES"; self.pools.add(row["pool_id"])
        stake, gross, tax, net = (dec(row[field], field) for field in ("stake_yuan", "gross_pre_tax_yuan", "tax_yuan", "tax_adjusted_net_yuan"))
        self.stake += stake; self.gross += gross; self.tax += tax; self.net += net
        self.issue_net[row["issue"]] += net; self.issue_stake[row["issue"]] += stake; self.issue_gross[row["issue"]] += gross
    def output(self) -> dict[str, object]:
        best_issue = max(self.issue_net, key=self.issue_net.get, default="")
        best_issue_net, best_issue_stake = self.issue_net.get(best_issue, Decimal(0)), self.issue_stake.get(best_issue, Decimal(0))
        positives, gross_total = [max(Decimal(0), item) for item in self.issue_net.values()], sum(self.issue_gross.values(), Decimal(0))
        positive_total = sum(positives, Decimal(0)); pre_net = self.gross-self.stake
        return {"scope": self.scope, "scope_value": self.value, "variant_id": self.variant, "seed_role": self.seed_role, "seed": self.seed, "sleeve_label": self.sleeve, "sleeve_fraction_nominal": self.fraction,
                "frontier_rows": self.rows, "gate_a_available": self.available, "no_bet_gate_a": self.no_bet, "unavailable_canonical_outcome": self.unavailable, "settled": self.settled,
                "stake_yuan": money(self.stake), "gross_pre_tax_yuan": money(self.gross), "pre_tax_net_yuan": money(pre_net), "no_tax_roi": ratio(pre_net/self.stake if self.stake else None), "tax_yuan": money(self.tax), "after_tax_gross_yuan": money(self.gross-self.tax), "tax_adjusted_net_yuan": money(self.net), "tax_adjusted_roi": ratio(self.net/self.stake if self.stake else None),
                "coverage_hits": self.hits, "coverage_hit_rate": ratio(Decimal(self.hits)/self.settled if self.settled else None), "coverage_miss_rate": ratio(Decimal(self.settled-self.hits)/self.settled if self.settled else None), "omitted_code_occurrences": self.omitted, "omitted_code_rate": ratio(Decimal(self.omitted)/self.settled if self.settled else None), "settled_issue_count": len(self.issue_net), "settled_pool_count": len(self.pools),
                "max_drawdown_yuan": "", "longest_miss_streak": "", "best_payout_portfolio_id": "", "best_payout_gross_yuan": "", "ex_best_payout_net_yuan": "", "ex_best_payout_roi": "", "best_net_issue": best_issue, "ex_best_issue_net_yuan": money(self.net-best_issue_net), "ex_best_issue_roi": ratio((self.net-best_issue_net)/(self.stake-best_issue_stake) if self.stake > best_issue_stake else None), "positive_net_top_issue_share": ratio(max(positives, default=Decimal(0))/positive_total if positive_total else None), "gross_top_issue_share": ratio(max(self.issue_gross.values(), default=Decimal(0))/gross_total if gross_total else None)}


def write_csv(path: Path, fields: tuple[str, ...], rows) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n"); writer.writeheader(); writer.writerows(rows)


def settlement_record(values: dict[str, object]) -> dict[str, object]:
    """Drop Gate-A-only helper columns before emitting the fixed Gate-B schema."""
    return {field: values.get(field, "") for field in SETTLEMENT_FIELDS}


def summarize(path: Path) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    all_m: dict[tuple[str, str, str, str], Metric] = {}; year_m: dict[tuple[str, str, str, str, str], Metric] = {}; fold_m: dict[tuple[str, str, str, str, str], Metric] = {}; years: set[str] = set()
    def add(target, key, scope, value, row):
        target.setdefault(key, Metric(row["variant_id"], row["seed_role"], row["seed"], row["sleeve_label"], row["sleeve_fraction_nominal"], scope, value)).add(row)
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            key = row["variant_id"], row["seed_role"], row["seed"], row["sleeve_label"]; years.add(row["year"])
            add(all_m, key, "ALL", "ALL", row); add(year_m, (row["year"], *key), "YEAR", row["year"], row); add(fold_m, (row["fold"], *key), "FOLD", row["fold"], row)
    all_rows = [metric.output() for _, metric in sorted(all_m.items())]
    robust = [metric.output() for _, metric in sorted(year_m.items())] + [metric.output() for _, metric in sorted(fold_m.items())]
    for omitted in sorted(years):
        loyo: dict[tuple[str, str, str, str], Metric] = {}
        with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row["year"] != omitted:
                    key = row["variant_id"], row["seed_role"], row["seed"], row["sleeve_label"]
                    add(loyo, key, "LEAVE_ONE_YEAR_OUT", omitted, row)
        robust.extend(metric.output() for _, metric in sorted(loyo.items()))
    return all_rows, robust


def add_all_event_stats(path: Path, all_rows: list[dict[str, object]], scratch: Path) -> None:
    """Compute exact ALL-scope path metrics with a disk-backed chronological sort.

    The normalized matrix has 1.89m active rows.  Keeping duplicate Python
    timelines for all/year/fold summaries is not a durable execution method;
    this bounded SQLite scratch table preserves the same event ordering without
    becoming an output or part of the immutable package.
    """
    index = {(row["variant_id"], row["seed_role"], row["seed"], row["sleeve_label"]): row for row in all_rows}
    db_path = scratch / "_all_event_stats.sqlite"
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript("PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF; PRAGMA temp_store=FILE;"
                               "CREATE TABLE event (variant TEXT, seed_role TEXT, seed TEXT, sleeve TEXT, kickoff TEXT, pool TEXT, portfolio TEXT, net TEXT, hit INTEGER, gross TEXT, stake TEXT);")
        pending = []
        with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row["settlement_status"] != "SETTLED":
                    continue
                pending.append((row["variant_id"], row["seed_role"], row["seed"], row["sleeve_label"], row["first_kickoff_ts"], row["pool_id"], row["portfolio_id"], row["tax_adjusted_net_yuan"], int(row["coverage_hit"] == "YES"), row["gross_pre_tax_yuan"], row["stake_yuan"]))
                if len(pending) == 10_000:
                    connection.executemany("INSERT INTO event VALUES (?,?,?,?,?,?,?,?,?,?,?)", pending); pending.clear()
        if pending:
            connection.executemany("INSERT INTO event VALUES (?,?,?,?,?,?,?,?,?,?,?)", pending)
        connection.execute("CREATE INDEX event_order ON event(variant,seed_role,seed,sleeve,kickoff,pool,portfolio)")
        current = None; cumulative = peak = drawdown = Decimal(0); streak = longest = 0
        best_gross = Decimal(-1); best_net = best_stake = Decimal(0); best_id = ""
        def flush() -> None:
            if current is None:
                return
            row = index[current]
            total_net, total_stake = dec(row["tax_adjusted_net_yuan"], "net"), dec(row["stake_yuan"], "stake")
            row["max_drawdown_yuan"] = money(drawdown); row["longest_miss_streak"] = longest
            row["best_payout_portfolio_id"] = best_id; row["best_payout_gross_yuan"] = money(max(best_gross, Decimal(0)))
            row["ex_best_payout_net_yuan"] = money(total_net-best_net)
            row["ex_best_payout_roi"] = ratio((total_net-best_net)/(total_stake-best_stake) if total_stake > best_stake else None)
        query = "SELECT variant,seed_role,seed,sleeve,portfolio,net,hit,gross,stake FROM event ORDER BY variant,seed_role,seed,sleeve,kickoff,pool,portfolio"
        for variant, role, seed, sleeve, portfolio, net_s, hit, gross_s, stake_s in connection.execute(query):
            key = variant, role, seed, sleeve
            if current != key:
                flush(); current = key; cumulative = peak = drawdown = Decimal(0); streak = longest = 0; best_gross = Decimal(-1); best_net = best_stake = Decimal(0); best_id = ""
            net, gross, stake = dec(net_s, "event net"), dec(gross_s, "event gross"), dec(stake_s, "event stake")
            cumulative += net; peak = max(peak, cumulative); drawdown = max(drawdown, peak-cumulative)
            streak = 0 if hit else streak+1; longest = max(longest, streak)
            if gross > best_gross:
                best_gross, best_net, best_stake, best_id = gross, net, stake, portfolio
        flush()
        if len(index) != len(all_rows) or any(not row["max_drawdown_yuan"] for row in all_rows):
            raise RuntimeError("ALL event-stat coverage drift")
    finally:
        connection.close()
        if db_path.exists():
            db_path.unlink()


def response(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    indexed = {(row["scope"], row["scope_value"], row["variant_id"], row["seed"], row["sleeve_label"]): row for row in rows}
    result = []
    for key, row in sorted(indexed.items()):
        scope, value, variant, seed, _ = key; full = indexed[(scope, value, variant, seed, "S100_FULL")]; hard = indexed[(scope, value, variant, seed, "S00_HARD_PRUNE")]
        def d(item, field): return dec(item[field], field)
        result.append({"scope": scope, "scope_value": value, "variant_id": variant, "seed_role": row["seed_role"], "seed": seed, "sleeve_label": row["sleeve_label"], "sleeve_fraction_nominal": row["sleeve_fraction_nominal"], "settled": row["settled"], "stake_yuan": row["stake_yuan"], "gross_pre_tax_yuan": row["gross_pre_tax_yuan"], "stake_retention_vs_full": ratio(d(row,"stake_yuan")/d(full,"stake_yuan") if d(full,"stake_yuan") else None), "gross_retention_vs_full": ratio(d(row,"gross_pre_tax_yuan")/d(full,"gross_pre_tax_yuan") if d(full,"gross_pre_tax_yuan") else None), "no_tax_roi": row["no_tax_roi"], "tax_adjusted_roi": row["tax_adjusted_roi"], "no_tax_roi_delta_vs_full": ratio(d(row,"no_tax_roi")-d(full,"no_tax_roi")) if row["no_tax_roi"] and full["no_tax_roi"] else "", "tax_adjusted_roi_delta_vs_full": ratio(d(row,"tax_adjusted_roi")-d(full,"tax_adjusted_roi")) if row["tax_adjusted_roi"] and full["tax_adjusted_roi"] else "", "no_tax_roi_delta_vs_hard_prune": ratio(d(row,"no_tax_roi")-d(hard,"no_tax_roi")) if row["no_tax_roi"] and hard["no_tax_roi"] else "", "tax_adjusted_roi_delta_vs_hard_prune": ratio(d(row,"tax_adjusted_roi")-d(hard,"tax_adjusted_roi")) if row["tax_adjusted_roi"] and hard["tax_adjusted_roi"] else "", "coverage_hit_rate": row["coverage_hit_rate"], "omitted_code_rate": row["omitted_code_rate"], "max_drawdown_yuan": row["max_drawdown_yuan"], "ex_best_payout_roi": row["ex_best_payout_roi"], "ex_best_issue_roi": row["ex_best_issue_roi"]})
    return result


def write_deltas(path: Path, settlement: Path) -> None:
    handles = gzip_writer(path, DELTA_FIELDS); writer = handles[-1]; pending: list[dict[str, str]] = []
    def flush(rows):
        if len(rows) != SLEEVES: raise RuntimeError("sleeve pairing drift")
        by_label = {row["sleeve_label"]: row for row in rows}; full, hard = by_label["S100_FULL"], by_label["S00_HARD_PRUNE"]
        if set(by_label) != {"S00_HARD_PRUNE", "S05_SOFT_COVER", "S10_SOFT_COVER", "S20_SOFT_COVER", "S33_SOFT_COVER", "S50_SOFT_COVER", "S100_FULL"}: raise RuntimeError("sleeve pairing labels drift")
        for row in rows:
            writer.writerow({"variant_id":row["variant_id"],"portfolio_id":row["portfolio_id"],"issue":row["issue"],"fold":row["fold"],"year":row["year"],"pool_id":row["pool_id"],"first_kickoff_ts":row["first_kickoff_ts"],"seed_role":row["seed_role"],"seed":row["seed"],"sleeve_label":row["sleeve_label"],"sleeve_fraction_nominal":row["sleeve_fraction_nominal"],"settlement_status":row["settlement_status"],"omitted_code_occurred":row["omitted_code_occurred"],"coverage_hit":row["coverage_hit"],"full_coverage_hit":full["coverage_hit"],"hard_prune_coverage_hit":hard["coverage_hit"],"formula_k":row["formula_k"],"stake_yuan":row["stake_yuan"],"full_stake_yuan":full["stake_yuan"],"hard_prune_stake_yuan":hard["stake_yuan"],"gross_pre_tax_yuan":row["gross_pre_tax_yuan"],"full_gross_pre_tax_yuan":full["gross_pre_tax_yuan"],"hard_prune_gross_pre_tax_yuan":hard["gross_pre_tax_yuan"],"tax_adjusted_net_yuan":row["tax_adjusted_net_yuan"],"full_tax_adjusted_net_yuan":full["tax_adjusted_net_yuan"],"hard_prune_tax_adjusted_net_yuan":hard["tax_adjusted_net_yuan"],"tax_net_delta_vs_full":money(dec(row["tax_adjusted_net_yuan"],"net")-dec(full["tax_adjusted_net_yuan"],"full net")),"tax_net_delta_vs_hard_prune":money(dec(row["tax_adjusted_net_yuan"],"net")-dec(hard["tax_adjusted_net_yuan"],"hard net"))})
    with gzip.open(settlement, "rt", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["settlement_status"] != "SETTLED": continue
            key = row["variant_id"], row["portfolio_id"], row["seed"]
            if pending and (pending[0]["variant_id"], pending[0]["portfolio_id"], pending[0]["seed"]) != key: flush(pending); pending = []
            pending.append(row)
    if pending: flush(pending)
    close_gzip(handles)


def build(output: Path) -> dict[str, object]:
    if output.exists(): raise RuntimeError(f"refusing immutable overwrite: {output}")
    # The settlement's exact path metrics need a bounded disk sort.  Keep its
    # scratch beside repository results rather than beside a caller-selected
    # output (which is commonly a capacity-limited /tmp filesystem).
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".bj131_gateb_", dir=ROOT / "results"))
    try:
        provenance = validate_inputs(); outcomes = load_outcomes(); matrix_rows = matrix(); order_map = orders(); bucket: dict[tuple[str,str,str,str], Decimal] = defaultdict(Decimal)
        for row in event_rows(outcomes, order_map, matrix_rows):
            bucket[bucket_key(row)] += dec(row["gross_pre_tax_yuan"], "gross")
        handles = gzip_writer(stage / "portfolio_settlement.csv.gz", SETTLEMENT_FIELDS); writer = handles[-1]
        for row in event_rows(outcomes, order_map, matrix_rows):
            gross = dec(row["gross_pre_tax_yuan"], "gross"); tax = tax_for(gross, bucket[bucket_key(row)]); stake = dec(row["stake_yuan"], "stake") if row["settlement_status"] == "SETTLED" else Decimal(0)
            writer.writerow(settlement_record({**row, "stake_yuan":money(stake), "issue_policy_gross_yuan":money(bucket[bucket_key(row)]), "tax_yuan":money(tax), "after_tax_gross_yuan":money(gross-tax), "pre_tax_net_yuan":money(gross-stake), "tax_adjusted_net_yuan":money(gross-tax-stake)}))
        for row in no_bet_events(matrix_rows):
            writer.writerow(settlement_record({**row, "issue_policy_gross_yuan":"0.000000", "tax_yuan":"0.000000", "after_tax_gross_yuan":"0.000000", "pre_tax_net_yuan":"0.000000", "tax_adjusted_net_yuan":"0.000000"}))
        close_gzip(handles)
        all_rows, robust = summarize(stage / "portfolio_settlement.csv.gz"); add_all_event_stats(stage / "portfolio_settlement.csv.gz", all_rows, stage); curve = response(all_rows + robust)
        write_csv(stage / "sleeve_summary.csv", SUMMARY_FIELDS, all_rows); write_csv(stage / "robustness_summary.csv", SUMMARY_FIELDS, robust); write_csv(stage / "sleeve_response_curve.csv", CURVE_FIELDS, curve); write_deltas(stage / "matched_sleeve_deltas.csv.gz", stage / "portfolio_settlement.csv.gz")
        positives = [row for row in all_rows if row["tax_adjusted_roi"] and dec(row["tax_adjusted_roi"], "ROI") > 0]
        decision = {"decision":"POSITIVE_REQUIRES_STRICT_INDEPENDENT_EV" if positives else "NO_PROMOTION", "positive_all_rows":len(positives), "promotion_authorized":False, "strict_independent_ev_required":bool(positives), "rule":"Positive historical ROI requires strict independent EV; a negative or non-promotable finding receives light review."}
        (stage / "decision.json").write_text(json.dumps(decision, indent=2, sort_keys=True)+"\n", encoding="utf-8")
        card = {"issue":131,"contract":CONTRACT,"runner_version":RUNNER_VERSION,"stage":"GATE_B_SOFT_COVER_CANONICAL_OUTCOME_SETTLEMENT","provenance":provenance,"denominator":{"active_base_rows":ACTIVE,"no_bet_base_rows":NO_BET,"seed_count":SEEDS,"sleeve_count":SLEEVES,"logical_active_rows":ACTIVE*SEEDS*SLEEVES,"logical_no_bet_rows":NO_BET*SEEDS*SLEEVES},"tax":"20% of winning gross when same issue+variant+seed+sleeve gross reaches ¥10,000; otherwise zero","settlement":"one ¥2 sequence pays ¥2×0.65×product(final winning SP) iff coverage includes the truth","outcome_boundary":"The outcome join is opened only after Gate-A and canonical-outcome manifests validate. No portfolio, seed, or sleeve is regenerated."}
        (stage / "settlement_card.json").write_text(json.dumps(card, indent=2, sort_keys=True)+"\n", encoding="utf-8")
        shutil.copyfile(__file__, stage / "settlement_runner.py")
        (stage / "README.md").write_text("# #131 Gate B\n\nCanonical settlement of the accepted soft-cover freeze. Run `python settlement_runner.py --output <new-dir>` and compare portable content identity, not compressed bytes.\n", encoding="utf-8")
        def decompressed(path: Path):
            digest, size = hashlib.sha256(), 0
            with gzip.open(path, "rb") as handle:
                for block in iter(lambda: handle.read(1 << 20), b""): digest.update(block); size += len(block)
            return digest.hexdigest(), size
        gz = {name:{"canonical_decompressed_sha256":decompressed(stage/name)[0],"canonical_decompressed_bytes":decompressed(stage/name)[1]} for name in ("portfolio_settlement.csv.gz","matched_sleeve_deltas.csv.gz")}
        content = {"contract_version":"bj131-gateb-portable-content-v1","gzip_payloads":gz,"non_compressed_controls":{path.name:sha256(path) for path in sorted(stage.iterdir()) if path.is_file() and path.suffix != ".gz"}}
        (stage / "CONTENT_IDENTITY.json").write_text(json.dumps(content, indent=2, sort_keys=True)+"\n", encoding="utf-8")
        sums = {path.name:sha256(path) for path in sorted(stage.iterdir()) if path.is_file()}; (stage / "SHA256SUMS.json").write_text(json.dumps(sums, indent=2, sort_keys=True)+"\n", encoding="utf-8")
        try:
            os.replace(stage, output)
        except OSError as error:
            if error.errno != errno.EXDEV:
                raise
            shutil.move(str(stage), str(output))
        return {"manifest_sha256":sha256(output/"SHA256SUMS.json"),"content_identity_sha256":sha256(output/"CONTENT_IDENTITY.json"),"active_logical_rows":ACTIVE*SEEDS*SLEEVES,"no_bet_logical_rows":NO_BET*SEEDS*SLEEVES}
    except Exception:
        shutil.rmtree(stage, ignore_errors=True); raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--output", type=Path, default=OUT)
    print(json.dumps(build(parser.parse_args().output.resolve()), sort_keys=True))


if __name__ == "__main__": main()
