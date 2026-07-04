#!/usr/bin/env python3
"""Run the BJDC live-day refresh workflow through the decision API app."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.decision_api.app import DEFAULT_500_DB, create_app  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_500_DB)
    parser.add_argument("--issue", default="current")
    parser.add_argument("--dry-run", action="store_true", help="Plan and log steps without external fetches.")
    parser.add_argument("--requested-by", default="cli")
    args = parser.parse_args()

    app = create_app(sqlite_db=args.db)
    query = "?dry_run=1" if args.dry_run else ""
    with app.test_client() as client:
        response = client.post(
            f"/api/issues/{args.issue}/live-workflow{query}",
            headers={"X-Requested-By": args.requested_by},
        )
        payload = response.get_json() or {"error": response.get_data(as_text=True)}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if response.status_code >= 400:
        raise SystemExit(response.status_code)


if __name__ == "__main__":
    main()
