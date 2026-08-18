from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "freeze_bj101_cold_pruning_gate_a.py"
PACKAGE = ROOT / "results" / "bj101_gate_a_preoutcome_v1r1"


def load():
    spec = importlib.util.spec_from_file_location("bj101_cold_pruning", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def row(position: int, kickoff: datetime, issue: str = "20001") -> dict[str, str]:
    return {
        "match_id": str(position),
        "issue": issue,
        "match_idx": str(position),
        "kickoff_ts": kickoff.isoformat(sep=" "),
        "year": "2020",
        "fold": "OOS_2020",
        "p3": "0.60",
        "p1": "0.30",
        "p0": "0.10",
    }


def test_cold_code_uses_frozen_code_tie_order():
    mod = load()
    tie = row(1, datetime(2020, 1, 1))
    tie.update({"p3": "0.10", "p1": "0.10", "p0": "0.80"})
    assert mod.cold_code(tie)[0] == "3"
    tie.update({"p3": "0.80", "p1": "0.10", "p0": "0.10"})
    assert mod.cold_code(tie)[0] == "1"


def test_rolling_segmentation_is_kickoff_only_and_non_overlapping():
    mod = load()
    start = datetime(2020, 1, 1)
    rows = [row(index, start + timedelta(hours=index - 1)) for index in range(1, 26)]
    pools = mod.make_pools(rows)
    assert [len(pool.rows) for pool in pools] == [13, 12]
    assert all(pool.disposition == "AVAILABLE" for pool in pools)
    identities = [item["match_id"] for pool in pools for item in pool.rows]
    assert identities == [str(index) for index in range(1, 26)]


def test_terminal_small_and_sparse_remainders_are_distinguished():
    mod = load()
    start = datetime(2020, 1, 1)
    small = mod.make_pools([row(index, start) for index in range(1, 7)])
    assert small[0].disposition == "UNAVAILABLE_INSUFFICIENT_MATCHES"

    sparse = mod.make_pools(
        [row(index, start + timedelta(hours=48 * index), "20002") for index in range(1, 26)]
    )
    assert len(sparse) == 1
    assert sparse[0].disposition == "UNAVAILABLE_NO_7_MATCH_WINDOW"
    assert len(sparse[0].rows) == 25


def test_descriptor_binds_arm_threshold_deleted_code_and_pool_identity():
    mod = load()
    pool_rows = tuple(row(index, datetime(2020, 1, 1)) for index in range(1, 8))
    candidate = {**pool_rows[0], "pool_id": "20001-OOS_2020-S01", "deleted_code": "0"}
    cold = mod.descriptor(candidate, "COLD_PMIN", mod.Decimal("0.10"), pool_rows)
    changed = {**candidate, "deleted_code": "1"}
    assert cold != mod.descriptor(changed, "COLD_PMIN", mod.Decimal("0.10"), pool_rows)
    assert cold != mod.descriptor(candidate, "HASH_DELETION_CONTROL", mod.Decimal("0.10"), pool_rows)
    assert cold != mod.descriptor(candidate, "COLD_PMIN", mod.Decimal("0.15"), pool_rows)


def test_immutable_package_has_full_denominator_and_complete_manifest():
    mod = load()
    manifest_path = PACKAGE / "SHA256SUMS.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest_path.is_file()
    assert set(manifest) == {
        "freeze_runner.py", "frontier_summary.csv", "gate_a_card.json",
        "issue_pool_census.csv", "issue_pool_membership.csv",
        "n7_cold_pruning_frontier.csv", "source_census.csv",
    }
    for name, expected in manifest.items():
        assert hashlib.sha256((PACKAGE / name).read_bytes()).hexdigest() == expected
    with (PACKAGE / "issue_pool_membership.csv").open(newline="", encoding="utf-8") as handle:
        membership = list(csv.DictReader(handle))
    assert len(membership) == 47_819
    assert {row["pool_disposition"] for row in membership} >= {
        "AVAILABLE", "UNAVAILABLE_INSUFFICIENT_MATCHES", "UNAVAILABLE_NO_7_MATCH_WINDOW"
    }
    with (PACKAGE / "source_census.csv").open(newline="", encoding="utf-8") as handle:
        census = {row["source"]: row for row in csv.DictReader(handle)}
    assert census["bj89_gate_a_preoutcome_v3"]["row_count"] == "71857"
    assert census["bj91_gate_a_preoutcome_v1r6"]["row_count"] == "47819"
    card = json.loads((PACKAGE / "gate_a_card.json").read_text(encoding="utf-8"))
    assert card["gate_b"].startswith("UNAUTHORIZED")
    assert card["source_denominators"]["joined_eligible_rows"] == 47_819
    assert mod.PRUNED_TICKETS == 1458
    assert mod.FULL_TICKETS == 2187
