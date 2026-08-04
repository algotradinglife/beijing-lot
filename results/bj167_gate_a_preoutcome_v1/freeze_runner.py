#!/usr/bin/env python3
"""Outcome-unexposed Gate-A freeze for #167 (N=7, 100 deterministic seeds).

The accepted #159 complete-issue identity/role/participation files are the
only inputs.  This program never opens a result, SP, payout, tax, or outcome
settlement file.  It freezes the N7 source rows, M grid, seed panel and the
first 128 Q-informed WOR ticket ordinals for every identity/seed pair.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import heapq
import itertools
import json
import math
import os
import concurrent.futures
from datetime import datetime, timezone
from pathlib import Path

CONTRACT = "BJ-HIST-N7-SEED-ENSEMBLE-001"
SOURCE_CONTRACT = "BJ-HIST-SELECTED-WOR-CROSS-N-001"
SOURCE_MANIFEST = "a15c585fc1836da4f558d07ce19c925561bfd1c240e834b7e3e0da22701cd325"
N = 7
M_GRID = (32, 64, 128)
SEEDS = tuple(f"137{i:03d}" for i in range(1, 101))
CODES = ("3", "1", "0")
TOP_K = 128


def repo_root(anchor: Path) -> Path:
    for candidate in (anchor.resolve().parent, *anchor.resolve().parents):
        if (candidate / ".git").exists() and (candidate / "results").is_dir():
            return candidate
    raise RuntimeError("repository root unavailable")


ROOT = repo_root(Path(__file__))
SOURCE = ROOT / "results/bj159_gate_a_preoutcome_v2r1"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def compact_hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def verify_bundle(path: Path, expected_manifest: str) -> dict[str, str]:
    manifest_path = path / "SHA256SUMS.json"
    if sha(manifest_path) != expected_manifest:
        raise RuntimeError(f"source manifest mismatch: {path}")
    declared = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = {item.name: sha(item) for item in path.iterdir() if item.is_file() and item.name != manifest_path.name}
    if declared != actual:
        raise RuntimeError(f"source manifest coverage drift: {path}")
    return declared


def read_gzip(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fields: tuple[str, ...]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n", extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def write_gzip(path: Path, rows: list[dict[str, object]], fields: tuple[str, ...]) -> None:
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            import io
            stream = io.TextIOWrapper(zipped, encoding="utf-8", newline="")
            writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n", extrasaction="raise")
            writer.writeheader()
            writer.writerows(rows)
            stream.flush()
            stream.detach()


def stable_uniform(*parts: object) -> float:
    token = "|".join(str(part) for part in parts).encode("utf-8")
    value = int.from_bytes(hashlib.sha256(token).digest()[:8], "big")
    return (value + 0.5) / (2 ** 64)


def allocation_for(identity: tuple[str, str, tuple[tuple[float, float, float], ...]]) -> list[dict[str, object]]:
    identity_id, signature, q_vectors = identity
    weights = tuple(
        math.prod(q_vectors[index][CODES.index(code)] for index, code in enumerate(ticket))
        for ticket in itertools.product(CODES, repeat=N)
    )
    if abs(sum(weights) - 1.0) > 2e-8:
        raise RuntimeError(f"ticket probability mass drift: {identity_id}")
    result = []
    for seed in SEEDS:
        keyed = []
        for ordinal, weight in enumerate(weights):
            key = math.inf if weight <= 0 else -math.log(max(stable_uniform("bj137", "WOR", seed, signature, ordinal), 1e-18)) / weight
            keyed.append((key, ordinal))
        selected = tuple(ordinal for _, ordinal in heapq.nsmallest(TOP_K, keyed))
        fingerprints = {
            str(m): hashlib.sha256(json.dumps(selected[:m], separators=(",", ":")).encode()).hexdigest()
            for m in M_GRID
        }
        result.append({
            "identity_id": identity_id,
            "n": N,
            "seed": seed,
            "identity_signature": signature,
            "ticket_space_k": 3 ** N,
            "top_k": TOP_K,
            "allocation_ordinals": "|".join(map(str, selected)),
            "allocation_fingerprint_32": fingerprints["32"],
            "allocation_fingerprint_64": fingerprints["64"],
            "allocation_fingerprint_128": fingerprints["128"],
            "allocator": "Q_INFORMED_WOR_DISTINCT",
            "mechanism": "WEIGHTED_WITHOUT_REPLACEMENT",
            "outcome_boundary": "No outcome/final-SP/payout/tax/ROI/settlement input read or emitted",
        })
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "results/bj167_gate_a_preoutcome_v1")
    parser.add_argument("--head-start", default="")
    parser.add_argument("--head-end", default="")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise RuntimeError(f"refusing overwrite: {output}")
    source_manifest = verify_bundle(SOURCE, SOURCE_MANIFEST)
    identities = [row for row in read_gzip(SOURCE / "identity_catalog.csv.gz") if int(row["n"]) == N]
    roles = [row for row in read_gzip(SOURCE / "role_vectors.csv.gz") if int(row["n"]) == N]
    participation = [row for row in read_csv(SOURCE / "issue_participation.csv") if int(row["n"]) == N]
    if len(identities) != 1005 or len(roles) != 7035:
        raise RuntimeError("N7 identity/role denominator drift")
    identity_ids = {row["identity_id"] for row in identities}
    role_map: dict[str, list[dict[str, str]]] = {identity_id: [] for identity_id in identity_ids}
    for role in roles:
        role_map[role["identity_id"]].append(role)
    for identity in identities:
        ordered = sorted(role_map[identity["identity_id"]], key=lambda row: int(row["selection_rank"]))
        if len(ordered) != N or "|".join(row["match_id"] for row in ordered) != identity["selected_match_ids"]:
            raise RuntimeError("N7 identity/role join drift")
    specs = []
    for identity in identities:
        ordered = sorted(role_map[identity["identity_id"]], key=lambda row: int(row["selection_rank"]))
        q_vectors = tuple(tuple(float(row[f"q_weight{code}"]) for code in CODES) for row in ordered)
        specs.append((identity["identity_id"], identity["selected_match_ids"], q_vectors))
    allocation_rows: list[dict[str, object]] = []
    workers = max(1, min(8, os.cpu_count() or 1))
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
        for rows in executor.map(allocation_for, specs, chunksize=1):
            allocation_rows.extend(rows)
    allocation_rows.sort(key=lambda row: (str(row["identity_id"]), str(row["seed"])))
    output.mkdir(parents=True)
    identity_fields = tuple(identities[0].keys())
    role_fields = tuple(roles[0].keys())
    part_fields = tuple(participation[0].keys())
    write_gzip(output / "identity_catalog.csv.gz", identities, identity_fields)
    write_gzip(output / "role_vectors.csv.gz", roles, role_fields)
    write_csv(output / "issue_participation.csv", participation, part_fields)
    allocation_fields = tuple(allocation_rows[0].keys())
    write_gzip(output / "allocation_catalog.csv.gz", allocation_rows, allocation_fields)
    plans = []
    for seed in SEEDS:
        for nominal_m in M_GRID:
            plans.append({
                "n": N, "nominal_M": nominal_m, "effective_M": nominal_m, "seed": seed,
                "allocator": "Q_INFORMED_WOR_DISTINCT", "probability_vector": "Q_WEIGHT",
                "mechanism": "WEIGHTED_WITHOUT_REPLACEMENT", "duplicate_policy": "EFFECTIVE_M_DISTINCT_TICKETS_PER_IDENTITY",
                "ticket_space_k": 3 ** N, "coverage_fraction": f"{nominal_m / (3 ** N):.12f}",
                "stake_per_ticket_yuan": "2", "primary_or_sensitivity": "PRIMARY" if nominal_m == 64 else "SENSITIVITY",
                "outcome_boundary": "Pre-outcome allocation specification only; Gate B joins canonical outcome after this freeze",
            })
    write_csv(output / "sampling_plan.csv", plans, tuple(plans[0].keys()))
    generated = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    source_binding = {
        "issue": 167, "contract": CONTRACT, "generated_at_utc": generated,
        "source_gate_a_159_manifest": SOURCE_MANIFEST,
        "source_gate_a_159_identity_payload": source_manifest["identity_catalog.csv.gz"],
        "source_gate_a_159_role_payload": source_manifest["role_vectors.csv.gz"],
        "source_gate_a_159_participation_payload": source_manifest["issue_participation.csv"],
        "source_contract": SOURCE_CONTRACT, "n": N, "M_grid": list(M_GRID), "seed_panel": list(SEEDS),
        "outcome_boundary": "No outcomes, final SP, payout, tax or settlement input was opened",
        "runner_head": __import__("subprocess").check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
    }
    card = {
        "issue": 167, "contract": CONTRACT, "stage": "GATE_A_OUTCOME_UNEXPOSED_N7_SEED_ENSEMBLE",
        "head_start": args.head_start, "head_end": args.head_end, "generated_at_utc": generated,
        "n": N, "M_grid": list(M_GRID), "seed_panel": list(SEEDS), "identity_count": len(identities),
        "role_count": len(roles), "participation_count": len(participation), "allocation_rows": len(allocation_rows),
        "ticket_space_k": 3 ** N, "top_k_frozen": TOP_K, "allocator": "Q_INFORMED_WOR_DISTINCT",
        "primary_metric": "pre-tax no_tax_roi; tax-adjusted ROI secondary in Gate B",
        "promotion_authorized": False, "no_purchase_production_or_betting_authority": True,
        "outcome_boundary": "No result, score, final SP, payout, tax, ROI or settlement input read or emitted",
    }
    (output / "source_binding.json").write_text(json.dumps(source_binding, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "gate_a_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "README.md").write_text("# #167 Gate A\n\nOutcome-unexposed N=7 only freeze: 1,005 complete-issue identities, M={32,64,128}, and deterministic seeds 137001..137100. Each identity/seed stores the first 128 Q-informed WOR ticket ordinals; no result or settlement input is opened.\n", encoding="utf-8")
    import shutil
    shutil.copy2(Path(__file__), output / "freeze_runner.py")
    content = {"package": output.name, "contract": CONTRACT, "files": {item.name: sha(item) for item in sorted(output.iterdir()) if item.is_file()}}
    (output / "CONTENT_IDENTITY.json").write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = {item.name: sha(item) for item in sorted(output.iterdir()) if item.is_file()}
    (output / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "manifest_sha256": sha(output / "SHA256SUMS.json"), "content_sha256": sha(output / "CONTENT_IDENTITY.json"), "identity_count": len(identities), "allocation_rows": len(allocation_rows)}, sort_keys=True))


if __name__ == "__main__":
    main()
