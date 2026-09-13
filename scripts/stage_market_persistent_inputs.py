"""Stage existing market inputs on a mounted persistent data root; no requests."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.market_storage import stage_market_inputs

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("plan", "index", "data-root", "mountpoint"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    print(json.dumps(stage_market_inputs(args.plan, args.index, args.data_root, mountpoint=args.mountpoint)))
