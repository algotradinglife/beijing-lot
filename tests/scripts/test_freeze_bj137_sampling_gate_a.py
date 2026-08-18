"""Contract tests for #137's outcome-unexposed sampling Gate-A runner."""
from __future__ import annotations

import importlib.util
import csv
import gzip
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "freeze_bj137_sampling_gate_a.py"
PACKAGE = ROOT / "results" / "bj137_gate_a_preoutcome_v2"


def load():
    spec = importlib.util.spec_from_file_location("bj137_gate_a", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_market_devig_and_bins_are_fixed_before_any_settlement() -> None:
    mod = load()
    p = mod.devig((2.0, 4.0, 4.0))
    assert p == {"3": 0.5, "1": 0.25, "0": 0.25}
    assert [mod.probability_bin(value) for value in (0.0, 0.099, 0.1, 0.999, 1.0)] == [0, 0, 1, 9, 9]
    assert mod.handicap_bucket(-0.25) == "NEGATIVE"
    assert mod.handicap_bucket(0.0) == "ZERO"
    assert mod.handicap_bucket(0.25) == "POSITIVE"


def test_market_mapping_uses_only_supplied_prior_aggregate_counts() -> None:
    mod = load()
    counts = {
        "cell": {("3", "ZERO", 5): [200, 140], ("1", "ZERO", 3): [200, 70], ("0", "ZERO", 2): [200, 30]},
        "code_bin": {},
        "code": {"3": [1000, 600], "1": [1000, 300], "0": [1000, 100]},
    }
    mapped, diagnostics = mod.mapped_market_probability({"3": 0.55, "1": 0.35, "0": 0.10}, "ZERO", counts)
    assert abs(sum(mapped.values()) - 1.0) < 1e-12
    assert mapped["3"] > mapped["1"] > mapped["0"]
    assert diagnostics["3"] == (200, 140, 0, 0, 1000, 600)
    assert "outcome_features" not in mod.mapped_market_probability.__code__.co_names


def test_product_ticket_mass_and_expected_unique_formula() -> None:
    mod = load()
    vectors = [{"3": 0.6, "1": 0.3, "0": 0.1}] * 7
    weights = mod.ticket_weights(vectors)
    assert len(weights) == mod.FULL_K == 2187
    assert abs(sum(weight for _, weight in weights) - 1.0) < 1e-12
    single = mod.expected_unique_coverage([weight for _, weight in weights], 1)
    assert abs(single - 1.0) < 1e-12
    repeated = mod.expected_unique_coverage([weight for _, weight in weights], 64)
    assert 1.0 < repeated < 64.0
    assert math.isclose(1.0 - (1.0 - 0.2) ** 3, 0.488, rel_tol=0.0, abs_tol=1e-12)


def test_fixed_seed_sampling_has_declared_duplicate_and_distinct_semantics() -> None:
    mod = load()
    weights = mod.ticket_weights([{"3": 0.8, "1": 0.15, "0": 0.05}] * 7)
    first = mod.weighted_with_replacement(weights, 128, 137001, "identity")
    assert first == mod.weighted_with_replacement(weights, 128, 137001, "identity")
    assert len(first) == 128
    assert len(set(first)) < len(first)  # repeated draws retain distinct stakes
    distinct = mod.weighted_without_replacement(weights, 128, 137001, "identity")
    assert distinct == mod.weighted_without_replacement(weights, 128, 137001, "identity")
    assert len(distinct) == len(set(distinct)) == 128
    top = mod.top_mass(weights, 128)
    assert len(top) == len(set(top)) == 128


def test_contract_has_complete_gate_and_sampling_surface_without_tmp_staging() -> None:
    mod = load()
    assert len(mod.GATES) == 10
    assert mod.GATES[0]["gate_id"] == "NO_GATE"
    assert mod.M_GRID[-1] == mod.FULL_K == 2187
    plan = mod.sampler_plan_rows()
    assert {row["sampler_id"] for row in plan} >= {
        "FULL_N7_CONTROL", "TOP_MODEL_P_CAL_DISTINCT", "MODEL_P_CAL_WR_DUPLICATE_STAKES",
        "MODEL_P_CAL_WOR_DISTINCT", "MARKET_WF_CAL_WOR_DISTINCT", "Q_INFORMED_WOR_DISTINCT",
        "P_MIN_GLOBAL_DELETE_CONTROL", "Q_MIN_GLOBAL_DELETE_CONTROL",
    }
    assert {row["M"] for row in plan if row["sampler_id"] == "TOP_MODEL_P_CAL_DISTINCT"} == set(mod.M_GRID)
    source = SCRIPT.read_text(encoding="utf-8")
    assert "dir=output.parent" in source
    assert 'mkdtemp(prefix=".bj137_gate_a_", dir=output.parent)' in source


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            value.update(block)
    return value.hexdigest()


def gzip_rows(name: str):
    with gzip.open(PACKAGE / name, "rt", newline="", encoding="utf-8") as handle:
        yield from csv.DictReader(handle)


def test_real_freeze_has_complete_manifest_and_required_primary_surface() -> None:
    manifest = json.loads((PACKAGE / "SHA256SUMS.json").read_text())
    assert manifest == {
        item.name: digest(item)
        for item in PACKAGE.iterdir()
        if item.is_file() and item.name != "SHA256SUMS.json"
    }
    card = json.loads((PACKAGE / "gate_a_card.json").read_text())
    assert card["stage"] == "GATE_A_OUTCOME_UNEXPOSED_COMPLETE_ISSUE_SAMPLING_FREEZE"
    assert card["denominator"] == {
        "eligible_matches": 47819,
        "issue_instances": 348,
        "gates": 10,
        "top_k_arms": 5,
        "portfolio_identities": 71704,
        "role_rows": 501928,
        "issue_participation_rows": 17400,
    }
    assert card["source"]["database_sha256"] == "7f62079b18b3c028884da92aa8393f5b198246c9d7c32cd0b401562a055c5d6f"
    assert card["gate_b_requirements"]["authorization"].startswith("NOT_RUN")
    assert "No test outcome" in card["outcome_boundary"]

    plans = list(csv.DictReader((PACKAGE / "sampler_plan.csv").open(newline="")))
    assert {row["gate_id"] for row in plans} == {gate["gate_id"] for gate in load().GATES}
    assert {row["M"] for row in plans if row["sampler_id"] == "MODEL_P_CAL_WOR_DISTINCT"} == {
        str(value) for value in load().M_GRID
    }
    assert {row["seed"] for row in plans if row["sampler_id"] == "MODEL_P_CAL_WR_DUPLICATE_STAKES"} == {
        "137001", "137002", "137003"
    }
    assert {row["top_k_id"] for row in plans} == {"K1", "K2", "K4", "K8", "K_ALL"}
    assert {row["M_scope"] for row in plans} == {"PER_N7_IDENTITY"}
    assert all(
        row["duplicate_policy"] == "DUPLICATE_STAKES"
        for row in plans
        if row["sampler_id"] == "MODEL_P_CAL_WR_DUPLICATE_STAKES"
    )

    participation = list(csv.DictReader((PACKAGE / "issue_participation_grid.csv").open(newline="")))
    assert len(participation) == 348 * 10 * 5
    assert {row["top_k_id"] for row in participation} == {"K1", "K2", "K4", "K8", "K_ALL"}
    assert {row["sample_M_scope"] for row in participation} == {
        "PER_N7_IDENTITY; issue total is selected_identity_count × M"
    }
    for row in participation:
        assert int(row["full_ticket_count"]) == int(row["selected_identity_count"]) * 2187
        assert int(row["full_stake_yuan"]) == int(row["full_ticket_count"]) * 2
        if row["disposition"] == "AVAILABLE":
            requested = row["requested_n7_count"]
            if requested != "ALL":
                assert int(row["selected_identity_count"]) == int(requested)
        else:
            assert row["selected_identity_count"] == "0"


def test_real_freeze_keeps_issue_whole_and_vector_roles_normalized() -> None:
    gate_census = list(csv.DictReader((PACKAGE / "gate_issue_census.csv").open(newline="")))
    assert len(gate_census) == 3480
    assert Counter(row["gate_id"] for row in gate_census) == {
        gate["gate_id"]: 348 for gate in load().GATES
    }
    assert {row["selection_scope"] for row in gate_census} == {"COMPLETE_ISSUE"}
    assert all(int(row["full_ticket_count"]) == int(row["portfolio_identity_count"]) * 2187 for row in gate_census)

    identities = list(gzip_rows("n7_identities.csv.gz"))
    assert len(identities) == 71704
    assert len({(row["gate_id"], row["portfolio_id"]) for row in identities}) == len(identities)
    assert {row["segment_boundary"] for row in identities} == {"NONE; source segments are diagnostic-only"}
    assert {row["selected_n"] for row in identities} == {"7"}
    assert all(int(row["candidate_search_count"]) <= 32 for row in identities)
    assert all(int(row["participation_rank"]) >= 1 for row in identities)

    grouped = defaultdict(list)
    for row in gzip_rows("n7_role_vectors.csv.gz"):
        grouped[(row["gate_id"], row["portfolio_id"])].append(row)
        for prefix in ("p_model", "p_market_raw", "p_market_cal", "p_blend_a25_", "p_blend_a50_", "p_blend_a75_", "q_weight"):
            values = [float(row[f"{prefix}{code}"]) for code in ("3", "1", "0")]
            assert abs(sum(values) - 1.0) < 2e-9
    assert len(grouped) == 71704
    assert {len(rows) for rows in grouped.values()} == {7}


def test_real_freeze_market_mapping_is_chronological_and_aggregate_only() -> None:
    census = list(csv.DictReader((PACKAGE / "market_calibration_census.csv").open(newline="")))
    assert [row["test_year"] for row in census] == [str(year) for year in range(2019, 2026)]
    assert {row["test_outcomes_read"] for row in census} == {"0"}
    assert all(row["train_years"].endswith(str(int(row["test_year"]) - 1)) for row in census)
    mapping = list(csv.DictReader((PACKAGE / "market_calibration_map.csv").open(newline="")))
    assert len(mapping) == 7 * 4 * 10 * 3
    assert {row["fallback_order"] for row in mapping} == {
        "code×handicap_bucket×probability_bin;code×probability_bin;code"
    }
    assert all(int(row["code_n"]) > 0 for row in mapping)
