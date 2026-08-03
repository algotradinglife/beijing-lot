#!/usr/bin/env python3
"""Freeze the #137/#151 fixed N=7 candidate for #167's 100-seed test.

This is outcome-unexposed.  It reads only the accepted #151 Gate-A package,
copies its fixed identities/Q vectors, and deterministically adds the frozen
100-seed WOR allocation fingerprints required by the controlling #167 contract.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import csv
import gzip
import hashlib
import heapq
import itertools
import json
import math
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

CONTRACT = "BJ-HIST-N7-SEED-ENSEMBLE-002"
SOURCE_MANIFEST = "3605278bd6067fc7aa279a0625f4c4cab91603d8a1490c8608381e8fca997ac6"
SOURCE_CONTENT = "ac36bc2422d1afd22c3bb4bd680568401cbaec30e0d2006d13afcdfa141b89a5"
SOURCE_137_MANIFEST = "0aabeb94cec6d68831d233553e710b425bf02c1a843eae21adad50c4f9fac2df"
SOURCE_137_CONTENT = "36d6afcc33a5b5ceb3e4a990bfe6ec05503be115270c3489f4973dc3a59dd236"
N, FULL_TICKETS, TOP_K = 7, 2187, 128
M_GRID = (32, 64, 128)
SEEDS = tuple(f"137{i:03d}" for i in range(1, 101))
CODES = ("3", "1", "0")


def root(anchor: Path) -> Path:
    for candidate in (anchor.resolve().parent, *anchor.resolve().parents):
        if (candidate / ".git").exists() and (candidate / "results").is_dir():
            return candidate
    raise RuntimeError("repository root unavailable")


ROOT = root(Path(__file__))
SOURCE = ROOT / "results/bj151_gate_a_preoutcome_v1"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def verify_bundle(path: Path, expected: str) -> dict[str, str]:
    manifest_path = path / "SHA256SUMS.json"
    if sha(manifest_path) != expected:
        raise RuntimeError(f"source manifest mismatch: {path}")
    declared = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = {item.name: sha(item) for item in path.iterdir() if item.is_file() and item.name != manifest_path.name}
    if declared != actual:
        raise RuntimeError(f"source manifest coverage drift: {path}")
    return declared


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_gzip(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fields: tuple[str, ...]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n", extrasaction="raise")
        writer.writeheader(); writer.writerows(rows)


def write_gzip(path: Path, rows: list[dict[str, object]], fields: tuple[str, ...]) -> None:
    import io
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            stream = io.TextIOWrapper(zipped, encoding="utf-8", newline="")
            writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n", extrasaction="raise")
            writer.writeheader(); writer.writerows(rows); stream.flush(); stream.detach()


def stable_uniform(*parts: object) -> float:
    token = "|".join(str(part) for part in parts).encode("utf-8")
    return (int.from_bytes(hashlib.sha256(token).digest()[:8], "big") + 0.5) / (2 ** 64)


def allocate(spec: tuple[str, str, tuple[tuple[float, float, float], ...]]) -> list[dict[str, object]]:
    portfolio_id, signature, q_vectors = spec
    weights = tuple(math.prod(q_vectors[index][CODES.index(code)] for index, code in enumerate(ticket)) for ticket in itertools.product(CODES, repeat=N))
    if abs(sum(weights) - 1.0) > 2e-8:
        raise RuntimeError(f"Q mass drift: {portfolio_id}")
    output = []
    for seed in SEEDS:
        keyed = []
        for ordinal, weight in enumerate(weights):
            key = math.inf if weight <= 0 else -math.log(max(stable_uniform("bj137", "WOR", seed, signature, ordinal), 1e-18)) / weight
            keyed.append((key, ordinal))
        selected = tuple(ordinal for _, ordinal in heapq.nsmallest(TOP_K, keyed))
        output.append({
            "portfolio_id": portfolio_id, "identity_signature": signature, "n": N, "seed": seed,
            "ticket_space_k": FULL_TICKETS, "top_k": TOP_K, "allocation_ordinals": "|".join(map(str, selected)),
            "allocation_fingerprint_32": hashlib.sha256(json.dumps(selected[:32], separators=(",", ":")).encode()).hexdigest(),
            "allocation_fingerprint_64": hashlib.sha256(json.dumps(selected[:64], separators=(",", ":")).encode()).hexdigest(),
            "allocation_fingerprint_128": hashlib.sha256(json.dumps(selected[:128], separators=(",", ":")).encode()).hexdigest(),
            "allocator": "Q_INFORMED_WOR_DISTINCT", "mechanism": "WEIGHTED_WITHOUT_REPLACEMENT",
            "outcome_boundary": "No outcome/final-SP/payout/tax/ROI/settlement input read or emitted",
        })
    return output


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--output", type=Path, default=ROOT / "results/bj167_gate_a_preoutcome_v2")
    parser.add_argument("--head-start", default=""); parser.add_argument("--head-end", default="")
    args = parser.parse_args(); output = args.output.resolve()
    if output.exists():
        raise RuntimeError(f"refusing overwrite: {output}")
    source_manifest = verify_bundle(SOURCE, SOURCE_MANIFEST)
    source_card = json.loads((SOURCE / "gate_a_card.json").read_text(encoding="utf-8"))
    source_content = json.loads((SOURCE / "CONTENT_IDENTITY.json").read_text(encoding="utf-8"))
    if source_content.get("contract_version") != "bj151-gate-a-content-v1" or source_card.get("stage") != "GATE_A_OUTCOME_UNEXPOSED_FIXED_CANDIDATE_DENSE_M_FREEZE":
        raise RuntimeError("unexpected #151 Gate-A source contract")
    if source_card["sources"]["bj137_gate_a_v2"]["manifest_sha256"] != SOURCE_137_MANIFEST or source_card["sources"]["bj137_gate_a_v2"]["content_identity_sha256"] != SOURCE_137_CONTENT:
        raise RuntimeError("#137 source binding drift")
    cohort = read_csv(SOURCE / "candidate_cohort.csv")
    identities = read_gzip(SOURCE / "candidate_identities.csv.gz")
    roles = read_gzip(SOURCE / "candidate_role_vectors.csv.gz")
    if len(cohort) != 348 or len(identities) != 1356 or len(roles) != 9492:
        raise RuntimeError("#151 source denominator drift")
    if sum(row["selection_status"] == "AVAILABLE" for row in cohort) != 339 or sum(row["selection_status"] != "AVAILABLE" for row in cohort) != 9:
        raise RuntimeError("#151 availability drift")
    role_map: dict[str, list[dict[str, str]]] = {row["portfolio_id"]: [] for row in identities}
    for row in roles:
        role_map[row["portfolio_id"]].append(row)
    specs = []
    for identity in identities:
        ordered = sorted(role_map[identity["portfolio_id"]], key=lambda row: int(row["selection_rank"]))
        if len(ordered) != N or "|".join(row["match_id"] for row in ordered) != identity["selected_match_ids"]:
            raise RuntimeError("#151 identity/role join drift")
        q_vectors = tuple(tuple(float(row[f"q_weight{code}"]) for code in CODES) for row in ordered)
        specs.append((identity["portfolio_id"], identity["selected_match_ids"], q_vectors))
    allocation_rows: list[dict[str, object]] = []
    workers = max(1, min(8, os.cpu_count() or 1))
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
        for rows in executor.map(allocate, specs, chunksize=1):
            allocation_rows.extend(rows)
    allocation_rows.sort(key=lambda row: (str(row["portfolio_id"]), str(row["seed"])) )
    output.mkdir(parents=True)
    write_gzip(output / "candidate_identities.csv.gz", identities, tuple(identities[0].keys()))
    write_gzip(output / "candidate_role_vectors.csv.gz", roles, tuple(roles[0].keys()))
    write_csv(output / "candidate_cohort.csv", cohort, tuple(cohort[0].keys()))
    write_gzip(output / "allocation_catalog.csv.gz", allocation_rows, tuple(allocation_rows[0].keys()))
    plans = []
    for m in M_GRID:
        plans.append({"M": m, "seed_count": len(SEEDS), "seed_panel": "|".join(SEEDS), "sampler": "Q_INFORMED_WOR_DISTINCT", "mechanism": "WEIGHTED_WITHOUT_REPLACEMENT", "outcome_boundary": "pre-outcome allocation specification only"})
    plans.append({"M": FULL_TICKETS, "seed_count": 1, "seed_panel": "NA", "sampler": "FULL_ENUMERATED", "mechanism": "ALL_DISTINCT_TICKETS", "outcome_boundary": "pre-outcome control specification only"})
    write_csv(output / "sampling_plan.csv", plans, tuple(plans[0].keys()))
    source_census = [
        {"source": "bj151_gate_a_preoutcome_v1", "role": "accepted exact #137 NO_GATE/K4 identities, roles and q vectors", "identity": "SHA256SUMS.json", "sha256": SOURCE_MANIFEST, "rows": len(identities) + len(roles), "join_status": "copied without outcome exposure or re-selection"},
        {"source": "bj137_gate_a_preoutcome_v2", "role": "underlying accepted candidate definition", "identity": "SHA256SUMS.json", "sha256": SOURCE_137_MANIFEST, "rows": 0, "join_status": "binding inherited from #151 Gate-A card"},
    ]
    write_csv(output / "source_census.csv", source_census, tuple(source_census[0].keys()))
    generated = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    binding = {"issue": 167, "contract": CONTRACT, "generated_at_utc": generated, "source_gate_a_151_manifest": SOURCE_MANIFEST, "source_gate_a_151_content_identity": SOURCE_CONTENT, "source_gate_a_137_manifest": SOURCE_137_MANIFEST, "source_gate_a_137_content_identity": SOURCE_137_CONTENT, "n": N, "M_grid": list(M_GRID), "full_control_M": FULL_TICKETS, "seed_panel": list(SEEDS), "sampler_namespace": "bj137|WOR|seed|identity_signature|ticket_ordinal", "outcome_boundary": "No outcome, score, final SP, payout, tax, ROI or settlement input was read or emitted", "runner_head": __import__("subprocess").check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()}
    card = {"issue": 167, "contract": CONTRACT, "stage": "GATE_A_OUTCOME_UNEXPOSED_FIXED_137_CANDIDATE_100_SEED_FREEZE", "generated_at_utc": generated, "head_start": args.head_start, "head_end": args.head_end, "source_gate_a_151_manifest": SOURCE_MANIFEST, "source_gate_a_151_content_identity": SOURCE_CONTENT, "source_gate_a_137_manifest": SOURCE_137_MANIFEST, "source_gate_a_137_content_identity": SOURCE_137_CONTENT, "n": N, "candidate_definition": "exact #137 NO_GATE/K4 selected portfolio IDs and q vectors copied from accepted #151 Gate-A; no selector/identity/vector/threshold search", "primary_arm": "Q_INFORMED_WOR_DISTINCT/M64/Q_WEIGHT", "M_grid": list(M_GRID), "full_control_M": FULL_TICKETS, "seed_panel": list(SEEDS), "sampler_namespace": "bj137|WOR|seed|identity_signature|ticket_ordinal", "candidate_identity_count": len(identities), "candidate_role_count": len(roles), "cohort_issue_count": len(cohort), "available_issue_count": sum(row["selection_status"] == "AVAILABLE" for row in cohort), "no_bet_issue_count": sum(row["selection_status"] != "AVAILABLE" for row in cohort), "allocation_rows": len(allocation_rows), "outcome_boundary": "No result, score, final SP, payout, tax, ROI or settlement input read or emitted", "promotion_authorized": False, "no_purchase_production_or_betting_authority": True}
    (output / "source_binding.json").write_text(json.dumps(binding, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "gate_a_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "README.md").write_text("# #167 Gate A v2\n\nOutcome-unexposed exact #137/#151 NO_GATE/K4 N=7 candidate freeze with 100 deterministic WOR seeds and M={32,64,128}; FULL is a Gate-B matched control. No outcome or settlement input is opened.\n", encoding="utf-8")
    shutil.copy2(Path(__file__), output / "freeze_runner.py")
    content = {"package": output.name, "contract": CONTRACT, "files": {item.name: sha(item) for item in sorted(output.iterdir()) if item.is_file()}}
    (output / "CONTENT_IDENTITY.json").write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {item.name: sha(item) for item in sorted(output.iterdir()) if item.is_file()}
    (output / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "manifest_sha256": sha(output / "SHA256SUMS.json"), "content_sha256": sha(output / "CONTENT_IDENTITY.json"), "candidate_identity_count": len(identities), "allocation_rows": len(allocation_rows)}, sort_keys=True))


if __name__ == "__main__":
    main()
