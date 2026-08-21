#!/usr/bin/env python3
"""Run Issue #299 from the repository root."""

from pathlib import Path

from issue299.experiment import run_experiment

ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    result = run_experiment(ROOT, ROOT / "results/issue-299")
    print(result["decision"])
