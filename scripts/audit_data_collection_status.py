#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.decision_api import app as decision_app  # noqa: E402


def run(db_path: Path, issue: str) -> dict[str, object]:
    with decision_app._connect(db_path) as conn:
        payload = decision_app._operations_status_payload(conn, issue)
    collectors = payload.get("collectors") if isinstance(payload.get("collectors"), dict) else {}
    return {
        "issue": payload.get("issue", issue),
        "generated_at": payload.get("generated_at", ""),
        "plan_status": collectors.get("plan_status", "missing"),
        "plan_error": collectors.get("plan_error", ""),
        "summary": collectors.get("summary", {}),
        "collectors": collectors.get("items", []),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit every registered Beidan data collector.")
    parser.add_argument("--db", type=Path, default=decision_app.DEFAULT_500_DB)
    parser.add_argument("--issue", default="current")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-on-warn", action="store_true")
    args = parser.parse_args()

    result = run(args.db, args.issue)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
        print(
            f"issue={result['issue']} plan={result['plan_status']} "
            f"ok={summary.get('ok', 0)} warn={summary.get('warn', 0)} "
            f"bad={summary.get('bad', 0)} standby={summary.get('standby', 0)}"
        )
        for item in result.get("collectors", []):
            if not isinstance(item, dict):
                continue
            print(
                f"{str(item.get('status') or '').upper():7} "
                f"{item.get('collector_id')} process={item.get('process_status')} "
                f"coverage={item.get('actual_count')}/{item.get('expected_count')} "
                f"last_success={item.get('last_success_at') or '-'} "
                f"reason={item.get('reason')}"
            )

    summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
    if result.get("plan_status") != "ok" or int(summary.get("bad") or 0) > 0:
        raise SystemExit(2)
    if args.fail_on_warn and int(summary.get("warn") or 0) > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
