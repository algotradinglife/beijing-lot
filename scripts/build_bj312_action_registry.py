#!/usr/bin/env python3
"""Freeze the Issue #312 action registry before any settlement is read."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from issue312.design import (  # noqa: E402
    DESIGN_SEED,
    SCREENING_ACTIONS,
    build_action_registry,
    registry_diagnostics,
)


def main() -> None:
    output = ROOT / "results/issue-312"
    output.mkdir(parents=True, exist_ok=True)
    registry = build_action_registry()
    marginal, pairwise = registry_diagnostics(registry)
    registry_path = output / "action_registry.csv"
    registry.to_csv(registry_path, index=False)
    marginal.to_csv(output / "action_design_marginals.csv", index=False)
    pairwise.to_csv(output / "action_design_pairwise_coverage.csv", index=False)
    receipt = {
        "issue": 312,
        "stage": "PRE_SETTLEMENT_ACTION_REGISTRY_FREEZE",
        "design": "SCIPY_QMC_DISCRETE_LATIN_HYPERCUBE_PLUS_EXACT_306_ANCHORS",
        "design_seed": DESIGN_SEED,
        "actions": SCREENING_ACTIONS,
        "anchors": int(registry["is_anchor"].sum()),
        "settlement_fields_read": [],
        "registry_sha256": hashlib.sha256(registry_path.read_bytes()).hexdigest(),
        "sealed_years": "2023 outcomes and 2024+ not read",
    }
    (output / "action_registry_receipt.json").write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(receipt)


if __name__ == "__main__":
    main()
