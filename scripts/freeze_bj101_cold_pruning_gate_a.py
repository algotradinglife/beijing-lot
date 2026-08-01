#!/usr/bin/env python3
"""Outcome-free Gate-A freeze for #101 issue-level cold-outcome N7 pruning."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import shutil
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, getcontext
from pathlib import Path

getcontext().prec = 60
CODES = ("3", "1", "0")
THRESHOLDS = (Decimal("0.05"), Decimal("0.10"), Decimal("0.15"), Decimal("0.20"))
WINDOW_HOURS = (12, 18, 24, 36)
MAX_POOL_MATCHES = 24
N = 7
PRUNED_TICKETS = 2 * 3**6
FULL_TICKETS = 3**7

BJ89_MANIFEST = "b22c33bddc71972e3c2a5e7b95955087ece2441b5728da6424d19b3de6f503e2"
BJ91_MANIFEST = "bd7159715cca84e9d2adb9e089d016ec4e4d72603f8f8d5a8b070eb5027c2c33"
BJ95_MANIFEST = "10b4d6d274aef53e1e1d4abe30cd9f683cf296865ee131f00f5c1e1d16d0725c"
BJ98_MANIFEST = "fd142cc2594f2e71b4b81136e91e7ecfcf8623b07c94d92d0b9c1cf6a212b4cb"

P89_FIELDS = (
    "match_id", "issue", "match_idx", "kickoff_ts", "year", "fold",
    "handicap_line_norm", "n_complete_10h", "euro_3_10h", "euro_1_10h",
    "euro_0_10h", "p3_raw", "p1_raw", "p0_raw", "top1_code_raw",
    "top1_mass_raw", "top2_mass_raw", "entropy_raw",
    "dispersion_mean_relative_range", "initial_status", "p3_initial",
    "p1_initial", "p0_initial", "initial_to_10h_log_probability_movement",
)
P91_FIELDS = (
    "match_id", "issue", "match_idx", "year", "fold", "p3", "p1", "p0",
    "point_sp_3", "point_sp_1", "point_sp_0", "m2_sp_3", "m2_sp_1",
    "m2_sp_0", "point_sp5_3", "point_sp5_1", "point_sp5_0", "m2_sp5_3",
    "m2_sp5_1", "m2_sp5_0",
)
MEMBERSHIP_FIELDS = (
    "issue", "fold", "year", "pool_id", "segment_index", "pool_disposition",
    "match_id", "match_idx", "kickoff_ts", "p3", "p1", "p0", "deleted_code",
    "p_min", "p_min_rank", "p_min_bucket", "eligible_t05", "eligible_t10",
    "eligible_t15", "eligible_t20",
)
POOL_FIELDS = (
    "issue", "fold", "year", "pool_id", "segment_index", "pool_disposition",
    "eligible_match_count", "pool_match_count", "first_kickoff_ts", "last_kickoff_ts",
    "window_hours", "terminal_remainder",
)
FRONTIER_FIELDS = (
    "issue", "fold", "year", "pool_id", "segment_index", "pool_match_count",
    "match_id", "match_idx", "kickoff_ts", "threshold", "arm", "deleted_code",
    "p_min", "p_min_rank", "n7_combination_count", "tickets_per_n7",
    "total_tickets", "stake_yuan", "portfolio_descriptor_sha256",
)
SUMMARY_FIELDS = (
    "threshold", "arm", "eligible_deleted_matches", "n7_combination_count",
    "total_tickets", "stake_yuan",
)
SOURCE_CENSUS_FIELDS = (
    "source", "role", "manifest_sha256", "payload", "payload_sha256",
    "row_count", "used_at_gate_a", "join_status",
)


def repository_root(anchor: Path) -> Path:
    for candidate in (anchor.resolve().parent, *anchor.resolve().parents):
        if (candidate / ".git").exists():
            return candidate
    return anchor.resolve().parent


ROOT = repository_root(Path(__file__))
P89 = ROOT / "results" / "bj89_gate_a_preoutcome_v3"
P91 = ROOT / "results" / "bj91_gate_a_preoutcome_v1r6"
P95 = ROOT / "results" / "bj95_gate_a_preoutcome_v5"
P98 = ROOT / "results" / "bj98_gate_a_preoutcome_v1"
OUT = ROOT / "results" / "bj101_gate_a_preoutcome_v1r1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def exact_manifest(bundle: Path, expected: str) -> dict[str, str]:
    manifest_path = bundle / "SHA256SUMS.json"
    if sha256(manifest_path) != expected:
        raise RuntimeError(f"unaccepted bundle manifest: {bundle}")
    declared = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = list(bundle.iterdir())
    if not isinstance(declared, dict) or any(not item.is_file() for item in entries):
        raise RuntimeError(f"non-exact bundle: {bundle}")
    actual = {item.name: sha256(item) for item in entries if item.name != manifest_path.name}
    if actual != declared:
        raise RuntimeError(f"manifest coverage drift: {bundle}")
    return declared


def authenticated_snapshot(private_dir: Path, name: str, source: Path, expected: str) -> Path:
    target = private_dir / name
    shutil.copyfile(source, target)
    if sha256(target) != expected:
        raise RuntimeError(f"authenticated source drift during copy: {source}")
    return target


def read_csv(path: Path, fields: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != fields:
            raise RuntimeError(f"schema mismatch: {path}")
        return list(reader)


def read_gzip(path: Path, fields: tuple[str, ...]) -> list[dict[str, str]]:
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != fields:
            raise RuntimeError(f"schema mismatch: {path}")
        return list(reader)


def money(value: int) -> str:
    return f"{value:.6f}"


def key(row: dict[str, str]) -> tuple[str, str, str, str]:
    return row["match_id"], row["issue"], row["match_idx"], row["fold"]


def threshold_label(value: Decimal) -> str:
    return f"T{int(value * 100):02d}"


def probability_bucket(value: Decimal) -> str:
    lower = (int(value * 20) * 5)
    return f"[{lower / 100:.2f},{(lower + 5) / 100:.2f})"


def cold_code(row: dict[str, str]) -> tuple[str, Decimal]:
    probabilities = {code: Decimal(row[f"p{code}"]) for code in CODES}
    if abs(sum(probabilities.values()) - Decimal(1)) > Decimal("0.000001"):
        raise RuntimeError(f"invalid calibrated probability mass: {row['match_id']}")
    code = min(CODES, key=lambda candidate: (probabilities[candidate], CODES.index(candidate)))
    return code, probabilities[code]


def hash_code(row: dict[str, str], threshold: Decimal) -> str:
    digest = hashlib.sha256(
        f"BJ-HIST-COLD-PRUNING-001|{threshold}|{row['pool_id']}|{row['match_id']}".encode()
    ).digest()
    return CODES[digest[0] % len(CODES)]


@dataclass(frozen=True)
class Pool:
    issue: str
    fold: str
    year: str
    pool_id: str
    segment_index: int
    disposition: str
    rows: tuple[dict[str, str], ...]
    window_hours: str
    terminal_remainder: bool


def make_pools(rows: list[dict[str, str]]) -> list[Pool]:
    """Apply the issue-only rolling segmentation without probability or outcome access."""
    by_issue: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        by_issue[(row["issue"], row["fold"])].append(row)
    pools: list[Pool] = []
    for (issue, fold), issue_rows in sorted(by_issue.items()):
        ordered = sorted(issue_rows, key=lambda row: (row["kickoff_ts"], int(row["match_idx"]), int(row["match_id"])))
        year = ordered[0]["year"]
        if len(ordered) < N:
            pools.append(Pool(issue, fold, year, f"{issue}-{fold}-S01", 1, "UNAVAILABLE_INSUFFICIENT_MATCHES", tuple(ordered), "", True))
            continue
        if len(ordered) <= MAX_POOL_MATCHES:
            pools.append(Pool(issue, fold, year, f"{issue}-{fold}-S01", 1, "AVAILABLE", tuple(ordered), "ENTIRE_ISSUE", False))
            continue
        cursor = 0
        segment = 1
        while cursor < len(ordered):
            remaining = ordered[cursor:]
            pool_id = f"{issue}-{fold}-S{segment:02d}"
            if len(remaining) < N:
                pools.append(Pool(issue, fold, year, pool_id, segment, "UNAVAILABLE_INSUFFICIENT_MATCHES", tuple(remaining), "", True))
                break
            start = datetime.fromisoformat(remaining[0]["kickoff_ts"])
            chosen: list[dict[str, str]] = []
            chosen_window = ""
            for hours in WINDOW_HOURS:
                end = start + timedelta(hours=hours)
                window = [row for row in remaining if datetime.fromisoformat(row["kickoff_ts"]) <= end]
                if len(window) >= N:
                    chosen = window[:MAX_POOL_MATCHES]
                    chosen_window = str(hours)
                    break
            if not chosen:
                pools.append(Pool(issue, fold, year, pool_id, segment, "UNAVAILABLE_NO_7_MATCH_WINDOW", tuple(remaining), "36", True))
                break
            pools.append(Pool(issue, fold, year, pool_id, segment, "AVAILABLE", tuple(chosen), chosen_window, False))
            cursor += len(chosen)
            segment += 1
    return pools


def descriptor(row: dict[str, str], arm: str, threshold: Decimal, pool_rows: tuple[dict[str, str], ...]) -> str:
    payload = {
        "contract": "BJ-HIST-COLD-PRUNING-001",
        "arm": arm,
        "threshold": str(threshold),
        "pool_id": row["pool_id"],
        "deleted_match_id": row["match_id"],
        "deleted_code": row["deleted_code"],
        "companions": "all_6_subsets_of_pool_excluding_deleted_match",
        "ordered_pool_match_ids": [item["match_id"] for item in pool_rows],
        "tickets_per_n7": PRUNED_TICKETS if arm != "FULL_COVER_CONTROL" else FULL_TICKETS,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def build(
    out: Path,
    p89: Path = P89,
    p91: Path = P91,
    p95: Path = P95,
    p98: Path = P98,
) -> dict[str, int]:
    if out.exists():
        raise RuntimeError(f"refusing to overwrite immutable output: {out}")
    m89 = exact_manifest(p89, BJ89_MANIFEST)
    m91 = exact_manifest(p91, BJ91_MANIFEST)
    exact_manifest(p95, BJ95_MANIFEST)
    exact_manifest(p98, BJ98_MANIFEST)
    with tempfile.TemporaryDirectory(prefix=".bj101_gate_a_", dir=out.parent) as temp_name:
        stage = Path(temp_name)
        private = stage / "_authenticated_inputs"
        private.mkdir()
        p89_path = authenticated_snapshot(private, "bj89_preoutcome_rows.csv", p89 / "frozen_preoutcome_rows.csv", m89["frozen_preoutcome_rows.csv"])
        p91_path = authenticated_snapshot(private, "bj91_calibrated_probabilities.csv.gz", p91 / "outcome_safe_common_inputs.csv.gz", m91["outcome_safe_common_inputs.csv.gz"])
        historical = {key(row): row for row in read_csv(p89_path, P89_FIELDS)}
        probabilities = read_gzip(p91_path, P91_FIELDS)
        if len(historical) != 71857 or len(probabilities) != 47819:
            raise RuntimeError("accepted source cardinality drift")
        eligible: list[dict[str, str]] = []
        for probability in probabilities:
            base = historical.get(key(probability))
            if base is None:
                raise RuntimeError("calibrated row missing frozen preoutcome identity")
            eligible.append({
                "match_id": probability["match_id"], "issue": probability["issue"],
                "match_idx": probability["match_idx"], "kickoff_ts": base["kickoff_ts"],
                "year": probability["year"], "fold": probability["fold"],
                "p3": probability["p3"], "p1": probability["p1"], "p0": probability["p0"],
            })
        pools = make_pools(eligible)
        membership: list[dict[str, object]] = []
        pool_rows: list[dict[str, object]] = []
        frontier: list[dict[str, object]] = []
        summary: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for pool in pools:
            decorated = []
            for row in pool.rows:
                code, p_min = cold_code(row)
                decorated.append((p_min, int(row["match_idx"]), int(row["match_id"]), code, row))
            decorated.sort()
            rank_by_match = {item[4]["match_id"]: index + 1 for index, item in enumerate(decorated)}
            rows_with_pool = []
            for p_min, _idx, _match, code, row in decorated:
                enriched = {**row, "pool_id": pool.pool_id, "deleted_code": code, "p_min": str(p_min), "p_min_rank": str(rank_by_match[row["match_id"]])}
                rows_with_pool.append(enriched)
                membership.append({
                    "issue": pool.issue, "fold": pool.fold, "year": pool.year, "pool_id": pool.pool_id,
                    "segment_index": pool.segment_index, "pool_disposition": pool.disposition,
                    "match_id": row["match_id"], "match_idx": row["match_idx"], "kickoff_ts": row["kickoff_ts"],
                    "p3": row["p3"], "p1": row["p1"], "p0": row["p0"], "deleted_code": code,
                    "p_min": str(p_min), "p_min_rank": rank_by_match[row["match_id"]], "p_min_bucket": probability_bucket(p_min),
                    "eligible_t05": str(p_min <= Decimal("0.05")).upper(), "eligible_t10": str(p_min <= Decimal("0.10")).upper(),
                    "eligible_t15": str(p_min <= Decimal("0.15")).upper(), "eligible_t20": str(p_min <= Decimal("0.20")).upper(),
                })
            pool_rows.append({
                "issue": pool.issue, "fold": pool.fold, "year": pool.year, "pool_id": pool.pool_id,
                "segment_index": pool.segment_index, "pool_disposition": pool.disposition,
                "eligible_match_count": len(pool.rows), "pool_match_count": len(pool.rows),
                "first_kickoff_ts": pool.rows[0]["kickoff_ts"], "last_kickoff_ts": pool.rows[-1]["kickoff_ts"],
                "window_hours": pool.window_hours, "terminal_remainder": str(pool.terminal_remainder).upper(),
            })
            if pool.disposition != "AVAILABLE":
                continue
            combinations = math.comb(len(pool.rows) - 1, 6)
            for row in rows_with_pool:
                p_min = Decimal(row["p_min"])
                for threshold in THRESHOLDS:
                    if p_min > threshold:
                        continue
                    for arm, deleted in (
                        ("COLD_PMIN", row["deleted_code"]),
                        ("HASH_DELETION_CONTROL", hash_code(row, threshold)),
                        ("FULL_COVER_CONTROL", ""),
                    ):
                        ticket_count = PRUNED_TICKETS if arm != "FULL_COVER_CONTROL" else FULL_TICKETS
                        output_row = {**row, "deleted_code": deleted}
                        frontier.append({
                            "issue": pool.issue, "fold": pool.fold, "year": pool.year, "pool_id": pool.pool_id,
                            "segment_index": pool.segment_index, "pool_match_count": len(pool.rows),
                            "match_id": row["match_id"], "match_idx": row["match_idx"], "kickoff_ts": row["kickoff_ts"],
                            "threshold": threshold_label(threshold), "arm": arm, "deleted_code": deleted,
                            "p_min": row["p_min"], "p_min_rank": row["p_min_rank"],
                            "n7_combination_count": combinations, "tickets_per_n7": ticket_count,
                            "total_tickets": combinations * ticket_count, "stake_yuan": money(2 * combinations * ticket_count),
                            "portfolio_descriptor_sha256": descriptor(output_row, arm, threshold, pool.rows),
                        })
                        bucket = summary[(threshold_label(threshold), arm)]
                        bucket["eligible_deleted_matches"] += 1
                        bucket["n7_combination_count"] += combinations
                        bucket["total_tickets"] += combinations * ticket_count
                        bucket["stake_yuan"] += 2 * combinations * ticket_count
        if len(membership) != len(eligible):
            raise RuntimeError("membership denominator drift")
        write_csv(stage / "issue_pool_membership.csv", MEMBERSHIP_FIELDS, membership)
        write_csv(stage / "issue_pool_census.csv", POOL_FIELDS, pool_rows)
        write_csv(stage / "n7_cold_pruning_frontier.csv", FRONTIER_FIELDS, frontier)
        write_csv(stage / "frontier_summary.csv", SUMMARY_FIELDS, [
            {"threshold": threshold, "arm": arm, **values}
            for (threshold, arm), values in sorted(summary.items())
        ])
        snapshots = {p89_path.name: sha256(p89_path), p91_path.name: sha256(p91_path)}
        write_csv(stage / "source_census.csv", SOURCE_CENSUS_FIELDS, [
            {
                "source": "bj89_gate_a_preoutcome_v3", "role": "frozen_identity_and_kickoff",
                "manifest_sha256": BJ89_MANIFEST, "payload": "frozen_preoutcome_rows.csv",
                "payload_sha256": m89["frozen_preoutcome_rows.csv"], "row_count": len(historical),
                "used_at_gate_a": "TRUE", "join_status": "47819 calibrated identities matched; 24038 source rows outside #91 calibrated projection",
            },
            {
                "source": "bj91_gate_a_preoutcome_v1r6", "role": "calibrated_probability_projection",
                "manifest_sha256": BJ91_MANIFEST, "payload": "outcome_safe_common_inputs.csv.gz",
                "payload_sha256": m91["outcome_safe_common_inputs.csv.gz"], "row_count": len(probabilities),
                "used_at_gate_a": "TRUE", "join_status": "47819 of 47819 rows matched #89 frozen identity",
            },
            {
                "source": "bj95_gate_a_preoutcome_v5", "role": "deferred_matched_control_reference",
                "manifest_sha256": BJ95_MANIFEST, "payload": "SHA256SUMS.json",
                "payload_sha256": BJ95_MANIFEST, "row_count": "", "used_at_gate_a": "FALSE",
                "join_status": "manifest authenticated only; no payload parsed in Gate A",
            },
            {
                "source": "bj98_gate_a_preoutcome_v1", "role": "deferred_matched_control_reference",
                "manifest_sha256": BJ98_MANIFEST, "payload": "SHA256SUMS.json",
                "payload_sha256": BJ98_MANIFEST, "row_count": "", "used_at_gate_a": "FALSE",
                "join_status": "manifest authenticated only; no payload parsed in Gate A",
            },
        ])
        shutil.rmtree(private)
        card = {
            "issue": 101,
            "stage": "GATE_A_OUTCOME_UNEXPOSED_COLD_PRUNING_FREEZE",
            "input_manifests": {"bj89": BJ89_MANIFEST, "bj91": BJ91_MANIFEST, "bj95_deferred_control": BJ95_MANIFEST, "bj98_deferred_control": BJ98_MANIFEST},
            "private_snapshot_sha256": snapshots,
            "private_snapshot_protocol": "authenticate accepted bundle, copy every parsed payload, verify copied bytes, then read only private copies",
            "source_denominators": {"bj89_identity_rows": len(historical), "bj91_calibrated_rows": len(probabilities), "joined_eligible_rows": len(eligible)},
            "probability_source": "#91 outcome_safe_common_inputs.csv.gz calibrated p3/p1/p0 joined only to #89 frozen kickoff identity fields",
            "outcome_boundary": "no result, score, final SP, payout, ROI, or settlement input is read or emitted",
            "segmentation": "issue/fold only; sort kickoff_ts, match_idx, match_id; 7-24 whole issue; >24 use 12/18/24/36h rolling windows capped at first 24; terminal <7 and terminal no-7-within-36h remainders remain explicitly unavailable",
            "thresholds": [str(value) for value in THRESHOLDS],
            "tie_break": "deleted code argmin p3,p1,p0 with code order 3,1,0; rank then match_idx",
            "arms": ["COLD_PMIN", "HASH_DELETION_CONTROL", "FULL_COVER_CONTROL"],
            "n7_accounting": {"pruned_tickets_per_n7": PRUNED_TICKETS, "pruned_stake_per_n7_yuan": 2 * PRUNED_TICKETS, "full_tickets_per_n7": FULL_TICKETS, "full_stake_per_n7_yuan": 2 * FULL_TICKETS, "companion_rule": "all six-match combinations in the same pool excluding deleted match"},
            "gate_b": "UNAUTHORIZED: canonical outcome/final-SP join only after PI accepts this exact Gate-A freeze",
            "scope": "historical research only; no purchase or production promotion",
        }
        (stage / "gate_a_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        shutil.copy2(Path(__file__), stage / "freeze_runner.py")
        manifest = {item.name: sha256(item) for item in sorted(stage.iterdir()) if item.is_file()}
        (stage / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        shutil.copytree(stage, out)
    return {"eligible_matches": len(eligible), "pools": len(pools), "frontier_rows": len(frontier)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--bj89", type=Path, default=P89)
    parser.add_argument("--bj91", type=Path, default=P91)
    parser.add_argument("--bj95", type=Path, default=P95)
    parser.add_argument("--bj98", type=Path, default=P98)
    args = parser.parse_args()
    print(json.dumps(build(args.output.resolve(), args.bj89.resolve(), args.bj91.resolve(), args.bj95.resolve(), args.bj98.resolve()), sort_keys=True))


if __name__ == "__main__":
    main()
