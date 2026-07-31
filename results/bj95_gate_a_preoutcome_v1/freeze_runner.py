#!/usr/bin/env python3
"""Freeze #95 N7 structured full-cover pruning portfolios without outcomes.

The program consumes only #91's accepted primary N7 legs plus a narrowly
projected (outcome-free) EURO 10h vector from its accepted #89 source.  Each
portfolio is represented analytically by its seven allowed-code sets: this is
an exact, compact representation of all K physical sequences, rather than an
unnecessary materialisation of hundreds of millions of rows.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import shutil
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


CODES = ("3", "1", "0")
DEPTHS = tuple(range(8))
PRUNING_ARMS = (
    "CAL_MIN_P",
    "EURO_MIN_P",
    "MIN_PXSP5",
    "MODEL_MARKET_AGREE",
    "RANDOM_HASH_BASELINE",
)
CONTROL_ARM = "FULL_COVERAGE_CONTROL"
STAKE_PER_SEQUENCE = 2
CONTRACT_ID = "BJ-HIST-N7-PRUNING-001"
GENERATOR_VERSION = "bj95-analytic-cartesian-v1"
P91_LEGS_SHA = "cd0fdfd42002bbeddc6a1676323ead65c4cb85915f2c1a83b916d6c2004526fc"
P89_ROWS_SHA = "ef02fccffdbe1d4f3cb70a4c8f7d24037bf2b9a40bea71e6fe0fbf465d679e7e"

LEG_FIELDS = (
    "group_id", "position", "match_id", "issue", "match_idx", "year", "fold",
    "handicap_line_norm", "p3", "p1", "p0", "euro_p3", "euro_p1", "euro_p0",
    "predicted_sp_3", "predicted_sp_1", "predicted_sp_0",
    "sp5_3", "sp5_1", "sp5_0",
)
FRONTIER_FIELDS = (
    "cohort", "group_id", "issue", "fold", "year", "arm", "depth", "disposition",
    "eligible_removals", "actual_removals", "removed_positions", "removed_codes",
    "formula_k", "selected_sequence_count", "stake_yuan", "calibrated_mass",
    "euro_novig_mass", "portfolio_descriptor_sha256", "generator_version",
)
DELETION_FIELDS = (
    "group_id", "arm", "removal_rank", "position", "removed_code",
    "handicap_line_norm", "calibrated_probability", "euro_novig_probability",
    "predicted_sp", "sp5", "p_times_sp5", "selection_score", "score_semantics",
)


def repository_root(anchor: Path) -> Path:
    """Find checkout root from either scripts/ or a copied result runner."""
    resolved = anchor.resolve()
    for candidate in (resolved.parent, *resolved.parents):
        if (candidate / ".git").exists():
            return candidate
    raise RuntimeError("could not locate repository root")


ROOT = repository_root(Path(__file__))
DEFAULT_OUT = ROOT / "results" / "bj95_gate_a_preoutcome_v1"
P91 = ROOT / "results" / "bj91_gate_a_preoutcome_v1r6"
P89 = ROOT / "results" / "bj89_gate_b_selector_v1_1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest_sha(bundle: Path) -> str:
    manifest = bundle / "SHA256SUMS.json"
    declared = json.loads(manifest.read_text(encoding="utf-8"))
    actual = {
        path.name: sha256(path)
        for path in bundle.iterdir()
        if path.is_file() and path.name != manifest.name
    }
    if actual != declared:
        raise RuntimeError(f"input manifest mismatch: {bundle}")
    return sha256(manifest)


def fmt(value: float) -> str:
    # 17 significant digits round-trip an IEEE-754 input exactly.  This keeps
    # the safe projection independently replayable without rounding a ranking
    # boundary before it is written to the immutable package.
    return format(value, ".17g")


def canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def no_vig_probabilities(row: dict[str, str]) -> dict[str, float]:
    odds = {code: float(row[f"euro_{code}_10h"]) for code in CODES}
    if any(value <= 1.0 for value in odds.values()):
        raise RuntimeError(f"invalid EURO odds for {row['match_id']}")
    inverse = {code: 1.0 / value for code, value in odds.items()}
    total = sum(inverse.values())
    return {code: inverse[code] / total for code in CODES}


def identity(row: dict[str, str]) -> tuple[str, str, str, str]:
    return (row["match_id"], row["issue"], row["match_idx"], row["fold"])


def euro_rows() -> dict[tuple[str, str, str, str], dict[str, object]]:
    path = P89 / "deployed_policy_rows.csv"
    if sha256(path) != P89_ROWS_SHA:
        raise RuntimeError("#89 deployed_policy_rows.csv hash mismatch")
    required = {
        "match_id", "issue", "match_idx", "fold", "handicap_line_norm",
        "euro_3_10h", "euro_1_10h", "euro_0_10h",
    }
    rows: dict[tuple[str, str, str, str], dict[str, object]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise RuntimeError("#89 source lacks safe EURO fields")
        for raw in reader:
            # Never project `outcome` or any result-derived field from #89.
            safe = {field: raw[field] for field in required}
            key = identity(safe)
            if key in rows:
                raise RuntimeError(f"duplicate #89 identity: {key}")
            rows[key] = {
                "euro_probability": no_vig_probabilities(safe),
                "handicap_line_norm": safe["handicap_line_norm"],
            }
    return rows


def primary_n7_legs(euros: dict[tuple[str, str, str, str], dict[str, object]]) -> list[dict[str, object]]:
    path = P91 / "outcome_safe_legs.csv.gz"
    if sha256(path) != P91_LEGS_SHA:
        raise RuntimeError("#91 outcome_safe_legs.csv.gz hash mismatch")
    required = {
        "cohort", "n", "group_id", "position", "match_id", "issue", "match_idx",
        "year", "fold", "p3", "p1", "p0", "point_sp_3", "point_sp_1", "point_sp_0",
        "point_sp5_3", "point_sp5_1", "point_sp5_0",
    }
    rows: list[dict[str, object]] = []
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise RuntimeError("#91 safe-leg schema drift")
        for raw in reader:
            if raw["cohort"] != "PRIMARY" or raw["n"] != "7":
                continue
            key = identity(raw)
            euro = euros.get(key)
            if euro is None:
                raise RuntimeError(f"missing #89 EURO identity for #91 N7 leg: {key}")
            probability = {code: float(raw[f"p{code}"]) for code in CODES}
            if abs(sum(probability.values()) - 1.0) > 1e-9 or min(probability.values()) <= 0:
                raise RuntimeError(f"invalid calibrated probabilities: {key}")
            rows.append({
                "group_id": raw["group_id"], "position": int(raw["position"]),
                "match_id": raw["match_id"], "issue": raw["issue"], "match_idx": raw["match_idx"],
                "year": raw["year"], "fold": raw["fold"],
                "handicap_line_norm": euro["handicap_line_norm"],
                "calibrated_probability": probability,
                "euro_probability": euro["euro_probability"],
                "predicted_sp": {code: float(raw[f"point_sp_{code}"]) for code in CODES},
                "sp5": {code: float(raw[f"point_sp5_{code}"]) for code in CODES},
            })
    groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        groups[str(row["group_id"])].append(row)
    if len(groups) != 6_686 or len(rows) != 46_802:
        raise RuntimeError(f"unexpected #91 primary N7 count: groups={len(groups)} legs={len(rows)}")
    for group_id, legs in groups.items():
        positions = sorted(int(leg["position"]) for leg in legs)
        if positions != list(range(1, 8)):
            raise RuntimeError(f"invalid N7 positions: {group_id}")
    return rows


def bottom_code(probability: dict[str, float]) -> str:
    return min(CODES, key=lambda code: (probability[code], CODES.index(code)))


def hashed_rank(*parts: object) -> int:
    encoded = "|".join(str(item) for item in parts).encode("utf-8")
    return int.from_bytes(hashlib.sha256(encoded).digest(), "big")


def deletion_order(legs: list[dict[str, object]], arm: str) -> tuple[list[dict[str, object]], str | None]:
    """Return seven ordered removals, or a rule-unavailable reason."""
    candidates: list[dict[str, object]] = []
    for leg in legs:
        cal = leg["calibrated_probability"]
        euro = leg["euro_probability"]
        assert isinstance(cal, dict) and isinstance(euro, dict)
        if arm == "CAL_MIN_P":
            code, score, semantics = bottom_code(cal), None, "ascending_calibrated_probability"
            score = cal[code]
        elif arm == "EURO_MIN_P":
            code, score, semantics = bottom_code(euro), None, "ascending_euro_novig_probability"
            score = euro[code]
        elif arm == "MIN_PXSP5":
            code = min(CODES, key=lambda value: (cal[value] * float(leg["sp5"][value]), CODES.index(value)))
            score, semantics = cal[code] * float(leg["sp5"][code]), "ascending_calibrated_probability_times_sp5"
        elif arm == "MODEL_MARKET_AGREE":
            cal_bottom, euro_bottom = bottom_code(cal), bottom_code(euro)
            if cal_bottom != euro_bottom:
                continue
            code, score, semantics = cal_bottom, max(cal[cal_bottom], euro[euro_bottom]), "ascending_max_calibrated_euro_bottom_probability"
        elif arm == "RANDOM_HASH_BASELINE":
            code = CODES[hashed_rank(CONTRACT_ID, leg["group_id"], leg["position"], "code") % len(CODES)]
            score, semantics = float(hashed_rank(CONTRACT_ID, leg["group_id"], leg["position"], "order")), "ascending_contract_hash"
        else:
            raise RuntimeError(f"unknown arm: {arm}")
        candidates.append({"leg": leg, "code": code, "score": float(score), "semantics": semantics})
    candidates.sort(key=lambda item: (item["score"], int(item["leg"]["position"]), CODES.index(str(item["code"]))))
    if arm == "MODEL_MARKET_AGREE" and len(candidates) < 7:
        return candidates, "UNAVAILABLE_BY_RULE"
    if len(candidates) != 7:
        raise RuntimeError(f"expected seven removals for {arm}")
    return candidates, None


def descriptor(group_id: str, arm: str, depth: int, allowed: list[tuple[str, ...]]) -> str:
    return canonical_hash({
        "contract": CONTRACT_ID, "generator_version": GENERATOR_VERSION,
        "group_id": group_id, "arm": arm, "depth": depth,
        "code_order": CODES, "allowed_codes_by_position": allowed,
    })


def write_csv(path: Path, fields: Iterable[str], rows: Iterable[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_gzip_csv(path: Path, fields: Iterable[str], rows: Iterable[dict[str, object]]) -> None:
    # GzipFile's explicit mtime makes bytes reproducible across reruns.
    with path.open("wb") as binary:
        with gzip.GzipFile(fileobj=binary, mode="wb", mtime=0) as compressed:
            with io.TextIOWrapper(compressed, newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(fields), lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)


def build(out: Path) -> dict[str, object]:
    if out.exists():
        raise RuntimeError(f"refusing to overwrite immutable bundle: {out}")
    p91_manifest = manifest_sha(P91)
    p89_manifest = manifest_sha(P89)
    euros = euro_rows()
    input_legs = primary_n7_legs(euros)
    by_group: dict[str, list[dict[str, object]]] = defaultdict(list)
    for leg in input_legs:
        by_group[str(leg["group_id"])].append(leg)
    for legs in by_group.values():
        legs.sort(key=lambda item: int(item["position"]))

    with tempfile.TemporaryDirectory(prefix="bj95_gate_a_") as temp_name:
        temp = Path(temp_name)
        safe_legs: list[dict[str, object]] = []
        frontier: list[dict[str, object]] = []
        removals: list[dict[str, object]] = []
        availability = Counter()
        for group_id, legs in sorted(by_group.items()):
            first = legs[0]
            for leg in legs:
                cal = leg["calibrated_probability"]
                euro = leg["euro_probability"]
                sp = leg["predicted_sp"]
                sp5 = leg["sp5"]
                assert isinstance(cal, dict) and isinstance(euro, dict) and isinstance(sp, dict) and isinstance(sp5, dict)
                safe_legs.append({
                    "group_id": group_id, "position": leg["position"], "match_id": leg["match_id"],
                    "issue": leg["issue"], "match_idx": leg["match_idx"], "year": leg["year"], "fold": leg["fold"],
                    "handicap_line_norm": leg["handicap_line_norm"],
                    **{f"p{code}": fmt(cal[code]) for code in CODES},
                    **{f"euro_p{code}": fmt(euro[code]) for code in CODES},
                    **{f"predicted_sp_{code}": fmt(sp[code]) for code in CODES},
                    **{f"sp5_{code}": fmt(sp5[code]) for code in CODES},
                })
            full_allowed = [CODES] * 7
            frontier.append({
                "cohort": "PRIMARY_N7", "group_id": group_id, "issue": first["issue"], "fold": first["fold"], "year": first["year"],
                "arm": CONTROL_ARM, "depth": 0, "disposition": "AVAILABLE", "eligible_removals": 7,
                "actual_removals": 0, "removed_positions": "", "removed_codes": "", "formula_k": 2187,
                "selected_sequence_count": 2187, "stake_yuan": 4374, "calibrated_mass": "1", "euro_novig_mass": "1",
                "portfolio_descriptor_sha256": descriptor(group_id, CONTROL_ARM, 0, full_allowed), "generator_version": GENERATOR_VERSION,
            })
            for arm in PRUNING_ARMS:
                ordered, unavailable = deletion_order(legs, arm)
                availability[(arm, unavailable or "AVAILABLE")] += 1
                for rank, selection in enumerate(ordered, start=1):
                    leg = selection["leg"]
                    cal = leg["calibrated_probability"]
                    euro = leg["euro_probability"]
                    sp = leg["predicted_sp"]
                    sp5 = leg["sp5"]
                    code = str(selection["code"])
                    assert isinstance(cal, dict) and isinstance(euro, dict) and isinstance(sp, dict) and isinstance(sp5, dict)
                    removals.append({
                        "group_id": group_id, "arm": arm, "removal_rank": rank, "position": leg["position"], "removed_code": code,
                        "handicap_line_norm": leg["handicap_line_norm"], "calibrated_probability": fmt(cal[code]),
                        "euro_novig_probability": fmt(euro[code]), "predicted_sp": fmt(sp[code]), "sp5": fmt(sp5[code]),
                        "p_times_sp5": fmt(cal[code] * sp5[code]), "selection_score": fmt(selection["score"]),
                        "score_semantics": selection["semantics"],
                    })
                for depth in DEPTHS[1:]:
                    selected = ordered[:depth]
                    if unavailable is not None and len(ordered) < depth:
                        frontier.append({
                            "cohort": "PRIMARY_N7", "group_id": group_id, "issue": first["issue"], "fold": first["fold"], "year": first["year"],
                            "arm": arm, "depth": depth, "disposition": unavailable, "eligible_removals": len(ordered),
                            "actual_removals": 0, "removed_positions": "", "removed_codes": "", "formula_k": 2**depth * 3**(7-depth),
                            "selected_sequence_count": 0, "stake_yuan": 0, "calibrated_mass": "", "euro_novig_mass": "",
                            "portfolio_descriptor_sha256": "", "generator_version": GENERATOR_VERSION,
                        })
                        continue
                    deleted = {int(item["leg"]["position"]): str(item["code"]) for item in selected}
                    allowed = [tuple(code for code in CODES if code != deleted.get(position)) for position in range(1, 8)]
                    k = 1
                    cal_mass = 1.0
                    euro_mass = 1.0
                    for leg, choices in zip(legs, allowed):
                        cal = leg["calibrated_probability"]
                        euro = leg["euro_probability"]
                        assert isinstance(cal, dict) and isinstance(euro, dict)
                        k *= len(choices)
                        cal_mass *= sum(cal[code] for code in choices)
                        euro_mass *= sum(euro[code] for code in choices)
                    expected_k = 2**depth * 3**(7-depth)
                    if k != expected_k:
                        raise RuntimeError(f"analytic K mismatch: {group_id} {arm} d={depth}")
                    frontier.append({
                        "cohort": "PRIMARY_N7", "group_id": group_id, "issue": first["issue"], "fold": first["fold"], "year": first["year"],
                        "arm": arm, "depth": depth, "disposition": "AVAILABLE", "eligible_removals": len(ordered),
                        "actual_removals": depth, "removed_positions": "|".join(str(item["leg"]["position"]) for item in selected),
                        "removed_codes": "|".join(str(item["code"]) for item in selected), "formula_k": expected_k,
                        "selected_sequence_count": k, "stake_yuan": k * STAKE_PER_SEQUENCE, "calibrated_mass": fmt(cal_mass),
                        "euro_novig_mass": fmt(euro_mass), "portfolio_descriptor_sha256": descriptor(group_id, arm, depth, allowed),
                        "generator_version": GENERATOR_VERSION,
                    })
        write_gzip_csv(temp / "outcome_safe_n7_legs.csv.gz", LEG_FIELDS, safe_legs)
        write_gzip_csv(temp / "pruning_frontier.csv.gz", FRONTIER_FIELDS, frontier)
        write_gzip_csv(temp / "pruning_deletions.csv.gz", DELETION_FIELDS, removals)
        write_csv(temp / "availability_census.csv", ("arm", "disposition", "group_count"), (
            {"arm": arm, "disposition": disposition, "group_count": count}
            for (arm, disposition), count in sorted(availability.items())
        ))
        card = {
            "issue": 95, "stage": "GATE_A_PREOUTCOME_STRUCTURED_PRUNING_FREEZE", "contract": CONTRACT_ID,
            "outcome_boundary": "No result, score, winning/final SP, payout, ROI, or settlement field is projected, emitted, or used.",
            "source_boundary": {
                "bj91_bundle": "results/bj91_gate_a_preoutcome_v1r6", "bj91_manifest_sha256": p91_manifest,
                "bj91_n7_legs_sha256": P91_LEGS_SHA, "bj89_bundle": "results/bj89_gate_b_selector_v1_1",
                "bj89_manifest_sha256": p89_manifest, "bj89_rows_sha256": P89_ROWS_SHA,
                "bj89_projection": ["match_id", "issue", "match_idx", "fold", "handicap_line_norm", "euro_3_10h", "euro_1_10h", "euro_0_10h"],
            },
            "grouping": "exactly the 6,686 PRIMARY N=7 chronological groups frozen by #91; no group regenerated or filtered",
            "code_order": list(CODES), "depths": list(DEPTHS), "arms": [CONTROL_ARM, *PRUNING_ARMS],
            "sequence_definition": "At depth d, forbid exactly one frozen code in each of d distinct legs; selected set is the ordered Cartesian product of allowed code sets.",
            "k_formula": "K=2^d*3^(7-d); stake_yuan=2*K; factor 0.65 is reserved for Gate B settlement only.",
            "hash_definition": "portfolio_descriptor_sha256 is SHA-256 canonical JSON of contract, generator, group, arm, depth, code order and allowed codes by all seven positions; it uniquely defines every physical sequence.",
            "model_market_agree_rule": "only legs whose calibrated and EURO no-vig bottom code agree are eligible; depth beyond eligible count is UNAVAILABLE_BY_RULE.",
            "random_rule": "removed code and removal order are independently derived from SHA-256 of contract ID, group ID, position and purpose; it is a baseline only.",
            "counts": {"groups": len(by_group), "legs": len(safe_legs), "frontier_rows": len(frontier), "deletion_rows": len(removals)},
        }
        (temp / "preoutcome_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        shutil.copy2(Path(__file__), temp / "freeze_runner.py")
        payload = {path.name: sha256(path) for path in sorted(temp.iterdir()) if path.is_file()}
        (temp / "SHA256SUMS.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        shutil.copytree(temp, out)
    return {"out": str(out), "groups": len(by_group), "frontier_rows": len(frontier), "deletion_rows": len(removals)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    print(json.dumps(build(args.output), sort_keys=True))


if __name__ == "__main__":
    main()
