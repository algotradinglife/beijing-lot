#!/usr/bin/env python3
"""Freeze the outcome-unexposed probability/SP value atlas for Issue #106."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import shutil
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

CODES = ("3", "1", "0")
CONTRACT = "BJ-HIST-Q-ATLAS-001"
VERSION = "bj106-q-atlas-v2r1"
MIN_SUPPORT = 500
TICKET_FACTOR = 0.65
CONTENT_IDENTITY_VERSION = "bj106-portable-content-v1"
CANONICAL_Q_ATLAS_ARTIFACT_SHA256 = (
    "b710dd4fe792e69727b898a615e1cb4899175e329c71bcee46788fb859c43b26"
)
CANONICAL_Q_ATLAS_CONTENT_SHA256 = (
    "ba3c3e1a846466a95376117b0d9ac44650bc1de9cb894ded3d84f0609efa4dbe"
)
CANONICAL_Q_ATLAS_CONTENT_BYTES = 44_208_242
GM_REFERENCE_THRESHOLDS = {
    n_legs: (1.0 / TICKET_FACTOR) ** (1.0 / n_legs) for n_legs in range(4, 10)
}
# This retained descriptive band boundary is not an eligibility threshold. The
# factor is evaluated only after a complete N-leg ticket has been assembled.
Q_HIGH_BAND_BOUNDARY = 1.0 / TICKET_FACTOR
BJ89_MANIFEST = "b22c33bddc71972e3c2a5e7b95955087ece2441b5728da6424d19b3de6f503e2"
BJ90_MANIFEST = "4a1107ca64d169bf0171a394d1e450a14ee5386005fce34f6ca7ebb70bd720b2"
BJ91_MANIFEST = "bd7159715cca84e9d2adb9e089d016ec4e4d72603f8f8d5a8b070eb5027c2c33"

P89_FIELDS = (
    "match_id",
    "issue",
    "match_idx",
    "kickoff_ts",
    "year",
    "fold",
    "handicap_line_norm",
    "n_complete_10h",
    "euro_3_10h",
    "euro_1_10h",
    "euro_0_10h",
    "p3_raw",
    "p1_raw",
    "p0_raw",
    "top1_code_raw",
    "top1_mass_raw",
    "top2_mass_raw",
    "entropy_raw",
    "dispersion_mean_relative_range",
    "initial_status",
    "p3_initial",
    "p1_initial",
    "p0_initial",
    "initial_to_10h_log_probability_movement",
)
P91_FIELDS = (
    "match_id",
    "issue",
    "match_idx",
    "year",
    "fold",
    "p3",
    "p1",
    "p0",
    "point_sp_3",
    "point_sp_1",
    "point_sp_0",
    "m2_sp_3",
    "m2_sp_1",
    "m2_sp_0",
    "point_sp5_3",
    "point_sp5_1",
    "point_sp5_0",
    "m2_sp5_3",
    "m2_sp5_1",
    "m2_sp5_0",
)
P90_FIELDS = (
    "match_id",
    "issue",
    "match_idx",
    "year",
    "fold",
    "deployed_method",
    "deployed_sp_3",
    "deployed_sp_1",
    "deployed_sp_0",
    "m2_conservative_sp_3",
    "m2_conservative_sp_1",
    "m2_conservative_sp_0",
)
ATLAS_FIELDS = (
    "match_id",
    "issue",
    "match_idx",
    "kickoff_ts",
    "year",
    "fold",
    "candidate_code",
    "p_cal",
    "predicted_sp",
    "conservative_sp",
    "q_hat",
    "q_lb",
    "entropy",
    "dispersion_mean_relative_range",
    "initial_to_10h_log_probability_movement",
    "handicap_line_norm",
    "handicap_sign",
    "league_stratum",
    "probability_band",
    "predicted_sp_band",
    "conservative_sp_band",
    "q_hat_band",
    "q_lb_band",
    "stratum_id",
    "fallback_level",
    "stratum_support",
    "stratum_issue_count",
    "stratum_year_count",
    "nomination_eligible",
)
CENSUS_FIELDS = (
    "stratum_id",
    "fallback_level",
    "candidate_code",
    "probability_band",
    "q_lb_band",
    "handicap_component",
    "rows",
    "issues",
    "years",
    "nomination_eligible",
)
SOURCE_FIELDS = (
    "source",
    "role",
    "manifest_sha256",
    "payload",
    "payload_sha256",
    "rows",
    "join_status",
)


def root(anchor: Path) -> Path:
    for item in (anchor.resolve().parent, *anchor.resolve().parents):
        if (item / ".git").exists():
            return item
    raise RuntimeError("repository root not found")


ROOT = root(Path(__file__))
P89 = ROOT / "results" / "bj89_gate_a_preoutcome_v3"
P90 = ROOT / "results" / "bj90_downstream_safe_projection_v1r1"
P91 = ROOT / "results" / "bj91_gate_a_preoutcome_v1r6"
OUT = ROOT / "results" / "bj106_gate_a_preoutcome_v2r1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def decompressed_identity(path: Path) -> tuple[str, int]:
    """Return the canonical decompressed SHA-256 and byte length of a gzip file."""
    digest = hashlib.sha256()
    size = 0
    with gzip.open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def verified_bundle_manifest(path: Path) -> dict[str, str]:
    """Verify a bundle's own exact byte manifest and return its entries."""
    manifest_path = path / "SHA256SUMS.json"
    declared = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = {
        item.name: sha256(item)
        for item in path.iterdir()
        if item.is_file() and item.name != manifest_path.name
    }
    if not isinstance(declared, dict) or actual != declared:
        raise RuntimeError(f"manifest coverage drift: {path}")
    return declared


def verify_portable_replay(replay: Path, committed: Path) -> dict[str, object]:
    """Verify replay identity without conflating gzip wrappers with CSV content."""
    replay_manifest = verified_bundle_manifest(replay)
    committed_manifest = verified_bundle_manifest(committed)
    identity_name = "CONTENT_IDENTITY.json"
    replay_identity_path = replay / identity_name
    committed_identity_path = committed / identity_name
    if replay_identity_path.read_bytes() != committed_identity_path.read_bytes():
        raise RuntimeError("portable content-identity metadata drift")
    identity = json.loads(committed_identity_path.read_text(encoding="utf-8"))
    if identity.get("contract_version") != CONTENT_IDENTITY_VERSION:
        raise RuntimeError("unsupported portable content-identity contract")
    gzip_payloads = identity.get("gzip_payloads")
    controls = identity.get("non_compressed_controls")
    if not isinstance(gzip_payloads, dict) or not isinstance(controls, dict):
        raise RuntimeError("invalid portable content-identity metadata")
    expected_files = {
        *gzip_payloads,
        *controls,
        identity_name,
    }
    if set(committed_manifest) != expected_files or set(replay_manifest) != expected_files:
        raise RuntimeError("portable bundle file-set drift")
    for name, metadata in gzip_payloads.items():
        if not isinstance(metadata, dict) or metadata.get("container_type") != "gzip":
            raise RuntimeError(f"invalid gzip identity metadata: {name}")
        committed_artifact = metadata.get("committed_artifact_sha256")
        canonical_hash = metadata.get("canonical_decompressed_sha256")
        canonical_bytes = metadata.get("canonical_decompressed_bytes")
        if committed_manifest.get(name) != committed_artifact:
            raise RuntimeError(f"committed gzip artifact drift: {name}")
        committed_content = decompressed_identity(committed / name)
        replay_content = decompressed_identity(replay / name)
        expected_content = (canonical_hash, canonical_bytes)
        if committed_content != expected_content or replay_content != expected_content:
            raise RuntimeError(f"canonical decompressed content drift: {name}")
    for name, expected_hash in controls.items():
        if not isinstance(expected_hash, str):
            raise RuntimeError(f"invalid non-compressed control metadata: {name}")
        if (
            committed_manifest.get(name) != expected_hash
            or replay_manifest.get(name) != expected_hash
            or (committed / name).read_bytes() != (replay / name).read_bytes()
        ):
            raise RuntimeError(f"non-compressed control drift: {name}")
    return {
        "status": "PASS",
        "gzip_wrapper_byte_identical": all(
            replay_manifest[name] == committed_manifest[name] for name in gzip_payloads
        ),
        "gzip_payloads": len(gzip_payloads),
        "non_compressed_controls": len(controls),
    }


def exact_bundle(path: Path, expected: str) -> dict[str, str]:
    manifest_path = path / "SHA256SUMS.json"
    if sha256(manifest_path) != expected:
        raise RuntimeError(f"unaccepted manifest: {path}")
    declared = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = {
        item.name: sha256(item)
        for item in path.iterdir()
        if item.is_file() and item.name != manifest_path.name
    }
    if not isinstance(declared, dict) or actual != declared:
        raise RuntimeError(f"manifest coverage drift: {path}")
    return declared


def copied(stage: Path, source: Path, digest: str, name: str) -> Path:
    target = stage / name
    shutil.copyfile(source, target)
    if sha256(target) != digest:
        raise RuntimeError(f"authenticated copy drift: {source}")
    return target


def identity(row: dict[str, str]) -> tuple[str, str, str, str, str]:
    return row["match_id"], row["issue"], row["match_idx"], row["year"], row["fold"]


def check_schema(reader: csv.DictReader, expected: tuple[str, ...], label: str) -> None:
    if tuple(reader.fieldnames or ()) != expected:
        raise RuntimeError(f"schema mismatch {label}: {reader.fieldnames}")


def positive(raw: str, label: str) -> float:
    try:
        value = float(raw)
    except ValueError as error:
        raise RuntimeError(f"invalid {label}: {raw!r}") from error
    if not math.isfinite(value) or value <= 0:
        raise RuntimeError(f"non-positive {label}: {raw!r}")
    return value


def finite(raw: str, label: str) -> float:
    try:
        value = float(raw)
    except ValueError as error:
        raise RuntimeError(f"invalid {label}: {raw!r}") from error
    if not math.isfinite(value):
        raise RuntimeError(f"non-finite {label}: {raw!r}")
    return value


def fmt(value: float) -> str:
    return format(value, ".12f")


def band(value: float, boundaries: tuple[float, ...], labels: tuple[str, ...]) -> str:
    for boundary, label in zip(boundaries, labels):
        if value < boundary:
            return label
    return labels[-1]


def probability_band(value: float) -> str:
    return band(
        value,
        (0.10, 0.20, 0.35, 0.50, 0.70, math.inf),
        ("P00_10", "P10_20", "P20_35", "P35_50", "P50_70", "P70_100"),
    )


def sp_band(value: float) -> str:
    return band(
        value,
        (2.0, 3.0, 5.0, 10.0, math.inf),
        ("SP1_2", "SP2_3", "SP3_5", "SP5_10", "SP10_INF"),
    )


def q_band(value: float) -> str:
    return band(
        value,
        (0.65, 0.90, 1.10, 1.35, Q_HIGH_BAND_BOUNDARY, 2.0, math.inf),
        (
            "Q00_065",
            "Q065_090",
            "Q090_110",
            "Q110_135",
            "Q135_1538",
            "Q1538_200",
            "Q200_INF",
        ),
    )


def comparison_eligible(support: int, years: int, fallback_level: str) -> bool:
    """Return Gate-B comparison-family eligibility without a per-leg q gate."""
    return support >= MIN_SUPPORT and years >= 3 and fallback_level != "L5_CODE_ONLY"


def complete_ticket_gross(leg_contributions: tuple[float, ...]) -> float:
    """Apply the 0.65 factor once after all N4-N9 leg contributions exist."""
    if len(leg_contributions) not in GM_REFERENCE_THRESHOLDS:
        raise ValueError("complete-ticket accounting is frozen for N4-N9")
    if any(not math.isfinite(value) or value < 0 for value in leg_contributions):
        raise ValueError("leg contributions must be finite and non-negative")
    return TICKET_FACTOR * math.prod(leg_contributions)


def handicap_sign(raw: str) -> str:
    value = finite(raw, "handicap")
    return "HNEG" if value < 0 else ("HPOS" if value > 0 else "HZERO")


def stratum_candidates(row: dict[str, object]) -> tuple[tuple[str, str], ...]:
    core = f"CODE={row['candidate_code']}|P={row['probability_band']}|QLB={row['q_lb_band']}"
    return (
        (f"{core}|H={row['handicap_line_norm']}", "L1_EXACT_HANDICAP"),
        (f"{core}|HS={row['handicap_sign']}", "L2_HANDICAP_SIGN"),
        (core, "L3_CODE_P_QLB"),
        (f"CODE={row['candidate_code']}|QLB={row['q_lb_band']}", "L4_CODE_QLB"),
        (f"CODE={row['candidate_code']}", "L5_CODE_ONLY"),
    )


def write_csv(
    path: Path, fields: tuple[str, ...], rows: list[dict[str, object]]
) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def build(
    out: Path, p89: Path = P89, p90: Path = P90, p91: Path = P91
) -> dict[str, int]:
    if out.exists():
        raise RuntimeError(f"refusing immutable overwrite: {out}")
    m89, m90, m91 = (
        exact_bundle(p89, BJ89_MANIFEST),
        exact_bundle(p90, BJ90_MANIFEST),
        exact_bundle(p91, BJ91_MANIFEST),
    )
    with tempfile.TemporaryDirectory(prefix=".bj106_gate_a_", dir=out.parent) as temp:
        stage = Path(temp)
        private = stage / "_authenticated_inputs"
        private.mkdir()
        a89 = copied(
            private,
            p89 / "frozen_preoutcome_rows.csv",
            m89["frozen_preoutcome_rows.csv"],
            "bj89.csv",
        )
        a90 = copied(
            private,
            p90 / "oos_prediction_vectors.csv.gz",
            m90["oos_prediction_vectors.csv.gz"],
            "bj90.csv.gz",
        )
        a91 = copied(
            private,
            p91 / "outcome_safe_common_inputs.csv.gz",
            m91["outcome_safe_common_inputs.csv.gz"],
            "bj91.csv.gz",
        )
        with a89.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            check_schema(reader, P89_FIELDS, "#89")
            f89 = {identity(row): row for row in reader}
        f90: dict[tuple[str, str, str, str, str], dict[str, str]] = {}
        with gzip.open(a90, "rt", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            check_schema(reader, P90_FIELDS, "#90")
            for row in reader:
                key = identity(row)
                if key in f90:
                    raise RuntimeError(f"duplicate #90 identity {key}")
                f90[key] = row
        with gzip.open(a91, "rt", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            check_schema(reader, P91_FIELDS, "#91")
            probabilities = list(reader)
        base_rows: list[dict[str, object]] = []
        for p_row in probabilities:
            key = identity(p_row)
            history, prices = f89.get(key), f90.get(key)
            if history is None or prices is None:
                raise RuntimeError(f"safe input join failure {key}")
            p = {
                code: positive(p_row[f"p{code}"], f"probability {key} {code}")
                for code in CODES
            }
            if abs(sum(p.values()) - 1) > 1e-6:
                raise RuntimeError(f"probability mass drift {key}")
            entropy = -sum(value * math.log(value) for value in p.values())
            for code in CODES:
                point = positive(
                    prices[f"deployed_sp_{code}"], f"predicted SP {key} {code}"
                )
                conservative = positive(
                    prices[f"m2_conservative_sp_{code}"],
                    f"conservative SP {key} {code}",
                )
                if (
                    abs(
                        point - positive(p_row[f"point_sp_{code}"], "#91 point carrier")
                    )
                    > 1e-9
                    or abs(
                        conservative
                        - positive(p_row[f"m2_sp_{code}"], "#91 conservative carrier")
                    )
                    > 1e-9
                ):
                    raise RuntimeError(f"#90/#91 SP carrier mismatch {key} {code}")
                row: dict[str, object] = {
                    "match_id": p_row["match_id"],
                    "issue": p_row["issue"],
                    "match_idx": p_row["match_idx"],
                    "kickoff_ts": history["kickoff_ts"],
                    "year": p_row["year"],
                    "fold": p_row["fold"],
                    "candidate_code": code,
                    "p_cal": p[code],
                    "predicted_sp": point,
                    "conservative_sp": conservative,
                    "q_hat": p[code] * point,
                    "q_lb": p[code] * conservative,
                    "entropy": entropy,
                    "dispersion_mean_relative_range": finite(
                        history["dispersion_mean_relative_range"], "dispersion"
                    ),
                    "initial_to_10h_log_probability_movement": finite(
                        history["initial_to_10h_log_probability_movement"], "movement"
                    ),
                    "handicap_line_norm": history["handicap_line_norm"],
                    "handicap_sign": handicap_sign(history["handicap_line_norm"]),
                    "league_stratum": "UNAVAILABLE_SOURCE",
                    "probability_band": probability_band(p[code]),
                    "predicted_sp_band": sp_band(point),
                    "conservative_sp_band": sp_band(conservative),
                    "q_hat_band": q_band(p[code] * point),
                    "q_lb_band": q_band(p[code] * conservative),
                }
                base_rows.append(row)
        assignments: dict[int, tuple[str, str]] = {}
        remaining = set(range(len(base_rows)))
        for level_index in range(4):
            level_counts = Counter(
                stratum_candidates(base_rows[index])[level_index][0]
                for index in remaining
            )
            accepted = {
                candidate
                for candidate, count in level_counts.items()
                if count >= MIN_SUPPORT
            }
            selected = {
                index
                for index in remaining
                if stratum_candidates(base_rows[index])[level_index][0] in accepted
            }
            for index in selected:
                assignments[index] = stratum_candidates(base_rows[index])[level_index]
            remaining.difference_update(selected)
        for index in remaining:
            assignments[index] = stratum_candidates(base_rows[index])[-1]
        selected_counts = Counter(
            candidate for candidate, _level in assignments.values()
        )
        selected_issues: dict[str, set[str]] = defaultdict(set)
        selected_years: dict[str, set[str]] = defaultdict(set)
        for index, (candidate, _level) in assignments.items():
            selected_issues[candidate].add(str(base_rows[index]["issue"]))
            selected_years[candidate].add(str(base_rows[index]["year"]))
        census: dict[str, dict[str, object]] = {}
        atlas_path = stage / "q_atlas.csv.gz"
        with (
            atlas_path.open("wb") as raw,
            gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed,
            io.TextIOWrapper(compressed, encoding="utf-8", newline="") as text,
        ):
            writer = csv.DictWriter(text, fieldnames=ATLAS_FIELDS, lineterminator="\n")
            writer.writeheader()
            for index, row in enumerate(base_rows):
                stratum_id, level = assignments[index]
                support = selected_counts[stratum_id]
                issues = len(selected_issues[stratum_id])
                years = len(selected_years[stratum_id])
                eligible = comparison_eligible(support, years, level)
                output = {
                    **row,
                    "p_cal": fmt(row["p_cal"]),
                    "predicted_sp": fmt(row["predicted_sp"]),
                    "conservative_sp": fmt(row["conservative_sp"]),
                    "q_hat": fmt(row["q_hat"]),
                    "q_lb": fmt(row["q_lb"]),
                    "entropy": fmt(row["entropy"]),
                    "dispersion_mean_relative_range": fmt(
                        row["dispersion_mean_relative_range"]
                    ),
                    "initial_to_10h_log_probability_movement": fmt(
                        row["initial_to_10h_log_probability_movement"]
                    ),
                    "stratum_id": stratum_id,
                    "fallback_level": level,
                    "stratum_support": support,
                    "stratum_issue_count": issues,
                    "stratum_year_count": years,
                    "nomination_eligible": str(eligible).upper(),
                }
                writer.writerow(output)
                if stratum_id not in census:
                    parts = dict(part.split("=", 1) for part in stratum_id.split("|"))
                    census[stratum_id] = {
                        "stratum_id": stratum_id,
                        "fallback_level": level,
                        "candidate_code": row["candidate_code"],
                        "probability_band": parts.get("P", "ALL"),
                        "q_lb_band": parts.get("QLB", "ALL"),
                        "handicap_component": parts.get("H", parts.get("HS", "ALL")),
                        "rows": support,
                        "issues": issues,
                        "years": years,
                        "nomination_eligible": str(eligible).upper(),
                    }
        write_csv(
            stage / "stratum_census.csv",
            CENSUS_FIELDS,
            [census[key] for key in sorted(census)],
        )
        write_csv(
            stage / "source_census.csv",
            SOURCE_FIELDS,
            [
                {
                    "source": "bj89_gate_a_preoutcome_v3",
                    "role": "kickoff and pre-outcome market-quality features",
                    "manifest_sha256": BJ89_MANIFEST,
                    "payload": "frozen_preoutcome_rows.csv",
                    "payload_sha256": m89["frozen_preoutcome_rows.csv"],
                    "rows": len(f89),
                    "join_status": "all atlas matches joined; no outcome payload opened",
                },
                {
                    "source": "bj90_downstream_safe_projection_v1r1",
                    "role": "outcome-safe point and conservative final-SP predictions",
                    "manifest_sha256": BJ90_MANIFEST,
                    "payload": "oos_prediction_vectors.csv.gz",
                    "payload_sha256": m90["oos_prediction_vectors.csv.gz"],
                    "rows": len(f90),
                    "join_status": "all atlas matches joined",
                },
                {
                    "source": "bj91_gate_a_preoutcome_v1r6",
                    "role": "accepted outcome-safe carrier of #89 deployed calibrated probabilities",
                    "manifest_sha256": BJ91_MANIFEST,
                    "payload": "outcome_safe_common_inputs.csv.gz",
                    "payload_sha256": m91["outcome_safe_common_inputs.csv.gz"],
                    "rows": len(probabilities),
                    "join_status": "47819 probabilities joined; point/conservative SP equality rechecked against #90",
                },
            ],
        )
        card = {
            "issue": 106,
            "contract": CONTRACT,
            "version": VERSION,
            "stage": "GATE_A_OUTCOME_UNEXPOSED_Q_ATLAS",
            "input_manifests": {
                "bj89": BJ89_MANIFEST,
                "bj90": BJ90_MANIFEST,
                "bj91_outcome_safe_probability_carrier": BJ91_MANIFEST,
            },
            "rows": {
                "matches": len(probabilities),
                "match_outcomes": len(base_rows),
                "selected_strata": len(census),
            },
            "compression_contract": {
                "portable_identity": "CONTENT_IDENTITY.json",
                "container_type": "gzip",
                "gzip_payload": "q_atlas.csv.gz",
                "committed_artifact_sha256": CANONICAL_Q_ATLAS_ARTIFACT_SHA256,
                "canonical_decompressed_sha256": CANONICAL_Q_ATLAS_CONTENT_SHA256,
                "canonical_decompressed_bytes": CANONICAL_Q_ATLAS_CONTENT_BYTES,
                "verification": "The committed gzip delivery remains byte-bound by SHA256SUMS.json. Cross-runtime replay compares canonical decompressed CSV identity and exact bytes for every non-compressed control; gzip wrapper-byte variation alone is not content drift.",
            },
            "definitions": {
                "q_hat_pre_factor_leg_contribution": "p_cal * predicted_sp",
                "q_lb_pre_factor_leg_contribution": "p_cal * conservative_sp",
                "realized_leg_contribution_pre_factor": "indicator(actual_result_code == candidate_code) * final_winning_sp(candidate_code)",
                "complete_ticket_expected_gross_per_unit": "0.65 * product(q_i)",
                "complete_ticket_realized_gross_per_unit": "0.65 * product(realized_leg_contribution_pre_factor_i)",
                "factor_application": "apply 0.65 exactly once after assembling the complete N-leg ticket; never deduct or gate at row/stratum level",
            },
            "gm_break_even_reference": {
                f"N{n_legs}": fmt(threshold)
                for n_legs, threshold in GM_REFERENCE_THRESHOLDS.items()
            },
            "bands": {
                "probability": ["0,.10,.20,.35,.50,.70,1"],
                "sp": ["1,2,3,5,10,inf"],
                "q": ["0,.65,.90,1.10,1.35,1.538461538462,2,inf"],
            },
            "sparse_fallback": {
                "minimum_rows": MIN_SUPPORT,
                "order": [
                    "code+p_band+q_lb_band+exact_handicap",
                    "code+p_band+q_lb_band+handicap_sign",
                    "code+p_band+q_lb_band",
                    "code+q_lb_band",
                    "code_only",
                ],
            },
            "league_boundary": "league unavailable in accepted safe inputs; emitted explicitly as UNAVAILABLE_SOURCE and never inferred",
            "handicap_boundary": "accepted #89 source is degenerate at handicap_line_norm=0.0; the exact/support fallback remains frozen and no nonzero handicap is inferred",
            "shrinkage": "Gate B occurrence posterior mean and interval use Jeffreys Beta(0.5,0.5); realized pre-factor leg contribution remains unshrunk and cells below frozen support remain explicit unavailable",
            "comparison_family": "Every selected stratum with support>=500, >=3 years and non-code-only fallback enters Gate B. No row or stratum is excluded by q_hat, q_lb or any per-leg factor threshold.",
            "multiple_comparison": "Gate B Benjamini-Hochberg FDR 0.10 over the complete comparison-eligible selected-stratum family; no alternate family",
            "uncertainty": "Gate B exact Jeffreys Beta(0.5,0.5) occurrence interval plus 10000 issue-cluster bootstrap replicates, seed 10620260801",
            "nomination": "At most two strata from the frozen comparison family, only BH q<=0.10, positive lower 95% issue-cluster bounds for calibration alignment and realized pre-factor leg contribution under point and conservative views, stable direction in every chronological fold and leave-one-year-out, and positive after ex-best-payout and ex-best-issue removal. No individual row or stratum must exceed 1/0.65; downstream economics require exact complete-ticket product-q, factor-once and tax-adjusted evaluation.",
            "outcome_boundary": "candidate_code is the prospective 3/1/0 code, not an observed result. No actual result, score, winning SP, payout, tax, ROI, or settlement input is read or emitted.",
            "gate_b": "UNAUTHORIZED pending independent EV and PI acceptance of this exact package.",
            "scope": "historical paper-only research; no purchase, production, frontend, or portfolio promotion.",
        }
        (stage / "gate_a_card.json").write_text(
            json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        shutil.copy2(Path(__file__), stage / "freeze_runner.py")
        content_hash, content_bytes = decompressed_identity(atlas_path)
        if (
            content_hash != CANONICAL_Q_ATLAS_CONTENT_SHA256
            or content_bytes != CANONICAL_Q_ATLAS_CONTENT_BYTES
        ):
            raise RuntimeError("canonical q_atlas.csv content drift")
        control_names = (
            "freeze_runner.py",
            "gate_a_card.json",
            "source_census.csv",
            "stratum_census.csv",
        )
        content_identity = {
            "contract_version": CONTENT_IDENTITY_VERSION,
            "gzip_payloads": {
                "q_atlas.csv.gz": {
                    "container_type": "gzip",
                    "committed_artifact_sha256": CANONICAL_Q_ATLAS_ARTIFACT_SHA256,
                    "canonical_decompressed_sha256": content_hash,
                    "canonical_decompressed_bytes": content_bytes,
                }
            },
            "non_compressed_controls": {
                name: sha256(stage / name) for name in control_names
            },
        }
        (stage / "CONTENT_IDENTITY.json").write_text(
            json.dumps(content_identity, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        manifest = {
            item.name: sha256(item)
            for item in sorted(stage.iterdir())
            if item.is_file()
        }
        (stage / "SHA256SUMS.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        shutil.rmtree(private)
        shutil.copytree(stage, out)
    return {
        "matches": len(probabilities),
        "atlas_rows": len(base_rows),
        "strata": len(census),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUT)
    parser.add_argument("--bj89", type=Path, default=P89)
    parser.add_argument("--bj90", type=Path, default=P90)
    parser.add_argument("--bj91", type=Path, default=P91)
    parser.add_argument(
        "--verify-against",
        type=Path,
        help="after replay, verify portable identity against a committed bundle",
    )
    args = parser.parse_args()
    result: dict[str, object] = build(
        args.output.resolve(),
        args.bj89.resolve(),
        args.bj90.resolve(),
        args.bj91.resolve(),
    )
    if args.verify_against:
        result["portable_replay"] = verify_portable_replay(
            args.output.resolve(), args.verify_against.resolve()
        )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
