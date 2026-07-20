"""Integrity checks for the quarantined post-hoc proxy result.

The test intentionally reads only the emitted lock and result, never the
label-bearing replay source, so it cannot create another holdout evaluation.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RESULT_DIR = ROOT / "results/research/score_projection_26071_26074_posthoc_proxy_v1"
LOCK_PATH = RESULT_DIR / "selection_lock.json"
RESULT_PATH = RESULT_DIR / "result.json"


def test_posthoc_proxy_holdout_result_remains_locked_and_nonselectable():
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    result = json.loads(RESULT_PATH.read_text(encoding="utf-8"))

    assert result["status"] == "research_only_post_hoc_proxy_non_executable_non_selectable_roi_unauthorized"
    assert result["evidence_classification"] == "small_sample_post_hoc_proxy_only_never_promotion_evidence"
    assert lock["partition"]["tuning_issues"] == ["26071", "26072", "26073"]
    assert lock["partition"]["holdout_issue"] == "26074"
    assert lock["partition"]["holdout_labels_parsed_at_lock"] is False
    assert result["selection_lock"]["verified_before_holdout_label_parse"] is True
    assert result["selection_lock"]["holdout_label_evaluations"] == 1
    assert result["selection_lock"]["sha256"] == hashlib.sha256(LOCK_PATH.read_bytes()).hexdigest()

    selected = result["selected_candidate"]
    assert selected["name"] == "G1_logit_L2_1"
    assert selected["fitted_rows"] == 93
    assert result["aggregates"]["tuning_26071_26073"]["n"] == 93
    assert result["aggregates"]["holdout_26074"]["n"] == 65
    assert result["aggregates"]["descriptive_all_26071_26074"]["n"] == 158

    holdout = result["aggregates"]["holdout_26074"]
    assert holdout["G1_logit_L2_1"]["binary_draw_brier"] > holdout["G0_no_change"]["binary_draw_brier"]
    assert holdout["G1_logit_L2_1"]["binary_draw_log_loss"] > holdout["G0_no_change"]["binary_draw_log_loss"]
    assert holdout["G1_logit_L2_1"]["binary_draw_brier"] < holdout["G1_no_change"]["binary_draw_brier"]
    assert holdout["G1_logit_L2_1"]["binary_draw_log_loss"] < holdout["G1_no_change"]["binary_draw_log_loss"]
    assert holdout["G1_logit_L2_1"]["draw_ece_10bin"] > holdout["G1_no_change"]["draw_ece_10bin"]
    assert result["transfer_supported"] is False
    assert {"roi", "ticket_data", "terminal_correct_score_odds", "shared_sqlite"} <= set(result["prohibited"])
