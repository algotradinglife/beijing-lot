"""Run the frozen observed-history plan; capture status is not acceptance."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.fundamentals_market_history import run_market_history

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('plan', 'index', 'output', 'ledger', 'budget-id'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--request-budget', type=int, required=True)
    parser.add_argument('--min-free-bytes', type=int, required=True)
    parser.add_argument("--min-interval-seconds", type=float, required=True)
    parser.add_argument("--workers", type=int, default=5)
    args = parser.parse_args()
    result = run_market_history(args.plan, args.index, args.output, ledger_path=args.ledger,
        budget_id=args.budget_id, request_budget=args.request_budget, min_free_bytes=args.min_free_bytes,
        min_interval_seconds=args.min_interval_seconds, workers=args.workers)
    print(json.dumps(result), flush=True)
