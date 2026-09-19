"""Collect fixed market inputs with durable, budgeted 429 recovery."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.market_capture_recovery import run_supervised_market_history

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('contract', 'plan', 'index', 'output', 'ledger-path', 'budget-id'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--request-budget', type=int, required=True)
    parser.add_argument('--min-free-bytes', type=int, required=True)
    parser.add_argument('--min-interval-seconds', type=float, required=True)
    parser.add_argument('--workers', type=int, required=True)
    result = run_supervised_market_history(**vars(parser.parse_args()))
    print(json.dumps({k: v for k, v in result.items() if k != 'accounted_manifests'}), flush=True)
