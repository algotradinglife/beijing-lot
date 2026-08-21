#!/usr/bin/env python3
"""Run Issue #302 from the repository root."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from issue302.experiment import run_experiment  # noqa: E402

if __name__ == "__main__":
    print(run_experiment(ROOT, ROOT / "results/issue-302"))
