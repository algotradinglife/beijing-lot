#!/usr/bin/env python3
"""Build the immutable SHA256SUMS.txt manifest for the issue-209 results.

Uses sha256sum text format (``<hex>  <filename>``) so the method-preflight
receipt check can parse the method.yaml hash line.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path("results/issue-209")
FILES = [
    "census.csv",
    "market_only_probabilities.parquet",
    "cell_value_distribution.parquet",
    "dryrun_issue_results.csv",
    "dryrun_capital_path.csv",
    "dryrun_ticket_log.csv",
    "decision.json",
    "schema.json",
    "DECISION_REPORT.md",
]
EXTRA_ROOT = Path(".")  # files rooted at repo root, referenced by their relative path
EXTRA = [
    "method.yaml",
    "notebooks/research/issue-209/bj209_gate_a.ipynb",
    "docs/research/issue_209_unified_learning_gate_a.md",
    "docs/handoffs/bj209-gate-a-to-210.md",
]


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


lines = []
for f in EXTRA:
    p = Path(f)
    if p.exists():
        lines.append(f"{sha256_bytes(p.read_bytes())}  {f}")
for f in FILES:
    p = ROOT / f
    if p.exists():
        lines.append(f"{sha256_bytes(p.read_bytes())}  results/issue-209/{f}")

dst = ROOT / "SHA256SUMS.txt"
dst.write_text("\n".join(lines) + "\n")
print(f"SHA256SUMS.txt files: {len(lines)}")
print("\n".join("  " + l.split()[-1] for l in lines))
