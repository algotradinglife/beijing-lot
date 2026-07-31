#!/usr/bin/env python3
"""One-shot outcome settlement for #91's immutable Gate-A package.

The program deliberately refuses to rebuild a single selection.  It verifies
the merged Gate-A payload first, then reads the canonical settlement columns
for only the frozen match identities and emits an immutable Gate-B bundle.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import itertools
import json
import os
import shutil
import sqlite3
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FREEZE = ROOT / "results" / "bj91_gate_a_preoutcome_v1r6"
INHERITED79 = ROOT / "results" / "bj79_gate_a_closing_sp_proxy_v2r1"
OUT = ROOT / "results" / "bj91_gate_b_outcome_settlement_v1"
SOURCE_DB = ROOT.parent.parent / "data" / "derived" / "beidan_xlsm" / "beidan_xlsm.sqlite"

EXPECTED_GATE_A_MANIFEST = "bd7159715cca84e9d2adb9e089d016ec4e4d72603f8f8d5a8b070eb5027c2c33"
EXPECTED_SOURCE_SHA256 = "7f62079b18b3c028884da92aa8393f5b198246c9d7c32cd0b401562a055c5d6f"
FACTOR = Decimal("0.65")
STAKE_PER_SEQUENCE = Decimal("2")
SP_CAP = Decimal("5")
CODES = ("3", "1", "0")
MONEY_QUANTUM = Decimal("0.000001")
getcontext().prec = 128

ARM_SPECS = {
    "POINT_SP5_POSITIVE_EV": ("point_k", "point_retained_mass", "point_stake_yuan", "POINT_SP5"),
    "CONSERVATIVE_M2_SP5_POSITIVE_EV": ("conservative_k", "conservative_retained_mass", "conservative_stake_yuan", "M2_SP5"),
    "PROBABILITY_ONLY_MATCHED_TO_POINT": ("probability_matched_point_k", "probability_matched_point_mass", "probability_matched_point_stake_yuan", "POINT_SP5"),
    "PROBABILITY_ONLY_MATCHED_TO_CONSERVATIVE": ("probability_matched_conservative_k", "probability_matched_conservative_mass", "probability_matched_conservative_stake_yuan", "M2_SP5"),
    "FULL_3_TO_N_ANALYTIC": ("full_coverage_k", "full_coverage_mass", "full_coverage_stake_yuan", "POINT_SP5"),
    "INHERITED79_SP5_CAPPED_60PCT_PREFIX": ("inherited79_k", "inherited79_retained_mass", "inherited79_stake_yuan", "INHERITED79_CLOSING_SP5_PROXY"),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def d(value: object) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise RuntimeError(f"invalid Decimal: {value!r}") from exc


def six(value: Decimal | None) -> str:
    return "" if value is None else format(value.quantize(MONEY_QUANTUM), "f")


def ratio(value: Decimal | None) -> str:
    return "" if value is None else format(value, ".12f")


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_gzip_csv(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def verify_manifest(bundle: Path) -> tuple[dict[str, str], str]:
    manifest_path = bundle / "SHA256SUMS.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest or len(manifest) != len(set(manifest)):
        raise RuntimeError(f"invalid manifest: {bundle}")
    actual = {
        path.name: sha256(path)
        for path in bundle.iterdir()
        if path.is_file() and path.name != manifest_path.name
    }
    if manifest != actual:
        raise RuntimeError(f"manifest is not an exact non-empty bundle coverage: {bundle}")
    return manifest, sha256(manifest_path)


def frozen_quarter(issue: str) -> str:
    """Derive calendar quarter only from the frozen YYMM... issue identity."""
    if len(issue) < 5 or not issue.isdigit():
        raise RuntimeError(f"cannot derive frozen issue quarter: {issue!r}")
    month = int(issue[2:4])
    if month < 1 or month > 12:
        raise RuntimeError(f"invalid frozen issue month: {issue!r}")
    return f"20{issue[:2]}-Q{(month - 1) // 3 + 1}"


def sequence_hash(sequences: list[str]) -> str:
    return hashlib.sha256("\n".join(sequences).encode("ascii")).hexdigest()


def verify_gate_a_before_outcomes() -> dict[str, object]:
    _, gate_a_manifest_sha = verify_manifest(FREEZE)
    if gate_a_manifest_sha != EXPECTED_GATE_A_MANIFEST:
        raise RuntimeError("unexpected Gate-A manifest identity")
    card = json.loads((FREEZE / "preoutcome_card.json").read_text(encoding="utf-8"))
    if card.get("gate_b_settlement_binding", {}).get("factor") != "0.65":
        raise RuntimeError("Gate-A factor binding drift")
    if card.get("gate_b_settlement_binding", {}).get("rounding") != "pre_round_decimal_value_serialized_to_6_decimal_places; no_paid_cent_rounding_applied":
        raise RuntimeError("Gate-A rounding binding drift")
    source_sha = sha256(SOURCE_DB)
    if source_sha != EXPECTED_SOURCE_SHA256:
        raise RuntimeError("canonical outcome source SHA-256 mismatch; stop before outcome query")
    return {
        "gate_a_manifest_sha256": gate_a_manifest_sha,
        "source_db_sha256": source_sha,
        "gate_a_settlement_binding": card["gate_b_settlement_binding"],
        "inherited79_manifest_sha256": card["input_manifests_sha256"]["bj79"],
    }


def load_frozen_inputs() -> tuple[dict[str, dict[str, str]], dict[str, list[dict[str, str]]], dict[tuple[str, str], list[str]], dict[str, dict[str, list[dict[str, str]]]]]:
    definitions = read_csv(FREEZE / "group_definitions.csv")
    summaries = read_csv(FREEZE / "group_arm_summaries.csv")
    legs = read_gzip_csv(FREEZE / "outcome_safe_legs.csv.gz")
    if len(definitions) != len(summaries) or len(definitions) != 30_352:
        raise RuntimeError("Gate-A group definitions/summaries cardinality drift")
    summary_by_group = {row["group_id"]: row for row in summaries}
    definition_by_group = {row["group_id"]: row for row in definitions}
    if len(summary_by_group) != len(summaries) or set(summary_by_group) != set(definition_by_group):
        raise RuntimeError("duplicate or mismatched frozen group identity")
    legs_by_group: dict[str, list[dict[str, str]]] = defaultdict(list)
    for leg in legs:
        legs_by_group[leg["group_id"]].append(leg)
    if set(legs_by_group) != set(definition_by_group):
        raise RuntimeError("frozen leg groups do not exactly cover definitions")
    for group_id, rows in legs_by_group.items():
        rows.sort(key=lambda row: int(row["position"]))
        expected_n = int(definition_by_group[group_id]["n"])
        if len(rows) != expected_n or [int(row["position"]) for row in rows] != list(range(1, expected_n + 1)):
            raise RuntimeError(f"invalid frozen leg ordering: {group_id}")
        if any(row["issue"] != definition_by_group[group_id]["issue"] for row in rows):
            raise RuntimeError(f"frozen issue mismatch: {group_id}")

    selected: dict[tuple[str, str], list[str]] = defaultdict(list)
    with gzip.open(FREEZE / "selected_sequences.jsonl.gz", "rt", encoding="utf-8") as handle:
        for line in handle:
            item = json.loads(line)
            key = (item["group_id"], item["arm"])
            selected[key].append(item["sequence"])
    for key, sequences in selected.items():
        if len(sequences) != len(set(sequences)) or any(set(sequence) - set(CODES) for sequence in sequences):
            raise RuntimeError(f"duplicate/invalid frozen selection: {key}")

    inherited_legs: dict[str, dict[str, list[dict[str, str]]]] = defaultdict(dict)
    _, inherited_sha = verify_manifest(INHERITED79)
    card = json.loads((FREEZE / "preoutcome_card.json").read_text(encoding="utf-8"))
    if inherited_sha != card["input_manifests_sha256"]["bj79"]:
        raise RuntimeError("inherited #79 manifest drift")
    source_rows = read_csv(INHERITED79 / "frozen_group_legs.csv")
    raw: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in source_rows:
        raw[row["group_id"]].append(row)
    for source_group_id, rows in raw.items():
        rows.sort(key=lambda row: int(row["position"]))
        if len(rows) != 7 or [int(row["position"]) for row in rows] != list(range(1, 8)):
            raise RuntimeError(f"bad inherited #79 legs: {source_group_id}")
        inherited_legs[source_group_id]["legs"] = rows
    return summary_by_group, legs_by_group, selected, inherited_legs


def load_outcomes(match_ids: set[int]) -> tuple[dict[int, dict[str, str]], list[dict[str, str]]]:
    """Read only PI-authorized canonical settlement columns for frozen IDs."""
    outcomes: dict[int, dict[str, str]] = {}
    rows: list[dict[str, str]] = []
    connection = sqlite3.connect(f"file:{SOURCE_DB}?mode=ro", uri=True)
    try:
        ids = sorted(match_ids)
        for start in range(0, len(ids), 900):
            chunk = ids[start:start + 900]
            marks = ",".join("?" for _ in chunk)
            query = f"""
                SELECT match_id, result_code, winning_sp, winning_sp_source,
                       settlement_quality, has_trusted_settlement
                FROM match_features
                WHERE match_id IN ({marks})
            """
            for values in connection.execute(query, chunk):
                match_id, code, winning_sp, source, quality, trusted = values
                match_id = int(match_id)
                if match_id in outcomes:
                    raise RuntimeError(f"duplicate canonical outcome identity: {match_id}")
                record = {
                    "match_id": str(match_id),
                    "result_code": "" if code is None else str(code),
                    "winning_sp": "" if winning_sp is None else str(winning_sp),
                    "winning_sp_source": "" if source is None else str(source),
                    "settlement_quality": "" if quality is None else str(quality),
                    "has_trusted_settlement": str(int(trusted or 0)),
                }
                outcomes[match_id] = record
                rows.append(record)
    finally:
        connection.close()
    rows.sort(key=lambda row: int(row["match_id"]))
    return outcomes, rows


def valid_outcome(row: dict[str, str] | None) -> bool:
    if row is None or row["result_code"] not in CODES or not row["winning_sp_source"]:
        return False
    try:
        return d(row["winning_sp"]) > 0 and row["settlement_quality"] == "trusted" and row["has_trusted_settlement"] == "1"
    except RuntimeError:
        return False


def probabilities_and_prices(legs: list[dict[str, str]], sequence: str, basis: str, inherited: list[dict[str, str]] | None) -> tuple[Decimal, Decimal, Decimal]:
    if len(sequence) != len(legs):
        raise RuntimeError("frozen selection has wrong leg count")
    probability, uncapped, effective = Decimal("1"), Decimal("1"), Decimal("1")
    for position, (leg, code) in enumerate(zip(legs, sequence)):
        if basis == "INHERITED79_CLOSING_SP5_PROXY":
            if inherited is None:
                raise RuntimeError("missing inherited #79 proxy legs")
            source = inherited[position]
            if source["match_id"] != leg["match_id"]:
                raise RuntimeError("inherited #79 identity mismatch")
            probability *= d(source[f"p_{code}"])
            price = d(source[f"closing_sp_{code}"])
        else:
            probability *= d(leg[f"p{code}"])
            prefix = "point_sp" if basis == "POINT_SP5" else "m2_sp"
            price = d(leg[f"{prefix}_{code}"])
        uncapped *= price
        effective *= min(price, SP_CAP)
    return probability, uncapped, effective


def arm_sequences(group_id: str, n: int, arm: str, selected: dict[tuple[str, str], list[str]]) -> list[str]:
    if arm == "FULL_3_TO_N_ANALYTIC":
        # Full coverage has an analytical expected value; materializing every
        # 3^N sequence for every group would be needless work and would not
        # alter a frozen selection (there is no selection to reconstruct).
        return []
    return selected.get((group_id, arm), [])


def metric_for_group(legs: list[dict[str, str]], group_id: str, n: int, arm: str, summary: dict[str, str], selected: dict[tuple[str, str], list[str]], inherited: list[dict[str, str]] | None) -> tuple[int, Decimal, Decimal, Decimal, str]:
    k_field, mass_field, stake_field, basis = ARM_SPECS[arm]
    raw_k = summary[k_field]
    if not raw_k.isdigit():
        if arm == "INHERITED79_SP5_CAPPED_60PCT_PREFIX":
            return 0, Decimal("0"), Decimal("0"), Decimal("0"), "NOT_APPLICABLE"
        raise RuntimeError(f"invalid frozen K: {group_id}/{arm}")
    k = int(raw_k)
    sequences = arm_sequences(group_id, n, arm, selected)
    if arm != "FULL_3_TO_N_ANALYTIC" and len(sequences) != k:
        raise RuntimeError(f"frozen K/selection mismatch: {group_id}/{arm}")
    if arm == "FULL_3_TO_N_ANALYTIC" and k != 3 ** n:
        raise RuntimeError(f"full analytical K mismatch: {group_id}")
    stake = d(summary[stake_field])
    if stake != STAKE_PER_SEQUENCE * k:
        raise RuntimeError(f"frozen stake mismatch: {group_id}/{arm}")
    if arm == "FULL_3_TO_N_ANALYTIC":
        expectation = Decimal("1")
        for position, leg in enumerate(legs):
            one_leg = Decimal("0")
            for code in CODES:
                probability, _, effective = probabilities_and_prices([leg], code, basis, None if inherited is None else [inherited[position]])
                one_leg += probability * effective
            expectation *= one_leg
        expected_gross = STAKE_PER_SEQUENCE * FACTOR * expectation
    else:
        expected_gross = Decimal("0")
        for sequence in sequences:
            probability, _, effective = probabilities_and_prices(legs, sequence, basis, inherited)
            expected_gross += STAKE_PER_SEQUENCE * FACTOR * probability * effective
    return k, d(summary[mass_field]), stake, expected_gross, basis


def row_sort_key(row: dict[str, object]) -> tuple[int, int, int, str]:
    return (int(str(row["issue"])), int(str(row["group_ordinal"])), int(str(row["n"])), str(row["group_id"]))


def aggregate(rows: list[dict[str, object]], **scope: object) -> dict[str, object]:
    settled = [row for row in rows if row["settlement_status"] != "UNAVAILABLE"]
    bet_rows = [row for row in settled if int(str(row["k"])) > 0]
    unavailable = len(rows) - len(settled)
    stake = sum((d(row["stake_yuan"]) for row in bet_rows), Decimal("0"))
    gross = sum((d(row["gross_yuan"]) for row in bet_rows), Decimal("0"))
    net = gross - stake
    predicted_gross = sum((d(row["predicted_gross_yuan"]) for row in bet_rows), Decimal("0"))
    predicted_net = predicted_gross - stake
    cumulative = peak = drawdown = Decimal("0")
    streak = longest_streak = 0
    for row in sorted(bet_rows, key=row_sort_key):
        value = d(row["net_yuan"])
        cumulative += value
        peak = max(peak, cumulative)
        drawdown = max(drawdown, peak - cumulative)
        if row["hit"] == "YES":
            streak = 0
        else:
            streak += 1
            longest_streak = max(longest_streak, streak)
    hits = sum(row["hit"] == "YES" for row in bet_rows)
    positives = [(max(Decimal("0"), d(row["net_yuan"])), row) for row in bet_rows]
    total_positive = sum((value for value, _ in positives), Decimal("0"))
    by_issue: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for value, row in positives:
        by_issue[str(row["issue"])] += value
    best = max(bet_rows, key=lambda row: d(row["gross_yuan"]), default=None)
    best_issue = max(by_issue, key=by_issue.get, default="")
    ex_best_group = [row for row in bet_rows if best is None or row["group_id"] != best["group_id"]]
    ex_best_issue = [row for row in bet_rows if row["issue"] != best_issue]
    def net_and_stake(items: list[dict[str, object]]) -> tuple[Decimal, Decimal]:
        item_stake = sum((d(row["stake_yuan"]) for row in items), Decimal("0"))
        item_net = sum((d(row["net_yuan"]) for row in items), Decimal("0"))
        return item_net, item_stake
    ex_group_net, ex_group_stake = net_and_stake(ex_best_group)
    ex_issue_net, ex_issue_stake = net_and_stake(ex_best_issue)
    return {
        **scope,
        "group_arms_total": len(rows), "group_arms_settled_or_no_bet": len(settled), "group_arms_unavailable": unavailable,
        "bet_groups": len(bet_rows), "no_bet_groups": len(settled) - len(bet_rows),
        "bet_rate_all_groups": ratio(Decimal(len(bet_rows)) / Decimal(len(rows))) if rows else "",
        "unavailable_rate_all_groups": ratio(Decimal(unavailable) / Decimal(len(rows))) if rows else "",
        "total_k": sum(int(str(row["k"])) for row in bet_rows), "mean_k_bet_groups": ratio(Decimal(sum(int(str(row["k"])) for row in bet_rows)) / Decimal(len(bet_rows))) if bet_rows else "",
        "mean_retained_mass_bet_groups": ratio(sum((d(row["retained_mass"]) for row in bet_rows), Decimal("0")) / Decimal(len(bet_rows))) if bet_rows else "",
        "hits": hits, "hit_rate_bet_groups": ratio(Decimal(hits) / Decimal(len(bet_rows))) if bet_rows else "",
        "stake_yuan": six(stake), "gross_yuan": six(gross), "net_yuan": six(net), "roi": ratio(net / stake) if stake else "",
        "predicted_gross_yuan": six(predicted_gross), "predicted_net_yuan": six(predicted_net), "predicted_roi": ratio(predicted_net / stake) if stake else "",
        "realized_minus_predicted_net_yuan": six(net - predicted_net), "max_drawdown_yuan": six(drawdown),
        "longest_losing_streak_bet_groups": longest_streak,
        "best_payout_group_id": "" if best is None else str(best["group_id"]), "best_payout_issue": "" if best is None else str(best["issue"]),
        "best_gross_yuan": "" if best is None else six(d(best["gross_yuan"])),
        "ex_best_group_net_yuan": six(ex_group_net), "ex_best_group_roi": ratio(ex_group_net / ex_group_stake) if ex_group_stake else "",
        "ex_best_issue_net_yuan": six(ex_issue_net), "ex_best_issue_roi": ratio(ex_issue_net / ex_issue_stake) if ex_issue_stake else "",
        "positive_net_top_group_share": ratio(max((value for value, _ in positives), default=Decimal("0")) / total_positive) if total_positive else "",
        "positive_net_top_issue_share": ratio(max(by_issue.values(), default=Decimal("0")) / total_positive) if total_positive else "",
    }


def sp_error_summary(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    buckets: dict[tuple[str, str, str, str], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        if row["hit"] == "YES" and row["settlement_status"] == "SETTLED":
            buckets[(str(row["cohort"]), str(row["n"]), str(row["arm"]), str(row["prediction_price_basis"]))].append(row)
    output = []
    for key, members in sorted(buckets.items()):
        ratios = [d(row["final_over_predicted_winning_sp_product"]) for row in members]
        predicted_hit_gross = sum((d(row["predicted_hit_gross_yuan"]) for row in members), Decimal("0"))
        final_hit_gross = sum((d(row["gross_yuan"]) for row in members), Decimal("0"))
        output.append({
            "cohort": key[0], "n": key[1], "arm": key[2], "prediction_price_basis": key[3], "hit_groups": len(members),
            "mean_final_over_predicted_winning_sp_product": ratio(sum(ratios) / Decimal(len(ratios))),
            "min_final_over_predicted_winning_sp_product": ratio(min(ratios)), "max_final_over_predicted_winning_sp_product": ratio(max(ratios)),
            "predicted_hit_gross_yuan": six(predicted_hit_gross), "final_hit_gross_yuan": six(final_hit_gross),
            "final_minus_predicted_hit_gross_yuan": six(final_hit_gross - predicted_hit_gross),
        })
    return output


def main() -> int:
    if OUT.exists():
        raise SystemExit(f"refusing to overwrite immutable output: {OUT}")
    stage = Path(tempfile.mkdtemp(prefix="bj91-gate-b-", dir=OUT.parent))
    try:
        provenance = verify_gate_a_before_outcomes()
        summaries, legs_by_group, selected, inherited_legs = load_frozen_inputs()
        all_match_ids = {int(leg["match_id"]) for legs in legs_by_group.values() for leg in legs}
        outcomes, outcome_rows = load_outcomes(all_match_ids)
        if len(outcomes) > len(all_match_ids):
            raise RuntimeError("outcome query returned an unfrozen identity")

        settlement_rows: list[dict[str, object]] = []
        for group_id, summary in sorted(summaries.items()):
            legs = legs_by_group[group_id]
            n = int(summary["n"])
            inherited = None
            if summary["cohort"] == "PAIRED79":
                inherited = inherited_legs.get(summary["source_group_id"], {}).get("legs")
                if inherited is None:
                    raise RuntimeError(f"missing inherited #79 legs: {group_id}")
            invalid_ids = [leg["match_id"] for leg in legs if not valid_outcome(outcomes.get(int(leg["match_id"])))]
            status = "UNAVAILABLE" if invalid_ids else "SETTLED"
            truth = ""
            final_product = None
            final_sources = ""
            if status == "SETTLED":
                truth = "".join(outcomes[int(leg["match_id"])]["result_code"] for leg in legs)
                final_product = Decimal("1")
                final_sources = ";".join(sorted({outcomes[int(leg["match_id"])]["winning_sp_source"] for leg in legs}))
                for leg in legs:
                    final_product *= d(outcomes[int(leg["match_id"])]["winning_sp"])
            for arm in ARM_SPECS:
                k, retained_mass, stake, predicted_gross, basis = metric_for_group(legs, group_id, n, arm, summary, selected, inherited)
                if basis == "NOT_APPLICABLE":
                    continue
                hit = "UNAVAILABLE" if status == "UNAVAILABLE" else ("NO_BET" if k == 0 else ("YES" if arm == "FULL_3_TO_N_ANALYTIC" or truth in set(arm_sequences(group_id, n, arm, selected)) else "NO"))
                gross = None if status == "UNAVAILABLE" else (Decimal("0") if hit != "YES" else STAKE_PER_SEQUENCE * FACTOR * final_product)
                net = None if status == "UNAVAILABLE" else gross - stake
                predicted_winning_uncapped = predicted_winning_effective = predicted_hit_gross = None
                final_over_predicted = None
                if status == "SETTLED":
                    _, predicted_winning_uncapped, predicted_winning_effective = probabilities_and_prices(legs, truth, basis, inherited)
                    predicted_hit_gross = STAKE_PER_SEQUENCE * FACTOR * predicted_winning_effective
                    if predicted_winning_uncapped > 0:
                        final_over_predicted = final_product / predicted_winning_uncapped
                settlement_rows.append({
                    "cohort": summary["cohort"], "n": n, "group_id": group_id, "source_group_id": summary["source_group_id"],
                    "issue": summary["issue"], "year": summary["year"], "quarter": frozen_quarter(summary["issue"]), "fold": summary["fold"], "group_ordinal": summary["group_ordinal"],
                    "arm": arm, "prediction_price_basis": basis, "k": k, "stake_yuan": six(stake), "retained_mass": ratio(retained_mass),
                    "predicted_gross_yuan": six(predicted_gross), "predicted_net_yuan": six(predicted_gross - stake),
                    "settlement_status": status, "unavailable_match_ids": ";".join(invalid_ids), "unavailable_leg_count": len(invalid_ids),
                    "truth_sequence": truth, "final_winning_sp_product_uncapped": six(final_product), "winning_sp_sources": final_sources,
                    "hit": hit, "gross_yuan": six(gross), "net_yuan": six(net),
                    "predicted_winning_sp_product_uncapped": six(predicted_winning_uncapped), "predicted_winning_sp_product_effective_sp5": six(predicted_winning_effective),
                    "final_over_predicted_winning_sp_product": ratio(final_over_predicted), "predicted_hit_gross_yuan": six(predicted_hit_gross),
                    "settlement_factor": "0.65", "paid_cent_rounding_applied": "NO",
                })

        all_arms = sorted({str(row["arm"]) for row in settlement_rows})
        overview = []
        annual = []
        quarterly = []
        leave_one_year = []
        paired = []
        for cohort in sorted({str(row["cohort"]) for row in settlement_rows}):
            for n in sorted({int(row["n"]) for row in settlement_rows if row["cohort"] == cohort}):
                scoped = [row for row in settlement_rows if row["cohort"] == cohort and int(row["n"]) == n]
                for arm in all_arms:
                    rows = [row for row in scoped if row["arm"] == arm]
                    if not rows:
                        continue
                    overview.append(aggregate(rows, cohort=cohort, n=n, arm=arm, scope="ALL"))
                    for year in sorted({str(row["year"]) for row in rows}):
                        annual.append(aggregate([row for row in rows if row["year"] == year], cohort=cohort, n=n, arm=arm, scope="YEAR", scope_value=year))
                        leave_one_year.append(aggregate([row for row in rows if row["year"] != year], cohort=cohort, n=n, arm=arm, scope="LEAVE_ONE_YEAR_OUT", scope_value=year))
                    for quarter in sorted({str(row["quarter"]) for row in rows}):
                        quarterly.append(aggregate([row for row in rows if row["quarter"] == quarter], cohort=cohort, n=n, arm=arm, scope="QUARTER", scope_value=quarter))
                    if cohort == "PAIRED79":
                        paired.append(aggregate(rows, cohort=cohort, n=n, arm=arm, scope="SAME_IDENTITY_PAIRED79"))

        errors = sp_error_summary(settlement_rows)
        group_fields = list(settlement_rows[0])
        write_csv(stage / "outcome_join.csv", outcome_rows, ["match_id", "result_code", "winning_sp", "winning_sp_source", "settlement_quality", "has_trusted_settlement"])
        write_csv(stage / "group_arm_settlement.csv", settlement_rows, group_fields)
        summary_fields = list(overview[0])
        write_csv(stage / "arm_overview.csv", overview, summary_fields)
        write_csv(stage / "annual_summary.csv", annual, list(annual[0]))
        write_csv(stage / "quarterly_summary.csv", quarterly, list(quarterly[0]))
        write_csv(stage / "leave_one_year_out_summary.csv", leave_one_year, list(leave_one_year[0]))
        write_csv(stage / "paired79_same_identity_comparison.csv", paired, list(paired[0]))
        write_csv(stage / "predicted_sp_error_sensitivity.csv", errors, list(errors[0]))
        shutil.copyfile(__file__, stage / "settlement_runner.py")
        card = {
            "issue": 91,
            "stage": "GATE_B_ONE_SHOT_OUTCOME_SETTLEMENT",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "provenance": provenance,
            "input_freeze": str(FREEZE),
            "outcome_read_whitelist": ["match_features.match_id", "match_features.result_code", "match_features.winning_sp", "match_features.winning_sp_source", "match_features.settlement_quality", "match_features.has_trusted_settlement"],
            "quarter_rule": "derived from frozen issue YYMM... identity; no additional outcome column read",
            "settlement_rule": "stake=2*K; gross=2*0.65*product(final winning SP) only on a selected full-N hit; final winning SP uncapped; factor applied exactly once; pre-round Decimal serialized to 6 places; no paid-cent rounding",
            "unavailable_rule": "any missing, invalid, duplicate, ambiguous, or untrusted frozen leg makes every arm for that group UNAVAILABLE with no stake",
            "selection_rule": "all selections, K, probabilities, prices, ranks, caps, and groups are byte-frozen Gate-A inputs; no outcome-based re-selection or parameter search",
            "scope": "historical research only; no purchase, production, prospective policy, or promotion claim",
            "arms": list(ARM_SPECS),
        }
        (stage / "settlement_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest = {path.name: sha256(path) for path in sorted(stage.iterdir()) if path.is_file()}
        (stage / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(stage, OUT)
        print(json.dumps({
            "output": str(OUT), "gate_b_manifest_sha256": sha256(OUT / "SHA256SUMS.json"),
            "group_arm_rows": len(settlement_rows), "unavailable_group_arm_rows": sum(row["settlement_status"] == "UNAVAILABLE" for row in settlement_rows),
            "outcome_rows": len(outcome_rows),
        }, sort_keys=True))
        return 0
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
