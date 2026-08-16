"""BJ #234 build/verify CLI for the canonical source-schema contract.

Usage:
  python scripts/build_bj234_source_schema.py build [--package results/bj234_source_schema_v1] [--out-dir results]
  python scripts/build_bj234_source_schema.py verify --package <dir>
  python scripts/build_bj234_source_schema.py preflight --worktree <path> [--package results/bj234_source_schema_v1]

build     — profile databases, render DDL/schemas/crosswalk/feasibility,
            publish immutable package + manifest + sha256sums.
verify    — re-hash a published package and compare to MANIFEST (replay).
preflight — method-protocol gate: exit 0 only if the package is present and
            verifies and the DDL/schema contract is intact.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from source_schema import contract  # noqa: E402
from source_schema import crosswalk  # noqa: E402
from source_schema import feasibility  # noqa: E402
from source_schema import profiler  # noqa: E402
from source_schema import publication  # noqa: E402
from source_schema import schemas  # noqa: E402

DEFAULT_PACKAGE = "results/bj234_source_schema_v1"


def _code_hash() -> str:
    """Hash the reusable source package (deterministic file census)."""
    src = ROOT / "src/source_schema"
    h = hashlib.sha256()
    for p in sorted(src.glob("*.py")):
        h.update(p.name.encode("utf-8"))
        h.update(b"\0")
        h.update(p.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def _notebook_hash() -> str:
    nb = ROOT / "notebooks/research/issue-234/bj234_source_schema.ipynb"
    if not nb.exists():
        return "NOT_PRESENT"
    data = json.loads(nb.read_text())
    cells = [c for c in data.get("cells", [])
             if c.get("cell_type") == "code"
             and not "".join(c.get("source", [])).strip().startswith("%")]
    return hashlib.sha256(
        json.dumps([c["source"] for c in cells], sort_keys=True).encode("utf-8")
    ).hexdigest()


def _env() -> dict:
    import numpy
    import pandas
    import pyarrow

    return {
        "pandas": pandas.__version__,
        "numpy": numpy.__version__,
        "pyarrow": pyarrow.__version__,
    }


def _commit_sha() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or "UNKNOWN"
    except Exception:  # noqa: BLE001
        return "UNKNOWN"


def _csv_text(rows: list[dict]) -> str:
    if not rows:
        return ""
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def build(package: str) -> Path:
    profile = profiler.profile_all()
    clocks = profiler.classify_source_clocks(profile)
    pkg_hashes = profiler.package_source_hashes(ROOT)
    raw_hashes = profiler.raw_archive_hashes()

    ddl = schemas.render_ddl()
    arrow_json = json.dumps(schemas.all_arrow_schemas_json(), indent=1)
    domain_rows = schemas.domain_dictionary()
    crosswalk_rows = crosswalk.identity_crosswalk_rows()
    matrix_rows = feasibility.feasibility_matrix()

    files: dict[str, str] = {
        "schema.sql": ddl,
        "pyarrow_schemas.json": arrow_json,
        "domain_dictionary.csv": _csv_text(domain_rows),
        "identity_crosswalk.csv": _csv_text(crosswalk_rows),
        "identity_rule.json": json.dumps(crosswalk.canonical_identity_rule(),
                                         indent=1, sort_keys=True),
        "source_feasibility_matrix.csv": _csv_text(matrix_rows),
        "replacement_plan.json": json.dumps(feasibility.REPLACEMENT_PLAN,
                                            indent=1, sort_keys=True),
        "source_clock_classification.csv": _csv_text(clocks),
        "profile.json": json.dumps(profile, indent=1, default=str),
        "contract.json": json.dumps({
            "contract_version": f"{contract.CONTRACT_VERSION}/{contract.CONTRACT_REVISION}",
            "frozen_at_utc": contract.FROZEN_AT_UTC,
            "outcome_codes": list(contract.OUTCOME_CODES),
            "admissible_use_classes": [u.value for u in contract.AdmissibleUse],
            "clock_semantics": [c.value for c in contract.ClockSemantics],
            "snapshot_kinds": [s.value for s in contract.SnapshotKind],
            "source_families": contract.SOURCE_FAMILIES,
            "tables": [s["name"] for s in contract.table_specs()],
            "canonical_identity": crosswalk.canonical_identity_rule(),
        }, indent=1, sort_keys=True),
        "README.md": _readme(),
    }

    package_dir = publication.write_package(
        Path(package),
        files=files,
        profile=profile,
        source_hashes=pkg_hashes,
        raw_hashes=raw_hashes,
        code_hash=_code_hash(),
        notebook_hash=_notebook_hash(),
        environment=_env(),
        producer_commit_sha=_commit_sha(),
    )
    verdict = publication.verify_package(package_dir)
    print(json.dumps(verdict, indent=1))
    return package_dir


def _readme() -> str:
    return (
        "# BJ #234 — Unified Data Source Schema (frozen contract)\n\n"
        f"Contract: {contract.CONTRACT_VERSION} / {contract.CONTRACT_REVISION} "
        f"(frozen {contract.FROZEN_AT_UTC})\n\n"
        "This package is the immutable interface for all #232 recovery "
        "branches (#235 BJ SP, #236 EU odds, #237 power features, #238 "
        "materializer).\n\n"
        "## Artifacts\n\n"
        "- `schema.sql` — versioned SQLite DDL (capture/inference/settlement "
        "namespaces)\n"
        "- `pyarrow_schemas.json` — canonical PyArrow schemas for research "
        "Parquet partitions\n"
        "- `domain_dictionary.csv` — column semantics and domain constraints\n"
        "- `identity_crosswalk.csv` — legacy DB → canonical fixture binding\n"
        "- `source_feasibility_matrix.csv` — cost/access/licensing/coverage/"
        "clock grade per source, selected source per branch\n"
        "- `replacement_plan.json` — migration-free replacement plan\n"
        "- `source_clock_classification.csv` — REQ-DS01 admissible-use "
        "classification with evidence\n"
        "- `profile.json` — machine-readable DB profile (tables/rows/keys/ts "
        "ranges/nulls/duplicates)\n"
        "- `contract.json` — machine-readable contract\n"
        "- `MANIFEST.json` + `SHA256SUMS.json` — binding hashes (REQ-DS07)\n\n"
        "## Replay\n\n"
        "```bash\n"
        ".venv/bin/python scripts/build_bj234_source_schema.py verify "
        "--package results/bj234_source_schema_v1\n"
        "```\n"
    )


def verify(package: str) -> int:
    verdict = publication.verify_package(Path(package))
    print(json.dumps(verdict, indent=1))
    return 0


def preflight(worktree: str, package: str) -> int:
    """Method-protocol gate: package present + verifies + contract intact."""
    pkg = Path(worktree) / package
    if not pkg.exists():
        print(f"PREFLIGHT FAIL: package missing at {pkg}")
        return 1
    try:
        verdict = publication.verify_package(pkg)
    except AssertionError as e:
        print(f"PREFLIGHT FAIL: {e}")
        return 1
    # DDL must render identically from the worktree contract
    ddl_now = schemas.render_ddl()
    manifest = json.loads((pkg / "MANIFEST.json").read_text())
    if hashlib.sha256(ddl_now.encode("utf-8")).hexdigest() != manifest.get("ddl_sha256"):
        print("PREFLIGHT FAIL: ddl_sha256 mismatch")
        return 1
    print(f"PREFLIGHT OK: {verdict['files']} files, ddl_sha256 "
          f"{verdict['ddl_sha256'][:16]}…")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="BJ #234 source-schema build/verify")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--package", default=DEFAULT_PACKAGE)
    v = sub.add_parser("verify")
    v.add_argument("--package", default=DEFAULT_PACKAGE)
    p = sub.add_parser("preflight")
    p.add_argument("--worktree", required=True)
    p.add_argument("--package", default=DEFAULT_PACKAGE)
    args = ap.parse_args()
    if args.cmd == "build":
        build(args.package)
        return 0
    if args.cmd == "verify":
        return verify(args.package)
    if args.cmd == "preflight":
        return preflight(args.worktree, args.package)
    return 1


if __name__ == "__main__":
    sys.exit(main())
