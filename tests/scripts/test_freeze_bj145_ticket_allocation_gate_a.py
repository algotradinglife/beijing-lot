from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "results" / "bj145_gate_a_preoutcome_v8"
MANIFEST = "da1165d3d2be49deac85a494443ba04606d176ca059c265857573ce24360114c"
SOURCE_137 = ROOT / "results" / "bj137_gate_a_preoutcome_v2"
SOURCE_137_MANIFEST = "0aabeb94cec6d68831d233553e710b425bf02c1a843eae21adad50c4f9fac2df"


def rows(path: Path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def gzip_rows(path: Path):
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def package_engine():
    spec = importlib.util.spec_from_file_location("bj145_package_engine", PACKAGE / "bj145_allocation_engine.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_manifest_is_self_consistent_and_bound():
    manifest_path = PACKAGE / "SHA256SUMS.json"
    assert hashlib.sha256(manifest_path.read_bytes()).hexdigest() == MANIFEST
    declared = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = {
        item.name: hashlib.sha256(item.read_bytes()).hexdigest()
        for item in PACKAGE.iterdir()
        if item.is_file() and item.name != "SHA256SUMS.json"
    }
    assert declared == actual


def test_gate_a_contract_and_denominators():
    card = json.loads((PACKAGE / "gate_a_card.json").read_text(encoding="utf-8"))
    assert card["stage"] == "GATE_A_OUTCOME_UNEXPOSED_TICKET_ALLOCATION_FREEZE"
    assert card["gate_b_requirements"]["authorization"].startswith("NOT_RUN")
    assert card["denominator"] == {
        "allocation_plan_rows": 1_006_416,
        "cohort_rows": 696,
        "identity_rows": 3_540,
        "m_points": 20,
        "primary_available": 339,
        "primary_no_bet": 9,
        "role_rows": 24_780,
        "secondary_available": 273,
        "secondary_no_bet": 75,
        "seed_count": 3,
        "weight_sources": 6,
    }
    assert card["weights"] == ["MODEL_P_CAL", "MARKET_WF_CAL", "BLEND_A25", "BLEND_A50", "BLEND_A75", "Q_WEIGHT"]
    assert card["caps"] == [1, 2, 4, 8]
    assert card["m_grid"] == list(range(16, 257, 16)) + [512, 1024, 1458, 2187]
    assert card["mechanisms"] == [
        "WR_DUPLICATE_STAKE", "WOR_DISTINCT", "RESIDUAL_SYSTEMATIC", "CAPPED_REPEAT",
        "DETERMINISTIC_TOP_MASS", "FULL_ENUMERATED",
    ]
    binding = json.loads((PACKAGE / "allocation_binding.json").read_text(encoding="utf-8"))
    assert card["allocation_binding"] == binding
    assert binding["binding_version"] == "bj145-allocation-binding-v2"
    assert hashlib.sha256((PACKAGE / binding["module_file"]).read_bytes()).hexdigest() == binding["module_sha256"]
    assert hashlib.sha256((PACKAGE / binding["golden_vectors_file"]).read_bytes()).hexdigest() == binding["golden_vectors_sha256"]
    assert binding["ticket_space"] == {"legs": 7, "outcomes_per_leg": 3, "k": 2187, "codes": ["3", "1", "0"], "ordinal_order": "#137 product order"}
    assert binding["identity_signature_rule"] == "exact selected_match_ids pipe string from frozen identity row; no portfolio_id substitution"


def test_selection_and_role_geometry():
    cohort = rows(PACKAGE / "selection_cohort.csv")
    assert len(cohort) == 696
    assert Counter((r["arm_id"], r["selection_status"]) for r in cohort) == Counter({
        ("PRIMARY_NO_GATE_K4", "AVAILABLE"): 339,
        ("PRIMARY_NO_GATE_K4", "NO_BET_K_UNSATISFIED"): 9,
        ("SECONDARY_ESP300_GM290_K8", "AVAILABLE"): 273,
        ("SECONDARY_ESP300_GM290_K8", "NO_BET_K_UNSATISFIED"): 75,
    })
    identities = gzip_rows(PACKAGE / "identity_catalog.csv.gz")
    role_rows = gzip_rows(PACKAGE / "role_vectors.csv.gz")
    assert len(identities) == 3540
    assert len(role_rows) == 24780
    ids = {(r["arm_id"], r["issue_instance"], r["portfolio_id"]) for r in identities}
    assert len(ids) == len(identities)
    role_counts = Counter((r["arm_id"], r["issue_instance"], r["portfolio_id"]) for r in role_rows)
    assert set(role_counts.values()) == {7}
    assert set(role_counts) == ids
    for row in identities:
        assert row["selected_n"] == "7"
        assert row["outcome_boundary"].startswith("No outcome")


def test_complete_plan_surface_and_per_ticket_accounting():
    plans = gzip_rows(PACKAGE / "allocation_plan.csv.gz")
    assert len(plans) == 1_006_416
    assert len({r["plan_id"] for r in plans}) == len(plans)
    assert Counter(r["mechanism"] for r in plans) == {
        "CAPPED_REPEAT": 334_080,
        "DETERMINISTIC_TOP_MASS": 83_520,
        "FULL_ENUMERATED": 4_176,
        "RESIDUAL_SYSTEMATIC": 83_520,
        "WOR_DISTINCT": 250_560,
        "WR_DUPLICATE_STAKE": 250_560,
    }
    for row in plans:
        count, m = int(row["selected_identity_count"]), int(row["M"])
        expected = count * m * 2 if row["selection_status"] == "AVAILABLE" else 0
        assert int(row["planned_draw_count"]) == (count * m if row["selection_status"] == "AVAILABLE" else 0)
        assert int(row["planned_stake_yuan"]) == expected
        assert row["outcome_boundary"].startswith("No outcome")
    mechanisms = rows(PACKAGE / "mechanism_contract.csv")
    assert len(mechanisms) == 6
    assert all("no" in row["tax_unit_rule"] and "pooling" in row["tax_unit_rule"] for row in mechanisms)
    assert all(row["expected_unique_formula"] for row in mechanisms)
    assert all(row["realized_unique_rule"] for row in mechanisms)


def test_no_target_outcome_fields_in_frozen_payload_headers():
    forbidden = {"result", "score", "final_sp", "winning_sp", "payout", "settlement", "roi", "tax"}
    for path in (PACKAGE / "identity_catalog.csv.gz", PACKAGE / "role_vectors.csv.gz", PACKAGE / "allocation_plan.csv.gz"):
        with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
            fields = next(csv.reader(handle))
        fields = [field for field in fields if field not in {"tax_unit_rule", "outcome_boundary"}]
        assert not any(any(token in field.lower() for token in forbidden) for field in fields)


def test_executable_allocator_golden_vectors_and_fingerprints():
    module = package_engine()
    vectors = json.loads((PACKAGE / "allocation_golden_vectors.json").read_text(encoding="utf-8"))
    assert vectors["engine_version"] == module.ENGINE_VERSION
    weights = module.golden_weights(2187)
    assert len(vectors["cases"]) == 6
    for case in vectors["cases"]:
        counts = module.allocate(
            case["mechanism"], weights, case["M"], seed=case["seed"],
            identity_signature=case["identity_signature"], cap=case["cap"],
        )
        fingerprint = module.counts_fingerprint(counts)
        assert fingerprint == {
            "counts_sha256": case["counts_sha256"],
            "draw_count": case["draw_count"],
            "unique_count": case["unique_count"],
            "duplicate_count": case["duplicate_count"],
            "max_multiplicity": case["max_multiplicity"],
        }
        assert sum(counts) == case["M"]
        if case["mechanism"] in {"WOR_DISTINCT", "DETERMINISTIC_TOP_MASS", "FULL_ENUMERATED"}:
            assert max(counts) <= 1
        if case["mechanism"] == "CAPPED_REPEAT":
            assert max(counts) <= case["cap"]


def test_wr_wor_namespace_parity_against_immutable_137_runner():
    assert hashlib.sha256((SOURCE_137 / "SHA256SUMS.json").read_bytes()).hexdigest() == SOURCE_137_MANIFEST
    source = load_module(SOURCE_137 / "freeze_runner.py", "bj137_namespace_reference")
    module = package_engine()
    for parts in (("bj137", "WR", 137001, "identity", 0), ("bj137", "WOR", 137002, "identity", 41)):
        assert module.stable_uniform(*parts) == source.stable_uniform(*parts)
    identity = gzip_rows(SOURCE_137 / "n7_identities.csv.gz")[0]
    identity_signature = identity["selected_match_ids"]
    roles = [
        row for row in gzip_rows(SOURCE_137 / "n7_role_vectors.csv.gz")
        if row["issue_instance"] == identity["issue_instance"] and row["portfolio_id"] == identity["portfolio_id"]
    ]
    roles.sort(key=lambda row: int(row["match_idx"]))
    leg_vectors = [{code: float(row[f"p_model{code}"]) for code in source.CODES} for row in roles]
    reference_weights = source.ticket_weights(leg_vectors)
    flat_weights = [mass for _, mass in reference_weights]
    ordinal = {ticket: index for index, (ticket, _) in enumerate(reference_weights)}
    for seed in (137001, 137002, 137003):
        expected_wr = [0] * source.FULL_K
        for ticket in source.weighted_with_replacement(reference_weights, 32, seed, identity_signature):
            expected_wr[ordinal[ticket]] += 1
        actual_wr = module.allocate("WR_DUPLICATE_STAKE", flat_weights, 32, seed=str(seed), identity_signature=identity_signature)
        assert actual_wr == tuple(expected_wr)
        expected_wor = [0] * source.FULL_K
        for ticket in source.weighted_without_replacement(reference_weights, 32, seed, identity_signature):
            expected_wor[ordinal[ticket]] += 1
        actual_wor = module.allocate("WOR_DISTINCT", flat_weights, 32, seed=str(seed), identity_signature=identity_signature)
        assert actual_wor == tuple(expected_wor)


def test_wr_raw_unit_real_cell_m2187_regression_against_137():
    source = load_module(SOURCE_137 / "freeze_runner.py", "bj137_real_cell_reference")
    module = package_engine()
    identity = next(
        row for row in gzip_rows(PACKAGE / "identity_catalog.csv.gz")
        if row["arm_id"] == "SECONDARY_ESP300_GM290_K8"
        and row["issue_instance"] == "20101@OOS_2020"
        and row["portfolio_id"] == "7c1f7df8c2a7f25df04ce7e31daf6258817e6a13b9a03eff53a00d418ed35b67"
    )
    roles = [
        row for row in gzip_rows(PACKAGE / "role_vectors.csv.gz")
        if row["arm_id"] == identity["arm_id"]
        and row["issue_instance"] == identity["issue_instance"]
        and row["portfolio_id"] == identity["portfolio_id"]
    ]
    roles.sort(key=lambda row: int(row["match_idx"]))
    reference_weights = source.ticket_weights([{code: float(row[f"p_blend_a50_{code}"]) for code in source.CODES} for row in roles])
    flat_weights = [mass for _, mass in reference_weights]
    expected = [0] * source.FULL_K
    ordinal = {ticket: index for index, (ticket, _) in enumerate(reference_weights)}
    selected = source.weighted_with_replacement(reference_weights, 2187, 137003, identity["selected_match_ids"])
    for ticket in selected:
        expected[ordinal[ticket]] += 1
    actual = module.allocate(
        "WR_DUPLICATE_STAKE", flat_weights, 2187, seed="137003",
        identity_signature=identity["selected_match_ids"],
    )
    assert actual == tuple(expected)
    assert actual[427] == 1
    assert actual[428] == 0
