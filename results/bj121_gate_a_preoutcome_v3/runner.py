#!/usr/bin/env python3
"""Freeze #121's outcome-unexposed E_SP x lowest-probability frontier.

Gate A consumes only the authenticated #106 probability/SP projection and
#101 native issue/pool membership.  It never opens an outcome or final-SP
settlement source.  Exact payout, tax and ROI remain Gate-B-only work.
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
from pathlib import Path

CODES = ("3", "1", "0")
CONTRACT = "BJ-HIST-EXPECTED-SP-LOWP-001"
GENERATOR_VERSION = "bj121-gatea-v3"
CONTENT_IDENTITY_VERSION = "bj121-portable-content-v1"
BJ106_MANIFEST = "fb45cacccb4c9ab2b52c8a538f489fb3e3197fa138245f0d83cf98a3cbb0db5d"
BJ101_MANIFEST = "86e37682a95fad2a2a67187f1ee528f665d371583c621dc9d14af58f74302447"
STAKE_PER_TICKET = 2
PAYOUT_FACTOR_DIAGNOSTIC = 0.65
BANKER_P_MAX_MIN = 0.50

# Paired match-floor / portfolio-GM regimes keep the freeze bounded.  The
# three lowest-probability thresholds are crossed with every regime.
E_SP_REGIMES = (
    (2.80, 2.90),
    (2.90, 3.00),
    (3.00, 3.05),
)
LOW_P_THRESHOLDS = (0.20, 0.25, 0.30)
VARIANTS = {
    f"ESP{int(e_sp * 100):03d}_GM{int(gm * 100):03d}_LOWP{int(low_p * 100):02d}": {
        "e_sp_min": e_sp,
        "gm_e_sp_min": gm,
        "low_p_max": low_p,
        "banker_p_max_min": BANKER_P_MAX_MIN,
    }
    for e_sp, gm in E_SP_REGIMES
    for low_p in LOW_P_THRESHOLDS
}

SIZE_SUFFIXES = ("N4", "N7", "DYNAMIC_4_7")
ARMS = (
    "NO_BET_CONTROL",
    *(f"UNFILTERED_FULL_{suffix}" for suffix in SIZE_SUFFIXES),
    *(f"FULL_{suffix}" for suffix in SIZE_SUFFIXES),
    *(f"PRUNE_{suffix}" for suffix in SIZE_SUFFIXES),
    *(f"MIXED_{suffix}" for suffix in SIZE_SUFFIXES),
)
POOL_FIELDS = (
    "issue", "fold", "year", "pool_id", "segment_index", "pool_disposition",
    "eligible_match_count", "pool_match_count", "first_kickoff_ts", "last_kickoff_ts",
    "window_hours", "terminal_remainder",
)
FRONTIER_FIELDS = POOL_FIELDS + (
    "variant_id", "arm", "candidate_match_count", "selected_n", "selected_match_ids",
    "role_codes", "full_legs", "double_legs", "single_legs", "gm_e_sp",
    "expected_portfolio_mass", "formula_k", "stake_yuan", "g_be_pre_tax",
    "disposition", "reason", "descriptor_sha256",
)
ASSIGNMENT_FIELDS = (
    "variant_id", "arm", "issue", "fold", "year", "pool_id", "match_id",
    "match_idx", "selection_rank", "role", "allowed_codes", "omitted_codes",
    "p3", "p1", "p0", "p_min", "p_max", "argmin_code", "argmax_code",
    "e_sp", "q3", "q1", "q0",
)
SUMMARY_FIELDS = (
    "variant_id", "arm", "pools", "available", "no_bet", "candidate_matches",
    "full_legs", "double_legs", "single_legs", "tickets", "stake_yuan",
)


def repository_root(path: Path) -> Path:
    for ancestor in (path.resolve().parent, *path.resolve().parents):
        if (ancestor / ".git").exists():
            return ancestor
    raise RuntimeError("repository root not found")


ROOT = repository_root(Path(__file__))
BJ106 = ROOT / "results/bj106_gate_a_preoutcome_v2r1"
BJ101 = ROOT / "results/bj101_gate_a_preoutcome_v1r1"
OUTPUT = ROOT / "results/bj121_gate_a_preoutcome_v3"


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


def exact_manifest(directory: Path, expected_hash: str) -> dict[str, str]:
    manifest_path = directory / "SHA256SUMS.json"
    if sha256(manifest_path) != expected_hash:
        raise RuntimeError(f"unaccepted source manifest: {directory}")
    declared = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = {
        item.name: sha256(item)
        for item in directory.iterdir()
        if item.is_file() and item.name != manifest_path.name
    }
    if not isinstance(declared, dict) or declared != actual:
        raise RuntimeError(f"source manifest coverage drift: {directory}")
    return declared


def fmt(value: float) -> str:
    if not math.isfinite(value):
        raise RuntimeError("non-finite output")
    return format(value, ".12f")


def geometric(values: list[float]) -> float:
    if not values or any(value <= 0 or not math.isfinite(value) for value in values):
        raise RuntimeError("invalid geometric mean input")
    return math.exp(sum(math.log(value) for value in values) / len(values))


def descriptor(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def outcome_unexposed_feature(outcomes: list[dict[str, str]]) -> dict[str, object]:
    """Compute E_SP=sum(p_cal * predicted_sp) and probability ranks."""
    if len(outcomes) != 3 or {row["candidate_code"] for row in outcomes} != set(CODES):
        raise RuntimeError("expected one row per 3/1/0 code")
    by_code = {row["candidate_code"]: row for row in outcomes}
    p = {code: float(by_code[code]["p_cal"]) for code in CODES}
    sp = {code: float(by_code[code]["predicted_sp"]) for code in CODES}
    if any(value <= 0 or not math.isfinite(value) for value in (*p.values(), *sp.values())):
        raise RuntimeError("invalid probability/SP vector")
    if abs(sum(p.values()) - 1.0) > 1e-6:
        raise RuntimeError("probability mass drift")
    low = min(CODES, key=lambda code: (p[code], CODES.index(code)))
    high = min(CODES, key=lambda code: (-p[code], CODES.index(code)))
    q = {code: p[code] * sp[code] for code in CODES}
    return {
        "p": p,
        "sp": sp,
        "q": q,
        "p_min": p[low],
        "p_max": p[high],
        "argmin_code": low,
        "argmax_code": high,
        "e_sp": sum(q.values()),
    }


def role_for(policy: str, feature: dict[str, object], rule: dict[str, float]) -> tuple[str, str, str]:
    p_min = float(feature["p_min"])
    p_max = float(feature["p_max"])
    low = str(feature["argmin_code"])
    high = str(feature["argmax_code"])
    if policy == "FULL":
        return "FULL", "310", ""
    if policy == "PRUNE":
        if p_min <= rule["low_p_max"]:
            return "DOUBLE", "".join(code for code in CODES if code != low), low
        return "FULL", "310", ""
    if policy == "MIXED":
        if p_min <= rule["low_p_max"] and p_max >= rule["banker_p_max_min"]:
            return "SINGLE", high, "".join(code for code in CODES if code != high)
        if p_min <= rule["low_p_max"]:
            return "DOUBLE", "".join(code for code in CODES if code != low), low
        return "FULL", "310", ""
    raise RuntimeError(f"unsupported role policy: {policy}")


def arm_components(arm: str, candidate_count: int) -> tuple[str, int, bool]:
    if arm == "NO_BET_CONTROL":
        return "NO_BET", 0, False
    unfiltered = arm.startswith("UNFILTERED_")
    remainder = arm.removeprefix("UNFILTERED_") if unfiltered else arm
    if remainder.endswith("_DYNAMIC_4_7"):
        policy = remainder.removesuffix("_DYNAMIC_4_7")
        n = 7 if candidate_count >= 7 else 4 if candidate_count >= 4 else 0
    else:
        policy, suffix = remainder.rsplit("_", 1)
        n = 4 if suffix == "N4" else 7
    return policy, n, unfiltered


def load_sources() -> tuple[dict[str, object], list[dict[str, str]], dict[str, list[dict[str, object]]]]:
    manifest106 = exact_manifest(BJ106, BJ106_MANIFEST)
    manifest101 = exact_manifest(BJ101, BJ101_MANIFEST)
    pools: list[dict[str, str]]
    with (BJ101 / "issue_pool_census.csv").open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != POOL_FIELDS:
            raise RuntimeError("#101 pool schema drift")
        pools = list(reader)
    if len(pools) != 2659 or len({row["issue"] for row in pools}) != 344:
        raise RuntimeError("native issue/pool denominator drift")
    with (BJ101 / "issue_pool_membership.csv").open(newline="", encoding="utf-8") as handle:
        membership = {row["match_id"]: row for row in csv.DictReader(handle)}
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    with gzip.open(BJ106 / "q_atlas.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["match_id"] in membership:
                grouped[row["match_id"]].append(row)
    by_pool: dict[str, list[dict[str, object]]] = defaultdict(list)
    for match_id, outcomes in grouped.items():
        feature = outcome_unexposed_feature(outcomes)
        row = {**membership[match_id], **feature, "match_id": match_id}
        by_pool[str(row["pool_id"])].append(row)
    if sum(len(rows) for rows in by_pool.values()) != len(membership):
        raise RuntimeError("#101/#106 match join drift")
    for rows in by_pool.values():
        rows.sort(key=lambda row: (-float(row["e_sp"]), float(row["p_min"]), int(str(row["match_idx"]))))
    provenance = {
        "bj106_manifest_sha256": BJ106_MANIFEST,
        "bj106_q_atlas_sha256": manifest106["q_atlas.csv.gz"],
        "bj101_manifest_sha256": BJ101_MANIFEST,
        "bj101_pool_census_sha256": manifest101["issue_pool_census.csv"],
        "bj101_membership_sha256": manifest101["issue_pool_membership.csv"],
    }
    return provenance, pools, by_pool


def gzip_csv_writer(path: Path, fields: tuple[str, ...]):
    raw = path.open("wb")
    zipped = gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0)
    text = io.TextIOWrapper(zipped, encoding="utf-8", newline="")
    writer = csv.DictWriter(text, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    return raw, zipped, text, writer


def freeze(output: Path) -> dict[str, object]:
    if output.exists():
        raise RuntimeError(f"refusing immutable overwrite: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".bj121_gatea_", dir=output.parent))
    try:
        provenance, pools, by_pool = load_sources()
        frontier_handles = gzip_csv_writer(stage / "portfolio_frontier.csv.gz", FRONTIER_FIELDS)
        assignment_handles = gzip_csv_writer(stage / "candidate_assignments.csv.gz", ASSIGNMENT_FIELDS)
        frontier_writer = frontier_handles[-1]
        assignment_writer = assignment_handles[-1]
        summary = {
            (variant_id, arm): defaultdict(int)
            for variant_id in VARIANTS
            for arm in ARMS
        }
        frontier_rows = 0
        assignment_rows = 0
        for variant_id, rule in VARIANTS.items():
            for pool in pools:
                all_matches = by_pool.get(pool["pool_id"], [])
                for arm in ARMS:
                    policy, requested_n, unfiltered = arm_components(arm, len(all_matches))
                    candidates = all_matches if unfiltered else [row for row in all_matches if float(row["e_sp"]) >= rule["e_sp_min"]]
                    if policy == "NO_BET":
                        candidates = []
                        selected: list[dict[str, object]] = []
                        reason = "NO_BET_CONTROL"
                    else:
                        if arm.endswith("_DYNAMIC_4_7"):
                            policy, requested_n, unfiltered = arm_components(arm, len(candidates))
                        selected = candidates[:requested_n] if requested_n and len(candidates) >= requested_n else []
                        reason = "AVAILABLE_FROZEN" if selected else "INSUFFICIENT_MATCHES_FOR_N"
                    gm_e_sp = geometric([float(row["e_sp"]) for row in selected]) if selected else 0.0
                    if selected and not unfiltered and gm_e_sp < rule["gm_e_sp_min"]:
                        selected = []
                        reason = "GM_E_SP_BELOW_THRESHOLD"
                    role_rows: list[dict[str, object]] = []
                    mass = 1.0
                    k = 1
                    for rank, row in enumerate(selected, 1):
                        role, allowed, omitted = role_for(policy, row, rule)
                        probabilities = row["p"]
                        assert isinstance(probabilities, dict)
                        retained = sum(float(probabilities[code]) for code in allowed)
                        mass *= retained
                        k *= len(allowed)
                        role_rows.append({
                            "variant_id": variant_id, "arm": arm, "issue": pool["issue"],
                            "fold": pool["fold"], "year": pool["year"], "pool_id": pool["pool_id"],
                            "match_id": row["match_id"], "match_idx": row["match_idx"],
                            "selection_rank": rank, "role": role, "allowed_codes": allowed,
                            "omitted_codes": omitted, "p3": fmt(float(probabilities["3"])),
                            "p1": fmt(float(probabilities["1"])), "p0": fmt(float(probabilities["0"])),
                            "p_min": fmt(float(row["p_min"])), "p_max": fmt(float(row["p_max"])),
                            "argmin_code": row["argmin_code"], "argmax_code": row["argmax_code"],
                            "e_sp": fmt(float(row["e_sp"])), "q3": fmt(float(row["q"]["3"])),
                            "q1": fmt(float(row["q"]["1"])), "q0": fmt(float(row["q"]["0"])),
                        })
                    if not selected:
                        k = 0
                        mass = 0.0
                    full_legs = sum(row["role"] == "FULL" for row in role_rows)
                    double_legs = sum(row["role"] == "DOUBLE" for row in role_rows)
                    single_legs = sum(row["role"] == "SINGLE" for row in role_rows)
                    g_be = (k / (PAYOUT_FACTOR_DIAGNOSTIC * mass)) ** (1 / len(selected)) if selected and mass > 0 else 0.0
                    role_codes = ";".join(f"{row['match_id']}:{row['role']}:{row['allowed_codes']}" for row in role_rows)
                    payload = {
                        "contract": CONTRACT, "variant_id": variant_id, "arm": arm,
                        "pool_id": pool["pool_id"], "roles": role_codes, "reason": reason,
                    }
                    frontier_writer.writerow({
                        **pool, "variant_id": variant_id, "arm": arm,
                        "candidate_match_count": len(candidates), "selected_n": len(selected),
                        "selected_match_ids": ";".join(str(row["match_id"]) for row in selected),
                        "role_codes": role_codes, "full_legs": full_legs,
                        "double_legs": double_legs, "single_legs": single_legs,
                        "gm_e_sp": fmt(gm_e_sp) if selected else "",
                        "expected_portfolio_mass": fmt(mass) if selected else "",
                        "formula_k": k, "stake_yuan": fmt(STAKE_PER_TICKET * k),
                        "g_be_pre_tax": fmt(g_be) if selected else "",
                        "disposition": "AVAILABLE" if selected else "NO_BET", "reason": reason,
                        "descriptor_sha256": descriptor(payload),
                    })
                    assignment_writer.writerows(role_rows)
                    frontier_rows += 1
                    assignment_rows += len(role_rows)
                    bucket = summary[(variant_id, arm)]
                    bucket["pools"] += 1
                    bucket["available"] += bool(selected)
                    bucket["no_bet"] += not bool(selected)
                    bucket["candidate_matches"] += len(candidates)
                    bucket["full_legs"] += full_legs
                    bucket["double_legs"] += double_legs
                    bucket["single_legs"] += single_legs
                    bucket["tickets"] += k
                    bucket["stake_yuan"] += STAKE_PER_TICKET * k
        for raw, zipped, text, _ in (frontier_handles, assignment_handles):
            text.flush()
            text.detach()
            zipped.close()
            raw.close()
        with (stage / "frontier_density_summary.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS, lineterminator="\n")
            writer.writeheader()
            for variant_id in VARIANTS:
                for arm in ARMS:
                    writer.writerow({"variant_id": variant_id, "arm": arm, **summary[(variant_id, arm)]})
        card = {
            "issue": 121,
            "contract": CONTRACT,
            "generator_version": GENERATOR_VERSION,
            "stage": "GATE_A_OUTCOME_UNEXPOSED_FREEZE",
            "provenance": provenance,
            "denominator": {"native_issues": 344, "native_pools": 2659, "frontier_rows": frontier_rows},
            "features": "Per-match E_SP=sum_code(p_cal(code)*predicted_sp(code)); rank descending by E_SP, then p_min ascending, then match_idx.",
            "segmentation": "Reuse #101 pre-outcome native issue/24-hour pool segmentation; every pool is retained, including explicit NO_BET rows.",
            "variants": VARIANTS,
            "arms": ARMS,
            "roles": {
                "FULL": "all 3/1/0 codes",
                "PRUNE": "DOUBLE by deleting argmin p_cal when p_min<=low_p_max; otherwise FULL",
                "MIXED": "SINGLE argmax when p_min<=low_p_max and p_max>=0.50; else DOUBLE after deleting argmin when p_min<=low_p_max; otherwise FULL",
                "UNFILTERED_FULL_CONTROL": "top E_SP matches without E_SP/GM threshold, all codes retained",
            },
            "portfolio_gate": "Filtered arms require match E_SP>=e_sp_min and GM(selected E_SP)>=gm_e_sp_min. Dynamic N uses N7 when >=7 candidates, else N4 when >=4, else NO_BET.",
            "accounting": "K=product allowed-code counts; stake=2*K. H=product retained calibrated probability. G_BE=[K/(0.65*H)]^(1/N) is outcome-free pre-tax diagnostic only.",
            "outcome_boundary": "No result, actual final SP, payout, tax, ROI, or settlement source is opened or emitted in Gate A.",
            "gate_b": "NOT_RUN and NOT_AUTHORIZED. Only this exact immutable matrix may later be settled without adding or selecting thresholds after outcomes.",
            "scope": "historical paper-only research; no purchase, production or promotion",
        }
        (stage / "gate_a_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        shutil.copyfile(__file__, stage / "runner.py")
        (stage / "README.md").write_text(
            "# #121 Gate A\n\nOutcome-unexposed E_SP × lowest-probability frontier. "
            "Run `python3 runner.py --output <new-dir>` from a compatible checkout. Gate B is not run.\n",
            encoding="utf-8",
        )
        gzip_names = ("portfolio_frontier.csv.gz", "candidate_assignments.csv.gz")
        controls = ("README.md", "frontier_density_summary.csv", "gate_a_card.json", "runner.py")
        identity = {
            "contract_version": CONTENT_IDENTITY_VERSION,
            "gzip_payloads": {
                name: {
                    "canonical_decompressed_sha256": decompressed_identity(stage / name)[0],
                    "canonical_decompressed_bytes": decompressed_identity(stage / name)[1],
                }
                for name in gzip_names
            },
            "non_compressed_controls": {name: sha256(stage / name) for name in controls},
        }
        (stage / "CONTENT_IDENTITY.json").write_text(json.dumps(identity, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest = {item.name: sha256(item) for item in sorted(stage.iterdir()) if item.is_file()}
        (stage / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(stage, output)
        return {
            "manifest_sha256": sha256(output / "SHA256SUMS.json"),
            "frontier_rows": frontier_rows,
            "assignment_rows": assignment_rows,
            "variants": len(VARIANTS),
            "arms": len(ARMS),
        }
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(json.dumps(freeze(args.output.resolve()), sort_keys=True))


if __name__ == "__main__":
    main()
