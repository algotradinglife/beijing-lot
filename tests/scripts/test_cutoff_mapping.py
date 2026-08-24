from __future__ import annotations

import inspect
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.cutoff_mapping.api import (
    CutoffContractError,
    fit_cutoff_mapping,
    fit_issue_walk_forward,
    replay_gate,
    replay_mapped,
)
from src.temporal_learning import (
    AvailabilityFilter,
    AvailabilityPolicy,
    Cutoff,
    PartitionPolicy,
    WeightingPolicy,
    prepare_learning_context,
    implementation_closure,
    temporal_cache_key,
)
from src.temporal_learning.example_selector import select_cutoff_threshold


REPO_ROOT = Path(__file__).resolve().parents[2]
OBSERVED = AvailabilityPolicy.observed("SYNTHETIC_OBSERVED_LABEL_AVAILABILITY")


def _frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(382)
    rows = []
    outcomes = np.array(["3", "1", "0"])
    for year in range(2014, 2022):
        for i in range(36):
            q = rng.dirichlet([3, 2, 2])
            line = float([-1, 0, 1][i % 3])
            rows.append(
                {
                    "issue_code": f"{year}-{i:03}",
                    "issue_year": year,
                    "match_idx": i,
                    "label_available_ts": pd.Timestamp(f"{year}-06-01", tz="UTC")
                    + pd.Timedelta(minutes=i),
                    "fixture_decision_ts": pd.Timestamp(f"{year}-05-31", tz="UTC")
                    + pd.Timedelta(minutes=i),
                    "target_outcome": outcomes[rng.choice(3, p=q)],
                    "native_line_supported": True,
                    "native_handicap_line": line,
                    "q_eu_3": q[0],
                    "q_eu_1": q[1],
                    "q_eu_0": q[2],
                    "line_x_q_eu_3": line * q[0],
                    "line_x_q_eu_1": line * q[1],
                    "line_x_q_eu_0": line * q[2],
                }
            )
    development = pd.DataFrame(rows)
    target = (
        development.tail(6)
        .drop(columns=["target_outcome", "label_available_ts"])
        .copy()
    )
    target["issue_code"] = [f"target-{i}" for i in range(6)]
    target["issue_year"] = 2022
    target["fixture_decision_ts"] = pd.Timestamp("2022-01-01", tz="UTC")
    return development, target


def _fit(development: pd.DataFrame, target: pd.DataFrame, cutoff: Cutoff | None = None):
    cutoff = cutoff or Cutoff.evaluation_year(2022, "2022-01-01T00:00:00Z")
    return fit_cutoff_mapping(
        development,
        target,
        cutoff,
        repository_root=REPO_ROOT,
        implementation_modules=("src.cutoff_mapping.api",),
        source_hashes={"synthetic": "abc123"},
        availability_policy=OBSERVED,
        intended_use="HISTORICAL_DIAGNOSTIC",
    )


def test_post_cutoff_label_mutation_leaves_science_invariant() -> None:
    development, target = _frames()
    future = development.tail(3).copy()
    future["issue_year"] = 2022
    future["label_available_ts"] = pd.Timestamp("2022-01-02", tz="UTC")
    first = _fit(pd.concat([development, future], ignore_index=True), target)
    future["target_outcome"] = future["target_outcome"].map(
        {"3": "0", "0": "1", "1": "3"}
    )
    second = _fit(pd.concat([development, future], ignore_index=True), target)
    assert first.receipt["model_identity"] == second.receipt["model_identity"]
    pd.testing.assert_frame_equal(first.mapped, second.mapped)


def test_equal_or_later_labels_never_enter_partitions() -> None:
    development, target = _frames()
    development.loc[development.index[-1], "label_available_ts"] = pd.Timestamp(
        "2022-01-01", tz="UTC"
    )
    result = _fit(development, target)
    assert pd.Timestamp(
        result.receipt["maximum_training_label_timestamp"]
    ) < pd.Timestamp(result.receipt["cutoff_ts"])
    assert result.receipt["partition"]["final_refit_rows"] == len(development) - 1


def test_decision_epoch_structurally_excludes_same_issue_history() -> None:
    development, target = _frames()
    target_issue = str(
        development.loc[development["issue_year"].eq(2021), "issue_code"].iloc[-1]
    )
    target = target.assign(
        issue_code=target_issue,
        fixture_decision_ts=pd.Timestamp("2022-01-01", tz="UTC"),
    )
    cutoff = Cutoff.decision_epoch(target_issue, "2022-01-01T00:00:00Z")
    first = _fit(development, target, cutoff)
    mutated = development.copy()
    same_target = mutated["issue_code"].eq(target_issue)
    mutated.loc[same_target, "target_outcome"] = mutated.loc[
        same_target, "target_outcome"
    ].map({"3": "0", "1": "3", "0": "1"})
    second = _fit(mutated, target, cutoff)
    assert first.receipt["target_rows_seen"] == int(same_target.sum())
    assert first.receipt["target_rows_excluded"] == int(same_target.sum())
    assert (
        first.receipt["admitted_history_sha256"]
        == second.receipt["admitted_history_sha256"]
    )
    assert first.receipt["model_identity"] == second.receipt["model_identity"]
    pd.testing.assert_frame_equal(first.mapped, second.mapped)


def test_decision_epoch_rejects_mismatched_target_identity() -> None:
    development, target = _frames()
    with pytest.raises(CutoffContractError):
        _fit(
            development,
            target,
            Cutoff.decision_epoch("DIFFERENT", "2022-01-01T00:00:00Z"),
        )


def test_historical_proxy_cannot_authorize_prospective_use() -> None:
    development, target = _frames()
    with pytest.raises(CutoffContractError):
        fit_cutoff_mapping(
            development,
            target,
            Cutoff.evaluation_year(2022, "2022-01-01T00:00:00Z"),
            repository_root=REPO_ROOT,
            implementation_modules=("src.cutoff_mapping.api",),
            source_hashes={"synthetic": "abc123"},
            availability_policy=AvailabilityPolicy.historical_proxy(
                "KICKOFF_PLUS_4H_PROXY"
            ),
            intended_use="PROSPECTIVE_DECISION",
        )


def test_earlier_cutoff_excludes_later_source_year() -> None:
    development, target = _frames()
    target["fixture_decision_ts"] = pd.Timestamp("2021-01-01", tz="UTC")
    result = _fit(
        development, target, Cutoff.evaluation_year(2021, "2021-01-01T00:00:00Z")
    )
    assert result.receipt["partition"]["calibration_years"] == [2020]
    assert pd.Timestamp(
        result.receipt["maximum_training_label_timestamp"]
    ) < pd.Timestamp("2021-01-01", tz="UTC")


def test_equivalent_cutoff_forms_have_identical_science() -> None:
    development, target = _frames()
    a = _fit(development, target, Cutoff.evaluation_year(2022, "2022-01-01T00:00:00Z"))
    b = _fit(
        development, target, Cutoff.last_issue("2021-LAST", "2022-01-01T00:00:00Z")
    )
    assert a.receipt["model_identity"] == b.receipt["model_identity"]
    pd.testing.assert_frame_equal(a.mapped, b.mapped)


def test_cache_keys_prevent_cross_cutoff_reuse() -> None:
    a = Cutoff.evaluation_year(2022, "2022-01-01T00:00:00Z")
    b = Cutoff.evaluation_year(2023, "2023-01-01T00:00:00Z")
    partition = PartitionPolicy()
    weighting = WeightingPolicy.expanding_equal(minimum_ess=10)

    def key(cutoff, source, implementation, policy=weighting, availability=OBSERVED):
        return temporal_cache_key(
            cutoff,
            source,
            implementation,
            availability,
            "HISTORICAL_DIAGNOSTIC",
            partition,
            policy,
        )

    assert key(a, {"x": "1"}, {"client": "impl"}) != key(
        b, {"x": "1"}, {"client": "impl"}
    )
    assert key(a, {"x": "1"}, {"client": "impl"}) != key(
        a, {"x": "2"}, {"client": "impl"}
    )
    assert key(a, {"x": "1"}, {"client": "impl"}) != key(
        a, {"x": "1"}, {"client": "changed"}
    )
    recency = WeightingPolicy.expanding_exponential(365, minimum_ess=10)
    assert key(a, {"x": "1"}, {"client": "impl"}) != key(
        a, {"x": "1"}, {"client": "impl"}, recency
    )
    assert key(a, {"x": "1"}, {"client": "impl"}) != key(
        a,
        {"x": "1"},
        {"client": "impl"},
        availability=AvailabilityPolicy.historical_proxy("PROXY"),
    )


def test_no_hard_coded_future_partition_year_in_decision_path() -> None:
    source = inspect.getsource(fit_cutoff_mapping)
    assert (
        "TUNE_YEAR" not in source
        and "CALIBRATION_YEAR" not in source
        and "FIT_END" not in source
    )


def test_transitive_contract_module_mutation_changes_closure(tmp_path: Path) -> None:
    (tmp_path / "src/client").mkdir(parents=True)
    (tmp_path / "src/__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "src/client/__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "src/client/api.py").write_text(
        "from .contract import VALUE\n\ndef use():\n    return VALUE\n",
        encoding="utf-8",
    )
    contract = tmp_path / "src/client/contract.py"
    contract.write_text("VALUE = 1\n", encoding="utf-8")
    first = implementation_closure(tmp_path, ("src.client.api",))
    assert "src/client/contract.py" in first["files"]
    contract.write_text("VALUE = 2\n", encoding="utf-8")
    second = implementation_closure(tmp_path, ("src.client.api",))
    assert first["closure_sha256"] != second["closure_sha256"]


def test_receipt_replays_gate_and_probabilities() -> None:
    development, target = _frames()
    result = _fit(development, target)
    assert (
        replay_gate(development, result.receipt, repository_root=REPO_ROOT)
        == result.receipt["gate_predicates"]
    )
    pd.testing.assert_frame_equal(
        replay_mapped(target, result.receipt, repository_root=REPO_ROOT),
        result.mapped,
        rtol=0,
        atol=1e-12,
    )


def test_missing_or_insufficient_chronology_fails_closed() -> None:
    development, target = _frames()
    with pytest.raises(CutoffContractError):
        _fit(development.drop(columns="label_available_ts"), target)
    with pytest.raises(CutoffContractError):
        _fit(development[development["issue_year"].eq(2021)], target)
    with pytest.raises(CutoffContractError):
        fit_cutoff_mapping(
            development,
            target,
            Cutoff.evaluation_year(2022, "2022-01-01T00:00:00Z"),
            repository_root=REPO_ROOT,
            implementation_modules=("src.cutoff_mapping.api",),
            source_hashes={"synthetic": "abc123"},
            availability_policy=OBSERVED,
            intended_use="HISTORICAL_DIAGNOSTIC",
            weighting_policy=WeightingPolicy.expanding_exponential(
                1.0, minimum_ess=10_000
            ),
        )


def test_recency_weights_are_monotone_reconciled_and_retain_prior() -> None:
    development, _ = _frames()
    cutoff = Cutoff.decision_epoch("2022-001", "2022-03-01T00:00:00Z")
    exponential = prepare_learning_context(
        development,
        cutoff,
        source_hashes={"source": "x"},
        repository_root=REPO_ROOT,
        implementation_modules=("src.temporal_learning.example_selector",),
        availability=AvailabilityFilter(policy=OBSERVED),
        intended_use="HISTORICAL_DIAGNOSTIC",
        weighting_policy=WeightingPolicy.expanding_exponential(365.0, minimum_ess=10),
    ).weight_ledger.sort_values("label_available_ts")
    assert exponential["weight"].is_monotonic_increasing
    assert exponential["weight"].gt(0).all()
    assert exponential["weight"].sum() == pytest.approx(len(exponential))
    ess = exponential["weight"].sum() ** 2 / exponential["weight"].pow(2).sum()
    assert ess >= 10

    blended = prepare_learning_context(
        development,
        cutoff,
        source_hashes={"source": "x"},
        repository_root=REPO_ROOT,
        implementation_modules=("src.temporal_learning.example_selector",),
        availability=AvailabilityFilter(policy=OBSERVED),
        intended_use="HISTORICAL_DIAGNOSTIC",
        weighting_policy=WeightingPolicy.recent_state_blend(4, 0.7, minimum_ess=5),
    ).weight_ledger
    assert blended["weight"].min() > 0
    assert blended["weight"].nunique() == 2
    assert blended["long_mass"].sum() == pytest.approx(0.3)
    assert blended["recent_mass"].sum() == pytest.approx(0.7)
    assert blended["total_mass"].sum() == pytest.approx(1.0)


def _walk_forward_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    development, target = _frames()
    target = pd.concat(
        [
            target.assign(
                issue_code="2022-001",
                fixture_decision_ts=pd.Timestamp("2022-02-01", tz="UTC"),
            ),
            target.assign(
                issue_code="2022-002",
                fixture_decision_ts=pd.Timestamp("2022-03-01", tz="UTC"),
            ),
        ],
        ignore_index=True,
    )
    current = target[target["issue_code"].eq("2022-001")].copy()
    current["target_outcome"] = np.resize(np.array(["3", "1", "0"]), len(current))
    current["label_available_ts"] = pd.Timestamp("2022-02-02", tz="UTC")
    return pd.concat([development, current], ignore_index=True), target


def test_issue_walk_forward_admits_current_year_only_after_availability() -> None:
    history, targets = _walk_forward_frames()
    _, receipts, _ = fit_issue_walk_forward(
        history,
        targets,
        repository_root=REPO_ROOT,
        implementation_modules=("src.cutoff_mapping.api",),
        source_hashes={"synthetic": "walk"},
        weighting_policy=WeightingPolicy.expanding_equal(minimum_ess=10),
        availability_policy=OBSERVED,
        intended_use="HISTORICAL_DIAGNOSTIC",
    )
    assert len(receipts) == 2
    assert receipts[0]["partition"]["final_refit_rows"] == len(history) - 6
    assert receipts[1]["partition"]["final_refit_rows"] == len(history)
    assert pd.Timestamp(receipts[0]["maximum_training_label_timestamp"]) < pd.Timestamp(
        receipts[0]["cutoff_ts"]
    )
    assert pd.Timestamp(receipts[1]["maximum_training_label_timestamp"]) < pd.Timestamp(
        receipts[1]["cutoff_ts"]
    )
    assert receipts[0]["cache_key"] != receipts[1]["cache_key"]


def test_later_label_mutation_cannot_rewrite_earlier_issue_artifact() -> None:
    history, targets = _walk_forward_frames()
    policy = WeightingPolicy.expanding_exponential(730.0, minimum_ess=10)
    mapped_a, receipts_a, _ = fit_issue_walk_forward(
        history,
        targets,
        repository_root=REPO_ROOT,
        implementation_modules=("src.cutoff_mapping.api",),
        source_hashes={"synthetic": "walk"},
        weighting_policy=policy,
        availability_policy=OBSERVED,
        intended_use="HISTORICAL_DIAGNOSTIC",
    )
    mutated = history.copy()
    later = mutated["label_available_ts"].eq(pd.Timestamp("2022-02-02", tz="UTC"))
    mutated.loc[later, "target_outcome"] = mutated.loc[later, "target_outcome"].map(
        {"3": "0", "1": "3", "0": "1"}
    )
    mapped_b, receipts_b, _ = fit_issue_walk_forward(
        mutated,
        targets,
        repository_root=REPO_ROOT,
        implementation_modules=("src.cutoff_mapping.api",),
        source_hashes={"synthetic": "walk"},
        weighting_policy=policy,
        availability_policy=OBSERVED,
        intended_use="HISTORICAL_DIAGNOSTIC",
    )
    first_a = mapped_a[
        mapped_a["artifact_cutoff_identity"].eq("DECISION_EPOCH_2022-001")
    ]
    first_b = mapped_b[
        mapped_b["artifact_cutoff_identity"].eq("DECISION_EPOCH_2022-001")
    ]
    pd.testing.assert_frame_equal(
        first_a.reset_index(drop=True), first_b.reset_index(drop=True)
    )
    assert (
        receipts_a[0]["scientific_output_sha256"]
        == receipts_b[0]["scientific_output_sha256"]
    )


def test_synthetic_regime_shift_adapts_only_after_availability_and_is_bounded() -> None:
    history, targets = _walk_forward_frames()
    policy = WeightingPolicy.recent_state_blend(1, 0.6, minimum_ess=2)
    _, receipts, weights = fit_issue_walk_forward(
        history,
        targets,
        repository_root=REPO_ROOT,
        implementation_modules=("src.cutoff_mapping.api",),
        source_hashes={"synthetic": "shift"},
        weighting_policy=policy,
        availability_policy=OBSERVED,
        intended_use="HISTORICAL_DIAGNOSTIC",
    )
    assert receipts[0]["model_identity"] != receipts[1]["model_identity"]
    second = weights[weights["target_issue"].eq("2022-002")]
    prior = second[~second["issue_code"].eq("2022-001")]
    recent = second[second["issue_code"].eq("2022-001")]
    assert recent["weight"].min() > prior["weight"].max()
    assert prior["weight"].min() > 0
    assert receipts[1]["weight_receipt"]["effective_sample_size"] >= 2


def test_second_selection_client_uses_same_cutoff_and_is_future_invariant() -> None:
    history, _ = _frames()
    history["score"] = history["q_eu_3"] - history["q_eu_0"]
    history["binary_label"] = history["target_outcome"].eq("3").astype(int)
    cutoff = Cutoff.evaluation_year(2022, "2022-01-01T00:00:00Z")
    first = select_cutoff_threshold(
        history,
        cutoff,
        repository_root=REPO_ROOT,
        implementation_modules=("src.temporal_learning.example_selector",),
        score_column="score",
        binary_label_column="binary_label",
        source_hashes={"synthetic": "selector"},
        availability_policy=OBSERVED,
        intended_use="HISTORICAL_DIAGNOSTIC",
        weighting_policy=WeightingPolicy.expanding_equal(minimum_ess=10),
    )
    future = history.tail(6).copy()
    future["label_available_ts"] = pd.Timestamp("2022-02-01", tz="UTC")
    future["binary_label"] = 1 - future["binary_label"]
    second = select_cutoff_threshold(
        pd.concat([history, future], ignore_index=True),
        cutoff,
        repository_root=REPO_ROOT,
        implementation_modules=("src.temporal_learning.example_selector",),
        score_column="score",
        binary_label_column="binary_label",
        source_hashes={"synthetic": "selector"},
        availability_policy=OBSERVED,
        intended_use="HISTORICAL_DIAGNOSTIC",
        weighting_policy=WeightingPolicy.expanding_equal(minimum_ess=10),
    )
    assert first.selection == second.selection
    assert first.receipt["selection_identity"] == second.receipt["selection_identity"]
