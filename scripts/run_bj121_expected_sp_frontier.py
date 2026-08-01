#!/usr/bin/env python3
"""Freeze and settle #121 expected-SP / probability-role frontier.

Gate A intentionally reads only #106's outcome-unexposed q/expected-SP atlas
and #101's pool membership.  Gate B is the sole place canonical outcomes are
opened, after the Gate-A manifest has been fixed.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import os
import shutil
import tempfile
from collections import Counter, defaultdict
from decimal import Decimal, getcontext
from pathlib import Path

getcontext().prec = 80


def repository_root(path: Path) -> Path:
    for ancestor in (path.resolve().parent, *path.resolve().parents):
        if (ancestor / ".git").exists():
            return ancestor
    raise RuntimeError("repository root not found")


ROOT = repository_root(Path(__file__))
ATLAS = ROOT / "results/bj106_gate_a_preoutcome_v2r1"
POOLS = ROOT / "results/bj101_gate_a_preoutcome_v1r1"
OUTCOMES = ROOT / "results/bj95_gate_b_outcome_settlement_v2r8"
GATE_A = ROOT / "results/bj121_gate_a_preoutcome_v2"
GATE_B = ROOT / "results/bj121_gate_b_outcome_settlement_v1"
EXPECTED = {
    "atlas": "fb45cacccb4c9ab2b52c8a538f489fb3e3197fa138245f0d83cf98a3cbb0db5d",
    "pools": "86e37682a95fad2a2a67187f1ee528f665d371583c621dc9d14af58f74302447",
    "outcomes": "fbbd3b53bd86f4bb0caff8f2587933cd6b0e4e7d04fb0f709bac934ec2a705cc",
}
EXPECTED_GATE_A_MANIFEST = ""
FACTOR = Decimal(".65")
TAX_RATE = Decimal(".20")
TAX_CLIFF = Decimal("10000")
MONEY = Decimal(".000001")

# The complete finite pre-outcome grid: expected SP is a role-level geometric
# mean; GM-SP is the selected N-leg geometric mean.  Low P controls a 2-code
# exclusion cover; DAN requires a max calibrated probability of at least .50.
VARIANTS = {
    f"ESP{esp.replace('.', '')}_LOWP{low.replace('.', '')}": {
        "expected_sp_min": Decimal(esp),
        "gm_sp_min": Decimal(gm),
        "low_probability_max": Decimal(low),
        "dan_probability_min": Decimal(dan),
    }
    # Values span the observed pre-outcome expected-SP range for DAN rather
    # than making its entire arm mechanically empty.  Each triple has the
    # same three low-P thresholds, so low-P sensitivity remains identifiable.
    for esp, gm, dan in (("1.5", "1.8", ".50"), ("2.0", "2.2", ".45"), ("2.5", "2.7", ".45"))
    for low in (".20", ".25", ".30")
}
ARMS = (
    "NO_BET_CONTROL",
    "DAN_N4", "DOUBLE_N4", "FULL_N4",
    "DAN_N7", "DOUBLE_N7", "FULL_N7",
    "DAN_DYNAMIC_4_7", "DOUBLE_DYNAMIC_4_7", "FULL_DYNAMIC_4_7",
)
POOL_FIELDS = (
    "issue", "fold", "year", "pool_id", "segment_index", "pool_disposition",
    "eligible_match_count", "pool_match_count", "first_kickoff_ts", "last_kickoff_ts",
    "window_hours", "terminal_remainder",
)
FRONTIER_FIELDS = POOL_FIELDS + (
    "variant_id", "arm", "role", "candidate_match_count", "selected_n",
    "selected_match_ids", "selected_code_sets", "selected_role_expected_sps",
    "gm_expected_sp", "formula_k", "stake_yuan", "disposition", "reason",
)
ASSIGNMENT_FIELDS = (
    "variant_id", "role", "issue", "fold", "year", "pool_id", "match_id", "match_idx",
    "code_set", "role_expected_sp", "min_probability", "max_probability", "rank",
)
SETTLEMENT_FIELDS = FRONTIER_FIELDS + (
    "settlement_status", "coverage_hit", "final_sp_product", "gross_yuan", "tax_yuan",
    "after_tax_gross_yuan", "net_yuan",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def decimal(value: object) -> Decimal:
    return Decimal(str(value))


def money(value: Decimal) -> str:
    return format(value.quantize(MONEY), "f")


def verify_manifest(directory: Path, expected: str, required: tuple[str, ...]) -> dict[str, str]:
    manifest_path = directory / "SHA256SUMS.json"
    if sha256(manifest_path) != expected:
        raise RuntimeError(f"manifest identity mismatch: {directory}")
    manifest = json.loads(manifest_path.read_text())
    for name in required:
        if name not in manifest or sha256(directory / name) != manifest[name]:
            raise RuntimeError(f"payload mismatch: {directory / name}")
    return manifest


def read_exact_csv(path: Path, fields: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != fields:
            raise RuntimeError(f"schema mismatch: {path}")
        return list(reader)


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def gate_a_provenance() -> dict[str, object]:
    atlas = verify_manifest(ATLAS, EXPECTED["atlas"], ("gate_a_card.json", "q_atlas.csv.gz"))
    pools = verify_manifest(POOLS, EXPECTED["pools"], ("issue_pool_census.csv", "issue_pool_membership.csv"))
    card = json.loads((ATLAS / "gate_a_card.json").read_text())
    if card["outcome_boundary"].startswith("candidate_code") is False:
        raise RuntimeError("#106 outcome-safe boundary drift")
    return {"atlas_manifest": EXPECTED["atlas"], "pool_manifest": EXPECTED["pools"],
            "atlas_payload": atlas["q_atlas.csv.gz"], "pool_payload": pools["issue_pool_census.csv"],
            "membership_payload": pools["issue_pool_membership.csv"]}


def geometric_mean(values: list[Decimal]) -> Decimal:
    if not values:
        return Decimal(0)
    return decimal(math.exp(sum(math.log(float(value)) for value in values) / len(values)))


def role_vectors() -> tuple[dict[str, dict[str, str]], dict[str, list[dict[str, object]]]]:
    membership = {row["match_id"]: row for row in csv.DictReader((POOLS / "issue_pool_membership.csv").open())}
    by_match: dict[str, list[dict[str, str]]] = defaultdict(list)
    with gzip.open(ATLAS / "q_atlas.csv.gz", "rt", newline="") as handle:
        for row in csv.DictReader(handle):
            if row["match_id"] in membership:
                by_match[row["match_id"]].append(row)
    vectors: dict[str, list[dict[str, object]]] = defaultdict(list)
    for match_id, outcomes in by_match.items():
        if len(outcomes) != 3:
            continue
        outcomes.sort(key=lambda row: "310".index(row["candidate_code"]))
        min_row = min(outcomes, key=lambda row: decimal(row["p_cal"]))
        dan = max(outcomes, key=lambda row: (decimal(row["p_cal"]), -"310".index(row["candidate_code"])))
        double = [row for row in outcomes if row is not min_row]
        for role, code_rows in (("DAN", [dan]), ("DOUBLE", double), ("FULL", outcomes)):
            vectors[role].append({
                **membership[match_id], "match_id": match_id, "role": role,
                "code_set": "/".join(row["candidate_code"] for row in code_rows),
                "role_expected_sp": geometric_mean([decimal(row["predicted_sp"]) for row in code_rows]),
                "min_probability": decimal(min_row["p_cal"]),
                "max_probability": decimal(dan["p_cal"]),
            })
    for rows in vectors.values():
        rows.sort(key=lambda row: (int(str(row["match_idx"])), int(str(row["match_id"]))))
    return membership, vectors


def arm_role_n(arm: str, candidate_count: int) -> tuple[str, int]:
    if arm == "NO_BET_CONTROL":
        return "NO_BET", 0
    if arm.endswith("_DYNAMIC_4_7"):
        role = arm.removesuffix("_DYNAMIC_4_7")
        n = 7 if candidate_count >= 7 else 4 if candidate_count >= 4 else 0
        return role, n
    role, size = arm.rsplit("_", 1)
    n = 4 if size == "N4" else 7
    return role, n


def build_frontier() -> tuple[dict[str, object], list[dict[str, str]], list[dict[str, object]], list[dict[str, object]]]:
    provenance = gate_a_provenance()
    pools = read_exact_csv(POOLS / "issue_pool_census.csv", POOL_FIELDS)
    if len(pools) != 2659 or len({row["issue"] for row in pools}) != 344:
        raise RuntimeError("pool denominator drift")
    _, vectors = role_vectors()
    pool_role: dict[str, dict[str, list[dict[str, object]]]] = defaultdict(lambda: defaultdict(list))
    for role, rows in vectors.items():
        for row in rows:
            pool_role[str(row["pool_id"])][role].append(row)
    frontiers: list[dict[str, object]] = []
    assignments: list[dict[str, object]] = []
    for variant_id, rule in VARIANTS.items():
        for pool in pools:
            for arm in ARMS:
                role, requested_n = arm_role_n(arm, 0)
                candidates = []
                if role != "NO_BET":
                    candidates = [row for row in pool_role[pool["pool_id"]][role]
                                  if decimal(row["role_expected_sp"]) >= rule["expected_sp_min"]
                                  and (role != "DOUBLE" or decimal(row["min_probability"]) <= rule["low_probability_max"])
                                  and (role != "DAN" or decimal(row["max_probability"]) >= rule["dan_probability_min"])]
                    candidates.sort(key=lambda row: (-decimal(row["role_expected_sp"]), int(str(row["match_idx"])), int(str(row["match_id"]))))
                role, requested_n = arm_role_n(arm, len(candidates))
                selected = candidates[:requested_n] if requested_n and len(candidates) >= requested_n else []
                gm = geometric_mean([decimal(row["role_expected_sp"]) for row in selected])
                if selected and gm < rule["gm_sp_min"]:
                    selected = []
                if selected:
                    for rank, row in enumerate(selected, 1):
                        assignments.append({"variant_id": variant_id, "role": role, "issue": row["issue"], "fold": row["fold"], "year": row["year"], "pool_id": row["pool_id"], "match_id": row["match_id"], "match_idx": row["match_idx"], "code_set": row["code_set"], "role_expected_sp": format(decimal(row["role_expected_sp"]), ".12f"), "min_probability": format(decimal(row["min_probability"]), ".12f"), "max_probability": format(decimal(row["max_probability"]), ".12f"), "rank": rank})
                formula_k = math.prod(len(row["code_set"].split("/")) for row in selected) if selected else 0
                reason = "NO_BET_CONTROL" if arm == "NO_BET_CONTROL" else "AVAILABLE_FROZEN" if selected else "INSUFFICIENT_MATCHES_FOR_N" if len(candidates) < requested_n else "GM_SP_BELOW_THRESHOLD"
                frontiers.append({**pool, "variant_id": variant_id, "arm": arm, "role": role,
                                  "candidate_match_count": len(candidates), "selected_n": len(selected),
                                  "selected_match_ids": ";".join(str(row["match_id"]) for row in selected),
                                  "selected_code_sets": ";".join(str(row["code_set"]) for row in selected),
                                  "selected_role_expected_sps": ";".join(format(decimal(row["role_expected_sp"]), ".12f") for row in selected),
                                  "gm_expected_sp": format(gm, ".12f") if selected else "",
                                  "formula_k": formula_k, "stake_yuan": money(Decimal(2 * formula_k)) if selected else money(Decimal(0)),
                                  "disposition": "AVAILABLE" if selected else "NO_BET", "reason": reason})
    return provenance, pools, frontiers, assignments


def freeze_gate_a(output: Path) -> None:
    if output.exists():
        raise SystemExit("immutable output exists")
    stage = Path(tempfile.mkdtemp(prefix="bj121_gate_a_", dir=output.parent))
    try:
        provenance, pools, frontiers, assignments = build_frontier()
        write_csv(stage / "portfolio_frontier.csv", FRONTIER_FIELDS, frontiers)
        write_csv(stage / "candidate_assignments.csv", ASSIGNMENT_FIELDS, assignments)
        summary = []
        for variant_id in VARIANTS:
            for arm in ARMS:
                rows = [row for row in frontiers if row["variant_id"] == variant_id and row["arm"] == arm]
                available = [row for row in rows if row["disposition"] == "AVAILABLE"]
                summary.append({"variant_id": variant_id, "arm": arm, "pools": len(rows), "available": len(available), "no_bet": len(rows) - len(available), "candidate_matches": sum(int(row["candidate_match_count"]) for row in rows), "tickets": sum(int(row["formula_k"]) for row in available), "stake_yuan": money(sum((decimal(row["stake_yuan"]) for row in available), Decimal(0)))})
        write_csv(stage / "frontier_density_summary.csv", ("variant_id", "arm", "pools", "available", "no_bet", "candidate_matches", "tickets", "stake_yuan"), summary)
        card = {"issue": 121, "stage": "GATE_A_OUTCOME_UNEXPOSED_EXPECTED_SP_FRONTIER", "provenance": provenance, "variants": {key: {name: str(value) for name, value in value.items()} for key, value in VARIANTS.items()}, "arms": ARMS, "candidate_definition": "DAN=max p_cal code when max p_cal>=.50; DOUBLE=all but min p_cal code when min p_cal<=low threshold; FULL=all three codes. Role expected SP is geometric mean of the allowed codes' predicted SP. Selected N legs must meet both role expected-SP and portfolio GM-SP thresholds.", "outcome_boundary": "No result, final SP, payout, tax, ROI or settlement source is opened in Gate A.", "gate_b": "Only exact immutable frontier may be settled; no threshold, role, arm, or pool may be added after outcome access.", "scope": "historical paper-only research; no purchase, production or promotion."}
        (stage / "gate_a_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n")
        shutil.copyfile(__file__, stage / "runner.py")
        (stage / "README.md").write_text("# #121 Gate A\n\nOutcome-unexposed expected-SP/probability-role frontier. Run `python runner.py gate-a --output <empty-dir>` from a compatible checkout.\n")
        manifest = {item.name: sha256(item) for item in sorted(stage.iterdir()) if item.is_file()}
        (stage / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        os.replace(stage, output)
        print(json.dumps({"manifest": sha256(output / "SHA256SUMS.json"), "frontiers": len(frontiers), "assignments": len(assignments)}))
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("gate-a",))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    freeze_gate_a((args.output or GATE_A).resolve())


if __name__ == "__main__":
    main()
