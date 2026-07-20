from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/analyze_historical_league_tag_effect.py"


def load_module():
    spec = importlib.util.spec_from_file_location("analyze_historical_league_tag_effect", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_target_label_normalizes_current_k2_name() -> None:
    module = load_module()

    assert module.target_label("韩K2联") == "K2联赛"
    assert module.target_label("瑞典超") == "瑞典超"
    assert module.target_label("韩K联") == ""


def test_recent_positive_leagues_have_frozen_deltas() -> None:
    module = load_module()

    assert set(module.TARGET_LEAGUES) == set(module.RECENT_DELTAS_PP)
    assert module.RECENT_DELTAS_PP["瑞典超"] == 37.5
