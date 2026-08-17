#!/usr/bin/env python3
"""Settle #121's accepted expected-SP / low-probability Gate-A matrix.

The runner consumes exactly the immutable 9 x 13 x 2,659 Gate-A frontier and
one authenticated canonical outcome payload.  It never changes a threshold,
arm, selected match, or allowed-code set after outcomes are visible.
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


def repository_root(anchor: Path) -> Path:
    for candidate in (anchor.resolve().parent, *anchor.resolve().parents):
        if (candidate / ".git").exists():
            return candidate
    raise RuntimeError("repository root not found")


ROOT = repository_root(Path(__file__))
GATE_A = ROOT / "results/bj121_gate_a_preoutcome_v3"
OUTCOMES = ROOT / "results/bj95_gate_b_outcome_settlement_v2r8"
OUTPUT = ROOT / "results/bj121_gate_b_outcome_settlement_v1"

CONTRACT = "BJ-HIST-EXPECTED-SP-LOWP-001"
RUNNER_VERSION = "bj121-gateb-v1"
EXPECTED_GATE_A_MANIFEST = "acef123c062c4deafd637941ea4ebe5cb165078dfdf0bd1998cc2b6e00446eee"
EXPECTED_GATE_A_CONTENT_IDENTITY = "9dd4eaeefd9aa76ec976108469bfdd4ae230bc6129c7c4574191d8bf9e9f1a76"
EXPECTED_OUTCOME_MANIFEST = "fbbd3b53bd86f4bb0caff8f2587933cd6b0e4e7d04fb0f709bac934ec2a705cc"
EXPECTED_OUTCOME_PAYLOAD = "13d709d253c31519734dbf0447e6961ac8a6060772975d7461741224e5251a89"
EXPECTED_FRONTIERS = 311_103
EXPECTED_VARIANTS = 9
EXPECTED_ARMS = 13
EXPECTED_POOLS = 2_659

FACTOR = Decimal("0.65")
UNIT_STAKE = Decimal("2")
TAX_RATE = Decimal("0.20")
TAX_THRESHOLD = Decimal("10000")
Q = Decimal("0.000001")
getcontext().prec = 128

FRONTIER_FIELDS = (
    "issue", "fold", "year", "pool_id", "segment_index", "pool_disposition",
    "eligible_match_count", "pool_match_count", "first_kickoff_ts", "last_kickoff_ts",
    "window_hours", "terminal_remainder", "variant_id", "arm", "candidate_match_count",
    "selected_n", "selected_match_ids", "role_codes", "full_legs", "double_legs",
    "single_legs", "gm_e_sp", "expected_portfolio_mass", "formula_k", "stake_yuan",
    "g_be_pre_tax", "disposition", "reason", "descriptor_sha256",
)
OUTCOME_FIELDS = (
    "match_id", "result_code", "winning_sp", "winning_sp_source",
    "settlement_quality", "has_trusted_settlement",
)
SETTLEMENT_FIELDS = FRONTIER_FIELDS + (
    "settlement_status", "outcome_gap_count", "coverage_hit", "excluded_outcome_hits",
    "truth_sequence", "final_winning_sp_product", "gross_pre_tax_yuan",
    "issue_policy_gross_yuan", "tax_yuan", "after_tax_gross_yuan",
    "tax_adjusted_net_yuan", "winning_sp_sources",
)
SUMMARY_FIELDS = (
    "scope", "scope_value", "variant_id", "e_sp_min", "gm_e_sp_min", "low_p_max",
    "arm", "frontier_rows", "gate_a_available", "no_bet_gate_a",
    "unavailable_canonical_outcome", "settled", "selected_n_total", "total_tickets",
    "stake_yuan", "coverage_hits", "coverage_hit_rate", "excluded_outcome_hits",
    "gross_pre_tax_yuan", "tax_yuan", "after_tax_gross_yuan", "tax_adjusted_net_yuan",
    "tax_adjusted_roi", "max_drawdown_yuan", "longest_losing_streak",
    "best_payout_pool_id", "best_payout_gross_yuan", "ex_best_payout_net_yuan",
    "ex_best_payout_roi", "best_net_issue", "ex_best_issue_net_yuan",
    "ex_best_issue_roi", "positive_net_top_issue_share", "gross_top_issue_share",
    "settled_issue_count", "settled_pool_count",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def decompressed_identity(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with gzip.open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


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


def verified_manifest(bundle: Path, expected: str) -> dict[str, str]:
    path = bundle / "SHA256SUMS.json"
    if sha256(path) != expected:
        raise RuntimeError(f"unaccepted manifest: {bundle}")
    declared = json.loads(path.read_text(encoding="utf-8"))
    actual = {
        item.name: sha256(item)
        for item in bundle.iterdir()
        if item.is_file() and item.name != path.name
    }
    if not isinstance(declared, dict) or declared != actual:
        raise RuntimeError(f"manifest coverage drift: {bundle}")
    return declared


def validate_inputs() -> dict[str, str]:
    gate_a = verified_manifest(GATE_A, EXPECTED_GATE_A_MANIFEST)
    if gate_a.get("CONTENT_IDENTITY.json") != EXPECTED_GATE_A_CONTENT_IDENTITY:
        raise RuntimeError("Gate-A content identity drift")
    card = json.loads((GATE_A / "gate_a_card.json").read_text(encoding="utf-8"))
    if card.get("contract") != CONTRACT or card.get("denominator", {}).get("frontier_rows") != EXPECTED_FRONTIERS:
        raise RuntimeError("unexpected Gate-A contract or denominator")
    if len(card.get("variants", {})) != EXPECTED_VARIANTS or len(card.get("arms", [])) != EXPECTED_ARMS:
        raise RuntimeError("Gate-A matrix geometry drift")
    outcome = verified_manifest(OUTCOMES, EXPECTED_OUTCOME_MANIFEST)
    if outcome.get("canonical_outcome_join.csv") != EXPECTED_OUTCOME_PAYLOAD:
        raise RuntimeError("canonical outcome payload drift")
    return {
        "gate_a_manifest_sha256": EXPECTED_GATE_A_MANIFEST,
        "gate_a_content_identity_sha256": EXPECTED_GATE_A_CONTENT_IDENTITY,
        "outcome_manifest_sha256": EXPECTED_OUTCOME_MANIFEST,
        "canonical_outcome_join_sha256": EXPECTED_OUTCOME_PAYLOAD,
    }


def load_outcomes() -> dict[str, dict[str, str]]:
    with (OUTCOMES / "canonical_outcome_join.csv").open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != OUTCOME_FIELDS:
            raise RuntimeError("canonical outcome schema drift")
        rows = list(reader)
    result = {row["match_id"]: row for row in rows}
    if len(result) != len(rows):
        raise RuntimeError("duplicate canonical outcome match id")
    for row in result.values():
        if (row["result_code"] not in {"3", "1", "0"}
                or row["settlement_quality"] != "trusted"
                or row["has_trusted_settlement"] != "1"
                or dec(row["winning_sp"], "winning SP") <= 0):
            raise RuntimeError(f"untrusted canonical outcome: {row['match_id']}")
    return result


def parse_roles(value: str) -> list[tuple[str, str, str]]:
    if not value:
        return []
    roles = []
    for item in value.split(";"):
        parts = item.split(":")
        if len(parts) != 3:
            raise RuntimeError(f"invalid frozen role: {item}")
        match_id, role, allowed = parts
        if role not in {"FULL", "DOUBLE", "SINGLE"} or not allowed or any(code not in "310" for code in allowed):
            raise RuntimeError(f"invalid frozen role geometry: {item}")
        expected = {"FULL": 3, "DOUBLE": 2, "SINGLE": 1}[role]
        if len(allowed) != expected or len(set(allowed)) != expected:
            raise RuntimeError(f"role/code cardinality drift: {item}")
        roles.append((match_id, role, allowed))
    return roles


def settlement_geometry(frontier: dict[str, str], outcomes: dict[str, dict[str, str]]) -> dict[str, object]:
    roles = parse_roles(frontier["role_codes"])
    selected_n = int(frontier["selected_n"])
    formula_k = int(frontier["formula_k"])
    frozen_stake = dec(frontier["stake_yuan"], "frozen stake")
    if frontier["disposition"] == "NO_BET":
        if roles or selected_n or formula_k or frozen_stake:
            raise RuntimeError("NO_BET row has active frozen geometry")
        return {"status": "NO_BET_GATE_A", "gap": 0, "hit": "", "excluded": 0,
                "truth": "", "product": Decimal(0), "gross": Decimal(0), "sources": ""}
    if frontier["disposition"] != "AVAILABLE":
        raise RuntimeError(f"unknown Gate-A disposition: {frontier['disposition']}")
    if len(roles) != selected_n or selected_n not in {4, 7}:
        raise RuntimeError("selected role count drift")
    expected_k = 1
    for _, _, allowed in roles:
        expected_k *= len(allowed)
    if expected_k != formula_k or frozen_stake != UNIT_STAKE * formula_k:
        raise RuntimeError("frozen ticket/stake geometry drift")
    missing = [match_id for match_id, _, _ in roles if match_id not in outcomes]
    if missing:
        return {"status": "UNAVAILABLE_CANONICAL_OUTCOME", "gap": len(missing), "hit": "",
                "excluded": 0, "truth": "", "product": Decimal(0), "gross": Decimal(0), "sources": ""}
    truth = []
    product = Decimal(1)
    sources: set[str] = set()
    hit = True
    excluded = 0
    for match_id, _, allowed in roles:
        outcome = outcomes[match_id]
        code = outcome["result_code"]
        truth.append(code)
        product *= dec(outcome["winning_sp"], "winning SP")
        sources.add(outcome["winning_sp_source"])
        if code not in allowed:
            hit = False
            excluded += 1
    gross = UNIT_STAKE * FACTOR * product if hit else Decimal(0)
    return {"status": "SETTLED", "gap": 0, "hit": "YES" if hit else "NO",
            "excluded": excluded, "truth": "".join(truth), "product": product,
            "gross": gross, "sources": ";".join(sorted(sources))}


def issue_policy_key(row: dict[str, str]) -> tuple[str, str, str]:
    return row["issue"], row["variant_id"], row["arm"]


def allocated_tax(gross: Decimal, issue_policy_gross: Decimal) -> Decimal:
    if gross < 0 or issue_policy_gross < 0:
        raise RuntimeError("negative gross cannot be taxed")
    return gross * TAX_RATE if issue_policy_gross >= TAX_THRESHOLD else Decimal(0)


def variant_rule(variant_id: str) -> tuple[str, str, str]:
    parts = variant_id.split("_")
    if len(parts) != 3 or not parts[0].startswith("ESP") or not parts[1].startswith("GM") or not parts[2].startswith("LOWP"):
        raise RuntimeError(f"invalid variant id: {variant_id}")
    return ratio(Decimal(parts[0][3:]) / 100), ratio(Decimal(parts[1][2:]) / 100), ratio(Decimal(parts[2][4:]) / 100)


@dataclass
class Metric:
    variant_id: str
    arm: str
    scope: str
    scope_value: str
    rows: int = 0
    available: int = 0
    no_bet: int = 0
    unavailable: int = 0
    settled: int = 0
    selected_n: int = 0
    tickets: int = 0
    stake: Decimal = Decimal(0)
    hits: int = 0
    excluded: int = 0
    gross: Decimal = Decimal(0)
    tax: Decimal = Decimal(0)
    after_tax: Decimal = Decimal(0)
    net: Decimal = Decimal(0)
    best_gross: Decimal = Decimal(-1)
    best_net: Decimal = Decimal(0)
    best_stake: Decimal = Decimal(0)
    best_pool: str = ""
    issue_net: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    issue_stake: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    issue_gross: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    timeline: list[tuple[str, str, Decimal, bool]] = field(default_factory=list)

    def add(self, row: dict[str, str]) -> None:
        self.rows += 1
        if row["disposition"] == "AVAILABLE":
            self.available += 1
        status = row["settlement_status"]
        if status == "NO_BET_GATE_A":
            self.no_bet += 1
            return
        if status == "UNAVAILABLE_CANONICAL_OUTCOME":
            self.unavailable += 1
            return
        if status != "SETTLED":
            raise RuntimeError(f"unknown settlement status: {status}")
        self.settled += 1
        self.selected_n += int(row["selected_n"])
        self.tickets += int(row["formula_k"])
        stake = dec(row["stake_yuan"], "stake")
        gross = dec(row["gross_pre_tax_yuan"], "gross")
        tax = dec(row["tax_yuan"], "tax")
        after_tax = dec(row["after_tax_gross_yuan"], "after-tax gross")
        net = dec(row["tax_adjusted_net_yuan"], "net")
        self.stake += stake
        self.gross += gross
        self.tax += tax
        self.after_tax += after_tax
        self.net += net
        self.hits += row["coverage_hit"] == "YES"
        self.excluded += int(row["excluded_outcome_hits"])
        self.timeline.append((row["first_kickoff_ts"], row["pool_id"], net, row["coverage_hit"] == "YES"))
        if gross > self.best_gross:
            self.best_gross, self.best_net, self.best_stake, self.best_pool = gross, net, stake, row["pool_id"]
        issue = row["issue"]
        self.issue_net[issue] += net
        self.issue_stake[issue] += stake
        self.issue_gross[issue] += gross

    def output(self) -> dict[str, object]:
        e_sp, gm, low_p = variant_rule(self.variant_id)
        cumulative = peak = max_drawdown = Decimal(0)
        streak = max_streak = 0
        for _, _, net, hit in sorted(self.timeline, key=lambda item: (item[0], item[1])):
            cumulative += net
            peak = max(peak, cumulative)
            max_drawdown = max(max_drawdown, peak - cumulative)
            streak = 0 if hit else streak + 1
            max_streak = max(max_streak, streak)
        best_issue = max(self.issue_net, key=self.issue_net.get, default="")
        best_issue_net = self.issue_net.get(best_issue, Decimal(0))
        best_issue_stake = self.issue_stake.get(best_issue, Decimal(0))
        positive = [max(Decimal(0), value) for value in self.issue_net.values()]
        positive_total = sum(positive, Decimal(0))
        gross_total = sum(self.issue_gross.values(), Decimal(0))
        return {
            "scope": self.scope, "scope_value": self.scope_value,
            "variant_id": self.variant_id, "e_sp_min": e_sp, "gm_e_sp_min": gm,
            "low_p_max": low_p, "arm": self.arm, "frontier_rows": self.rows,
            "gate_a_available": self.available, "no_bet_gate_a": self.no_bet,
            "unavailable_canonical_outcome": self.unavailable, "settled": self.settled,
            "selected_n_total": self.selected_n, "total_tickets": self.tickets,
            "stake_yuan": money(self.stake), "coverage_hits": self.hits,
            "coverage_hit_rate": ratio(Decimal(self.hits) / self.settled) if self.settled else "",
            "excluded_outcome_hits": self.excluded, "gross_pre_tax_yuan": money(self.gross),
            "tax_yuan": money(self.tax), "after_tax_gross_yuan": money(self.after_tax),
            "tax_adjusted_net_yuan": money(self.net),
            "tax_adjusted_roi": ratio(self.net / self.stake) if self.stake else "",
            "max_drawdown_yuan": money(max_drawdown), "longest_losing_streak": max_streak,
            "best_payout_pool_id": self.best_pool,
            "best_payout_gross_yuan": money(max(self.best_gross, Decimal(0))),
            "ex_best_payout_net_yuan": money(self.net - self.best_net),
            "ex_best_payout_roi": ratio((self.net - self.best_net) / (self.stake - self.best_stake)) if self.stake > self.best_stake else "",
            "best_net_issue": best_issue, "ex_best_issue_net_yuan": money(self.net - best_issue_net),
            "ex_best_issue_roi": ratio((self.net - best_issue_net) / (self.stake - best_issue_stake)) if self.stake > best_issue_stake else "",
            "positive_net_top_issue_share": ratio(max(positive, default=Decimal(0)) / positive_total) if positive_total else "",
            "gross_top_issue_share": ratio(max(self.issue_gross.values(), default=Decimal(0)) / gross_total) if gross_total else "",
            "settled_issue_count": len(self.issue_net), "settled_pool_count": self.settled,
        }


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def summarize(path: Path) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    metrics: dict[tuple[str, ...], Metric] = {}
    years: set[str] = set()
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != SETTLEMENT_FIELDS:
            raise RuntimeError("settlement schema drift")
        for row in reader:
            variant, arm, year, fold = row["variant_id"], row["arm"], row["year"], row["fold"]
            years.add(year)
            keys = [
                ("ALL", "ALL", variant, arm),
                ("YEAR", year, variant, arm),
                ("FOLD", fold, variant, arm),
            ]
            for key in keys:
                metrics.setdefault(key, Metric(variant, arm, key[0], key[1])).add(row)
    # LOYO is a second streaming pass so the complete year set is known.
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            for omitted in sorted(years):
                if row["year"] == omitted:
                    continue
                key = ("LEAVE_ONE_YEAR_OUT", omitted, row["variant_id"], row["arm"])
                metrics.setdefault(key, Metric(row["variant_id"], row["arm"], key[0], key[1])).add(row)
    rows = [metric.output() for _, metric in sorted(metrics.items())]
    all_rows = [row for row in rows if row["scope"] == "ALL"]
    return all_rows, rows


def build(output: Path) -> dict[str, object]:
    if output.exists():
        raise RuntimeError(f"refusing immutable overwrite: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".bj121_gateb_", dir=output.parent))
    try:
        provenance = validate_inputs()
        outcomes = load_outcomes()
        pre_tax = stage / "_pre_tax.csv"
        bucket_gross: dict[tuple[str, str, str], Decimal] = defaultdict(Decimal)
        status_counts: dict[str, int] = defaultdict(int)
        variants: set[str] = set()
        arms: set[str] = set()
        pools: set[str] = set()
        with gzip.open(GATE_A / "portfolio_frontier.csv.gz", "rt", newline="", encoding="utf-8") as source, pre_tax.open("w", newline="", encoding="utf-8") as target:
            reader = csv.DictReader(source)
            if tuple(reader.fieldnames or ()) != FRONTIER_FIELDS:
                raise RuntimeError("Gate-A frontier schema drift")
            fields = FRONTIER_FIELDS + (
                "settlement_status", "outcome_gap_count", "coverage_hit", "excluded_outcome_hits",
                "truth_sequence", "final_winning_sp_product", "gross_pre_tax_yuan", "winning_sp_sources",
            )
            writer = csv.DictWriter(target, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            count = 0
            for frontier in reader:
                geometry = settlement_geometry(frontier, outcomes)
                writer.writerow({
                    **frontier, "settlement_status": geometry["status"],
                    "outcome_gap_count": geometry["gap"], "coverage_hit": geometry["hit"],
                    "excluded_outcome_hits": geometry["excluded"], "truth_sequence": geometry["truth"],
                    "final_winning_sp_product": money(geometry["product"]),
                    "gross_pre_tax_yuan": money(geometry["gross"]), "winning_sp_sources": geometry["sources"],
                })
                if geometry["status"] == "SETTLED":
                    bucket_gross[issue_policy_key(frontier)] += geometry["gross"]
                status_counts[str(geometry["status"])] += 1
                variants.add(frontier["variant_id"]); arms.add(frontier["arm"]); pools.add(frontier["pool_id"])
                count += 1
        if (count, len(variants), len(arms), len(pools)) != (EXPECTED_FRONTIERS, EXPECTED_VARIANTS, EXPECTED_ARMS, EXPECTED_POOLS):
            raise RuntimeError("frozen matrix cardinality drift")
        raw = (stage / "portfolio_settlement.csv.gz").open("wb")
        zipped = gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0)
        text = io.TextIOWrapper(zipped, encoding="utf-8", newline="")
        try:
            with pre_tax.open(newline="", encoding="utf-8") as source:
                reader = csv.DictReader(source)
                writer = csv.DictWriter(text, fieldnames=SETTLEMENT_FIELDS, lineterminator="\n")
                writer.writeheader()
                for row in reader:
                    bucket = bucket_gross[issue_policy_key(row)]
                    gross = dec(row["gross_pre_tax_yuan"], "gross")
                    tax = allocated_tax(gross, bucket)
                    after_tax = gross - tax
                    stake = dec(row["stake_yuan"], "stake") if row["settlement_status"] == "SETTLED" else Decimal(0)
                    net = after_tax - stake
                    # Outcome-unavailable rows are not silently treated as bets.
                    if row["settlement_status"] != "SETTLED":
                        row["stake_yuan"] = money(Decimal(0))
                    writer.writerow({
                        **row, "issue_policy_gross_yuan": money(bucket), "tax_yuan": money(tax),
                        "after_tax_gross_yuan": money(after_tax), "tax_adjusted_net_yuan": money(net),
                    })
            text.flush()
        finally:
            text.detach(); zipped.close(); raw.close()
        pre_tax.unlink()
        all_rows, robustness = summarize(stage / "portfolio_settlement.csv.gz")
        write_csv(stage / "arm_comparison.csv", SUMMARY_FIELDS, all_rows)
        write_csv(stage / "robustness_summary.csv", SUMMARY_FIELDS, robustness)
        heatmap_fields = (
            "variant_id", "e_sp_min", "gm_e_sp_min", "low_p_max", "arm", "settled",
            "stake_yuan", "coverage_hits", "tax_adjusted_net_yuan", "tax_adjusted_roi",
            "ex_best_payout_roi", "ex_best_issue_roi", "max_drawdown_yuan",
        )
        heatmap = [
            {field: row[field] for field in heatmap_fields}
            for row in all_rows
            if row["arm"] in {"FULL_DYNAMIC_4_7", "PRUNE_DYNAMIC_4_7", "MIXED_DYNAMIC_4_7"}
        ]
        write_csv(stage / "threshold_heatmap.csv", heatmap_fields, heatmap)
        positive = [row for row in all_rows if row["tax_adjusted_roi"] and dec(row["tax_adjusted_roi"], "ROI") > 0]
        robust_positive = [
            row for row in positive
            if row["ex_best_payout_roi"] and row["ex_best_issue_roi"]
            and dec(row["ex_best_payout_roi"], "ex-best payout ROI") > 0
            and dec(row["ex_best_issue_roi"], "ex-best issue ROI") > 0
        ]
        decision = {
            "decision": "FROZEN_POSITIVE_REQUIRES_STRICT_EV" if positive else "NO_PROMOTION",
            "positive_all_rows": len(positive),
            "positive_after_ex_best_rows": len(robust_positive),
            "strict_independent_ev_required": bool(positive),
            "promotion_authorized": False,
            "rule": "Positive historical ROI freezes the result and requires strict independent EV; it never directly authorizes promotion.",
        }
        (stage / "decision.json").write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        card = {
            "issue": 121, "contract": CONTRACT, "runner_version": RUNNER_VERSION,
            "stage": "GATE_B_CANONICAL_OUTCOME_SETTLEMENT", "provenance": provenance,
            "frozen_matrix": {"variants": EXPECTED_VARIANTS, "arms": EXPECTED_ARMS, "pools": EXPECTED_POOLS, "rows": EXPECTED_FRONTIERS},
            "status_counts": dict(sorted(status_counts.items())),
            "settlement_rule": "Hit iff every canonical result code is in its frozen allowed set; gross=2*0.65*product(canonical final winning SP) once on hit, else zero; stake=2*product allowed-code counts.",
            "tax_rule": "Each variant/arm is a separate counterfactual policy. Aggregate gross by native issue; when issue-policy gross >=10000, apply 20% tax to each winning pool gross in that bucket.",
            "availability_rule": "Every Gate-A row remains. NO_BET_GATE_A is distinct from UNAVAILABLE_CANONICAL_OUTCOME; unavailable portfolios receive zero realized stake and are not replaced.",
            "chronology_rule": "Drawdown and losing streak are accumulated in first_kickoff_ts then frozen pool order; non-monotone input fails.",
            "scope": "historical paper research only; no purchase, release, or promotion authorization",
        }
        (stage / "settlement_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        shutil.copyfile(__file__, stage / "settlement_runner.py")
        (stage / "README.md").write_text(
            "# #121 Gate B\n\nCanonical one-shot settlement of the accepted 9 × 13 × 2,659 Gate-A matrix. "
            "Run `python settlement_runner.py --output <new-directory>` from a compatible checkout.\n",
            encoding="utf-8",
        )
        gzip_hash, gzip_bytes = decompressed_identity(stage / "portfolio_settlement.csv.gz")
        identity = {
            "contract_version": "bj121-gateb-portable-content-v1",
            "gzip_payloads": {"portfolio_settlement.csv.gz": {"canonical_decompressed_sha256": gzip_hash, "canonical_decompressed_bytes": gzip_bytes}},
            "non_compressed_controls": {
                item.name: sha256(item) for item in sorted(stage.iterdir())
                if item.is_file() and item.name not in {"portfolio_settlement.csv.gz"}
            },
        }
        (stage / "CONTENT_IDENTITY.json").write_text(json.dumps(identity, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest = {item.name: sha256(item) for item in sorted(stage.iterdir()) if item.is_file()}
        (stage / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(stage, output)
        return {
            "output": str(output), "manifest_sha256": sha256(output / "SHA256SUMS.json"),
            "content_identity_sha256": sha256(output / "CONTENT_IDENTITY.json"),
            "status_counts": dict(sorted(status_counts.items())), "decision": decision,
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
