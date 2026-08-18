"""Contract tests for #133's outcome-unexposed allocator Gate-A freeze."""
from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "freeze_bj133_diversified_allocator_gate_a.py"
PACKAGE = ROOT / "results" / "bj133_gate_a_preoutcome_v1"


def load():
    spec = importlib.util.spec_from_file_location("bj133_gate_a", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            value.update(block)
    return value.hexdigest()


def synthetic(portfolio_id: str, rank: int, matches: str, delete: str = "m0") -> dict[str, str]:
    return {
        "portfolio_id": portfolio_id,
        "candidate_rank_in_complete_issue": str(rank),
        "selected_match_ids": matches,
        "q_min_delete_match_id": delete,
        "q_min_delete_code": "0",
    }


def test_strict_caps_create_explicit_no_bet_instead_of_a_partial_relaxation() -> None:
    mod = load()
    candidates = [
        synthetic("one", 1, "a|b|c|d|e|f|g"),
        synthetic("two", 2, "a|b|c|d|e|f|h"),
        synthetic("three", 3, "a|b|c|d|e|f|i"),
    ]
    selected, status = mod.select_identities(candidates, 2, {"match_cap": 1, "delete_cap": None, "jaccard_cap": None})
    assert selected == []
    assert status == "NO_BET_CAP_UNSATISFIED"
    selected, status = mod.select_identities(candidates, 2, {"match_cap": None, "delete_cap": None, "jaccard_cap": 1.0})
    assert status == "AVAILABLE"
    assert [row["portfolio_id"] for row in selected] == ["one", "two"]


def test_geometry_is_complete_issue_exposure_not_segment_accounting() -> None:
    mod = load()
    rows = [
        synthetic("one", 1, "a|b|c|d|e|f|g", "a"),
        synthetic("two", 2, "a|b|c|d|e|f|h", "a"),
    ]
    values = mod.geometry(rows)
    assert values["total_leg_slots"] == 14
    assert values["unique_match_count"] == 8
    assert values["overlap_leg_slots"] == 6
    assert values["max_match_exposure"] == 2
    assert values["max_q_delete_exposure"] == 2
    assert values["max_pairwise_jaccard"] == 0.75


def test_contract_is_compact_complete_issue_frontier_and_uses_local_staging() -> None:
    mod = load()
    assert {row["config_id"] for row in mod.CONFIGS} == {
        "PRIMARY_NO_GATE_K4_M64", "PRIMARY_NO_GATE_K4_M128",
        "ECONOMIC_CONTROL_NO_GATE_K4_FULL", "SECONDARY_ESP300_GM290_K8_M128",
    }
    assert {row["allocator_family"] if "allocator_family" in row else row["family"] for row in mod.ALLOCATORS} >= {
        "CONCENTRATED_CONTROL", "MATCH_CAP", "OVERLAP_CAP", "DELETE_CODE_CAP", "JOINT_CAP",
    }
    assert "dir=output.parent" in SCRIPT.read_text(encoding="utf-8")
    assert "No test outcome" in SCRIPT.read_text(encoding="utf-8")


def test_real_freeze_manifest_and_card_bind_only_accepted_preoutcome_source() -> None:
    manifest = json.loads((PACKAGE / "SHA256SUMS.json").read_text())
    assert manifest == {item.name: digest(item) for item in PACKAGE.iterdir() if item.is_file() and item.name != "SHA256SUMS.json"}
    card = json.loads((PACKAGE / "gate_a_card.json").read_text())
    assert card["stage"] == "GATE_A_OUTCOME_UNEXPOSED_COMPLETE_ISSUE_DIVERSIFIED_ALLOCATION_FREEZE"
    assert card["source"]["bj137_gate_a_v2_manifest_sha256"] == "0aabeb94cec6d68831d233553e710b425bf02c1a843eae21adad50c4f9fac2df"
    assert card["gate_b_requirements"]["authorization"].startswith("NOT_RUN")
    assert "No test outcome" in card["outcome_boundary"]
    assert card["denominator"]["configuration_rows"] == 348 * 4 * 15


def test_real_plan_keeps_each_issue_intact_and_reconciles_equal_budget() -> None:
    mod = load()
    plans = list(csv.DictReader((PACKAGE / "allocation_plan.csv").open(newline="", encoding="utf-8")))
    assert len(plans) == 348 * len(mod.CONFIGS) * len(mod.ALLOCATORS)
    groups = defaultdict(list)
    for row in plans:
        groups[(row["config_id"], row["issue_instance"])].append(row)
        assert row["selection_scope"].startswith("COMPLETE_ISSUE")
        if row["selection_status"] == "AVAILABLE":
            assert int(row["selected_identity_count"]) == int(row["target_identity_count"])
            assert int(row["planned_draw_count"]) == int(row["selected_identity_count"]) * int(row["ticket_M"])
            assert float(row["planned_stake_yuan"]) == int(row["planned_draw_count"]) * 2
        else:
            assert int(row["selected_identity_count"]) == 0
            assert float(row["planned_stake_yuan"]) == 0.0
            assert row["reason"] in {"STRICT_CAP_UNSATISFIED_NO_RELAXATION", "NO_GATE_A_CANDIDATE_POOL"}
    assert {len(rows) for rows in groups.values()} == {len(mod.ALLOCATORS)}


def test_real_candidate_roles_are_outcome_free_and_normalized() -> None:
    forbidden = ("outcome", "result", "final", "winning", "payout", "roi", "tax", "settlement", "gross")
    with gzip.open(PACKAGE / "candidate_role_vectors.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        fields = tuple(reader.fieldnames or ())
        assert not any(token in field.lower() for field in fields for token in forbidden)
        seen = Counter()
        for row in reader:
            seen[(row["gate_id"], row["portfolio_id"])] += 1
            assert abs(sum(float(row[f"q_weight{code}"]) for code in ("3", "1", "0")) - 1.0) < 2e-9
        assert seen and set(seen.values()) == {7}


def test_real_concentrated_arm_is_ranked_and_all_cap_frontiers_are_present() -> None:
    plans = list(csv.DictReader((PACKAGE / "allocation_plan.csv").open(newline="", encoding="utf-8")))
    summaries = list(csv.DictReader((PACKAGE / "allocator_frontier_summary.csv").open(newline="", encoding="utf-8")))
    assert {row["allocator_id"] for row in plans} == {row["allocator_id"] for row in load().ALLOCATORS}
    assert len(summaries) == len(load().CONFIGS) * len(load().ALLOCATORS)
    control = [row for row in plans if row["allocator_id"] == "CONCENTRATED_TOP_SCORE" and row["selection_status"] == "AVAILABLE"]
    assert control
    assert all(len(row["selected_portfolio_ids"].split("|")) == int(row["target_identity_count"]) for row in control)
