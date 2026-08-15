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

from divergence_profile import handoff  # noqa: E402
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


def _verify_semantics(package: Path, root: Path = ROOT) -> list[str]:
    """Independent package-only semantic recomputation plus provenance."""
    return handoff.validate_package(
        package, repo_root=root.resolve(), expected_commit=builder._git_head(root.resolve())
    )


def main() -> None:
    arguments = parser().parse_args()
    if arguments.command == "build":
        receipt = builder.build(arguments.root.resolve())
        target = builder.write_package(receipt, force=arguments.force)
        print(f"BUILT {target}")
        print(f"disposition: {receipt.disposition}")
        print(f"cells: {len(receipt.cells)}")
        print(f"MANIFEST {target / 'MANIFEST.json'}")
        print(f"SHA256SUMS {target / 'SHA256SUMS.json'}")
    elif arguments.command == "verify":
        package = manifest_mod.resolve_package(
            arguments.root.resolve(), arguments.package
        )
        hashes = sources.verify_package_hashes(package)
        problems = _verify_semantics(package, arguments.root)
        if problems:
            for problem in problems:
                print(f"SEMANTIC PROBLEM: {problem}")
            raise SystemExit(1)
        print(f"VERIFIED {package}: {len(hashes)} files match SHA256SUMS.json")
        print("SEMANTIC CHECKS PASS (causal/divergence/labels/schema/profile/provenance/report)")
    elif arguments.command == "manifest":
        payload = json.loads((arguments.package / "MANIFEST.json").read_text())
        print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
