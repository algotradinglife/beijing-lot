#!/usr/bin/env python3
"""Create the one-purpose, outcome-free EURO input consumed by #95 Gate A.

This capture is deliberately narrow: it carries only the EURO 10h odds and
identity/line fields needed by the frozen #91 primary N7 legs.  Gate A itself
never opens the larger historical #89 artifact after this input is committed.
"""
from __future__ import annotations

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
OUT = ROOT / "results" / "bj95_euro_input_v1"
P91 = ROOT / "results" / "bj91_gate_a_preoutcome_v1r6"
P89 = ROOT / "results" / "bj89_gate_a_preoutcome_v3"
P91_LEGS_SHA = "cd0fdfd42002bbeddc6a1676323ead65c4cb85915f2c1a83b916d6c2004526fc"
P89_ROWS_SHA = "787bf3266403bebdcf3dfa4ae09f3dbc862a6542c04554fc1e37a0ba02296ae8"
FIELDS = ("match_id", "issue", "match_idx", "fold", "handicap_line_norm", "euro_3_10h", "euro_1_10h", "euro_0_10h")
FORBIDDEN = {"outcome", "score", "result", "result_code", "winning_sp", "final_sp", "payout", "roi", "settlement"}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def manifest_sha(bundle: Path) -> str:
    manifest = bundle / "SHA256SUMS.json"
    expected = json.loads(manifest.read_text())
    actual = {p.name: sha256(p) for p in bundle.iterdir() if p.is_file() and p.name != manifest.name}
    if actual != expected:
        raise RuntimeError(f"manifest mismatch: {bundle}")
    return sha256(manifest)


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


def main() -> None:
    if OUT.exists():
        raise RuntimeError(f"refusing to overwrite immutable output: {OUT}")
    p91_manifest, p89_manifest = manifest_sha(P91), manifest_sha(P89)
    p91_path, p89_path = P91 / "outcome_safe_legs.csv.gz", P89 / "frozen_preoutcome_rows.csv"
    if sha256(p91_path) != P91_LEGS_SHA or sha256(p89_path) != P89_ROWS_SHA:
        raise RuntimeError("source payload hash mismatch")
    required_n7: set[tuple[str, str, str, str]] = set()
    with gzip.open(p91_path, "rt", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or FORBIDDEN & set(reader.fieldnames):
            raise RuntimeError("#91 source is not outcome-free")
        for row in reader:
            if row["cohort"] == "PRIMARY" and row["n"] == "7":
                required_n7.add((row["match_id"], row["issue"], row["match_idx"], row["fold"]))
    rows: dict[tuple[str, str, str, str], dict[str, str]] = {}
    with p89_path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or FORBIDDEN & set(reader.fieldnames) or not set(FIELDS).issubset(reader.fieldnames):
            raise RuntimeError("#89 input schema is not a safe EURO projection source")
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
        shutil.copytree(stage, OUT)
    print(json.dumps({"out": str(OUT), "rows": len(rows)}, sort_keys=True))


if __name__ == "__main__":
    main()
