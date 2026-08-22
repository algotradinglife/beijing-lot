#!/usr/bin/env python3
"""Run the frozen Issue #312 terminal experiment."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from issue312.experiment import run_experiment  # noqa: E402


if __name__ == "__main__":
    print(run_experiment(ROOT / "results/issue-312"))
