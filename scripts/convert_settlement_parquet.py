#!/usr/bin/env python3
"""Convert the settlement SQLite release into a versioned Parquet dataset on NAS.

Reads the source registry for the release version and hash, then publishes
``<root>/datasets/settlement/versions/<version>/`` atomically. Read-only on the
source; never overwrites a published version.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT, ROOT / "packages/beidan/inst/python"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from beidan_backend.datasets import settlement_parquet as sp  # noqa: E402

DEFAULT_ROOT = Path("/mnt/nas/Data/beijing-lot")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    # The source registry is a required input: the settled Parquet dataset does
    # not bundle it, and the historical source disk is retired, so a default
    # path would silently point at something that no longer exists.
    parser.add_argument("--registry", type=Path, required=True,
                        help="source registry JSON recorded by the collector (required)")
    parser.add_argument("--source-root", type=Path, default=None,
                        help="base for a relative registry database path; required if not absolute")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT,
                        help="persistent Parquet root (must already exist)")
    parser.add_argument("--version", default=None, help="override the release version")
    parser.add_argument("--generated-at", default=None, help="ISO-8601 (reproducible manifests)")
    parser.add_argument("--verify", action="store_true", help="verify an existing version instead of converting")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = args.root
    if not root.is_dir():
        print(f"persistent root unavailable: {root}", file=sys.stderr)
        return 2

    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    version = args.version or registry["version"]
    version_dir = root / "datasets" / "settlement" / "versions" / version

    if args.verify:
        result = sp.verify_manifest(version_dir)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["ok"] else 1

    database = registry["database"]
    source = Path(database)
    if not source.is_absolute():
        if args.source_root is None:
            print("registry database path is relative; pass --source-root", file=sys.stderr)
            return 2
        source = args.source_root / database

    manifest = sp.convert_settlement(
        database=source, output_root=root, version=version,
        source_registry=registry, generated_at=args.generated_at,
    )
    rows = sum(manifest["row_counts"].values())
    print(f"published settlement {version}: {len(manifest['tables'])} tables, {rows} rows")
    print(f"  -> {version_dir}")
    print(f"  source sha256 {manifest['source']['sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
