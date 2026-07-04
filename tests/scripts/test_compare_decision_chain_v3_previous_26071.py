from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/compare_decision_chain_v3_previous_26071.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("compare_decision_chain_v3_previous_26071", SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_metrics_count_primary_protect_and_profit_proxy() -> None:
    mod = _load_module()
    rows = [
        mod.CompareRow(
            match_idx=1,
            league="测试",
            home="主",
            away="客",
            handicap_line=0,
            score="1:0",
            result_code="3",
            winning_sp=2.5,
            previous=mod.ArmDecision("0", ("0",)),
            v3=mod.ArmDecision("3", ("3", "0")),
            v3_recommendation="胜为押，保负",
        ),
        mod.CompareRow(
            match_idx=2,
            league="测试",
            home="主",
            away="客",
            handicap_line=0,
            score="0:1",
            result_code="0",
            winning_sp=3.2,
            previous=mod.ArmDecision("0", ("0",)),
            v3=mod.ArmDecision("3", ("3", "0")),
            v3_recommendation="胜为押，保负",
        ),
    ]

    previous = mod.arm_metrics(rows, "previous")
    v3 = mod.arm_metrics(rows, "v3")

    assert previous["primary_hits"] == 1
    assert previous["protect_hits"] == 0
    assert previous["coverage_hits"] == 1
    assert previous["stake"] == 2
    assert previous["profit"] == 1.2
    assert v3["primary_hits"] == 1
    assert v3["protect_hits"] == 1
    assert v3["coverage_hits"] == 2
    assert v3["stake"] == 4
    assert v3["profit"] == 1.7


def test_switch_tags_detect_primary_protection_swap() -> None:
    mod = _load_module()
    row = mod.CompareRow(
        match_idx=10,
        league="测试",
        home="主",
        away="客",
        handicap_line=0,
        score="",
        result_code=None,
        winning_sp=None,
        previous=mod.ArmDecision("1", ("1", "3")),
        v3=mod.ArmDecision("3", ("3", "1")),
        v3_recommendation="胜为押，保平",
    )

    tags = mod.switch_tags(row)

    assert "方向变" in tags
    assert "旧押改保" in tags
    assert "旧保改押" in tags
    assert "押保顺序调换" in tags
