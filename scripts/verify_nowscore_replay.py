#!/usr/bin/env python3
"""Compare independent Nowscore builds and persist a new local replay receipt."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.nowscore_issue_inventory import canonical  # noqa: E402
from src.nowscore_replay import compare_nowscore_databases, database_file_hash  # noqa: E402


def main(argv=None):
    """Verify two files, create a new receipt, print only aggregate row evidence."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left", type=Path, required=True)
    parser.add_argument("--right", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--chunk-rows", type=int, default=1000)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise FileExistsError(args.output)
    result = compare_nowscore_databases(args.left, args.right, chunk_rows=args.chunk_rows)
    result["generated_at"] = datetime.now(timezone.utc).isoformat()
    root = Path(__file__).resolve().parents[1]
    result["implementation_sha256"] = {
        name: database_file_hash(root / name) for name in (
            "src/nowscore_replay.py", "src/nowscore_issue_inventory.py", "scripts/verify_nowscore_replay.py")
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        handle.write(canonical(result) + "\n")
    print(canonical({"equal": result["equal"], "table_rows": {
        name: evidence["rows"] for name, evidence in result["tables"].items()
    }}))


if __name__ == "__main__":
    main()
