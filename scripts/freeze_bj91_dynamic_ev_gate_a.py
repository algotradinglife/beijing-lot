#!/usr/bin/env python3
"""Freeze #91's corrected, outcome-safe N4/N5/N7 portfolio inputs.

This runner is deliberately a Gate-A-only program.  It reads no result,
score, winning-SP, ROI, or settlement source.  Its only inputs are the
already-accepted #89 OOS probability rows, #90 outcome-safe price vectors,
and #79's byte-frozen N7 prefix selection identities.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import io
import itertools
import json
import os
import shutil
import tempfile
from collections import Counter, defaultdict
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
# v1-v1r3 are superseded local/reviewed freezes. v1r4 fixes exact
# probability ordering and the complete #64 settlement implementation bind.
OUT = ROOT / "results" / "bj91_gate_a_preoutcome_v1r4"
P89 = ROOT / "results" / "bj89_gate_b_selector_v1_1"
P90 = ROOT / "results" / "bj90_downstream_safe_projection_v1r1"
P79 = ROOT / "results" / "bj79_gate_a_closing_sp_proxy_v2r1"

N_VALUES = (4, 5, 7)
CODES = ("3", "1", "0")
CODE_RANK = {code: index for index, code in enumerate(CODES)}
PAYOUT_FACTOR = 0.65
SP_CAP = 5.0
STAKE_PER_SEQUENCE_YUAN = 2
P89_ROWS_SHA = "ef02fccffdbe1d4f3cb70a4c8f7d24037bf2b9a40bea71e6fe0fbf465d679e7e"
P90_VECTORS_SHA = "2375e5570a9fb964f1beb5f4a20e5019755f62213ebde1463a609d23d1e2807b"
P79_LEGS_SHA = "3eb93433fa92f6c4327dd97b24ed7581d338eda2a338b34cd1b4d1bb87fa7efe"
P79_SEQUENCES_SHA = "f838293723c1d32722311dcee1a442ab3f3424b2f5f0e38eb2c5d7e65dbea1c8"
SHARED_SETTLEMENT_COMMIT = "15b6a03bf2909fe7376b393472c7ec67d23398ba"
SHARED_SETTLEMENT_RUNNER_PATH = "scripts/estimate_segment_betting_plan.py"
SHARED_SETTLEMENT_TEST_PATH = "tests/scripts/test_estimate_segment_betting_plan.py"
SHARED_SETTLEMENT_RUNNER_SHA = "cf981324deba1ecdd4c823cf42ff1d390538e9d3f14b561cb2112fcc0543569d"
SHARED_SETTLEMENT_TEST_SHA = "376be20f90680c9912cba0778630b39b90a80b6377ecd6862a0249e2ef2355f3"

P89_REQUIRED = {"match_id", "issue", "match_idx", "year", "fold", "p3", "p1", "p0"}
P90_REQUIRED = {
    "match_id", "issue", "match_idx", "year", "fold", "deployed_sp_3",
    "deployed_sp_1", "deployed_sp_0", "m2_conservative_sp_3",
    "m2_conservative_sp_1", "m2_conservative_sp_0",
}
LEG_FIELDS = [
    "cohort", "n", "group_id", "source_group_id", "position", "match_id", "issue",
    "match_idx", "year", "fold", "p3", "p1", "p0", "point_sp_3", "point_sp_1",
    "point_sp_0", "m2_sp_3", "m2_sp_1", "m2_sp_0", "point_sp5_3", "point_sp5_1",
    "point_sp5_0", "m2_sp5_3", "m2_sp5_1", "m2_sp5_0",
]
GROUP_FIELDS = [
    "cohort", "n", "group_id", "source_group_id", "issue", "fold", "year",
    "group_ordinal", "candidate_sequence_count", "point_k", "conservative_k",
    "probability_matched_point_k", "probability_matched_conservative_k", "full_coverage_k",
    "point_retained_mass", "conservative_retained_mass", "probability_matched_point_mass",
    "probability_matched_conservative_mass", "full_coverage_mass", "point_stake_yuan",
    "conservative_stake_yuan", "probability_matched_point_stake_yuan",
    "probability_matched_conservative_stake_yuan", "full_coverage_stake_yuan",
    "inherited79_k", "inherited79_retained_mass", "inherited79_stake_yuan",
]
SELECTION_FIELDS = ["cohort", "n", "group_id", "arm", "rank", "sequence"]

# Seven source decimals with up to 17 significant digits require more than
# the default 28-place Decimal context for an exact product and comparison.
getcontext().prec = 128


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest_sha(bundle: Path) -> str:
    declared = json.loads((bundle / "SHA256SUMS.json").read_text())
    actual = {path.name: sha256(path) for path in bundle.iterdir() if path.is_file() and path.name != "SHA256SUMS.json"}
    if actual != declared:
        raise RuntimeError(f"input manifest mismatch: {bundle}")
    return sha256(bundle / "SHA256SUMS.json")


def open_text(path: Path):
    return gzip.open(path, "rt", newline="", encoding="utf-8") if path.suffix == ".gz" else path.open(newline="", encoding="utf-8")


def product(values: Iterable[float]) -> float:
    value = 1.0
    for item in values:
        value *= item
    return value


def fmt(value: float) -> str:
    return format(value, ".15g")


def identity(row: dict[str, str]) -> tuple[str, str, str, str]:
    return (row["match_id"], row["issue"], row["match_idx"], row["fold"])


def safe_probability_rows(path: Path) -> dict[tuple[str, str, str, str], dict[str, str]]:
    """Project #89 at read time, never copying an outcome-bearing field."""
    rows: dict[tuple[str, str, str, str], dict[str, str]] = {}
    with open_text(path) as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or not P89_REQUIRED.issubset(reader.fieldnames):
            raise RuntimeError("#89 deployed-policy schema is missing required safe fields")
        for raw in reader:
            row = {field: raw[field] for field in P89_REQUIRED}
            key = identity(row)
            if key in rows:
                raise RuntimeError(f"duplicate #89 identity: {key}")
            probabilities = [float(row[f"p{code}"]) for code in CODES]
            if any(value <= 0.0 for value in probabilities) or abs(sum(probabilities) - 1.0) > 1e-9:
                raise RuntimeError(f"invalid #89 probability vector: {key}")
            rows[key] = row
    return rows


def safe_price_rows(path: Path) -> dict[tuple[str, str, str, str], dict[str, str]]:
    rows: dict[tuple[str, str, str, str], dict[str, str]] = {}
    with open_text(path) as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or not P90_REQUIRED.issubset(reader.fieldnames):
            raise RuntimeError("#90 vector schema is missing required safe fields")
        for raw in reader:
            row = {field: raw[field] for field in P90_REQUIRED}
            key = identity(row)
            if key in rows:
                raise RuntimeError(f"duplicate #90 identity: {key}")
            prices = [float(row[f"{prefix}_{code}"]) for prefix in ("deployed_sp", "m2_conservative_sp") for code in CODES]
            if any(value <= 0.0 for value in prices):
                raise RuntimeError(f"invalid #90 price vector: {key}")
            rows[key] = row
    return rows


def common_rows(probabilities: dict[tuple[str, str, str, str], dict[str, str]], prices: dict[tuple[str, str, str, str], dict[str, str]]) -> dict[tuple[str, str, str, str], dict[str, object]]:
    common: dict[tuple[str, str, str, str], dict[str, object]] = {}
    for key in sorted(set(probabilities) & set(prices)):
        p, sp = probabilities[key], prices[key]
        if p["year"] != sp["year"]:
            raise RuntimeError(f"year disagreement across #89/#90: {key}")
        common[key] = {
            "match_id": p["match_id"], "issue": p["issue"], "match_idx": p["match_idx"],
            "year": p["year"], "fold": p["fold"],
            "probability": {code: float(p[f"p{code}"]) for code in CODES},
            "probability_decimal": {code: Decimal(p[f"p{code}"]) for code in CODES},
            "point_sp": {code: float(sp[f"deployed_sp_{code}"]) for code in CODES},
            "m2_sp": {code: float(sp[f"m2_conservative_sp_{code}"]) for code in CODES},
        }
    if len(common) != 47_819:
        raise RuntimeError(f"unexpected #89/#90 common row count: {len(common)}")
    return common


def make_primary_groups(common: dict[tuple[str, str, str, str], dict[str, object]], n: int):
    partitions: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in common.values():
        partitions[(str(row["issue"]), str(row["fold"]))].append(row)
    groups = []
    census = []
    for (issue, fold), rows in sorted(partitions.items(), key=lambda item: (int(item[0][0]), item[0][1])):
        rows.sort(key=lambda row: (int(str(row["match_idx"])), int(str(row["match_id"]))))
        complete_count, remainder = divmod(len(rows), n)
        census.append({
            "cohort": "PRIMARY", "n": n, "issue": issue, "fold": fold,
            "input_rows": len(rows), "complete_groups": complete_count, "dropped_remainder_rows": remainder,
            "drop_rule": "final_consecutive_chunk_lt_N_within_issue_fold",
        })
        for ordinal in range(complete_count):
            legs = rows[ordinal * n:(ordinal + 1) * n]
            groups.append({
                "cohort": "PRIMARY", "n": n,
                "group_id": f"PRIMARY-N{n}-{fold}-I{issue}-G{ordinal + 1:04d}",
                "source_group_id": "", "issue": issue, "fold": fold,
                "year": str(legs[0]["year"]), "group_ordinal": ordinal + 1, "legs": legs,
            })
    return groups, census


def inherited79_groups(common: dict[tuple[str, str, str, str], dict[str, object]]):
    groups: dict[str, list[tuple[int, tuple[str, str, str]]]] = defaultdict(list)
    common_by_bare = {(key[0], key[1], key[2]): key for key in common}
    if len(common_by_bare) != len(common):
        raise RuntimeError("#89/#90 common identity is ambiguous without fold")
    with (P79 / "frozen_group_legs.csv").open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"group_id", "position", "match_id", "issue", "match_idx"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise RuntimeError("#79 frozen-leg schema drift")
        for row in reader:
            groups[row["group_id"]].append((int(row["position"]), (row["match_id"], row["issue"], row["match_idx"])))
    categories = Counter()
    cross_fold_full_overlap = 0
    complete: dict[str, list[dict[str, object]]] = {}
    for source_group_id, entries in groups.items():
        entries.sort()
        if len(entries) != 7 or [position for position, _ in entries] != list(range(1, 8)):
            raise RuntimeError(f"invalid #79 group positions: {source_group_id}")
        candidates = []
        for _, bare in entries:
            if bare in common_by_bare:
                candidates.append(common_by_bare[bare])
        overlap = len(candidates)
        if overlap == 0:
            categories["zero_overlap"] += 1
        elif overlap < 7:
            categories["partial_overlap"] += 1
        else:
            folds = {key[3] for key in candidates}
            if len(folds) != 1:
                # It has all seven identities but cannot be a same-fold #91
                # paired group; PI's three-way census requires it be retained
                # in the non-complete/partial category rather than dropped.
                categories["partial_overlap"] += 1
                cross_fold_full_overlap += 1
            else:
                categories["complete_common"] += 1
                complete[source_group_id] = [common[key] for key in candidates]
    expected = {"complete_common": 2_419, "partial_overlap": 6_077, "zero_overlap": 1_405}
    if dict(categories) != expected:
        raise RuntimeError(f"#79 source census mismatch: {dict(categories)}")
    return complete, dict(categories), cross_fold_full_overlap


def inherited79_sequences(complete_ids: set[str]) -> dict[str, dict[str, object]]:
    selected: dict[str, dict[str, object]] = {}
    path = P79 / "frozen_prefix_sequences.jsonl.gz"
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            if record["group_id"] not in complete_ids or record["arm"] != "SP5_CAPPED_EXPECTED_CONTRIBUTION":
                continue
            if record["group_id"] in selected:
                raise RuntimeError(f"duplicate #79 baseline selection: {record['group_id']}")
            sequences = record["selected_sequences"]
            if record["n"] != 7 or record["k"] != len(sequences):
                raise RuntimeError(f"invalid #79 baseline record: {record['group_id']}")
            digest = hashlib.sha256("\n".join(sequences).encode("ascii")).hexdigest()
            if digest != record["sequence_set_sha256"]:
                raise RuntimeError(f"#79 baseline sequence hash mismatch: {record['group_id']}")
            selected[record["group_id"]] = record
    if set(selected) != complete_ids:
        raise RuntimeError("missing #79 baseline selections for complete paired cohort")
    return selected


def seq_metrics(legs: list[dict[str, object]], sequence: str) -> dict[str, float]:
    probability = product(float(leg["probability"][code]) for leg, code in zip(legs, sequence))
    point_product = product(min(float(leg["point_sp"][code]), SP_CAP) for leg, code in zip(legs, sequence))
    m2_product = product(min(float(leg["m2_sp"][code]), SP_CAP) for leg, code in zip(legs, sequence))
    return {
        "joint_probability": probability,
        "point_effective_sp_product": point_product,
        "conservative_effective_sp_product": m2_product,
        "point_ev_per_2": 2.0 * (PAYOUT_FACTOR * probability * point_product - 1.0),
        "conservative_ev_per_2": 2.0 * (PAYOUT_FACTOR * probability * m2_product - 1.0),
    }


def exact_joint_probability(legs: list[dict[str, object]], sequence: str) -> Decimal:
    """Multiply the frozen decimal source values without float rounding."""
    value = Decimal(1)
    for leg, code in zip(legs, sequence):
        value *= Decimal(leg["probability_decimal"][code])
    return value


def probability_desc_order(scored):
    """True exact joint-probability DESC, then the frozen 3/1/0 tuple order."""
    return sorted(scored, key=lambda item: (-item[2], tuple(CODE_RANK[code] for code in item[0])))


def write_csv(path: Path, fields: list[str], rows: Iterable[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_legs(path: Path, groups: list[dict[str, object]]) -> int:
    count = 0
    with path.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
        with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=LEG_FIELDS, lineterminator="\n")
            writer.writeheader()
            for group in groups:
                for position, leg in enumerate(group["legs"], start=1):
                    row = {key: group.get(key, "") for key in ("cohort", "n", "group_id", "source_group_id")}
                    row.update({key: leg[key] for key in ("match_id", "issue", "match_idx", "year", "fold")})
                    row["position"] = position
                    for code in CODES:
                        row[f"p{code}"] = fmt(float(leg["probability"][code]))
                        row[f"point_sp_{code}"] = fmt(float(leg["point_sp"][code]))
                        row[f"m2_sp_{code}"] = fmt(float(leg["m2_sp"][code]))
                        row[f"point_sp5_{code}"] = fmt(min(float(leg["point_sp"][code]), SP_CAP))
                        row[f"m2_sp5_{code}"] = fmt(min(float(leg["m2_sp"][code]), SP_CAP))
                    writer.writerow(row)
                    count += 1
    return count


def emit_group(group: dict[str, object], selections, summary_rows: list[dict[str, object]], inherited: dict[str, object] | None = None) -> None:
    legs = group["legs"]
    n = int(group["n"])
    all_sequences = ["".join(item) for item in itertools.product(CODES, repeat=n)]
    scored = [(sequence, seq_metrics(legs, sequence), exact_joint_probability(legs, sequence)) for sequence in all_sequences]
    point = [(sequence, values) for sequence, values, _ in scored if values["point_ev_per_2"] > 0.0]
    conservative = [(sequence, values) for sequence, values, _ in scored if values["conservative_ev_per_2"] > 0.0]
    probability_order = probability_desc_order(scored)
    arms = {
        "POINT_SP5_POSITIVE_EV": point,
        "CONSERVATIVE_M2_SP5_POSITIVE_EV": conservative,
        "PROBABILITY_ONLY_MATCHED_TO_POINT": [(sequence, values) for sequence, values, _ in probability_order[:len(point)]],
        "PROBABILITY_ONLY_MATCHED_TO_CONSERVATIVE": [(sequence, values) for sequence, values, _ in probability_order[:len(conservative)]],
    }
    for arm, items in arms.items():
        for rank, (sequence, values) in enumerate(items, start=1):
            # Values are intentionally not duplicated here.  The per-leg
            # outcome-safe table plus this exact sequence selection is the
            # complete, replayable source of each EV.  Avoiding repeated
            # values keeps the durable review package practical in Git.
            selections.write(json.dumps({
                "cohort": group["cohort"], "n": n, "group_id": group["group_id"],
                "arm": arm, "rank": rank, "sequence": sequence,
            }, sort_keys=True, separators=(",", ":")) + "\n")
    inherited_items = []
    if inherited is not None:
        for rank, sequence in enumerate(inherited["selected_sequences"], start=1):
            values = seq_metrics(legs, sequence)
            inherited_items.append((sequence, values))
            selections.write(json.dumps({
                "cohort": group["cohort"], "n": n, "group_id": group["group_id"],
                "arm": "INHERITED79_SP5_CAPPED_60PCT_PREFIX", "rank": rank, "sequence": sequence,
            }, sort_keys=True, separators=(",", ":")) + "\n")
    mass = lambda items: sum(values["joint_probability"] for _, values in items)
    summary_rows.append({
        **{key: group[key] for key in ("cohort", "n", "group_id", "source_group_id", "issue", "fold", "year", "group_ordinal")},
        "candidate_sequence_count": 3 ** n,
        "point_k": len(point), "conservative_k": len(conservative),
        "probability_matched_point_k": len(point), "probability_matched_conservative_k": len(conservative),
        "full_coverage_k": 3 ** n, "point_retained_mass": fmt(mass(point)),
        "conservative_retained_mass": fmt(mass(conservative)),
        "probability_matched_point_mass": fmt(mass([(sequence, values) for sequence, values, _ in probability_order[:len(point)]])),
        "probability_matched_conservative_mass": fmt(mass([(sequence, values) for sequence, values, _ in probability_order[:len(conservative)]])),
        "full_coverage_mass": "1", "point_stake_yuan": STAKE_PER_SEQUENCE_YUAN * len(point),
        "conservative_stake_yuan": STAKE_PER_SEQUENCE_YUAN * len(conservative),
        "probability_matched_point_stake_yuan": STAKE_PER_SEQUENCE_YUAN * len(point),
        "probability_matched_conservative_stake_yuan": STAKE_PER_SEQUENCE_YUAN * len(conservative),
        "full_coverage_stake_yuan": STAKE_PER_SEQUENCE_YUAN * (3 ** n),
        "inherited79_k": len(inherited_items) if inherited is not None else ("NOT_APPLICABLE_NO_FROZEN_N4_N5_BASELINE" if n < 7 else "NOT_APPLICABLE_ONLY_PAIRED79_N7_BASELINE"),
        "inherited79_retained_mass": fmt(mass(inherited_items)) if inherited is not None else ("NOT_APPLICABLE_NO_FROZEN_N4_N5_BASELINE" if n < 7 else "NOT_APPLICABLE_ONLY_PAIRED79_N7_BASELINE"),
        "inherited79_stake_yuan": STAKE_PER_SEQUENCE_YUAN * len(inherited_items) if inherited is not None else ("NOT_APPLICABLE_NO_FROZEN_N4_N5_BASELINE" if n < 7 else "NOT_APPLICABLE_ONLY_PAIRED79_N7_BASELINE"),
    })


def main() -> int:
    if OUT.exists():
        raise SystemExit(f"refusing to overwrite immutable output: {OUT}")
    expected_payloads = {
        P89 / "deployed_policy_rows.csv": P89_ROWS_SHA,
        P90 / "oos_prediction_vectors.csv.gz": P90_VECTORS_SHA,
        P79 / "frozen_group_legs.csv": P79_LEGS_SHA,
        P79 / "frozen_prefix_sequences.jsonl.gz": P79_SEQUENCES_SHA,
    }
    if any(sha256(path) != expected for path, expected in expected_payloads.items()):
        raise SystemExit("upstream required payload hash mismatch")
    stage = Path(tempfile.mkdtemp(prefix="bj91-gate-a-", dir=OUT.parent))
    try:
        input_manifests = {"bj89": manifest_sha(P89), "bj90": manifest_sha(P90), "bj79": manifest_sha(P79)}
        probabilities = safe_probability_rows(P89 / "deployed_policy_rows.csv")
        prices = safe_price_rows(P90 / "oos_prediction_vectors.csv.gz")
        common = common_rows(probabilities, prices)
        primary_by_n = {}
        census_rows = []
        all_groups = []
        for n in N_VALUES:
            groups, census = make_primary_groups(common, n)
            primary_by_n[n] = groups
            all_groups.extend(groups)
            census_rows.extend(census)
        complete79, overlap_census, cross_fold_full_overlap = inherited79_groups(common)
        frozen79 = inherited79_sequences(set(complete79))
        paired_groups = []
        for ordinal, source_group_id in enumerate(sorted(complete79), start=1):
            legs = complete79[source_group_id]
            paired_groups.append({
                "cohort": "PAIRED79", "n": 7, "group_id": f"PAIRED79-{source_group_id}",
                "source_group_id": source_group_id, "issue": str(legs[0]["issue"]),
                "fold": str(legs[0]["fold"]), "year": str(legs[0]["year"]), "group_ordinal": ordinal, "legs": legs,
            })
        all_groups.extend(paired_groups)
        write_csv(stage / "primary_partition_census.csv", ["cohort", "n", "issue", "fold", "input_rows", "complete_groups", "dropped_remainder_rows", "drop_rule"], census_rows)
        write_csv(stage / "inherited79_overlap_census.csv", ["category", "group_count"], [{"category": key, "group_count": overlap_census[key]} for key in ("complete_common", "partial_overlap", "zero_overlap")])
        write_csv(stage / "group_definitions.csv", ["cohort", "n", "group_id", "source_group_id", "issue", "fold", "year", "group_ordinal", "n_legs"], [{**{key: group[key] for key in ("cohort", "n", "group_id", "source_group_id", "issue", "fold", "year", "group_ordinal")}, "n_legs": len(group["legs"])} for group in all_groups])
        leg_count = write_legs(stage / "outcome_safe_legs.csv.gz", all_groups)
        group_summaries = []
        selection_path = stage / "selected_sequences.jsonl.gz"
        with selection_path.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="\n") as selections:
                for n in N_VALUES:
                    for group in primary_by_n[n]:
                        emit_group(group, selections, group_summaries)
                for group in paired_groups:
                    emit_group(group, selections, group_summaries, frozen79[str(group["source_group_id"])])
        write_csv(stage / "group_arm_summaries.csv", GROUP_FIELDS, group_summaries)
        card = {
            "issue": 91,
            "stage": "GATE_A_CORRECTED_PREOUTCOME_FREEZE",
            "outcome_boundary": "No result, score, winning-SP, ROI, or settlement input is read or emitted.",
            "input_manifests_sha256": input_manifests,
            "required_payload_sha256": {path.name: digest for path, digest in expected_payloads.items()},
            "common_identity_key": ["match_id", "issue", "match_idx", "fold"],
            "common_row_count": len(common),
            "primary_grouping": "For every N partition by issue/fold, sort numeric match_idx then match_id, take non-overlapping N-row chunks, drop only final remainder <N.",
            "paired79_grouping": "The #79 60% SP5 prefix is evaluated only on byte-frozen complete seven-leg groups; #91 N7 arms are re-evaluated on identical leg identities.",
            "inherited79_overlap_census": {**overlap_census, "cross_fold_full_overlap_in_partial": cross_fold_full_overlap},
            "effective_sp_rule": "codewise min(predicted_sp, 5.0) before EV ranking for both point and M2 price arms",
            "ev_per_2_rule": "2*(0.65*joint_calibrated_probability*product(effective_sp)-1), strict > 0",
            "comparators": ["POINT_SP5_POSITIVE_EV", "CONSERVATIVE_M2_SP5_POSITIVE_EV", "PROBABILITY_ONLY_MATCHED_TO_POINT", "PROBABILITY_ONLY_MATCHED_TO_CONSERVATIVE", "FULL_3_TO_N_ANALYTIC", "INHERITED79_SP5_CAPPED_60PCT_PREFIX_N7_PAIRED_ONLY"],
            "probability_tie_order": ["3", "1", "0"],
            "stake_rule": "cost_yuan=2*K; no multiplier; K is output not an eligibility gate",
            "gate_b_settlement_binding": {"commit": SHARED_SETTLEMENT_COMMIT, "runner_path": SHARED_SETTLEMENT_RUNNER_PATH, "runner_sha256": SHARED_SETTLEMENT_RUNNER_SHA, "test_path": SHARED_SETTLEMENT_TEST_PATH, "test_sha256": SHARED_SETTLEMENT_TEST_SHA, "factor": "0.65", "rounding": "pre_round_decimal_value_serialized_to_6_decimal_places; no_paid_cent_rounding_applied"},
            "files": ["outcome_safe_legs.csv.gz", "group_definitions.csv", "primary_partition_census.csv", "inherited79_overlap_census.csv", "selected_sequences.jsonl.gz", "group_arm_summaries.csv", "preoutcome_card.json", "freeze_runner.py"],
            "counts": {"groups": len(all_groups), "outcome_safe_leg_rows": leg_count, "primary_groups": {str(n): len(primary_by_n[n]) for n in N_VALUES}, "paired79_groups": len(paired_groups)},
        }
        (stage / "preoutcome_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n")
        shutil.copyfile(__file__, stage / "freeze_runner.py")
        manifest = {path.name: sha256(path) for path in sorted(stage.iterdir()) if path.is_file()}
        (stage / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        os.replace(stage, OUT)
        print(json.dumps({"output": str(OUT), "manifest_sha256": sha256(OUT / "SHA256SUMS.json"), **card["counts"]}, sort_keys=True))
        return 0
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
