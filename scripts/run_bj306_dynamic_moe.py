#!/usr/bin/env python3
"""Run the full Issue #306 experiment and write results/issue-306."""

from __future__ import annotations

import sys
import time

from issue306.experiment import run_experiment


def main() -> int:
    root = "."
    output = "results/issue-306"
    started = time.time()
    payload = run_experiment(root, output)
    elapsed = time.time() - started
    print(f"issue306 experiment done in {elapsed:.1f}s")
    print(f"verdict: {payload['decision']['verdict']}")
    print(f"stage_a_source: {payload['stage_a_source']}")
    print(f"selected_objective: {payload['selected_objective']}")
    print(f"results written to {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())