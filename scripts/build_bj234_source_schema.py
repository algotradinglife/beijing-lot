#!/usr/bin/env python3
"""Build and verify the immutable #234 source-schema contract package.

Commands:
- ``build``   run census + assemble + atomically publish the package;
- ``verify``  recompute hashes + semantic checks against a published package
              (fail closed on any tamper or contract violation);
- ``manifest`` print the package MANIFEST.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from source_schema import builder  # noqa: E402
from source_schema import handoff  # noqa: E402
from source_schema import manifest as manifest_mod  # noqa: E402
from source_schema import sources  # noqa: E402


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


def main() -> None:
    arguments = parser().parse_args()
    if arguments.command == "build":
        receipt = builder.build(arguments.root.resolve())
        target = builder.write_package(receipt, force=arguments.force)
        print(f"BUILT {target}")
        print(f"disposition: {receipt.manifest.get('disposition')}")
        print(f"databases: {receipt.manifest.get('database_count')}")
        print(f"tables: {receipt.manifest.get('table_count')}")
        print(f"MANIFEST {target / 'MANIFEST.json'}")
        print(f"SHA256SUMS {target / 'SHA256SUMS.json'}")
    elif arguments.command == "verify":
        package = manifest_mod.resolve_package(arguments.root.resolve(), arguments.package)
        checked = sources.verify_package_hashes(package)
        handoff.verify_package(package, arguments.root.resolve())
        print(f"VERIFIED {package}: {len(checked)} files match SHA256SUMS.json")
        print("SEMANTIC CHECKS PASS (ddl/registry/identity/temporal/namespaces/manifest)")
    elif arguments.command == "manifest":
        payload = json.loads((arguments.package / "MANIFEST.json").read_text())
        print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
