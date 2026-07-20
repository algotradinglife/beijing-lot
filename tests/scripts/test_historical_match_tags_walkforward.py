from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/backtest_historical_match_tags_walkforward.py"


def load_module():
    spec = importlib.util.spec_from_file_location("backtest_historical_match_tags_walkforward", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_feature_specs_isolate_each_tag_family() -> None:
    module = load_module()
    specs = {spec.name: spec for spec in module.feature_specs()}

    assert specs["market_hcap"].categorical == ()
    assert specs["market_hcap_league"].categorical == ("league",)
    assert "rank_home" in specs["market_hcap_ranks"].numeric
    assert "asian_line" in specs["market_hcap_asian"].numeric
    assert specs["all_no_league"].categorical == ()
    assert specs["all_with_league"].categorical == ("league",)


def test_metrics_calculates_top1_and_top2() -> None:
    module = load_module()
    probabilities = np.asarray([
        [0.7, 0.2, 0.1],
        [0.2, 0.3, 0.5],
        [0.4, 0.35, 0.25],
    ])
    result = module.metrics(probabilities, np.asarray(["3", "0", "1"]))

    assert result["accuracy"] == 2 / 3
    assert result["top2_coverage"] == 1.0
    assert result["logloss"] > 0
    assert result["brier"] > 0


def test_reorder_probabilities_uses_beidan_code_order() -> None:
    module = load_module()
    raw = np.asarray([[0.1, 0.2, 0.7]])

    reordered = module.reorder_probabilities(raw, ["0", "1", "3"])

    assert reordered.tolist() == [[0.7, 0.2, 0.1]]
