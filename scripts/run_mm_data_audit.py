#!/usr/bin/env python3
"""MM-DATA-AUDIT-001: Run the multi-market data readiness audit.

Usage:
    .venv/bin/python scripts/run_mm_data_audit.py [--output-dir OUTPUT_DIR]

The audit queries beidan_live.db and 500_bjdc.sqlite to classify four target
markets (Handicap 3/1/0, Correct Score, Total Goals, Half/Full Time) across
three dimensions: pre-event input, freeze support, and settlement support.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure the project root is on sys.path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.mm_data_audit.auditor import MultiMarketAuditor
from research.mm_data_audit.report import save_results


def main() -> None:
    parser = argparse.ArgumentParser(description="MM-DATA-AUDIT-001 multi-market audit")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "results/research/mm_data_audit",
        help="Output directory for audit results (default: results/research/mm_data_audit)",
    )
    parser.add_argument(
        "--fixtures-dir",
        type=Path,
        help="Directory containing mm_data_audit_live.db and mm_data_audit_500_bjdc.db",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON summary to stdout",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("MM-DATA-AUDIT-001: Multi-Market Data Readiness Audit")
    print("=" * 60)
    print()

    auditor = MultiMarketAuditor(fixtures_dir=args.fixtures_dir)
    result = auditor.audit_all()

    # Print summary
    print("Readiness Matrix:")
    print("-" * 50)
    print(f"{'Market':<20} {'Pre-Event':<15} {'Freeze':<15} {'Settlement':<15}")
    print("-" * 50)
    for playid in (34, 40, 42, 51):
        from research.mm_data_audit.contract import MARKETS
        m = MARKETS[playid]
        row = result.readiness_matrix.get(m.market_key, {})
        pe = row.get("pre_event_input", "UNAVAILABLE")
        fs = row.get("freeze_support", "UNAVAILABLE")
        ss = row.get("settlement_support", "UNAVAILABLE")
        print(f"{m.display_name:<20} {pe:<15} {fs:<15} {ss:<15}")
    print("-" * 50)
    print()

    # Per-market metrics
    for dim in result.dimensions:
        m = dim.market
        print(f"[{m.display_name}] {dim.dimension.value}: {dim.readiness.value}")
        for g in dim.gates:
            status = "PASS" if g.passed else "FAIL"
            print(f"  {g.gate_id.value}: {status} (score={g.score:.2f})")

    print()

    # Save results
    paths = save_results(result, args.output_dir)
    print(f"Report:   {paths['report_md']}")
    print(f"JSON:     {paths['audit_json']}")
    print(f"CSV:      {paths['readiness_csv']}")

    if args.json:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
