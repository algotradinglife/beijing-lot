#!/usr/bin/env python3
"""Create the one-purpose, outcome-free EURO input consumed by #95 Gate A.

This capture is deliberately narrow: it carries only the EURO 10h odds and
identity/line fields needed by the frozen #91 primary N7 legs.  Gate A itself
never opens the larger historical #89 artifact after this input is committed.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import platform
import shutil
import tempfile
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
P91 = ROOT / "results" / "bj91_gate_a_preoutcome_v1r6"
P91_LEGS_SHA = "cd0fdfd42002bbeddc6a1676323ead65c4cb85915f2c1a83b916d6c2004526fc"
P91_MANIFEST_SHA = "bd7159715cca84e9d2adb9e089d016ec4e4d72603f8f8d5a8b070eb5027c2c33"
P89_ROWS_SHA = "787bf3266403bebdcf3dfa4ae09f3dbc862a6542c04554fc1e37a0ba02296ae8"
P89_MANIFEST_SHA = "b22c33bddc71972e3c2a5e7b95955087ece2441b5728da6424d19b3de6f503e2"
FIELDS = ("match_id", "issue", "match_idx", "fold", "handicap_line_norm", "euro_3_10h", "euro_1_10h", "euro_0_10h")
P91_SOURCE_FIELDS = (
    "cohort", "n", "group_id", "source_group_id", "position", "match_id", "issue", "match_idx", "year", "fold",
    "p3", "p1", "p0", "point_sp_3", "point_sp_1", "point_sp_0", "m2_sp_3", "m2_sp_1", "m2_sp_0",
    "point_sp5_3", "point_sp5_1", "point_sp5_0", "m2_sp5_3", "m2_sp5_1", "m2_sp5_0",
)
P89_SOURCE_FIELDS = (
    "match_id", "issue", "match_idx", "kickoff_ts", "year", "fold", "handicap_line_norm", "n_complete_10h",
    "euro_3_10h", "euro_1_10h", "euro_0_10h", "p3_raw", "p1_raw", "p0_raw", "top1_code_raw", "top1_mass_raw",
    "top2_mass_raw", "entropy_raw", "dispersion_mean_relative_range", "initial_status", "p3_initial", "p1_initial",
    "p0_initial", "initial_to_10h_log_probability_movement",
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def manifest_sha(bundle: Path, accepted_sha256: str) -> str:
    manifest = bundle / "SHA256SUMS.json"
    if sha256(manifest) != accepted_sha256:
        raise RuntimeError(f"unaccepted manifest: {bundle}")
    expected = json.loads(manifest.read_text())
    actual = {p.name: sha256(p) for p in bundle.iterdir() if p.is_file() and p.name != manifest.name}
    if actual != expected:
        raise RuntimeError(f"manifest mismatch: {bundle}")
    return accepted_sha256


def assert_exact_schema(fieldnames: list[str] | None, expected: tuple[str, ...], label: str) -> None:
    if tuple(fieldnames or ()) != expected:
        raise RuntimeError(f"safe schema mismatch for {label}: {tuple(fieldnames or ())}")


def content_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with gzip.open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_gzip(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("wb") as binary:
        with gzip.GzipFile(fileobj=binary, mode="wb", mtime=0) as zipped:
            with io.TextIOWrapper(zipped, encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)


def build(source: Path, out: Path) -> None:
    if out.exists():
        raise RuntimeError(f"refusing to overwrite immutable output: {out}")
    p91_manifest, p89_manifest = manifest_sha(P91, P91_MANIFEST_SHA), manifest_sha(source.parent, P89_MANIFEST_SHA)
    p91_path, p89_path = P91 / "outcome_safe_legs.csv.gz", source
    if sha256(p91_path) != P91_LEGS_SHA or sha256(p89_path) != P89_ROWS_SHA:
        raise RuntimeError("source payload hash mismatch")
    required_n7: set[tuple[str, str, str, str]] = set()
    with gzip.open(p91_path, "rt", newline="") as handle:
        reader = csv.DictReader(handle)
        assert_exact_schema(reader.fieldnames, P91_SOURCE_FIELDS, "#91 accepted source")
        for row in reader:
            if row["cohort"] == "PRIMARY" and row["n"] == "7":
                required_n7.add((row["match_id"], row["issue"], row["match_idx"], row["fold"]))
    rows: dict[tuple[str, str, str, str], dict[str, str]] = {}
    with p89_path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        assert_exact_schema(reader.fieldnames, P89_SOURCE_FIELDS, "#89 accepted source")
        for raw in reader:
            key = (raw["match_id"], raw["issue"], raw["match_idx"], raw["fold"])
            if key in required_n7:
                if key in rows:
                    raise RuntimeError(f"duplicate EURO identity: {key}")
                rows[key] = {field: raw[field] for field in FIELDS}
    if len(required_n7) != 46_802 or set(rows) != required_n7:
        raise RuntimeError(f"EURO input identity mismatch: required={len(required_n7)} found={len(rows)}")
    with tempfile.TemporaryDirectory(prefix="bj95_euro_input_") as name:
        stage = Path(name)
        projection = stage / "euro_10h_safe_projection.csv.gz"
        write_gzip(projection, [rows[key] for key in sorted(rows)])
        card = {
            "issue": 95,
            "stage": "GATE_A_SAFE_EURO_INPUT",
            "outcome_boundary": "Only identity, handicap line and 10h EURO odds are emitted; no outcome, score, result, final SP, payout, ROI or settlement field is read or emitted.",
            "purpose": "immutable clean-checkout input for #95 Gate-A EURO no-vig pruning arms",
            "source": {
                "bj91_manifest_sha256": p91_manifest, "bj91_n7_legs_sha256": P91_LEGS_SHA,
                "bj89_gate_a_manifest_sha256": p89_manifest, "bj89_gate_a_rows_sha256": P89_ROWS_SHA,
            },
            "identity": "all and only #91 PRIMARY N7 legs; match_id, issue, match_idx, fold",
            "rows": len(rows),
            "compression_contract": {
                "gzip_mtime": 0,
                "runtime": {"python": platform.python_version(), "zlib_compile": zlib.ZLIB_VERSION, "zlib_runtime": getattr(zlib, "ZLIB_RUNTIME_VERSION", zlib.ZLIB_VERSION)},
                "canonical_decompressed_sha256": {projection.name: content_sha256(projection)},
            },
        }
        (stage / "input_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n")
        payload = {p.name: sha256(p) for p in sorted(stage.iterdir()) if p.is_file()}
        (stage / "SHA256SUMS.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        shutil.copytree(stage, out)
    print(json.dumps({"out": str(out), "rows": len(rows)}, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True, help="accepted #89 frozen_preoutcome_rows.csv")
    parser.add_argument("--output", type=Path, required=True, help="new immutable safe-input bundle")
    args = parser.parse_args()
    build(args.source, args.output)
