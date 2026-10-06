#!/usr/bin/env python3
"""Build the data-collection master ledger and its drift report.

Read-only: inventories repository collectors, scheduled units, the external
registry and data stores, then reports where they disagree. Writes only the
ledger JSON under ``results/data_collection/collection_ledger_v1`` (or --output).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT, ROOT / "src"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from collection_ledger import ledger as ledger_mod  # noqa: E402

DEFAULT_OUTPUT = ROOT / "results/data_collection/collection_ledger_v1/ledger.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=ROOT / "config/data_collection_plan.json")
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument(
        "--unit-dir",
        action="append",
        default=None,
        help="host systemd unit directory (repeatable; defaults to ~/.config/systemd/user)",
    )
    parser.add_argument("--registry-dir", type=Path, default=Path(ledger_mod.DEFAULT_EXTERNAL_REGISTRY))
    parser.add_argument("--external-data-root", type=Path, default=Path(ledger_mod.DEFAULT_EXTERNAL_DATA_ROOT))
    parser.add_argument("--no-external", action="store_true", help="skip the external registry and data root")
    parser.add_argument("--store-stale-days", type=float, default=ledger_mod.DEFAULT_STORE_STALE_DAYS)
    parser.add_argument("--generated-at", default=None, help="ISO-8601 timestamp (for reproducible reports)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--no-write", action="store_true", help="print only; do not write the ledger JSON")
    parser.add_argument("--json", action="store_true", help="emit the ledger JSON to stdout")
    parser.add_argument("--fail-on-error", action="store_true", help="exit 2 when any error finding is present")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    unit_dirs = args.unit_dir or [path for path in ledger_mod.DEFAULT_HOST_UNIT_DIRS]
    registry = None if args.no_external else args.registry_dir
    external_root = None if args.no_external else args.external_data_root

    ledger = ledger_mod.build_ledger(
        plan_path=args.plan,
        repo_root=args.repo_root,
        unit_dirs=unit_dirs,
        registry_dir=registry,
        external_data_root=external_root,
        generated_at=args.generated_at,
        store_stale_days=args.store_stale_days,
    )

    output = Path(args.output)
    if output.exists():
        try:
            previous = json.loads(output.read_text(encoding="utf-8"))
            ledger["drift"] = ledger_mod.diff_ledgers(previous, ledger)
        except (OSError, json.JSONDecodeError):
            ledger["drift"] = None

    if not args.no_write:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(ledger, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(ledger, ensure_ascii=False, indent=2))
    else:
        print(ledger_mod.render_text(ledger))
        drift = ledger.get("drift")
        if drift:
            print("")
            print(f"drift vs {drift['previous_generated_at']}: {drift['transition_count']} state transition(s)")
            for item in drift["transitions"]:
                print(f"  {item['object']:44} {item['from']} -> {item['to']}")
        if not args.no_write:
            print("")
            print(f"ledger written: {output}")

    if args.fail_on_error and ledger["summary"]["errors"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
