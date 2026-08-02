"""Integrity checks for #148's outcome-unexposed dense M-grid Gate-A freeze."""
from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "freeze_bj148_dense_m_grid_gate_a.py"
PACKAGE = ROOT / "results" / "bj148_gate_a_preoutcome_v1"
MANIFEST_SHA256 = "fd4a0f4dc0ab5ef97f3c260a082515aa7874a60a1ac1e5e0ecd865fdb1eeafd6"


def module():
    spec = importlib.util.spec_from_file_location("bj148_gate_a", SCRIPT)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def read_csv(name: str) -> list[dict[str, str]]:
    with (PACKAGE / name).open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_dense_grid_is_exact_and_full_is_not_a_wr_draw() -> None:
    runner = module()
    grid = read_csv("dense_m_grid.csv")
    assert tuple(int(row["M"]) for row in grid) == runner.M_GRID
    assert len(grid) == 58
    assert [int(row["M"]) for row in grid if row["grid_band"] == "DENSE_16"] == list(range(16, 513, 16))
    assert [int(row["M"]) for row in grid if row["grid_band"] == "DENSE_64_MID"] == list(range(576, 1025, 64))
    assert [int(row["M"]) for row in grid if row["grid_band"] == "DENSE_64_HIGH"] == list(range(1088, 2113, 64))
    assert grid[-1]["M"] == "2187"
    assert grid[-1]["is_full_control"] == "true"
    assert grid[-1]["WR_plan_count"] == grid[-1]["WOR_plan_count"] == "0"


def test_common_support_includes_all_133_no_gate_identities_and_explicit_no_bets() -> None:
    cohort = read_csv("common_support_cohort.csv")
    with gzip.open(PACKAGE / "common_support_identities.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        identities = list(csv.DictReader(handle))
    assert len(cohort) == 348
    assert len(identities) == 8_550
    assert {row["gate_id"] for row in identities} == {"NO_GATE"}
    counts = Counter((row["issue"], row["fold"], row["year"], row["issue_instance"]) for row in identities)
    assert sum(row["common_support_status"] == "AVAILABLE" for row in cohort) == 343
    assert sum(row["common_support_status"] != "AVAILABLE" for row in cohort) == 5
    for row in cohort:
        key = row["issue"], row["fold"], row["year"], row["issue_instance"]
        assert int(row["selected_identity_count"]) == counts[key]
        assert int(row["candidate_identity_count"]) == counts[key]
        if row["common_support_status"] == "AVAILABLE":
            assert row["common_support_reason"] == "ALL_INHERITED_RANK32_IDENTITIES"
        else:
            assert counts[key] == 0


def test_sampling_surface_preserves_wr_primary_wor_sensitivity_and_full_control() -> None:
    runner = module()
    plan = read_csv("sampling_plan.csv")
    assert len(plan) == 119_364
    assert len({row["plan_id"] for row in plan}) == len(plan)
    roles = Counter(row["sampling_role"] for row in plan)
    assert roles == {"PRIMARY_WR_NATURAL_BASELINE": 59_508, "SENSITIVITY_WOR_DISTINCT": 59_508, "FULL_ECONOMIC_CONTROL": 348}
    for row in plan:
        if row["sampling_role"] == "FULL_ECONOMIC_CONTROL":
            assert row["M"] == str(runner.FULL_TICKETS)
            assert row["seed"] == "NA"
            assert row["ticket_mechanism"] == "FULL_ENUMERATED"
        else:
            assert row["M"] != str(runner.FULL_TICKETS)
            assert row["seed"] in runner.SEEDS
            assert int(row["planned_draw_count"]) == int(row["candidate_identity_count"]) * int(row["M"])
            assert int(row["planned_stake_yuan"]) == int(row["planned_draw_count"]) * runner.UNIT_STAKE_YUAN
        assert row["outcome_boundary"].startswith("No outcome")


def test_manifest_content_identity_and_source_bindings_are_exact() -> None:
    runner = module()
    manifest = json.loads((PACKAGE / "SHA256SUMS.json").read_text(encoding="utf-8"))
    actual = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in PACKAGE.iterdir() if path.is_file() and path.name != "SHA256SUMS.json"}
    assert manifest == actual
    assert hashlib.sha256((PACKAGE / "SHA256SUMS.json").read_bytes()).hexdigest() == MANIFEST_SHA256
    card = json.loads((PACKAGE / "gate_a_card.json").read_text(encoding="utf-8"))
    assert card["contract"] == runner.CONTRACT
    assert card["sources"]["bj137_gate_a_v2"]["manifest_sha256"] == runner.SOURCE_137_MANIFEST
    assert card["sources"]["bj133_gate_a_v1"]["manifest_sha256"] == runner.SOURCE_133_MANIFEST
    assert card["denominator"] == {"available_issue_rows": 343, "common_support_identities": 8550, "common_support_role_rows": 59850, "complete_issue_rows": 348, "dense_m_points": 58, "no_bet_issue_rows": 5, "sampled_m_points": 57, "sampling_plan_rows": 119364, "seed_count": 3}
    content = json.loads((PACKAGE / "CONTENT_IDENTITY.json").read_text(encoding="utf-8"))
    assert content["contract_version"] == runner.CONTENT_VERSION
    assert "never in `/tmp`" in (PACKAGE / "README.md").read_text(encoding="utf-8")
