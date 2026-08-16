#!/usr/bin/env python3
"""Build and verify the immutable #232 divergence-support package (R2).

Commands:

- build: assemble the package from committed upstream packages, write it
  atomically, and report the disposition.  ``--audited-sha`` is the exact
  externally reviewed HEAD (E1); the zero placeholder is rejected.
- verify: hash-verify the package and run ALL independent semantic checks
  (causality, de-vig, disposition truth table, requirement evidence, source
  binding, schema, extra/missing files, E1 binding).  ``--audited-sha``
  supplies the external trust anchor; when omitted, binding fails closed.
- manifest: print a package MANIFEST.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from divergence_support import builder  # noqa: E402
from divergence_support import manifest as manifest_mod  # noqa: E402
from divergence_support import verifier  # noqa: E402


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    commands = value.add_subparsers(dest="command", required=True)

    build_all = commands.add_parser("build")
    build_all.add_argument("--root", type=Path, default=ROOT)
    build_all.add_argument("--force", action="store_true")
    build_all.add_argument(
        "--audited-sha",
        type=str,
        required=True,
        help="exact externally reviewed 40-hex HEAD (E1 binding); "
        "the zero placeholder is rejected",
    )

    verify = commands.add_parser("verify")
    verify.add_argument("--root", type=Path, default=ROOT)
    verify.add_argument("--package", type=Path, default=None)
    verify.add_argument(
        "--audited-sha",
        type=str,
        default=None,
        help="external trust anchor; when omitted the E1 binding fails closed",
    )

    manifest = commands.add_parser("manifest")
    manifest.add_argument("--package", type=Path, required=True)
    return value


def main() -> None:
    arguments = parser().parse_args()
    if arguments.command == "build":
        if arguments.audited_sha == "0" * 40:
            print("ERROR: --audited-sha must be the exact reviewed HEAD, "
                  "not the zero placeholder", file=sys.stderr)
            raise SystemExit(2)
        receipt = builder.build(arguments.root.resolve(), audited_sha=arguments.audited_sha)
        target = builder.write_package(
            receipt, arguments.root.resolve(),
            audited_sha=arguments.audited_sha, force=arguments.force,
        )
        print(f"BUILT {target}")
        print(f"disposition: {receipt.disposition}")
        print(f"evidence: {len(receipt.evidence)} requirements")
        print(f"debt closure: all_closed={receipt.debt_closure['all_closed']}")
        print(f"MANIFEST {target / 'MANIFEST.json'}")
        print(f"SHA256SUMS {target / 'SHA256SUMS.json'}")
    elif arguments.command == "verify":
        package = manifest_mod.resolve_package(arguments.root.resolve(), arguments.package)
        try:
            hashes = verifier.verify_package_hashes(package)
        except (FileNotFoundError, ValueError) as error:
            print(f"HASH PROBLEM: {error}")
            raise SystemExit(1)
        problems = verifier.verify_semantics(
            package, expected_sha=arguments.audited_sha
        )
        if problems:
            for problem in problems:
                print(f"SEMANTIC PROBLEM: {problem}")
            raise SystemExit(1)
        print(f"VERIFIED {package}: {len(hashes)} files match SHA256SUMS.json")
        print("SEMANTIC CHECKS PASS (causality/devig/disposition/evidence/"
              "binding/schema/files)")
    elif arguments.command == "manifest":
        payload = json.loads((arguments.package / "MANIFEST.json").read_text())
        print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
