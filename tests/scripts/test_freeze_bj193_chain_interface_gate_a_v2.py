from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import json
import sys
from pathlib import Path


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
        assert all(row["preserved_source_identity"] is True for row in rows)
        assert len({row["interface_action_key"] for row in rows}) == len(rows)
        assert all(row["source_identity"] for row in rows)
    assert {row["upstream_issue"] for row in stage1} == {127, 134, 190}
    assert {row["upstream_issue"] for row in stage2} == {190}
    assert {row["upstream_issue"] for row in stage3} == {167}
    assert sum(row["availability"] == "AVAILABLE" for row in stage2) == 2365
    assert all("seed" not in row["source_identity"].lower() for row in stage3)
    assert {json.loads(row["parameters_json"])["M"] for row in stage3} >= {
        "16", "64", "2187"
    }


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
    assert card["denominator"]["stage_model_grid_count"] == 90
    assert csv_count(PACKAGE / "stage1_selection_catalog.csv.gz") == 2469
    assert csv_count(PACKAGE / "stage2_direction_catalog.csv.gz") == 2425
    assert csv_count(PACKAGE / "stage3_bet_catalog.csv.gz") == 963
    fixture = json.loads((PACKAGE / "chain_decision_trace_fixture.json").read_text())
    assert fixture["expected"]["match_support_preserved"] is True
