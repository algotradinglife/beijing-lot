from __future__ import annotations

import importlib.util
import csv
import gzip
import hashlib
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "freeze_bj170_selector_allocator_stack_gate_a.py"


def load_module():
    spec = importlib.util.spec_from_file_location("bj170_gate_a", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_fixed_factorial_contract_and_frozen_hashes():
    module = load_module()
    assert [item[0] for item in module.SELECTORS] == ["BEST_FULL", "Q_SOURCE", "MODEL_SOURCE"]
    assert [item[0] for item in module.ARMS] == [
        "FULL_ENUMERATED", "Q_TOP_MASS_M192", "MODEL_CAP1_M512"
    ]
    assert {item[4] for item in module.ARMS} == {192, 512, 2187}
    assert module.sha256_file(ROOT / "scripts" / "bj145_fast_alloc.cpp") == module.EXPECTED_ALLOCATOR_SHA256
    assert module.sha256_file(module.GATE_A / "SHA256SUMS.json") == module.EXPECTED_GATE_A_MANIFEST
    assert module.sha256_file(module.GATE_A / "CONTENT_IDENTITY.json") == module.EXPECTED_GATE_A_CONTENT
    assert module.sha256_file(module.GATE_B / "SHA256SUMS.json") == module.EXPECTED_GATE_B_MANIFEST
    assert module.sha256_file(module.GATE_B / "CONTENT_IDENTITY.json") == module.EXPECTED_GATE_B_CONTENT


def test_native_allocator_exact_counts_for_all_three_arms():
    module = load_module()
    allocator = module.FrozenAllocator()
    weights = tuple(float(((ordinal * 37 + 11) % 1009) + 1) for ordinal in range(module.FULL_K))
    top = allocator.allocate(weights, "DETERMINISTIC_TOP_MASS", 192)
    capped = allocator.allocate(weights, "CAPPED_REPEAT", 512, 1)
    full = allocator.allocate(weights, "FULL_ENUMERATED", 2187)
    expected_top = set(sorted(range(module.FULL_K), key=lambda ordinal: (-weights[ordinal], ordinal))[:192])
    assert {ordinal for ordinal, count in enumerate(top) if count} == expected_top
    assert sum(top) == 192 and max(top) == 1
    assert sum(capped) == 512 and max(capped) == 1
    assert full == (1,) * module.FULL_K


def test_role_product_uses_canonical_base3_prefix_order():
    module = load_module()
    roles = []
    for leg in range(7):
        roles.append({
            "q_weight3": str(0.50 + leg * 0.001),
            "q_weight1": str(0.30 - leg * 0.0005),
            "q_weight0": str(0.20 - leg * 0.0005),
            "p_model3": "0.5", "p_model1": "0.3", "p_model0": "0.2",
        })
    weights = module.role_product_weights(roles, "Q_WEIGHT")
    assert len(weights) == 2187
    assert weights[0] == __import__("math").prod(float(role["q_weight3"]) for role in roles)
    assert weights[-1] == __import__("math").prod(float(role["q_weight0"]) for role in roles)


def test_support_views_freeze_native_pairwise_and_three_way_without_outcomes():
    module = load_module()
    participation = []
    for alias, selector_id, _ in module.SELECTORS:
        for issue_instance, count in (("A@F", 1), ("B@F", 1 if alias != "MODEL_SOURCE" else 0)):
            participation.append({
                "selector_alias": alias, "selector_id": selector_id,
                "issue": issue_instance.split("@")[0], "year": "2020", "fold": "F",
                "issue_instance": issue_instance, "selected_identity_count": count,
            })
    identities = [
        {"support_key_sha256": "same", "selector_alias": alias, "issue_instance": "A@F", "selected_match_ids": "m1|m2|m3|m4|m5|m6|m7"}
        for alias, _, _ in module.SELECTORS
    ]
    registry, membership, exact = module.support_views(participation, identities)
    three = next(row for row in registry if row["support_view_id"] == "THREE_WAY_ALL")
    assert three["eligible_issue_count"] == 1
    assert next(row for row in membership if row["support_view_id"] == "THREE_WAY_ALL")["issue_instance"] == "A@F"
    assert exact == [{
        "support_key_sha256": "same",
        "issue_instance": "A@F",
        "selected_match_ids": "m1|m2|m3|m4|m5|m6|m7",
        "selector_aliases": "BEST_FULL|Q_SOURCE|MODEL_SOURCE",
        "selector_count": 3,
        "identity_occurrence_count": 3,
        "pairwise_common": "1",
        "three_way_common": "1",
        "outcome_boundary": module.OUTCOME_BOUNDARY,
    }]


def test_gate_a_runner_has_no_outcome_or_settlement_loader():
    source = SCRIPT.read_text(encoding="utf-8")
    assert "load_outcomes" not in source
    assert "canonical_outcome_join" not in source
    assert "winning_sp" not in source
    assert "result_code" not in source
    # Terminal Gate-B evidence is only passed through the hash-only verifier.
    assert "verify_package(GATE_B" in source


def test_generated_package_is_complete_and_internally_reconciled():
    module = load_module()
    package = ROOT / "results" / "bj170_gate_a_preoutcome_v1"
    declared = json.loads((package / "SHA256SUMS.json").read_text(encoding="utf-8"))
    actual_files = {path.name for path in package.iterdir() if path.is_file() and path.name != "SHA256SUMS.json"}
    assert set(declared) == actual_files
    for name, expected in declared.items():
        assert hashlib.sha256((package / name).read_bytes()).hexdigest() == expected

    card = json.loads((package / "gate_a_card.json").read_text(encoding="utf-8"))
    assert card["denominator"] == {
        "allocation_arm_count": 3,
        "exact_identity_support_rows": 1758,
        "factorial_cell_count": 9,
        "identity_allocation_rows": 5337,
        "identity_rows": 1779,
        "issue_rows": 1044,
        "planned_stake_rows": 3132,
        "role_rows": 12453,
        "selector_count": 3,
        "support_issue_rows": 1539,
        "support_view_count": 7,
        "unique_issue_instances": 348,
    }
    with gzip.open(package / "identity_freeze.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        identities = list(csv.DictReader(handle))
    assert Counter(row["selector_alias"] for row in identities) == {
        "BEST_FULL": 189, "Q_SOURCE": 1356, "MODEL_SOURCE": 234
    }
    with gzip.open(package / "identity_allocation_digest.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        allocations = list(csv.DictReader(handle))
    assert Counter(row["allocation_arm"] for row in allocations) == {
        "FULL_ENUMERATED": 1779, "Q_TOP_MASS_M192": 1779, "MODEL_CAP1_M512": 1779
    }
    assert all(int(row["duplicate_ticket_count"]) == 0 for row in allocations)
    assert all(row["allocator_sha256"] == module.EXPECTED_ALLOCATOR_SHA256 for row in allocations)
