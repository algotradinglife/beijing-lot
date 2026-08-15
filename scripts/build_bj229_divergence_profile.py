#!/usr/bin/env python3
"""Build and verify the immutable #229 divergence-profile package.

Rework 2026-08-15: the verify command resolves the package name relative to
``results/`` (fixes the audited replay failure from the repo root) and also
runs the schema / evidence-closure checks so hash-only verification cannot
mask semantic defects.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in __import__("sys").path:
    __import__("sys").path.insert(0, str(ROOT / "src"))

from divergence_profile import builder  # noqa: E402
from divergence_profile import contract  # noqa: E402
from divergence_profile import manifest as manifest_mod  # noqa: E402
from divergence_profile import sources  # noqa: E402


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    commands = value.add_subparsers(dest="command", required=True)

    build_all = commands.add_parser("build")
    build_all.add_argument("--root", type=Path, default=ROOT)
    build_all.add_argument("--force", action="store_true")

    verify = commands.add_parser("verify")
    verify.add_argument("--root", type=Path, default=ROOT)
    verify.add_argument("--package", type=Path, default=None)

    manifest = commands.add_parser("manifest")
    manifest.add_argument("--package", type=Path, required=True)
    return value


def _verify_semantics(package: Path) -> list[str]:
    """Schema + evidence-closure checks beyond pure hash verification."""
    problems: list[str] = []
    schema_path = package / "handoff_schema.json"
    if not schema_path.exists():
        problems.append("missing handoff_schema.json")
        return problems
    schema = json.loads(schema_path.read_text())
    import pandas as pd
    import pyarrow.parquet as pq

    cells = pq.read_table(package / "inference_cells.parquet").to_pandas()
    schema_columns = {c["name"]: c for c in schema.get("columns", [])}
    for name, spec in schema_columns.items():
        if name not in cells.columns:
            problems.append(f"schema column missing from inference_cells: {name}")
    if schema.get("primary_key") not in cells.columns:
        problems.append("primary key column missing")
    # REQ-D evidence: every pass must be a real boolean, and any FALSE must be
    # reflected in the disposition (no hardcoded PASS)
    evidence = pd.read_csv(package / "evidence" / "req_d_evidence.csv")
    if "pass" not in evidence.columns:
        problems.append("req_d_evidence.csv missing pass column")
    else:
        failed = evidence.loc[~evidence["pass"].astype(bool), "requirement"].tolist()
        manifest = json.loads((package / "MANIFEST.json").read_text())
        if failed and manifest.get("disposition") == "READY_FOR_209":
            problems.append(
                f"READY_FOR_209 despite failed requirements: {failed}"
            )
    return problems


def main() -> None:
    arguments = parser().parse_args()
    if arguments.command == "build":
        receipt = builder.build(arguments.root.resolve())
        target = builder.write_package(receipt, force=arguments.force)
        print(f"BUILT {target}")
        print(f"disposition: {receipt.disposition}")
        print(f"cells: {len(receipt.cells)}")
        manifest_mod.write_replay(target, receipt, arguments.root.resolve())
        manifest_mod.write_sha256sums(target)
        print(f"MANIFEST {target / 'MANIFEST.json'}")
        print(f"SHA256SUMS {target / 'SHA256SUMS.json'}")
    elif arguments.command == "verify":
        package = manifest_mod.resolve_package(
            arguments.root.resolve(), arguments.package
        )
        hashes = sources.verify_package_hashes(package)
        problems = _verify_semantics(package)
        if problems:
            for problem in problems:
                print(f"SEMANTIC PROBLEM: {problem}")
            raise SystemExit(1)
        print(f"VERIFIED {package}: {len(hashes)} files match SHA256SUMS.json")
        print("SEMANTIC CHECKS PASS (schema + evidence closure)")
    elif arguments.command == "manifest":
        payload = json.loads((arguments.package / "MANIFEST.json").read_text())
        print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
