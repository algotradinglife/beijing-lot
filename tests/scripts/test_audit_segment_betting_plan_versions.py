from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/audit_segment_betting_plan_versions.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("audit_segment_betting_plan_versions", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_bundle_metrics_reports_overlap_coverage_and_exposure() -> None:
    mod = _load_module()
    rows = [
        {
            "match_indices": "1,2,3",
            "widths": "1,2,3",
            "scaled_cost_units": "4",
            "scaled_cost_yuan": "8",
        },
        {
            "match_indices": "1,2,4",
            "widths": "1,1,2",
            "scaled_cost_units": "6",
            "scaled_cost_yuan": "12",
        },
    ]

    result = mod.bundle_metrics(rows)

    assert result["base_bundles"] == 2
    assert result["expanded_tickets"] == 10
    assert result["covered_match_count"] == 4
    assert result["mean_pair_overlap"] == 2
    assert result["mean_pair_jaccard"] == 0.5
    assert result["max_bundle_cost_share"] == 0.6
    assert result["selected_leg_single_share"] == 0.5
    assert result["selected_leg_double_share"] == pytest.approx(2 / 6, abs=1e-6)
    assert result["selected_leg_full_share"] == pytest.approx(1 / 6, abs=1e-6)
