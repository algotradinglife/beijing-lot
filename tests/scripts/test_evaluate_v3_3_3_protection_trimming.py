from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/evaluate_v3_3_3_protection_trimming.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("evaluate_v3_3_3_protection_trimming", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_protection_category_separates_switch_and_model_ev() -> None:
    mod = _load_module()

    assert mod.protection_category('["EV方向 平 只作保护"]') == "switched_ev_original"
    assert mod.protection_category('["并保留模型EV双选保护 平"]') == "model_ev_second"
    assert mod.protection_category("[]") == "other"


def test_variant_codes_keeps_only_registered_protection_class() -> None:
    mod = _load_module()

    assert mod.variant_codes("3", ["3", "1"], "model_ev_second", "baseline") == ["3", "1"]
    assert mod.variant_codes("3", ["3", "1"], "model_ev_second", "primary_only") == ["3"]
    assert mod.variant_codes("3", ["3", "1"], "model_ev_second", "draw_only") == ["3", "1"]
    assert mod.variant_codes("3", ["3", "0"], "model_ev_second", "draw_only") == ["3"]
    assert mod.variant_codes("3", ["3", "0"], "model_ev_second", "model_ev_only") == ["3", "0"]
    assert mod.variant_codes("3", ["3", "0"], "model_ev_second", "switch_ev_only") == ["3"]
    assert mod.variant_codes("3", ["3", "0"], "model_ev_second", "drop_model_ev_away") == ["3"]
    assert mod.variant_codes("3", ["3", "1"], "switched_ev_original", "drop_switch_ev_draw") == ["3"]
    assert mod.variant_codes("3", ["3", "0"], "switched_ev_original", "drop_switch_ev_draw") == ["3", "0"]
