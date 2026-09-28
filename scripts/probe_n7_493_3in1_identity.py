#!/usr/bin/env python3
"""Thin entry point for the bounded #493 Nowscore 3in1 identity probe.

All reusable logic lives in src/n7_493_probe.py; this script only wires it to the
command line. Importing it performs no I/O.

The probe is complete (3 top-level requests; the per-hop attempt count is
unverified because redirect occurrence is unknown) and must not be re-run
without a new authorisation.
"""

from __future__ import annotations

import argparse
import sys
import threading
import uuid
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_OUT = ROOT / "results/data_collection/n7_493_3in1_probe_v1"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", choices=("base", "follow"), required=True)
    parser.add_argument("--companies", default="")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    from src.n7_493_probe import (Recorder, build_request_plan, close_quietly,
                                  count_attempts, count_top_level_requests,
                                  fetch_with_hops, load_ledger)

    args.out.mkdir(parents=True, exist_ok=True)
    # One session per recorder, so the recorded jar identity matches the jar used.
    session = requests.Session()
    recorder = Recorder(args.out, uuid.uuid4().hex[:12])
    try:
        for label, url in build_request_plan(args.plan, args.companies):
            fetch_with_hops(session, url, recorder, label, args.out)
    finally:
        # Off the deadline path: a blocking close must not extend a probe's budget.
        threading.Thread(target=close_quietly, args=(session,),
                         daemon=True).start()

    # Two distinct quantities, deliberately not conflated:
    #   hop_attempts     — reserved dispatches; budget is consumed at this level
    #   top_level_requests — logical requests, one per dispatch label
    # A redirect makes the first exceed the second, so neither can stand in for
    # the other and no remaining budget is derived from them.
    ledger = load_ledger(recorder.ledger_path)
    print(f"top_level_requests={count_top_level_requests(ledger)} "
          f"hop_attempts={count_attempts(ledger)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
