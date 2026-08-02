#!/usr/bin/env python3
"""One-shot primary complete-issue Gate-B settlement for #132.

Only the accepted complete-issue Gate-A freeze and canonical final-SP outcome
join are read.  The superseded segment package is intentionally not opened.
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
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path

CODES = ("3", "1", "0")
CONTRACT = "BJ-HIST-DELETE-SCORE-N7-001"
VERSION = "bj132-complete-issue-gateb-v1r1"
FREEZE_MANIFEST = "6583503ee80fd2b40bb1c000917ff094afa0551b6a3f0af4b8d175a6432872f9"
OUTCOME_MANIFEST = "fbbd3b53bd86f4bb0caff8f2587933cd6b0e4e7d04fb0f709bac934ec2a705cc"
OUTCOME_PAYLOAD = "13d709d253c31519734dbf0447e6961ac8a6060772975d7461741224e5251a89"
FULL_K, DELETE_K = 2187, 1458
UNIT, FACTOR, TAX_RATE, TAX_THRESHOLD = Decimal("2"), Decimal("0.65"), Decimal("0.20"), Decimal("10000")
QUANT = Decimal("0.000001")
getcontext().prec = 128

FRONTIER_FIELDS = (
    "issue", "fold", "year", "issue_instance", "eligible_match_count", "first_kickoff_ts", "last_kickoff_ts", "source_segment_count", "issue_disposition", "fold_integrity", "selection_scope", "variant_id", "arm", "portfolio_id", "candidate_match_id", "candidate_p_min", "candidate_rank_in_complete_issue", "candidate_count_complete_issue", "candidate_search_count", "candidate_cap_applied", "selected_match_ids", "selected_n", "gm_e_sp", "p_min_deleted_match_id", "p_min_deleted_code", "p_min_deleted_probability", "p_min_predicted_sp", "p_min_q", "q_min_deleted_match_id", "q_min_deleted_code", "q_min_deleted_probability", "q_min_predicted_sp", "q_min_q", "rankers_disagree", "formula_k", "stake_yuan", "matched_full_k", "matched_full_stake_yuan", "stake_reduction_fraction", "participation_policy", "tax_bucket_key", "disposition", "reason", "descriptor_sha256",
)
ROLE_FIELDS = (
    "variant_id", "portfolio_id", "issue", "fold", "year", "issue_instance", "match_id", "match_idx", "selection_rank", "e_sp", "p_min", "p3", "p1", "p0", "predicted_sp3", "predicted_sp1", "predicted_sp0", "q3", "q1", "q0", "is_candidate", "p_min_deleted_match_id", "p_min_deleted_code", "q_min_deleted_match_id", "q_min_deleted_code",
)
OUTCOME_FIELDS = ("match_id", "result_code", "winning_sp", "winning_sp_source", "settlement_quality", "has_trusted_settlement")
SETTLEMENT_FIELDS = FRONTIER_FIELDS + (
    "settlement_status", "outcome_gap_count", "coverage_hit", "deleted_code_occurred", "truth_sequence", "final_winning_sp_product", "gross_pre_tax_yuan", "issue_policy_gross_yuan", "tax_yuan", "after_tax_gross_yuan", "pre_tax_net_yuan", "tax_adjusted_net_yuan", "winning_sp_sources", "deleted_match_e_sp", "deleted_probability", "deleted_predicted_sp", "deleted_q",
)
SUMMARY_FIELDS = (
    "scope", "scope_value", "variant_id", "arm", "frontier_rows", "gate_a_available", "no_bet_gate_a", "unavailable_canonical_outcome", "settled", "stake_yuan", "gross_pre_tax_yuan", "pre_tax_net_yuan", "no_tax_roi", "tax_yuan", "after_tax_gross_yuan", "tax_adjusted_net_yuan", "tax_adjusted_roi", "coverage_hits", "coverage_hit_rate", "deleted_code_occurrences", "deleted_code_rate", "settled_issue_instance_count", "max_drawdown_yuan", "longest_miss_streak", "gross_top_issue_instance_share", "largest_event_gross_yuan", "ex_largest_event_tax_roi",
)
COMPARISON_FIELDS = (
    "scope", "scope_value", "variant_id", "full_settled", "ranker", "ranker_settled", "full_stake_yuan", "ranker_stake_yuan", "stake_retention_vs_full", "full_gross_pre_tax_yuan", "ranker_gross_pre_tax_yuan", "gross_retention_vs_full", "gross_lost_yuan_vs_full", "gross_loss_per_deleted_code_occurrence_yuan", "full_no_tax_roi", "ranker_no_tax_roi", "no_tax_roi_delta_ranker_minus_full", "full_tax_adjusted_roi", "ranker_tax_adjusted_roi", "tax_adjusted_roi_delta_ranker_minus_full", "full_coverage_hit_rate", "ranker_coverage_hit_rate", "ranker_deleted_code_rate", "full_max_drawdown_yuan", "ranker_max_drawdown_yuan",
)
DELTA_FIELDS = (
    "variant_id", "portfolio_id", "issue", "fold", "year", "issue_instance", "first_kickoff_ts", "rankers_disagree", "arm", "deleted_match_id", "deleted_code", "deleted_code_occurred", "full_coverage_hit", "arm_coverage_hit", "full_stake_yuan", "arm_stake_yuan", "stake_saved_yuan", "full_gross_pre_tax_yuan", "arm_gross_pre_tax_yuan", "full_tax_adjusted_net_yuan", "arm_tax_adjusted_net_yuan", "tax_net_delta_arm_minus_full",
)
QPAIR_FIELDS = (
    "variant_id", "portfolio_id", "issue", "fold", "year", "issue_instance", "p_min_deleted_match_id", "p_min_deleted_code", "p_min_deleted_probability", "p_min_predicted_sp", "p_min_q", "q_min_deleted_match_id", "q_min_deleted_code", "q_min_deleted_probability", "q_min_predicted_sp", "q_min_q", "p_min_deleted_code_occurred", "q_min_deleted_code_occurred", "p_min_tax_adjusted_net_yuan", "q_min_tax_adjusted_net_yuan", "q_minus_p_tax_net_yuan",
)
STRATUM_FIELDS = ("dimension", "stratum", "variant_id", "arm", "settled", "stake_yuan", "gross_pre_tax_yuan", "no_tax_roi", "tax_adjusted_roi", "expected_deleted_probability", "observed_deleted_code_rate", "deleted_code_occurrences")
ACCOUNTING_FIELDS = ("variant_id", "arm", "issue", "fold", "year", "issue_instance", "portfolio_count", "frozen_stake_yuan", "settled_portfolios", "settled_stake_yuan", "gross_pre_tax_yuan", "tax_yuan", "tax_bucket_key", "participation_policy", "overlap_semantics", "loyo_unit")
ISSUE_SUPPORT_FIELDS = ("issue", "fold", "year") + SUMMARY_FIELDS
SOURCE_FIELDS = ("source", "role", "manifest_sha256", "payload", "payload_sha256", "rows", "join_status")


def root(anchor: Path) -> Path:
    for candidate in (anchor.resolve().parent, *anchor.resolve().parents):
        if (candidate / ".git").exists():
            return candidate
    raise RuntimeError("repository root unavailable")


ROOT = root(Path(__file__))
FREEZE = ROOT / "results" / "bj132_gate_a_complete_issue_preoutcome_v1r1"
OUTCOMES = ROOT / "results" / "bj95_gate_b_outcome_settlement_v2r8"
OUTPUT = ROOT / "results" / "bj132_gate_b_complete_issue_outcome_settlement_v1r1"


def sha(path: Path) -> str:
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
        raise RuntimeError(f"non-finite {label}")
    return result


def money(value: Decimal) -> str:
    return format(value.quantize(QUANT), "f")


def ratio(value: Decimal | None) -> str:
    return "" if value is None else format(value, ".12f")


def exact_manifest(bundle: Path, expected: str) -> dict[str, str]:
    manifest_path = bundle / "SHA256SUMS.json"
    if sha(manifest_path) != expected:
        raise RuntimeError(f"unaccepted manifest: {bundle}")
    declared = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = {item.name: sha(item) for item in bundle.iterdir() if item.is_file() and item.name != manifest_path.name}
    if not isinstance(declared, dict) or actual != declared:
        raise RuntimeError(f"manifest coverage drift: {bundle}")
    return declared


def schema(reader: csv.DictReader, expected: tuple[str, ...], label: str) -> None:
    if tuple(reader.fieldnames or ()) != expected:
        raise RuntimeError(f"{label} schema drift")


def validate_inputs() -> dict[str, str]:
    freeze = exact_manifest(FREEZE, FREEZE_MANIFEST)
    card = json.loads((FREEZE / "gate_a_card.json").read_text(encoding="utf-8"))
    expected = {"eligible_matches": 47819, "issue_instances": 348, "frontier_rows": 160734, "portfolio_identities": 52534, "role_rows": 367738, "ranker_disagreements": 43120}
    if card.get("stage") != "GATE_A_OUTCOME_UNEXPOSED_COMPLETE_ISSUE_MATCHED_FREEZE" or card.get("denominator") != expected:
        raise RuntimeError("complete-issue Gate-A card drift")
    if card.get("complete_issue_contract", {}).get("primary_unit") != "(issue, fold) issue instance; no issue is segmented for selection or construction":
        raise RuntimeError("primary-unit drift")
    outcome = exact_manifest(OUTCOMES, OUTCOME_MANIFEST)
    if outcome.get("canonical_outcome_join.csv") != OUTCOME_PAYLOAD:
        raise RuntimeError("canonical outcome payload drift")
    return {"gate_a_manifest_sha256": FREEZE_MANIFEST, "gate_a_content_identity_sha256": freeze["CONTENT_IDENTITY.json"], "outcome_manifest_sha256": OUTCOME_MANIFEST, "outcome_payload_sha256": OUTCOME_PAYLOAD}


def load_outcomes() -> dict[str, dict[str, str]]:
    with (OUTCOMES / "canonical_outcome_join.csv").open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle); schema(reader, OUTCOME_FIELDS, "canonical outcomes")
        values = {row["match_id"]: row for row in reader}
    for row in values.values():
        if row["result_code"] not in CODES or row["settlement_quality"] != "trusted" or row["has_trusted_settlement"] != "1" or dec(row["winning_sp"], "winning SP") <= 0:
            raise RuntimeError("untrusted canonical outcome")
    return values


def load_roles() -> dict[tuple[str, str], list[dict[str, str]]]:
    values: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    with gzip.open(FREEZE / "portfolio_role_assignments.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle); schema(reader, ROLE_FIELDS, "complete-issue roles")
        for row in reader:
            values[(row["variant_id"], row["portfolio_id"])].append(row)
    if len(values) != 52534 or sum(len(rows) for rows in values.values()) != 367738:
        raise RuntimeError("role denominator drift")
    for key, rows in values.items():
        rows.sort(key=lambda row: int(row["selection_rank"]))
        if len(rows) != 7 or [int(row["selection_rank"]) for row in rows] != list(range(1, 8)):
            raise RuntimeError(f"seven-role geometry drift: {key}")
    return values


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


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)


def delete_for(frontier: dict[str, str]) -> tuple[str, str, str, str, str]:
    if frontier["arm"] == "P_MIN_DELETE_N7":
        return (frontier["p_min_deleted_match_id"], frontier["p_min_deleted_code"], frontier["p_min_deleted_probability"], frontier["p_min_predicted_sp"], frontier["p_min_q"])
    if frontier["arm"] == "Q_MIN_DELETE_N7":
        return (frontier["q_min_deleted_match_id"], frontier["q_min_deleted_code"], frontier["q_min_deleted_probability"], frontier["q_min_predicted_sp"], frontier["q_min_q"])
    return ("", "", "", "", "")


def settle(frontier: dict[str, str], roles: list[dict[str, str]] | None, outcomes: dict[str, dict[str, str]]) -> dict[str, object]:
    if frontier["arm"] == "NO_BET_CONTROL":
        if frontier["disposition"] != "NO_BET" or roles is not None:
            raise RuntimeError("no-bet geometry drift")
        return {"status": "NO_BET_GATE_A", "gap": 0, "hit": "", "deleted": "", "truth": "", "product": Decimal(0), "gross": Decimal(0), "sources": "", "e_sp": "", "p": "", "sp": "", "q": ""}
    if roles is None or len(roles) != 7 or frontier["disposition"] != "AVAILABLE":
        raise RuntimeError("available role geometry drift")
    if (frontier["variant_id"], frontier["portfolio_id"]) != (roles[0]["variant_id"], roles[0]["portfolio_id"]):
        raise RuntimeError("frontier/role identity drift")
    if any(row[key] != frontier[key] for row in roles for key in ("issue", "fold", "year", "issue_instance")):
        raise RuntimeError("issue-instance split")
    if ";".join(row["match_id"] for row in roles) != frontier["selected_match_ids"]:
        raise RuntimeError("selected match drift")
    expected_k = FULL_K if frontier["arm"] == "MATCHED_FULL_N7" else DELETE_K
    if frontier["arm"] not in {"MATCHED_FULL_N7", "P_MIN_DELETE_N7", "Q_MIN_DELETE_N7"} or int(frontier["formula_k"]) != expected_k or dec(frontier["stake_yuan"], "stake") != UNIT * expected_k:
        raise RuntimeError("ticket/stake drift")
    deleted_match, deleted_code, probability, predicted_sp, q = delete_for(frontier)
    missing = [row["match_id"] for row in roles if row["match_id"] not in outcomes]
    if missing:
        return {"status": "UNAVAILABLE_CANONICAL_OUTCOME", "gap": len(missing), "hit": "", "deleted": "", "truth": "", "product": Decimal(0), "gross": Decimal(0), "sources": "", "e_sp": "", "p": probability, "sp": predicted_sp, "q": q}
    truth: list[str] = []; product = Decimal(1); sources: set[str] = set(); hit = True; deleted_e_sp = ""
    for role in roles:
        outcome = outcomes[role["match_id"]]
        truth.append(outcome["result_code"]); product *= dec(outcome["winning_sp"], "winning SP"); sources.add(outcome["winning_sp_source"])
        allowed = CODES if not deleted_match or role["match_id"] != deleted_match else tuple(code for code in CODES if code != deleted_code)
        hit = hit and outcome["result_code"] in allowed
        if role["match_id"] == deleted_match:
            deleted_e_sp = role["e_sp"]
    deleted = "YES" if deleted_match and outcomes[deleted_match]["result_code"] == deleted_code else ("NO" if deleted_match else "")
    return {"status": "SETTLED", "gap": 0, "hit": "YES" if hit else "NO", "deleted": deleted, "truth": "".join(truth), "product": product, "gross": UNIT * FACTOR * product if hit else Decimal(0), "sources": ";".join(sorted(sources)), "e_sp": deleted_e_sp, "p": probability, "sp": predicted_sp, "q": q}


@dataclass
class Metric:
    variant: str; arm: str; scope: str; value: str; track_path: bool = False
    rows: int = 0; available: int = 0; no_bet: int = 0; unavailable: int = 0; settled: int = 0; hits: int = 0; deleted: int = 0
    stake: Decimal = Decimal(0); gross: Decimal = Decimal(0); tax: Decimal = Decimal(0); net: Decimal = Decimal(0)
    issues: set[str] = field(default_factory=set); issue_gross: dict[str, Decimal] = field(default_factory=lambda: defaultdict(Decimal)); events: list[tuple[str, str, str, Decimal, bool, Decimal, Decimal]] = field(default_factory=list)
    def add(self, row: dict[str, str]) -> None:
        self.rows += 1
        if row["disposition"] == "AVAILABLE": self.available += 1
        if row["settlement_status"] == "NO_BET_GATE_A": self.no_bet += 1; return
        if row["settlement_status"] == "UNAVAILABLE_CANONICAL_OUTCOME": self.unavailable += 1; return
        if row["settlement_status"] != "SETTLED": raise RuntimeError("unknown settlement state")
        self.settled += 1; self.hits += row["coverage_hit"] == "YES"; self.deleted += row["deleted_code_occurred"] == "YES"
        stake, gross, tax, net = (dec(row[name], name) for name in ("stake_yuan", "gross_pre_tax_yuan", "tax_yuan", "tax_adjusted_net_yuan"))
        self.stake += stake; self.gross += gross; self.tax += tax; self.net += net; self.issues.add(row["issue_instance"]); self.issue_gross[row["issue_instance"]] += gross
        if self.track_path: self.events.append((row["first_kickoff_ts"], row["issue_instance"], row["portfolio_id"], net, row["coverage_hit"] == "YES", gross, stake))
    def output(self) -> dict[str, object]:
        cumulative = peak = draw = Decimal(0); streak = longest = 0
        for _, _, _, net, hit, _, _ in sorted(self.events):
            cumulative += net; peak = max(peak, cumulative); draw = max(draw, peak - cumulative); streak = 0 if hit else streak + 1; longest = max(longest, streak)
        largest = max(self.events, key=lambda event: event[5], default=None); ex_net = self.net - (largest[3] if largest else Decimal(0)); ex_stake = self.stake - (largest[6] if largest else Decimal(0)); issue_total = sum(self.issue_gross.values(), Decimal(0)); top = max(self.issue_gross.values(), default=Decimal(0)); pre = self.gross - self.stake
        return {"scope": self.scope, "scope_value": self.value, "variant_id": self.variant, "arm": self.arm, "frontier_rows": self.rows, "gate_a_available": self.available, "no_bet_gate_a": self.no_bet, "unavailable_canonical_outcome": self.unavailable, "settled": self.settled, "stake_yuan": money(self.stake), "gross_pre_tax_yuan": money(self.gross), "pre_tax_net_yuan": money(pre), "no_tax_roi": ratio(pre / self.stake if self.stake else None), "tax_yuan": money(self.tax), "after_tax_gross_yuan": money(self.gross - self.tax), "tax_adjusted_net_yuan": money(self.net), "tax_adjusted_roi": ratio(self.net / self.stake if self.stake else None), "coverage_hits": self.hits, "coverage_hit_rate": ratio(Decimal(self.hits) / self.settled if self.settled else None), "deleted_code_occurrences": self.deleted, "deleted_code_rate": ratio(Decimal(self.deleted) / self.settled if self.settled else None), "settled_issue_instance_count": len(self.issues), "max_drawdown_yuan": money(draw), "longest_miss_streak": longest, "gross_top_issue_instance_share": ratio(top / issue_total if issue_total else None), "largest_event_gross_yuan": money(largest[5] if largest else Decimal(0)), "ex_largest_event_tax_roi": ratio(ex_net / ex_stake if ex_stake else None)}


def summaries(path: Path) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    all_metrics: dict[tuple[str, str], Metric] = {}; parts: dict[tuple[str, str, str, str], Metric] = {}; issue_metrics: dict[tuple[str, str, str], Metric] = {}; issue_meta: dict[str, tuple[str, str, str]] = {}; years: set[str] = set()
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            key = row["variant_id"], row["arm"]; years.add(row["year"]); all_metrics.setdefault(key, Metric(*key, "ALL", "ALL", True)).add(row)
            instance = row["issue_instance"]
            meta = (row["issue"], row["fold"], row["year"])
            if instance in issue_meta and issue_meta[instance] != meta: raise RuntimeError("issue-support metadata drift")
            issue_meta[instance] = meta
            issue_metrics.setdefault((*key, instance), Metric(*key, "ISSUE", instance)).add(row)
            for scope, value in (("YEAR", row["year"]), ("FOLD", row["fold"])):
                parts.setdefault((scope, value, *key), Metric(*key, scope, value)).add(row)
    robust = [metric.output() for _, metric in sorted(parts.items())]
    for omitted in sorted(years):
        local: dict[tuple[str, str], Metric] = {}
        with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row["year"] != omitted:
                    key = row["variant_id"], row["arm"]; local.setdefault(key, Metric(*key, "LEAVE_ONE_YEAR_OUT", omitted)).add(row)
        robust.extend(metric.output() for _, metric in sorted(local.items()))
    issue_support = []
    for (_, _, instance), metric in sorted(issue_metrics.items()):
        issue, fold, year = issue_meta[instance]
        issue_support.append({"issue": issue, "fold": fold, "year": year, **metric.output()})
    return [metric.output() for _, metric in sorted(all_metrics.items())], robust, issue_support


def comparisons(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    index = {(str(row["scope"]), str(row["scope_value"]), str(row["variant_id"]), str(row["arm"])): row for row in rows}; output = []
    for (scope, value, variant, arm), full in sorted(index.items()):
        if arm != "MATCHED_FULL_N7": continue
        for ranker in ("P_MIN_DELETE_N7", "Q_MIN_DELETE_N7"):
            other = index[(scope, value, variant, ranker)]
            def value_of(row: dict[str, object], field: str) -> Decimal: return dec(row[field], field)
            full_gross, ranker_gross = value_of(full, "gross_pre_tax_yuan"), value_of(other, "gross_pre_tax_yuan")
            gross_loss = full_gross - ranker_gross
            deleted = Decimal(str(other["deleted_code_occurrences"]))
            output.append({"scope": scope, "scope_value": value, "variant_id": variant, "full_settled": full["settled"], "ranker": ranker, "ranker_settled": other["settled"], "full_stake_yuan": full["stake_yuan"], "ranker_stake_yuan": other["stake_yuan"], "stake_retention_vs_full": ratio(value_of(other, "stake_yuan") / value_of(full, "stake_yuan") if value_of(full, "stake_yuan") else None), "full_gross_pre_tax_yuan": money(full_gross), "ranker_gross_pre_tax_yuan": money(ranker_gross), "gross_retention_vs_full": ratio(ranker_gross / full_gross if full_gross else None), "gross_lost_yuan_vs_full": money(gross_loss), "gross_loss_per_deleted_code_occurrence_yuan": money(gross_loss / deleted) if deleted else "", "full_no_tax_roi": full["no_tax_roi"], "ranker_no_tax_roi": other["no_tax_roi"], "no_tax_roi_delta_ranker_minus_full": ratio(value_of(other, "no_tax_roi") - value_of(full, "no_tax_roi")) if full["no_tax_roi"] else "", "full_tax_adjusted_roi": full["tax_adjusted_roi"], "ranker_tax_adjusted_roi": other["tax_adjusted_roi"], "tax_adjusted_roi_delta_ranker_minus_full": ratio(value_of(other, "tax_adjusted_roi") - value_of(full, "tax_adjusted_roi")) if full["tax_adjusted_roi"] else "", "full_coverage_hit_rate": full["coverage_hit_rate"], "ranker_coverage_hit_rate": other["coverage_hit_rate"], "ranker_deleted_code_rate": other["deleted_code_rate"], "full_max_drawdown_yuan": full["max_drawdown_yuan"], "ranker_max_drawdown_yuan": other["max_drawdown_yuan"]})
    return output


def bin_for(value: str, dimension: str) -> str:
    number = float(value)
    if dimension == "OUTCOME_TYPE": return value
    if dimension == "DELETED_PROBABILITY": return "LE_010" if number <= .10 else "LE_020" if number <= .20 else "LE_030" if number <= .30 else "GT_030"
    if dimension == "PREDICTED_SP": return "LT_300" if number < 3 else "300_400" if number < 4 else "GE_400"
    if dimension == "E_SP": return "LT_280" if number < 2.8 else "280_300" if number < 3 else "GE_300"
    return "LT_300" if number < 3 else "300_305" if number < 3.05 else "GE_305"


def deltas_and_strata(stage: Path, settlement: Path) -> tuple[int, int]:
    delta_h = gzip_writer(stage / "matched_full_deltas.csv.gz", DELTA_FIELDS); pair_h = gzip_writer(stage / "q_minus_p_disagreement_deltas.csv.gz", QPAIR_FIELDS)
    delta_writer, pair_writer = delta_h[-1], pair_h[-1]; current: tuple[str, str] | None = None; group: list[dict[str, str]] = []; delta_count = pair_count = 0
    stats: dict[tuple[str, str, str, str], list[object]] = defaultdict(lambda: [0, Decimal(0), Decimal(0), Decimal(0), Decimal(0), 0])
    def add_stat(row: dict[str, str], dimension: str, value: str) -> None:
        if row["arm"] == "MATCHED_FULL_N7" or row["settlement_status"] != "SETTLED": return
        item = stats[(dimension, bin_for(value, dimension), row["variant_id"], row["arm"])]
        item[0] += 1; item[1] += dec(row["stake_yuan"], "stake"); item[2] += dec(row["gross_pre_tax_yuan"], "gross"); item[3] += dec(row["tax_adjusted_net_yuan"], "net"); item[4] += dec(row["deleted_probability"], "probability"); item[5] += row["deleted_code_occurred"] == "YES"
    def flush(rows: list[dict[str, str]]) -> None:
        nonlocal delta_count, pair_count
        if not rows or rows[0]["arm"] == "NO_BET_CONTROL": return
        if len(rows) != 3 or {row["arm"] for row in rows} != {"MATCHED_FULL_N7", "P_MIN_DELETE_N7", "Q_MIN_DELETE_N7"}: raise RuntimeError("matched arm grouping drift")
        by_arm = {row["arm"]: row for row in rows}; full = by_arm["MATCHED_FULL_N7"]
        for arm in ("P_MIN_DELETE_N7", "Q_MIN_DELETE_N7"):
            row = by_arm[arm]
            mid, code, _probability, _predicted_sp, _q = delete_for(row)
            if row["settlement_status"] == "SETTLED" and full["settlement_status"] == "SETTLED":
                delta_writer.writerow({"variant_id": row["variant_id"], "portfolio_id": row["portfolio_id"], "issue": row["issue"], "fold": row["fold"], "year": row["year"], "issue_instance": row["issue_instance"], "first_kickoff_ts": row["first_kickoff_ts"], "rankers_disagree": row["rankers_disagree"], "arm": arm, "deleted_match_id": mid, "deleted_code": code, "deleted_code_occurred": row["deleted_code_occurred"], "full_coverage_hit": full["coverage_hit"], "arm_coverage_hit": row["coverage_hit"], "full_stake_yuan": full["stake_yuan"], "arm_stake_yuan": row["stake_yuan"], "stake_saved_yuan": money(dec(full["stake_yuan"], "stake") - dec(row["stake_yuan"], "stake")), "full_gross_pre_tax_yuan": full["gross_pre_tax_yuan"], "arm_gross_pre_tax_yuan": row["gross_pre_tax_yuan"], "full_tax_adjusted_net_yuan": full["tax_adjusted_net_yuan"], "arm_tax_adjusted_net_yuan": row["tax_adjusted_net_yuan"], "tax_net_delta_arm_minus_full": money(dec(row["tax_adjusted_net_yuan"], "net") - dec(full["tax_adjusted_net_yuan"], "net"))}); delta_count += 1
            for dimension, value in (("OUTCOME_TYPE", code), ("DELETED_PROBABILITY", row["deleted_probability"]), ("PREDICTED_SP", row["deleted_predicted_sp"]), ("E_SP", row["deleted_match_e_sp"]), ("GM_E_SP", row["gm_e_sp"])):
                add_stat(row, dimension, value)
        p_row, q_row = by_arm["P_MIN_DELETE_N7"], by_arm["Q_MIN_DELETE_N7"]
        if p_row["rankers_disagree"] == "1" and p_row["settlement_status"] == q_row["settlement_status"] == "SETTLED":
            pair_writer.writerow({"variant_id": p_row["variant_id"], "portfolio_id": p_row["portfolio_id"], "issue": p_row["issue"], "fold": p_row["fold"], "year": p_row["year"], "issue_instance": p_row["issue_instance"], "p_min_deleted_match_id": p_row["p_min_deleted_match_id"], "p_min_deleted_code": p_row["p_min_deleted_code"], "p_min_deleted_probability": p_row["p_min_deleted_probability"], "p_min_predicted_sp": p_row["p_min_predicted_sp"], "p_min_q": p_row["p_min_q"], "q_min_deleted_match_id": q_row["q_min_deleted_match_id"], "q_min_deleted_code": q_row["q_min_deleted_code"], "q_min_deleted_probability": q_row["q_min_deleted_probability"], "q_min_predicted_sp": q_row["q_min_predicted_sp"], "q_min_q": q_row["q_min_q"], "p_min_deleted_code_occurred": p_row["deleted_code_occurred"], "q_min_deleted_code_occurred": q_row["deleted_code_occurred"], "p_min_tax_adjusted_net_yuan": p_row["tax_adjusted_net_yuan"], "q_min_tax_adjusted_net_yuan": q_row["tax_adjusted_net_yuan"], "q_minus_p_tax_net_yuan": money(dec(q_row["tax_adjusted_net_yuan"], "q net") - dec(p_row["tax_adjusted_net_yuan"], "p net"))}); pair_count += 1
    with gzip.open(settlement, "rt", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            key = (row["variant_id"], row["portfolio_id"])
            if current is not None and key != current: flush(group); group = []
            current = key; group.append(row)
        flush(group)
    close_gzip(delta_h); close_gzip(pair_h)
    stratum_rows = []
    for (dimension, label, variant, arm), values in sorted(stats.items()):
        count, stake, gross, net, prob_sum, occurred = values
        assert isinstance(count, int) and isinstance(stake, Decimal) and isinstance(gross, Decimal) and isinstance(net, Decimal) and isinstance(prob_sum, Decimal) and isinstance(occurred, int)
        stratum_rows.append({"dimension": dimension, "stratum": label, "variant_id": variant, "arm": arm, "settled": count, "stake_yuan": money(stake), "gross_pre_tax_yuan": money(gross), "no_tax_roi": ratio((gross - stake) / stake if stake else None), "tax_adjusted_roi": ratio(net / stake if stake else None), "expected_deleted_probability": ratio(prob_sum / count if count else None), "observed_deleted_code_rate": ratio(Decimal(occurred) / count if count else None), "deleted_code_occurrences": occurred})
    write_csv(stage / "deletion_strata.csv", STRATUM_FIELDS, stratum_rows)
    return delta_count, pair_count


def uncompressed(path: Path) -> tuple[str, int]:
    digest, size = hashlib.sha256(), 0
    with gzip.open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block); size += len(block)
    return digest.hexdigest(), size


def build(output: Path) -> dict[str, object]:
    if output.exists(): raise RuntimeError(f"refusing immutable overwrite: {output}")
    output.parent.mkdir(parents=True, exist_ok=True); stage = Path(tempfile.mkdtemp(prefix=".bj132_complete_gateb_", dir=output.parent))
    try:
        provenance = validate_inputs(); outcomes = load_outcomes(); roles = load_roles(); pre = stage / "_pre_tax.csv"; buckets: dict[str, Decimal] = defaultdict(Decimal); total = no_bet = identities = role_rows = 0
        with gzip.open(FREEZE / "matched_delete_score_frontier.csv.gz", "rt", newline="", encoding="utf-8") as source, pre.open("w", newline="", encoding="utf-8") as target:
            reader = csv.DictReader(source); schema(reader, FRONTIER_FIELDS, "complete-issue frontier"); writer = csv.DictWriter(target, fieldnames=SETTLEMENT_FIELDS, lineterminator="\n"); writer.writeheader()
            for frontier in reader:
                role_set = None if frontier["arm"] == "NO_BET_CONTROL" else roles.get((frontier["variant_id"], frontier["portfolio_id"]))
                result = settle(frontier, role_set, outcomes)
                if frontier["arm"] == "NO_BET_CONTROL": no_bet += 1
                else:
                    role_rows += len(role_set or []); identities += frontier["arm"] == "MATCHED_FULL_N7"
                writer.writerow({**frontier, "settlement_status": result["status"], "outcome_gap_count": result["gap"], "coverage_hit": result["hit"], "deleted_code_occurred": result["deleted"], "truth_sequence": result["truth"], "final_winning_sp_product": money(result["product"]), "gross_pre_tax_yuan": money(result["gross"]), "winning_sp_sources": result["sources"], "deleted_match_e_sp": result["e_sp"], "deleted_probability": result["p"], "deleted_predicted_sp": result["sp"], "deleted_q": result["q"]})
                if result["status"] == "SETTLED": buckets[frontier["tax_bucket_key"]] += result["gross"]
                total += 1
        # Gate A stores each seven-role identity once; this settlement reads it
        # once for each of the three matched arms without duplicating the source.
        if (total, no_bet, identities, role_rows) != (160734, 3132, 52534, 1_103_214): raise RuntimeError("frozen denominator drift")
        h = gzip_writer(stage / "portfolio_settlement.csv.gz", SETTLEMENT_FIELDS); writer = h[-1]
        accounting: dict[str, dict[str, object]] = {}
        with pre.open(newline="", encoding="utf-8") as source:
            for row in csv.DictReader(source):
                gross = dec(row["gross_pre_tax_yuan"], "gross"); tax = gross * TAX_RATE if buckets[row["tax_bucket_key"]] >= TAX_THRESHOLD else Decimal(0); stake = dec(row["stake_yuan"], "stake") if row["settlement_status"] == "SETTLED" else Decimal(0)
                final = {**row, "stake_yuan": money(stake), "issue_policy_gross_yuan": money(buckets[row["tax_bucket_key"]]), "tax_yuan": money(tax), "after_tax_gross_yuan": money(gross-tax), "pre_tax_net_yuan": money(gross-stake), "tax_adjusted_net_yuan": money(gross-tax-stake)}; writer.writerow(final)
                if row["arm"] != "NO_BET_CONTROL":
                    entry = accounting.setdefault(row["tax_bucket_key"], {"variant_id": row["variant_id"], "arm": row["arm"], "issue": row["issue"], "fold": row["fold"], "year": row["year"], "issue_instance": row["issue_instance"], "portfolio_ids": set(), "frozen_stake_yuan": Decimal(0), "settled_portfolios": set(), "settled_stake_yuan": Decimal(0), "gross_pre_tax_yuan": Decimal(0), "tax_yuan": Decimal(0), "tax_bucket_key": row["tax_bucket_key"], "participation_policy": row["participation_policy"], "overlap_semantics": "all retained portfolios share one complete-issue policy bucket; no overlap rejection", "loyo_unit": "entire issue instance held intact within its year/fold"})
                    entry["portfolio_ids"].add(row["portfolio_id"]); entry["frozen_stake_yuan"] += dec(row["stake_yuan"], "frozen stake")
                    if row["settlement_status"] == "SETTLED": entry["settled_portfolios"].add(row["portfolio_id"]); entry["settled_stake_yuan"] += stake; entry["gross_pre_tax_yuan"] += gross; entry["tax_yuan"] += tax
        close_gzip(h); pre.unlink()
        all_rows, robust, issue_support = summaries(stage / "portfolio_settlement.csv.gz"); write_csv(stage / "arm_summary.csv", SUMMARY_FIELDS, all_rows); write_csv(stage / "robustness_summary.csv", SUMMARY_FIELDS, robust); write_csv(stage / "issue_support_summary.csv", ISSUE_SUPPORT_FIELDS, issue_support); write_csv(stage / "ranker_comparison.csv", COMPARISON_FIELDS, comparisons(all_rows + robust)); delta_count, pair_count = deltas_and_strata(stage, stage / "portfolio_settlement.csv.gz")
        accounting_rows = []
        for entry in accounting.values():
            portfolios = entry.pop("portfolio_ids"); settled = entry.pop("settled_portfolios")
            accounting_rows.append({**entry, "portfolio_count": len(portfolios), "frozen_stake_yuan": money(entry["frozen_stake_yuan"]), "settled_portfolios": len(settled), "settled_stake_yuan": money(entry["settled_stake_yuan"]), "gross_pre_tax_yuan": money(entry["gross_pre_tax_yuan"]), "tax_yuan": money(entry["tax_yuan"])})
        write_csv(stage / "issue_policy_accounting.csv", ACCOUNTING_FIELDS, sorted(accounting_rows, key=lambda row: (row["variant_id"], row["arm"], int(str(row["year"])), int(str(row["issue"])))) )
        positives = [row for row in all_rows if row["arm"] != "MATCHED_FULL_N7" and row["tax_adjusted_roi"] and dec(row["tax_adjusted_roi"], "ROI") > 0]
        decision = {"decision": "POSITIVE_REQUIRES_STRICT_INDEPENDENT_EV" if positives else "NO_PROMOTION", "primary_unit": "complete (issue, fold) instance", "positive_all_rows": len(positives), "promotion_authorized": False, "strict_independent_ev_required": bool(positives), "rule": "Only an ALL-scope positive primary complete-issue deletion arm can trigger strict independent EV; otherwise no promotion."}
        (stage / "decision.json").write_text(json.dumps(decision, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        write_csv(stage / "source_census.csv", SOURCE_FIELDS, [{"source": "bj132_gate_a_complete_issue_preoutcome_v1r1", "role": "accepted primary complete-issue outcome-unexposed freeze", "manifest_sha256": FREEZE_MANIFEST, "payload": "matched_delete_score_frontier.csv.gz", "payload_sha256": exact_manifest(FREEZE, FREEZE_MANIFEST)["matched_delete_score_frontier.csv.gz"], "rows": 160734, "join_status": "all frozen rows retained; 3132 explicit no-bets"}, {"source": "bj95_gate_b_outcome_settlement_v2r8", "role": "canonical final-SP outcome join", "manifest_sha256": OUTCOME_MANIFEST, "payload": "canonical_outcome_join.csv", "payload_sha256": OUTCOME_PAYLOAD, "rows": len(outcomes), "join_status": "missing outcome rows retained fail-closed"}])
        card = {"issue": 132, "contract": CONTRACT, "runner_version": VERSION, "stage": "GATE_B_PRIMARY_COMPLETE_ISSUE_OUTCOME_SETTLEMENT", "provenance": provenance, "frozen_matrix": {"frontier_rows": 160734, "no_bet_rows": 3132, "portfolio_identities": 52534, "role_rows": 367738, "variants": 9, "ranker_disagreement_pairs": 43120}, "primary_unit": "complete (issue, fold) instance; no segment is used for selection, tax, participation, overlap, folds, or LOYO", "settlement": "A ¥2 sequence pays ¥2×0.65×product(canonical final winning SP) exactly once iff frozen allowed codes cover truth; final SP is uncapped.", "tax": "Aggregate gross by frozen issue_instance×variant×arm tax_bucket_key; if it reaches ¥10,000, tax each winning portfolio gross at 20%.", "accounting": "K/stake are frozen outputs, not gates; all frozen portfolios are retained with no overlap rejection. Unavailable canonical outcomes receive zero realized stake and are never replaced.", "required_diagnostics": "ranker_comparison includes matched FULL deltas, stake/gross retention and explicit payout-loss severity; deletion_strata includes calibration and ROI by E_SP, GM_E_SP, probability, predicted-SP and outcome type; issue_support_summary provides per-issue support.", "robustness": "ALL/YEAR/FOLD/LEAVE_ONE_YEAR_OUT summaries preserve complete issue instances; issue_policy_accounting retains participation and tax buckets.", "legacy_boundary": "The superseded segment Gate-A/Gate-B result is non-controlling sensitivity only and is not read by this runner.", "boundary": "No matching, candidate ranking, N7 construction, deletion ranking, threshold, budget, or capital amount is regenerated after outcome validation."}
        (stage / "settlement_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8"); shutil.copyfile(__file__, stage / "settlement_runner.py"); (stage / "README.md").write_text("# #132 primary complete-issue Gate B\n\nCanonical settlement of accepted complete-issue FULL / p-min delete / q-min delete freeze. The segment settlement is legacy sensitivity only.\n", encoding="utf-8")
        gzip_names = ("portfolio_settlement.csv.gz", "matched_full_deltas.csv.gz", "q_minus_p_disagreement_deltas.csv.gz"); content = {"contract_version": "bj132-complete-issue-gateb-portable-content-v1", "gzip_payloads": {name: {"canonical_decompressed_sha256": uncompressed(stage / name)[0], "canonical_decompressed_bytes": uncompressed(stage / name)[1]} for name in gzip_names}, "non_compressed_controls": {item.name: sha(item) for item in sorted(stage.iterdir()) if item.is_file() and item.name not in gzip_names}}
        (stage / "CONTENT_IDENTITY.json").write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8"); sums = {item.name: sha(item) for item in sorted(stage.iterdir()) if item.is_file()}; (stage / "SHA256SUMS.json").write_text(json.dumps(sums, indent=2, sort_keys=True) + "\n", encoding="utf-8"); os.replace(stage, output)
        return {"manifest_sha256": sha(output / "SHA256SUMS.json"), "content_identity_sha256": sha(output / "CONTENT_IDENTITY.json"), "decision": decision, "summary_rows": len(all_rows), "delta_rows": delta_count, "q_pair_rows": pair_count}
    except Exception:
        shutil.rmtree(stage, ignore_errors=True); raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--output", type=Path, default=OUTPUT); args = parser.parse_args(); print(json.dumps(build(args.output.resolve()), sort_keys=True))


if __name__ == "__main__":
    main()
