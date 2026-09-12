"""Offline acceptance for the inventory-to-five-play boundary."""
from copy import deepcopy

import pytest

from src.nowscore_history_plan import make_history_capture_plan, validate_history_capture_plan
from src.nowscore_issue_inventory import canonical, digest, INVENTORY_SCHEMA


@pytest.fixture
def inventory():
    data = {
        "schema": INVENTORY_SCHEMA, "source": "nowscore",
        "generated_at": "2026-09-06T00:00:00+00:00",
        "candidate_coverage_complete": True, "production_enabled": False,
        "issues": ["190101", "20001", "26089"],
        "source_empty_candidates": ["20002"],
        "issue_count": 3, "source_empty_count": 1, "candidate_count": 4,
        "five_play_pages_to_capture": 15,
    }
    data["inventory_sha256"] = digest(canonical(data).encode())
    return data


def make_plan(inventory, **overrides):
    args = dict(issues_per_batch=2, control_issue="26089", interval_seconds=2,
                generated_at="2026-09-06T01:00:00+00:00")
    args.update(overrides)
    return make_history_capture_plan(inventory, **args)


def test_complete_domain_and_deterministic_plan(inventory):
    original = deepcopy(inventory)
    plan = make_plan(inventory)
    assert inventory == original
    assert plan == make_plan(inventory)
    assert plan["data_request_count"] == 15
    assert plan["control_request_count"] == 4
    assert plan["minimum_intra_batch_pacing_seconds"] == 34
    requests = [r for batch in plan["batches"] for r in batch["requests"]]
    assert {(r["issue"], r["typeid"]) for r in requests} == {
        (i, t) for i in inventory["issues"] for t in range(5, 10)
    }
    assert all("20002" not in r["url"] for r in requests)
    assert all(not key.startswith("/") for key in plan["implementation_sha256"])
    validate_history_capture_plan(plan, inventory)


@pytest.mark.parametrize("overrides", [
    {"issues_per_batch": 0}, {"issues_per_batch": True},
    {"interval_seconds": float("nan")}, {"interval_seconds": 1},
    {"control_issue": "20002"}, {"generated_at": "2026-09-05T00:00:00+00:00"},
    {"generated_at": "2026-09-06"},
])
def test_bad_parameters_rejected(inventory, overrides):
    with pytest.raises(ValueError):
        make_plan(inventory, **overrides)


@pytest.mark.parametrize("field,value", [
    ("candidate_coverage_complete", False), ("source", "mixed"),
    ("issue_count", 9), ("source_empty_candidates", ["20001"]),
    ("issues", []), ("five_play_pages_to_capture", 14),
])
def test_invalid_inventory_even_with_recomputed_hash(inventory, field, value):
    inventory[field] = value
    inventory.pop("inventory_sha256")
    inventory["inventory_sha256"] = digest(canonical(inventory).encode())
    with pytest.raises(ValueError):
        make_plan(inventory)


def test_tampered_inventory_and_plan_rejected(inventory):
    changed = deepcopy(inventory)
    changed["issues"][0] = "190102"
    with pytest.raises(ValueError, match="hash"):
        make_plan(changed)
    plan = make_plan(inventory)
    plan["batches"][0]["requests"][0]["typeid"] = 9
    with pytest.raises(ValueError, match="differs"):
        validate_history_capture_plan(plan, inventory)


def test_cli_preserves_inputs_and_refuses_overwrite(inventory, tmp_path, capsys):
    import json
    from scripts.plan_nowscore_history import main

    source = tmp_path / "inventory.json"
    source.write_text(canonical(inventory))
    output = tmp_path / "plan.json"
    argv = ["--inventory", str(source), "--output", str(output),
            "--issues-per-batch", "2", "--control-issue", "26089",
            "--generated-at", "2026-09-06T01:00:00+00:00"]
    main(argv)
    assert json.loads(capsys.readouterr().out)["data_request_count"] == 15
    validate_history_capture_plan(json.loads(output.read_text()), inventory)
    assert json.loads(source.read_text()) == inventory
    with pytest.raises(FileExistsError):
        main(argv)
