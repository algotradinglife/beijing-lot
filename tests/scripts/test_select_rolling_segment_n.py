from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/select_rolling_segment_n.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("select_rolling_segment_n", SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_good_coverage_uses_half_n_with_cap() -> None:
    mod = _load_module()

    rec = mod.recommend_segment_n(20, 0.80)

    assert rec.half_n == 8
    assert rec.recommended_n == 8
    assert rec.quality_drop == 0
    assert rec.capped_by_max_n is True


def test_normal_and_weak_coverage_drop_from_half_n() -> None:
    mod = _load_module()

    normal = mod.recommend_segment_n(16, 0.75)
    weak = mod.recommend_segment_n(16, 0.68)

    assert normal.half_n == 8
    assert normal.recommended_n == 7
    assert normal.quality_drop == 1
    assert weak.recommended_n == 6
    assert weak.quality_drop == 2


def test_budget_thin_drops_one_more_level() -> None:
    mod = _load_module()

    rec = mod.recommend_segment_n(16, 0.75, budget_coverage="thin")

    assert rec.recommended_n == 6
    assert rec.quality_drop == 1
    assert rec.budget_drop == 1
    assert "budget_coverage_thin_drop_1" in rec.reasons


def test_small_pool_prefers_expand_but_keeps_small_ticket_n() -> None:
    mod = _load_module()

    rec = mod.recommend_segment_n(5, 0.80)

    assert rec.recommended_n == 3
    assert rec.action == "expand_preferred_small_ticket_only"


def test_cli_accepts_percentage_rate() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--eligible-matches",
            "16",
            "--expected-coverage-hit-rate",
            "75",
            "--budget-coverage",
            "thin",
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    payload = json.loads(result.stdout)
    assert payload["expected_coverage_hit_rate"] == 0.75
    assert payload["recommended_n"] == 6
