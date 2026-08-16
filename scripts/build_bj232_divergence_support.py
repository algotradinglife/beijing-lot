#!/usr/bin/env python3
"""Build and verify the immutable #232 divergence-support package.

Commands:

- build: assemble the package from committed upstream packages, write it
  atomically, and report the disposition.
- verify: hash-verify the package and run semantic checks (evidence,
  schema, debt closure E1-E4).

The E1 binding SHA is supplied by the independent EV review; a placeholder
40-hex must be replaced by the exact reviewed HEAD before finalize.
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
from divergence_support import contract  # noqa: E402
from divergence_support import debt  # noqa: E402
from divergence_support import manifest as manifest_mod  # noqa: E402
from divergence_support import sources_verify  # noqa: E402


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    commands = value.add_subparsers(dest="command", required=True)

    build_all = commands.add_parser("build")
    build_all.add_argument("--root", type=Path, default=ROOT)
    build_all.add_argument("--force", action="store_true")
    build_all.add_argument(
        "--audited-sha",
        type=str,
        default="0" * 40,
        help="externally reviewed 40-hex HEAD (E1 binding); default placeholder",
    )

    verify = commands.add_parser("verify")
    verify.add_argument("--root", type=Path, default=ROOT)
    verify.add_argument("--package", type=Path, default=None)

    manifest = commands.add_parser("manifest")
    manifest.add_argument("--package", type=Path, required=True)
    return value


def _verify_semantics(package: Path, root: Path) -> list[str]:
    """Package-only semantic checks independent of the build receipt."""
    problems: list[str] = []

    # E1 binding
    try:
        binding = debt.read_audited_sha_binding(package)
        binding.validate()
    except debt.DebtError as error:
        problems.append(f"E1: {error}")

    # E2 schema
    schema = json.loads((package / "handoff_schema.json").read_text(encoding="utf-8"))
    problems.extend(debt.validate_schema(schema))

    # E3 journal
    journal = debt.CrashRestartJournal(package / "journal.jsonl")
    if not journal.is_consistent():
        problems.append("E3: journal has an open transaction")

    # E4 protocol log
    problems.extend(debt.validate_protocol_log(package))

    # REQ-S evidence present and all pass
    evidence_path = package / "evidence" / "req_s_evidence.csv"
    if not evidence_path.exists():
        problems.append("evidence: missing req_s_evidence.csv")
    else:
        import pandas as pd

        evidence = pd.read_csv(evidence_path)
        failed = evidence.loc[~evidence["pass"].astype(bool), "requirement"].tolist()
        if failed:
            problems.append(f"evidence: failing requirements {failed}")

    # Waterfall reconstructability (REQ-S06): replay the ledger per source.
    # RAW - sum(row DROPs) == COMPLETE rows; EXPAND == rows*3;
    # EXPAND - sum(cell DROPs) == final CAUSAL_INTERSECTION cells.
    waterfall_path = package / "tables" / "loss_of_support_waterfall.csv"
    if waterfall_path.exists():
        import pandas as pd

        waterfall = pd.read_csv(waterfall_path)
        for (source, source_key), sub in waterfall.groupby(
            ["source", "source_key"]
        ):
            current: int | None = None
            for _, row in sub.iterrows():
                kind = str(row["kind"])
                count = int(row["count"])
                if kind == "PASS" and row["stage"] == contract.STAGE_RAW:
                    current = count
                elif kind == "DROP":
                    if current is None:
                        problems.append(
                            f"waterfall: {source}/{source_key} DROP before RAW"
                        )
                        break
                    current -= count
                elif kind == "EXPAND":
                    factor = 3
                    reason = str(row["reason"])
                    if "AXIS_EXPAND_" in reason:
                        try:
                            factor = int(reason.split("AXIS_EXPAND_")[1].split("_")[0])
                        except ValueError:
                            factor = 3
                    if current is None or count != current * factor:
                        problems.append(
                            f"waterfall: {source}/{source_key} EXPAND {count} "
                            f"!= rows*{factor} ({current})"
                        )
                        break
                    current = count
                elif kind == "PASS":
                    current = count
            if current is not None and current != 0:
                problems.append(
                    f"waterfall: {source}/{source_key} final {current} != 0 "
                    "(zero causal intersection expected)"
                )

    return problems


def main() -> None:
    arguments = parser().parse_args()
    if arguments.command == "build":
        receipt = builder.build(arguments.root.resolve(), audited_sha=arguments.audited_sha)
        target = builder.write_package(
            receipt, audited_sha=arguments.audited_sha, force=arguments.force
        )
        print(f"BUILT {target}")
        print(f"disposition: {receipt.disposition}")
        print(f"evidence: {len(receipt.evidence)} requirements")
        print(f"debt closure: all_closed={receipt.debt_closure['all_closed']}")
        print(f"MANIFEST {target / 'MANIFEST.json'}")
        print(f"SHA256SUMS {target / 'SHA256SUMS.json'}")
    elif arguments.command == "verify":
        package = manifest_mod.resolve_package(arguments.root.resolve(), arguments.package)
        hashes = sources_verify.verify_package_hashes(package)
        problems = _verify_semantics(package, arguments.root.resolve())
        if problems:
            for problem in problems:
                print(f"SEMANTIC PROBLEM: {problem}")
            raise SystemExit(1)
        print(f"VERIFIED {package}: {len(hashes)} files match SHA256SUMS.json")
        print("SEMANTIC CHECKS PASS (evidence/schema/debt/waterfall/binding)")
    elif arguments.command == "manifest":
        payload = json.loads((arguments.package / "MANIFEST.json").read_text())
        print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
