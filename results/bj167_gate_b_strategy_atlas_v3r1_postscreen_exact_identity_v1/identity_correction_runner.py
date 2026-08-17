#!/usr/bin/env python3
"""Create the #167 post-screen identity-only immutable correction package.

This runner never opens outcomes, tickets, checkpoints, or bootstrap draws.  It
authenticates the completed post-screen package, copies every unaffected
payload byte-for-byte, and replaces only the two reporting tables whose blank
identity columns must be joined from candidate_freeze.csv by candidate_index.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "results" / "bj167_gate_b_strategy_atlas_v3r1_postscreen_exact"
OUTPUT = ROOT / "results" / "bj167_gate_b_strategy_atlas_v3r1_postscreen_exact_identity_v1"
SOURCE_MANIFEST_SHA256 = "903b7e555270c1b4509e215f41e9b6c1b709534fef66ade999b7ba3db8534d4f"
SOURCE_CONTENT_IDENTITY_SHA256 = "46757315891ceb6ab6fa289daada3b694d456582eb6139ec11934c60b1d4e433"
SOURCE_CANDIDATE_FREEZE_SHA256 = "56d77536807e1d8ab0e71caf547685820db68b71755becf336aafe84969dc15a"
CONTRACT = "bj167-gate-b-v3r1-postscreen-exact-identity-correction-v1"
CORRECTED_FILES = (
    "candidate_paired_bootstrap_20000.csv",
    "robust_pareto_front_exact.csv",
)
IDENTITY_FIELDS = (
    "selector_id", "weight_source", "mechanism", "cap", "M",
    "seed_scope", "candidate_inclusion",
)
DERIVED_FILES = {
    "SHA256SUMS.json", "CONTENT_IDENTITY.json", "file_census.csv",
    "correction_provenance.json",
}


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def git_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def verify_manifest(package: Path, expected_manifest: str, expected_content: str) -> dict[str, str]:
    if sha(package / "SHA256SUMS.json") != expected_manifest:
        raise RuntimeError("source post-screen manifest SHA-256 mismatch")
    if sha(package / "CONTENT_IDENTITY.json") != expected_content:
        raise RuntimeError("source post-screen content-identity SHA-256 mismatch")
    manifest = json.loads((package / "SHA256SUMS.json").read_text(encoding="utf-8"))
    for name, expected in manifest.items():
        path = package / name
        if not path.is_file() or sha(path) != expected:
            raise RuntimeError(f"source post-screen payload mismatch: {name}")
    return manifest


def load_freeze(path: Path) -> tuple[list[str], dict[str, dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or ())
        if "candidate_index" not in fields or any(field not in fields for field in IDENTITY_FIELDS):
            raise RuntimeError("candidate freeze identity schema mismatch")
        rows = list(reader)
    by_index: dict[str, dict[str, str]] = {}
    for row in rows:
        index = row["candidate_index"]
        if not index or index in by_index:
            raise RuntimeError(f"invalid/duplicate frozen candidate_index: {index!r}")
        if any(row[field] in (None, "") for field in IDENTITY_FIELDS):
            raise RuntimeError(f"blank frozen identity at candidate_index={index}")
        by_index[index] = row
    return fields, by_index


def projection_sha(path: Path, excluded_fields: tuple[str, ...] = IDENTITY_FIELDS) -> str:
    """Hash schema/order/all non-identity field strings exactly."""
    digest = hashlib.sha256()
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = [field for field in (reader.fieldnames or ()) if field not in excluded_fields]
        digest.update(json.dumps(fields, separators=(",", ":")).encode())
        digest.update(b"\n")
        for row in reader:
            digest.update(json.dumps([row[field] for field in fields], ensure_ascii=False,
                                     separators=(",", ":")).encode())
            digest.update(b"\n")
    return digest.hexdigest()


def correct_table(source: Path, target: Path, frozen: dict[str, dict[str, str]]) -> dict[str, object]:
    before_projection = projection_sha(source)
    with source.open(newline="", encoding="utf-8") as src:
        reader = csv.DictReader(src)
        fields = list(reader.fieldnames or ())
        if "candidate_index" not in fields or any(field not in fields for field in IDENTITY_FIELDS):
            raise RuntimeError(f"identity export schema mismatch: {source.name}")
        rows = list(reader)
    with target.open("w", newline="", encoding="utf-8") as dst:
        writer = csv.DictWriter(dst, fieldnames=fields, lineterminator="\n", extrasaction="raise")
        writer.writeheader()
        for row in rows:
            index = row["candidate_index"]
            if index not in frozen:
                raise RuntimeError(f"export candidate_index absent from freeze: {index}")
            for field in IDENTITY_FIELDS:
                row[field] = frozen[index][field]
            writer.writerow(row)
    after_projection = projection_sha(target)
    if after_projection != before_projection:
        raise RuntimeError(f"scientific non-identity values/order changed: {source.name}")
    with target.open(newline="", encoding="utf-8") as handle:
        corrected = list(csv.DictReader(handle))
    for row in corrected:
        expected = frozen[row["candidate_index"]]
        if any(row[field] != expected[field] for field in IDENTITY_FIELDS):
            raise RuntimeError(f"corrected identity mismatch: {source.name}:{row['candidate_index']}")
    return {
        "row_count": len(corrected),
        "source_sha256": sha(source),
        "corrected_sha256": sha(target),
        "non_identity_projection_sha256": after_projection,
        "identity_join_status": "PASS",
    }


def write_file_census(stage: Path) -> None:
    with (stage / "file_census.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["relative_path", "bytes", "sha256"])
        for path in sorted(stage.iterdir()):
            if path.is_file() and path.name not in {"SHA256SUMS.json", "CONTENT_IDENTITY.json", "file_census.csv"}:
                writer.writerow([path.name, path.stat().st_size, sha(path)])


def finalize_identity(stage: Path, controls: dict[str, object]) -> None:
    payloads = {
        path.name: sha(path)
        for path in sorted(stage.iterdir())
        if path.is_file() and path.name not in {"SHA256SUMS.json", "CONTENT_IDENTITY.json"}
    }
    content = {"contract_version": CONTRACT, "controls": controls, "payload_sha256": payloads}
    (stage / "CONTENT_IDENTITY.json").write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = dict(payloads)
    manifest["CONTENT_IDENTITY.json"] = sha(stage / "CONTENT_IDENTITY.json")
    (stage / "SHA256SUMS.json").write_text(json.dumps(dict(sorted(manifest.items())), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build(source: Path, output: Path, *, expected_manifest: str = SOURCE_MANIFEST_SHA256,
          expected_content: str = SOURCE_CONTENT_IDENTITY_SHA256,
          expected_freeze: str = SOURCE_CANDIDATE_FREEZE_SHA256) -> dict[str, object]:
    source, output = source.resolve(), output.resolve()
    if output.exists():
        raise RuntimeError(f"refusing immutable overwrite: {output}")
    source_manifest = verify_manifest(source, expected_manifest, expected_content)
    if sha(source / "candidate_freeze.csv") != expected_freeze:
        raise RuntimeError("source candidate freeze SHA-256 mismatch")
    _freeze_fields, frozen = load_freeze(source / "candidate_freeze.csv")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = output.with_name(f"{output.name}.stage-{uuid.uuid4().hex}")
    stage.mkdir()
    try:
        copied: dict[str, str] = {}
        for path in sorted(source.iterdir()):
            if not path.is_file() or path.name in {*CORRECTED_FILES, *DERIVED_FILES}:
                continue
            shutil.copyfile(path, stage / path.name)
            copied[path.name] = sha(stage / path.name)
            expected = source_manifest[path.name]
            if copied[path.name] != expected:
                raise RuntimeError(f"byte-preservation failure: {path.name}")
        corrected = {
            name: correct_table(source / name, stage / name, frozen)
            for name in CORRECTED_FILES
        }
        if corrected[CORRECTED_FILES[0]]["row_count"] != len(frozen):
            raise RuntimeError("candidate bootstrap export does not cover all frozen candidates")
        runner_copy = stage / "identity_correction_runner.py"
        shutil.copyfile(Path(__file__).resolve(), runner_copy)
        runner_sha = sha(runner_copy)
        execution_head = git_head()
        provenance = {
            "issue": 167,
            "contract": CONTRACT,
            "mode": "DETERMINISTIC_IDENTITY_JOIN_ONLY_NO_TICKET_REPLAY_NO_BOOTSTRAP_RERUN",
            "source_package": str(source.relative_to(ROOT)),
            "source_manifest_sha256": expected_manifest,
            "source_content_identity_sha256": expected_content,
            "source_candidate_freeze_sha256": expected_freeze,
            "identity_key": "candidate_index",
            "identity_fields": list(IDENTITY_FIELDS),
            "frozen_candidate_count": len(frozen),
            "correction_execution_head": execution_head,
            "correction_runner": "identity_correction_runner.py",
            "correction_runner_sha256": runner_sha,
            "corrected_payloads": corrected,
            "unaffected_payloads_copied_byte_for_byte": copied,
            "source_package_unchanged": True,
            "outcome_or_ticket_source_opened": False,
            "bootstrap_draws_read_or_recomputed": False,
        }
        (stage / "correction_provenance.json").write_text(
            json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        write_file_census(stage)
        finalize_identity(stage, {
            "source_manifest_sha256": expected_manifest,
            "source_content_identity_sha256": expected_content,
            "source_candidate_freeze_sha256": expected_freeze,
            "frozen_candidate_count": len(frozen),
            "corrected_files": list(CORRECTED_FILES),
            "correction_execution_head": execution_head,
            "correction_runner_sha256": runner_sha,
            "no_ticket_replay": True,
            "no_bootstrap_rerun": True,
        })
        verify_manifest(stage, sha(stage / "SHA256SUMS.json"), sha(stage / "CONTENT_IDENTITY.json"))
        os.replace(stage, output)
        return {
            "output": str(output),
            "manifest_sha256": sha(output / "SHA256SUMS.json"),
            "content_identity_sha256": sha(output / "CONTENT_IDENTITY.json"),
            "candidate_identity_join_count": len(frozen),
            "robust_identity_join_count": corrected[CORRECTED_FILES[1]]["row_count"],
            "unaffected_byte_identical_count": len(copied),
            "corrected": corrected,
        }
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(json.dumps(build(args.source, args.output), sort_keys=True))


if __name__ == "__main__":
    main()
