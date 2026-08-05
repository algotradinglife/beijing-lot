from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import inspect
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "freeze_bj193_chain_interface_gate_a_v2.py"
PACKAGE = ROOT / "results" / "bj193_gate_a_chain_interface_v2"


def load_module():
    spec = importlib.util.spec_from_file_location("bj193_chain_gate_a_v2", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def csv_count(path: Path) -> int:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", newline="", encoding="utf-8") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def test_v2_verifies_only_outcome_unexposed_gate_a_sources_and_v1_lineage():
    module = load_module()
    rows = module.verify_sources()
    assert len(rows) == 7
    assert rows[0]["package"] == "bj193_gate_a_preoutcome_v1"
    assert rows[0]["manifest_sha256"] == module.V1_MANIFEST_SHA256
    assert rows[0]["content_sha256"] == module.V1_CONTENT_SHA256
    assert {row["issue"] for row in rows[1:]} == {127, 134, 137, 145, 167, 190}
    assert all(row["access"] == "OUTCOME_UNEXPOSED_GATE_A_ONLY" for row in rows)
    assert all("gate_b" not in row["package"] for row in rows)
    assert all("settlement" not in row["parsed_files"] for row in rows)


def test_stage_catalogs_preserve_upstream_identity_and_are_not_joint_product():
    module = load_module()
    stage1 = module.stage1_catalog()
    stage2 = module.stage2_catalog()
    stage3 = module.stage3_catalog()
    assert len(stage1) == 2469
    assert len(stage2) == 2425
    assert len(stage3) == 963
    for rows, stage in (
        (stage1, "STAGE_1_SELECTION"),
        (stage2, "STAGE_2_DIRECTION"),
        (stage3, "STAGE_3_BET"),
    ):
        assert {row["stage"] for row in rows} == {stage}
        assert all(row["upstream_source_identity_bound"] is True for row in rows)
        assert len({row["interface_action_key"] for row in rows}) == len(rows)
        assert all(row["source_identity"] for row in rows)
    assert all(row["preserved_source_identity"] is True for row in stage1)
    assert sum(row["preserved_source_identity"] is True for row in stage2) == 1
    assert sum(row["preserved_source_identity"] is False for row in stage2) == 2424
    assert all(row["preserved_source_identity"] is False for row in stage3)
    assert all(
        row["derived_interface_identity_sha256"] and row["adapter_sha256"]
        for row in stage2
        if row["preserved_source_identity"] is False
    )
    assert all(
        row["interface_semantics"]
        == "DERIVED_STAGE2_CONDITIONAL_ACTION_WITH_BOUND_167_PARAMETERS"
        for row in stage3
    )
    assert {row["upstream_issue"] for row in stage1} == {127, 134, 190}
    assert {row["upstream_issue"] for row in stage2} == {190}
    assert {row["upstream_issue"] for row in stage3} == {167}
    assert sum(row["availability"] == "AVAILABLE" for row in stage2) == 2365
    assert all("seed" not in row["source_identity"].lower() for row in stage3)
    assert {json.loads(row["parameters_json"])["M"] for row in stage3} >= {
        "16", "64", "2187"
    }


def test_conditional_direction_adapter_binds_exact_stage1_support_and_190_estimators():
    module = load_module()
    adapter = module.load_module(module.ADAPTER_PATH, "bj193_test_adapter_direction")
    golden = module.direction_adapter_golden_fixture()
    output = golden["expected_output"]
    assert golden["reconstructed_190_joint_allocation_input_sha256"] == golden[
        "accepted_190_joint_allocation_input_sha256"
    ]
    assert output["status"] == "ACTIVE"
    assert output["reason_code"] == "DERIVED_STAGE1_CONDITIONAL_DIRECTION"
    assert output["strongest_match_id"] == "90622"
    assert output["omitted_code"] == "0"
    assert output["delete_leg_index_zero_based"] == 0
    assert output["ticket_support_size"] == 1458
    assert len(output["per_match"]) == 7
    assert [row["match_id"] for row in output["per_match"]] == golden["input"][
        "selected_match_ids"
    ]
    strongest = output["per_match"][0]
    assert strongest["allowed_codes"] == ["3", "1"]
    assert strongest["direction_weight_3_1_0"][2] == "0.000000000000"
    assert all(len(row["estimator_identity_sha256"]) == 64 for row in output["per_match"])
    assert all(
        row["estimator_component_identity_sha256"]
        for row in output["per_match"]
    )

    package = ROOT / "results" / "bj190_gate_a_preoutcome_v3r1"
    policy = next(
        row
        for row in module.read_csv(package / "detector_grid.csv")
        if row["policy_id"] == golden["input"]["policy_id"]
    )
    wanted = set(golden["input"]["selected_match_ids"])
    estimator = {
        row["match_id"]: row
        for row in module.read_csv(package / "estimator_match_freeze.csv.gz")
        if row["match_id"] in wanted
    }
    reordered = list(reversed(golden["input"]["selected_match_ids"]))
    replay = adapter.apply_direction_adapter(
        reordered,
        estimator,
        policy,
        stage1_output_sha256="1" * 64,
        adapter_sha256=module.sha256_file(module.ADAPTER_PATH),
    )
    assert replay["status"] == "ACTIVE"
    assert replay["ordered_match_ids"] == reordered
    assert replay["strongest_match_id"] == "90622"
    assert replay["delete_leg_index_zero_based"] == 6
    assert replay["derived_direction_action_sha256"] == output[
        "derived_direction_action_sha256"
    ]
    impossible = dict(policy, abs_delta_p_min="1.1")
    no_bet = adapter.apply_direction_adapter(
        reordered,
        estimator,
        impossible,
        stage1_output_sha256="2" * 64,
        adapter_sha256=module.sha256_file(module.ADAPTER_PATH),
    )
    assert no_bet["status"] == "NO_BET"
    assert no_bet["reason_code"] == "THRESHOLD_NOT_MET"
    assert no_bet["ticket_support_size"] == 0
    with pytest.raises(ValueError, match="forbidden outcome fields"):
        adapter.apply_direction_adapter(
            reordered,
            estimator,
            dict(policy, result_code="3"),
            stage1_output_sha256="3" * 64,
            adapter_sha256=module.sha256_file(module.ADAPTER_PATH),
        )


def test_composite_direction_identity_binds_every_compared_estimator_component():
    module = load_module()
    adapter = module.load_module(module.ADAPTER_PATH, "bj193_test_composite_identity")
    package = ROOT / "results" / "bj190_gate_a_preoutcome_v3r1"
    policy = next(
        row
        for row in module.read_csv(package / "detector_grid.csv")
        if row["detector_family"] == "DELTA_P"
        and row["estimator_variant"] == "UNION"
        and row["availability"] == "AVAILABLE"
    )
    row = next(
        row
        for row in module.read_csv(package / "estimator_match_freeze.csv.gz")
        if row["target_safe_consensus_status"] == "AVAILABLE"
    )
    metric = adapter.metric_for_match(row, policy)
    assert metric is not None
    binding = adapter.estimator_identity_binding(row, policy, metric)
    assert set(binding["components"]) == {
        "t1_score_estimator_identity_sha256",
        "target_safe_consensus_identity_sha256",
    }
    changed = dict(row, target_safe_consensus_identity_sha256="f" * 64)
    changed_metric = adapter.metric_for_match(changed, policy)
    assert changed_metric is not None
    changed_binding = adapter.estimator_identity_binding(
        changed, policy, changed_metric
    )
    assert changed_binding["binding_sha256"] != binding["binding_sha256"]


def test_conditional_builder_executes_all_golden_mechanisms_and_zero_flow_edges():
    module = load_module()
    adapter = module.load_module(module.ADAPTER_PATH, "bj193_test_adapter_builder")
    engine = adapter.load_frozen_allocation_engine(module.ALLOCATION_ENGINE_PATH)
    assert module.sha256_file(module.ALLOCATION_ENGINE_PATH) == (
        module.ALLOCATION_ENGINE_SHA256
    )
    golden = module.conditional_builder_golden_vectors()
    actual = {}
    for case in golden["cases"]:
        spec = case["input"]
        result = adapter.allocate_conditional_tickets(
            spec["mechanism"],
            spec["per_match_weight_3_1_0"],
            spec["M"],
            allocation_engine=engine,
            issue=spec["issue"],
            stage1_output_sha256=spec["stage1_output_sha256"],
            stage2_output_sha256=spec["stage2_output_sha256"],
            derived_stage3_action_sha256=spec[
                "derived_stage3_action_sha256"
            ],
            seed=spec["seed"],
            cap=spec["cap"],
        )
        comparable = {key: value for key, value in result.items() if key != "counts"}
        assert comparable == case["expected"]
        if result["status"] == "ACTIVE":
            assert not any(
                count and weight <= 0
                for count, weight in zip(
                    result["counts"],
                    adapter.canonical_ticket_weight_vector(
                        spec["per_match_weight_3_1_0"]
                    ),
                    strict=True,
                )
            )
        actual[case["case"]] = comparable
    assert actual["ALLOW_ALL_FULL"]["requested_ticket_count"] == 2187
    assert actual["ONE_DELETE_WOR_M64"]["positive_support_count"] == 1458
    assert actual["INSUFFICIENT_WOR_M2187"]["status"] == "NO_BET"
    assert actual["INSUFFICIENT_WOR_M2187"]["requested_stake_yuan"] == 0
    assert actual["REDUCED_FULL_FALLBACK"]["requested_ticket_count"] == 1458
    assert actual["REDUCED_FULL_FALLBACK"]["reason_code"] == (
        "ENUMERATE_UPSTREAM_SUPPORT_FALLBACK"
    )
    assert "identity_signature" not in inspect.signature(
        adapter.allocate_conditional_tickets
    ).parameters


def test_stage3_replay_signature_is_internal_deterministic_and_upstream_sensitive():
    module = load_module()
    adapter = module.load_module(module.ADAPTER_PATH, "bj193_test_replay_signature")
    engine = adapter.load_frozen_allocation_engine(module.ALLOCATION_ENGINE_PATH)
    weights = [[0.52, 0.28, 0.20] for _ in range(7)]
    base = {
        "issue": "26080",
        "stage1_output_sha256": "1" * 64,
        "stage2_output_sha256": "2" * 64,
        "derived_stage3_action_sha256": "3" * 64,
    }

    def allocate(context):
        return adapter.allocate_conditional_tickets(
            "WR_DUPLICATE_STAKE",
            weights,
            128,
            allocation_engine=engine,
            seed="137001",
            **context,
        )

    first = allocate(base)
    replay = allocate(base)
    assert first["stage3_replay_signature_sha256"] == replay[
        "stage3_replay_signature_sha256"
    ]
    assert first["counts_sha256"] == replay["counts_sha256"]
    for field, replacement in (
        ("issue", "26081"),
        ("stage1_output_sha256", "4" * 64),
        ("stage2_output_sha256", "5" * 64),
        ("derived_stage3_action_sha256", "6" * 64),
    ):
        changed = allocate({**base, field: replacement})
        assert changed["stage3_replay_signature_sha256"] != first[
            "stage3_replay_signature_sha256"
        ]
        assert changed["counts_sha256"] != first["counts_sha256"]


def test_stage2_stage3_weight_mapping_binds_real_137_role_vectors_and_masks():
    module = load_module()
    adapter = module.load_module(module.ADAPTER_PATH, "bj193_test_role_mapping")
    golden = module.conditional_builder_golden_vectors()[
        "role_vector_mapping_golden"
    ]
    ordered = golden["ordered_match_ids"]
    roles = {row["match_id"]: row for row in golden["complete_match_rows"]}
    directions = golden["stage2_direction_rows"]
    assert module.sha256_file(module.ROLE_VECTOR_PATH) == module.ROLE_VECTOR_SHA256
    for case in golden["mapping_cases"]:
        actual = adapter.combine_stage2_and_stage3_weights(
            ordered, directions, roles, case["weight_source"]
        )
        assert actual == case["expected_output"]
        assert actual["status"] == "ACTIVE"
        assert actual["per_match_weight_3_1_0"][0][2] == "0.000000000000"
        assert len(actual["role_identity_sha256_by_match"]) == 7
    q_case = next(
        case["expected_output"]
        for case in golden["mapping_cases"]
        if case["weight_source"] == "Q_WEIGHT"
    )
    assert q_case["per_match_weight_3_1_0"][1] == [
        "0.166666666667", "0.100000000000", "0.066666666667"
    ]
    missing = dict(roles)
    missing.pop(ordered[-1])
    unavailable = adapter.combine_stage2_and_stage3_weights(
        ordered, directions, missing, "Q_WEIGHT"
    )
    assert unavailable["status"] == "UNAVAILABLE"
    assert unavailable["reason_code"] == "STAGE3_ROLE_VECTOR_MISSING"
    assert unavailable["per_match_weight_3_1_0"] == []
    mismatched = {key: dict(value) for key, value in roles.items()}
    mismatched[ordered[-1]]["match_id"] = "NOT_THE_MAPPED_MATCH"
    identity_failure = adapter.combine_stage2_and_stage3_weights(
        ordered, directions, mismatched, "Q_WEIGHT"
    )
    assert identity_failure["status"] == "UNAVAILABLE"
    assert identity_failure["reason_code"] == "STAGE3_MATCH_IDENTITY_MISMATCH"
    legacy_roles = {
        row["match_id"]: row for row in golden["role_rows"]
    }
    no_legacy_fallback = adapter.combine_stage2_and_stage3_weights(
        ordered, directions, legacy_roles, "Q_WEIGHT"
    )
    assert no_legacy_fallback["status"] == "UNAVAILABLE"
    assert no_legacy_fallback["reason_code"] == (
        "STAGE3_WEIGHT_REGISTRY_KIND_MISMATCH"
    )
    # Unit-weight controls do not depend on a #137 role row.
    control = adapter.combine_stage2_and_stage3_weights(
        ordered, directions, {}, "NA"
    )
    assert control["status"] == "ACTIVE"
    assert control["source_portfolio_id"] == "NA"


def test_complete_match_registry_and_stage1_stage3_coverage_fail_closed():
    module = load_module()
    stage1 = module.stage1_catalog()
    stage3 = module.stage3_catalog()
    weights = module.complete_match_weight_registry()
    assert len(weights) == 47_819
    assert {row["registry_kind"] for row in weights} == {
        "BJ137_COMPLETE_MATCH_WEIGHT_REGISTRY_V1"
    }
    assert all(len(row["weight_registry_row_sha256"]) == 64 for row in weights)
    native = module.native_137_weight_reconciliation(weights)
    assert native["role_row_count"] == native["matched_role_row_count"]
    assert native["missing_role_row_count"] == 0
    assert native["mismatched_role_row_count"] == 0

    classes = module.stage3_compatibility_class_registry(stage3)
    assert len(classes) == 7
    assert sum(int(row["stage3_action_count"]) for row in classes) == 963
    coverage = module.stage1_stage3_coverage_registry(stage1, weights, classes)
    assert len(coverage) == 2_469 * 7
    assert sum(int(row["stage3_action_count"]) for row in coverage) == (
        2_469 * 963
    )
    non_na_127 = [
        row
        for row in coverage
        if row["stage1_upstream_issue"] == 127
        and row["stage3_weight_source"] != "NA"
    ]
    non_na_134 = [
        row
        for row in coverage
        if row["stage1_upstream_issue"] == 134
        and row["stage3_weight_source"] != "NA"
    ]
    non_na_190 = [
        row
        for row in coverage
        if row["stage1_upstream_issue"] == 190
        and row["stage3_weight_source"] != "NA"
    ]
    assert non_na_127 and non_na_134 and non_na_190
    assert {row["compatibility_status"] for row in non_na_127} == {
        "COMPATIBLE"
    }
    assert {row["complete_registry_coverage_fraction"] for row in non_na_127} == {
        "1.000000000000"
    }
    assert {row["compatibility_status"] for row in non_na_134} == {
        "COMPATIBLE"
    }
    assert {row["complete_registry_coverage_fraction"] for row in non_na_134} == {
        "1.000000000000"
    }
    assert "COMPATIBLE" not in {
        row["compatibility_status"] for row in non_na_190
    }
    assert all("NONE" in row["fallback_rule"] for row in coverage)
    assert all(
        row["reason_code"] == "INCOMPLETE_PRE_EVENT_WEIGHT_COVERAGE_NO_FALLBACK"
        for row in non_na_190
        if row["selected_output_count"]
        and int(row["selected_output_count"]) >= module.MIN_CHRONOLOGICAL_SUPPORT
        and int(row["supported_fold_count"]) >= module.MIN_CHRONOLOGICAL_FOLDS
        and row["compatibility_status"] == "INCOMPATIBLE"
    )


def test_chain_interfaces_bind_every_upstream_digest_and_match_support():
    module = load_module()
    fixture = module.chain_fixture()
    trace = fixture["trace"]
    module.validate_chain_trace(trace)
    assert trace["stage2"]["stage1_output_sha256"] == trace["stage1"]["output_sha256"]
    assert trace["stage3"]["stage2_output_sha256"] == trace["stage2"]["output_sha256"]
    assert trace["stage1"]["selected_match_ids_json"] == trace["stage2"]["ordered_match_ids_json"]
    assert trace["stage2"]["ordered_match_ids_json"] == trace["stage3"]["ordered_match_ids_json"]
    assert trace["stage2"]["per_match_outcome_weight_json"] == trace["stage3"]["per_match_outcome_weight_json"]
    adapter = module.load_module(module.ADAPTER_PATH, "bj193_test_trace_signature")
    assert trace["stage3"]["stage3_replay_signature_sha256"] == (
        adapter.stage3_replay_signature(
            issue=trace["stage3"]["issue"],
            stage1_output_sha256=trace["stage1"]["output_sha256"],
            stage2_output_sha256=trace["stage2"]["output_sha256"],
            derived_stage3_action_sha256=trace["stage3"][
                "derived_stage3_action_sha256"
            ],
        )
    )

    changed = json.loads(json.dumps(trace))
    changed["stage1"]["selected_match_ids_json"] = module.canonical_json(
        ["DIFFERENT"] * 7
    )
    changed["stage1"]["output_sha256"] = module.digest_stage_output(changed["stage1"])
    try:
        module.validate_chain_trace(changed)
    except RuntimeError as error:
        assert "upstream Stage-1 digest drift" in str(error)
    else:
        raise AssertionError("downstream digest must fail after upstream mutation")

    replaced = json.loads(json.dumps(trace))
    replaced["stage2"]["ordered_match_ids_json"] = module.canonical_json(
        ["REPLACED"] * 7
    )
    replaced["stage2"]["output_sha256"] = module.digest_stage_output(
        replaced["stage2"]
    )
    replaced["stage3"]["stage2_output_sha256"] = replaced["stage2"][
        "output_sha256"
    ]
    replaced["stage3"]["stage3_replay_signature_sha256"] = (
        adapter.stage3_replay_signature(
            issue=replaced["stage3"]["issue"],
            stage1_output_sha256=replaced["stage1"]["output_sha256"],
            stage2_output_sha256=replaced["stage2"]["output_sha256"],
            derived_stage3_action_sha256=replaced["stage3"][
                "derived_stage3_action_sha256"
            ],
        )
    )
    replaced["stage3"]["output_sha256"] = module.digest_stage_output(
        replaced["stage3"]
    )
    try:
        module.validate_chain_trace(replaced)
    except RuntimeError as error:
        assert "replaced Stage-1 match support" in str(error)
    else:
        raise AssertionError("Stage 2 must not replace Stage-1 matches")


def test_each_stage_has_separate_target_loss_support_model_and_fallback():
    module = load_module()
    training = module.stage_training_rows()
    assert [row["stage"] for row in training] == [
        "STAGE_1_SELECTION",
        "STAGE_2_DIRECTION",
        "STAGE_3_BET",
    ]
    assert len({row["target"] for row in training}) == 3
    assert len({row["support_mask"] for row in training}) == 3
    assert all(row["loss"] and row["prior_only_fallback"] for row in training)
    assert all("out-of-fold upstream outputs" in row["training_upstream_rule"] for row in training)
    assert all("no model" in row["test_update_rule"] for row in training)
    models = module.stage_model_grid()
    assert len(models) == 90
    assert {row["stage"] for row in models} == {
        "STAGE_1_SELECTION", "STAGE_2_DIRECTION", "STAGE_3_BET"
    }
    assert all(sum(row["prior_only_fallback"] for row in models if row["stage"] == stage) == 1 for stage in {row["stage"] for row in models})
    chronology = module.chronology_contract()
    assert chronology["outer_fold_count"] == 5
    assert len(chronology["frozen_folds"]) == 5
    assert all(len(row["outer_test_issue_sha256"]) == 64 for row in chronology["frozen_folds"])
    assert "out-of-fold" in chronology["inner_training_upstream_outputs"]
    assert "do not update" in chronology["outer_test"]


def test_stagewise_learner_projection_topology_screens_and_ties_are_executable():
    module = load_module()
    projections = module.stage_feature_projection_rows()
    by_stage = {
        stage: [row for row in projections if row["stage"] == stage]
        for stage in ("STAGE_1_SELECTION", "STAGE_2_DIRECTION", "STAGE_3_BET")
    }
    assert {stage: len(rows) for stage, rows in by_stage.items()} == {
        "STAGE_1_SELECTION": 68,
        "STAGE_2_DIRECTION": 79,
        "STAGE_3_BET": 90,
    }
    assert [int(row["feature_ordinal"]) for row in by_stage["STAGE_3_BET"]] == list(
        range(1, 91)
    )
    assert all(
        row["model_input"] is False and row["audit_binding_only"] is True
        for row in projections
        if row["dtype"] == "SHA256"
    )
    hashes = module.feature_projection_hashes()
    assert len(set(hashes.values())) == 3
    learner = module.stagewise_learner_execution_contract()
    assert "one action-specific" in learner["topology"]["model_scope"]
    assert learner["stage_screen"]["STAGE_1_SELECTION"]["keep"] == 16
    assert learner["stage_screen"]["STAGE_2_DIRECTION"]["keep"] == 64
    assert learner["stage_screen"]["STAGE_3_BET"]["keep"] == 64
    assert "compatibility_status==COMPATIBLE" in learner[
        "stage1_stage3_compatibility_gate"
    ]["screen_order"]
    fixture = module.learner_execution_fixture()
    assert fixture["screen"]["expected_action_order"] == ["A", "B"]
    assert fixture["validation"]["expected_model_id"] == "M1"
    assert fixture["action_choice"]["expected_action_identity"] == "X"
    assert module.select_predicted_action(
        fixture["action_choice"]["input"], 0.03
    ) is None
    models = module.stage_model_grid()
    assert all(row["feature_projection_sha256"] == hashes[row["stage"]] for row in models)
    assert all("ONE_ACTION_SPECIFIC" in row["model_topology"] for row in models)
    assert all(row["estimator_spec"] and row["screen_order"] for row in models)


def test_portable_identity_hashes_decompressed_gzip_not_transport_bytes(tmp_path):
    module = load_module()
    content = b"a,b\n1,2\n"
    left = tmp_path / "left.csv.gz"
    right = tmp_path / "right.csv.gz"
    for path, filename, level in ((left, "left.csv", 1), (right, "right.csv", 9)):
        with path.open("wb") as raw:
            with gzip.GzipFile(
                filename=filename,
                mode="wb",
                fileobj=raw,
                compresslevel=level,
                mtime=0,
            ) as compressed:
                compressed.write(content)
    assert hashlib.sha256(left.read_bytes()).hexdigest() != hashlib.sha256(
        right.read_bytes()
    ).hexdigest()
    assert module.portable_payload_sha256(left) == module.portable_payload_sha256(
        right
    )


def test_matched_controls_and_incremental_reporting_are_chain_ordered():
    module = load_module()
    controls = module.attribution_rows()
    assert [row["control_id"] for row in controls] == [
        "ALL_STATIC",
        "DYNAMIC_SELECTION_ONLY",
        "DYNAMIC_SELECTION_DIRECTION",
        "FULL_DYNAMIC_CHAIN",
    ]
    assert [row["incremental_comparator"] for row in controls] == [
        "NA", "ALL_STATIC", "DYNAMIC_SELECTION_ONLY",
        "DYNAMIC_SELECTION_DIRECTION",
    ]
    reporting = module.incremental_reporting_contract()
    assert [row["stage"] for row in reporting["contrasts"]] == [
        "STAGE_1_SELECTION", "STAGE_2_DIRECTION", "STAGE_3_BET", "END_TO_END"
    ]
    assert "issue" in reporting["metrics"][0] or "support" in reporting["metrics"]
    assert "#193 Gate B" in reporting["parent_192"]
    trace = module.decision_trace_schema()
    assert {
        "stage1_model_id", "stage1_model_version", "stage1_output_sha256",
        "stage2_model_id", "stage2_model_version", "stage2_output_sha256",
        "stage3_model_id", "stage3_model_version", "stage3_output_sha256",
        "ticket_builder_sha256", "final_ticket_ledger_sha256",
    } <= set(trace["fields"])
    seed = module.seed_aggregation_contract()
    assert "never sum seed stake" in seed["economics"]
    assert "before every Stage-3 screen" in seed["ranking_boundary"]


def test_committed_v2_package_manifest_and_contract_censuses():
    manifest = json.loads((PACKAGE / "SHA256SUMS.json").read_text())
    actual = {
        str(path.relative_to(PACKAGE))
        for path in PACKAGE.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    assert set(manifest) == actual
    for name, expected in manifest.items():
        assert hashlib.sha256((PACKAGE / name).read_bytes()).hexdigest() == expected
    portable = json.loads((PACKAGE / "PORTABLE_SHA256SUMS.json").read_text())
    for name, expected in portable.items():
        module = load_module()
        assert module.portable_payload_sha256(PACKAGE / name) == expected
    content = json.loads((PACKAGE / "CONTENT_IDENTITY.json").read_text())
    assert content["portable_payloads"] == portable
    assert content["portable_manifest_sha256"] == hashlib.sha256(
        (PACKAGE / "PORTABLE_SHA256SUMS.json").read_bytes()
    ).hexdigest()
    card = json.loads((PACKAGE / "gate_a_card.json").read_text())
    assert card["status"] == "READY_FOR_PI_REVIEW_NO_GATE_B_AUTHORITY"
    assert card["outcome_access"] is False
    assert card["gate_b_authorized"] is False
    assert card["parent_192_authority"] is False
    assert card["v1_lineage"]["manifest_sha256"] == (
        "408e8aa69cf2d336f8b3b65b1c94b30a3456864af01517a78fc27b3f2bab0c45"
    )
    assert card["denominator"]["stage1_action_count"] == 2469
    assert card["denominator"]["stage2_action_count"] == 2425
    assert card["denominator"]["stage3_seed_agnostic_action_count"] == 963
    assert card["denominator"]["stage3_complete_match_weight_row_count"] == 47_819
    assert card["denominator"]["stage3_compatibility_class_count"] == 7
    assert card["denominator"]["stage1_stage3_coverage_row_count"] == 2_469 * 7
    assert card["denominator"]["stage1_stage3_pair_count"] == 2_469 * 963
    assert card["denominator"]["stage_model_grid_count"] == 90
    assert card["denominator"]["stage_feature_projection_row_count"] == 237
    assert csv_count(PACKAGE / "stage1_selection_catalog.csv.gz") == 2469
    assert csv_count(PACKAGE / "stage2_direction_catalog.csv.gz") == 2425
    assert csv_count(PACKAGE / "stage3_bet_catalog.csv.gz") == 963
    assert csv_count(PACKAGE / "stage3_complete_match_weight_registry.csv.gz") == 47_819
    assert csv_count(PACKAGE / "stage3_compatibility_class_registry.csv") == 7
    assert csv_count(PACKAGE / "stage1_stage3_coverage_registry.csv.gz") == 2_469 * 7
    fixture = json.loads((PACKAGE / "chain_decision_trace_fixture.json").read_text())
    assert fixture["expected"]["match_support_preserved"] is True
    assert (PACKAGE / "conditional_chain_adapter.py").is_file()
    assert (PACKAGE / "bj145_allocation_engine.py").is_file()
    assert (PACKAGE / "direction_adapter_golden_fixture.json").is_file()
    assert (PACKAGE / "conditional_builder_golden_vectors.json").is_file()
    assert (PACKAGE / "stagewise_learner_execution_contract.json").is_file()
    assert (PACKAGE / "stage1_stage3_compatibility_contract.json").is_file()
    assert (PACKAGE / "native_137_weight_reconciliation.json").is_file()
