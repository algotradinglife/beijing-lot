"""R3 regression, mutation, and boundary tests for Issue #229.

These tests encode the EV R2 full-class sweep.  They are deliberately independent
of the 357k-cell build so each defect has a tight red/green loop.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from divergence_profile import builder, contract, divergence, handoff, manifest, probabilities as prob, profile, publication, quality, sources  # noqa: E402


def _cells(*, qbj_available: bool = True, power_available: bool = False) -> pd.DataFrame:
    qbj = [0.5, 0.3, 0.2]
    eu = [0.4, 0.25, 0.35]
    power = [0.45, 0.25, 0.30]
    rows: list[dict[str, object]] = []
    for outcome in contract.OUTCOME_CODES:
        rows.append(
            {
                "issue": "21001",
                "issue_instance": "21001@CANONICAL_2021",
                "match_idx": 1,
                "outcome_code": outcome,
                "cell_key": f"21001:1:{outcome}",
                "year": 2021,
                "cohort": "development",
                contract.DECISION_EPOCH_COLUMN: pd.Timestamp("2021-01-01T00:00:00Z"),
                contract.KICKOFF_COLUMN: pd.Timestamp("2021-01-02T00:00:00Z"),
                contract.Q_BJ_CALIBRATED: qbj,
                contract.Q_EU_RAW_1X2: eu,
                contract.Q_EU_BJLINE: eu,
                contract.P_POWER_BJLINE: power,
                contract.Q_BJ_SP_DEVIG: np.nan,
                contract.BJ_LINE_BOUNDARY: 0.0,
                contract.SOURCE_IDENTITY_Q_BJ: contract.SRC_BJ204_PCLOSE,
                contract.SOURCE_IDENTITY_EU: contract.SRC_BJ203_DEVIG_EURO,
                contract.SOURCE_IDENTITY_POWER: contract.SRC_BJ180_TEAM_MODEL,
                contract.SOURCE_IDENTITY_SP: contract.SRC_NONE,
                contract.available_col(contract.Q_BJ_CALIBRATED): qbj_available,
                contract.available_col(contract.Q_EU_RAW_1X2): True,
                contract.available_col(contract.Q_EU_BJLINE): True,
                contract.available_col(contract.P_POWER_BJLINE): power_available,
                contract.available_col(contract.Q_BJ_SP_DEVIG): False,
                contract.available_col(contract.BJ_LINE_BOUNDARY): qbj_available,
                "predicted_final_sp_input": 3.0,
                "market_uncertainty": 0.1,
            }
        )
    return pd.DataFrame(rows)


def _labels(year: int = 2021) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "cell_key": ["21001:1:3", "21001:1:1", "21001:1:0"],
            "cell_join_key": ["hash-3", "hash-1", "hash-0"],
            "issue": ["21001"] * 3,
            "issue_instance": ["21001@CANONICAL_2021"] * 3,
            "match_id": ["m1"] * 3,
            "match_idx": [1] * 3,
            "outcome_code": ["3", "1", "0"],
            "result_code": ["3"] * 3,
            "is_winner": [True, False, False],
            "final_sp": [2.1, 3.2, 4.0],
            "final_sp_available": [True] * 3,
            "settlement_status": ["SETTLED"] * 3,
            "settlement_quality": ["TRUSTED"] * 3,
            "settlement_source": ["#203"] * 3,
            "year": [year] * 3,
            "cohort": ["development"] * 3,
        }
    )


# Class 1: every producer publishes causal trace; every consumer uses it.
def test_qbj_materializer_publishes_observed_at_by_actual_source() -> None:
    frame = _cells().drop(
        columns=[
            contract.Q_BJ_CALIBRATED,
            contract.BJ_LINE_BOUNDARY,
            contract.SOURCE_IDENTITY_Q_BJ,
            contract.available_col(contract.Q_BJ_CALIBRATED),
            contract.available_col(contract.BJ_LINE_BOUNDARY),
        ]
    )
    frame["market_probability"] = [0.5, 0.3, 0.2]
    frame["native_handicap_line"] = 0.0
    frame["source_is_pclose"] = 1.0
    frame["source_is_average_eu"] = 0.0
    frame["euro_1h_available_ts_utc"] = pd.Timestamp("2020-12-31T23:00:00Z")
    out = prob.materialize_calibrated_and_line(frame)
    observed = contract.observed_at_col(contract.Q_BJ_CALIBRATED)
    assert observed in out.columns
    # #204 explicitly grades pclose as retrospective proxy without an observed-at.
    assert out[observed].isna().all()
    assert contract.observed_at_col(contract.BJ_LINE_BOUNDARY) in out.columns

    avg = frame.copy()
    avg["source_is_pclose"] = 0.0
    avg["source_is_average_eu"] = 1.0
    out_avg = prob.materialize_calibrated_and_line(avg)
    assert out_avg[observed].notna().all()
    assert out_avg[observed].eq(pd.Timestamp("2020-12-31T23:00:00Z")).all()


def test_all_causal_consumers_reject_raw_presence() -> None:
    cells = _cells(qbj_available=False, power_available=False)
    built = divergence.build_divergence_features(cells)
    assert built[divergence.DIVERGENCE_EU_BJ].isna().all()
    assert built[divergence.DIVERGENCE_POWER_BJ].isna().all()

    missing = profile.missingness_matrix(cells).set_index("representation")
    assert missing.loc[contract.Q_BJ_CALIBRATED, "causally_available"] == 0
    intersections = profile.intersection_coverage(cells).set_index("intersection")
    assert intersections.loc["Q_BJ_CALIBRATED", "cell_count"] == 0
    complete = profile.complete_matches_per_n(cells, n_values=(1,))
    assert complete["eligible_issues"].sum() == 0
    scatter = profile.power_vs_bj_scatter_table(cells)
    assert scatter.empty
    strata = divergence.coverage_strata(cells).set_index("representation")
    assert strata.loc[contract.P_POWER_BJLINE, "raw_present_cells"] == 3
    assert strata.loc[contract.P_POWER_BJLINE, "causally_available_cells"] == 0


def test_causal_eligibility_receipt_is_keyed_and_covers_line() -> None:
    cells = _cells().copy()
    for rep in contract.CAUSAL_REPRESENTATIONS:
        cells[contract.observed_at_col(rep)] = pd.Timestamp("2020-12-31T23:00:00Z")
    causal = quality.causal_eligibility(cells)
    assert {"cell_key", "representation", "available", "unavailable_reason"}.issubset(causal.columns)
    assert set(causal["representation"]) == set(contract.CAUSAL_REPRESENTATIONS)
    assert not causal.duplicated(["cell_key", "representation"]).any()


# Class 2: authoritative cell_identity.year, never issue prefix.
def test_label_namespaces_use_authoritative_identity_year() -> None:
    labels = _labels().drop(columns=["cell_key", "match_idx", "year", "cohort"])
    identity = pd.DataFrame(
        {
            "cell_join_key": ["hash-3", "hash-1", "hash-0"],
            "issue": ["21001"] * 3,
            "issue_instance": ["21001@CANONICAL_2021"] * 3,
            "match_idx": [1] * 3,
            "outcome_code": ["3", "1", "0"],
            "year": [2021] * 3,
            "split": ["development"] * 3,
        }
    )
    dev, sealed = builder.prepare_label_namespaces(labels, identity)
    assert len(dev) == 3
    assert dev["year"].eq(2021).all()
    assert dev["cell_key"].tolist() == ["21001:1:3", "21001:1:1", "21001:1:0"]
    assert int(sealed["upstream_rows"].sum()) == 0


def test_label_boundary_seals_2024_and_2025_separately() -> None:
    labels = pd.concat([_labels(2021), _labels(2024), _labels(2025)], ignore_index=True)
    labels["cell_join_key"] = [f"h{i}" for i in range(len(labels))]
    identity = labels[["cell_join_key", "issue", "issue_instance", "match_idx", "outcome_code", "year", "cohort"]].rename(columns={"cohort": "split"})
    labels = labels.drop(columns=["cell_key", "match_idx", "year", "cohort"])
    dev, sealed = builder.prepare_label_namespaces(labels, identity)
    assert set(dev["year"]) == {2021}
    by_namespace = sealed.set_index("namespace")["upstream_rows"].to_dict()
    assert by_namespace["2024_labels"] == 3
    assert by_namespace["2025_plus_labels"] == 3
    assert sealed["handoff_rows"].eq(0).all()


# Class 3: complete profiling includes every source/outcome and unavailable receipt.
def test_calibration_profiles_every_representation_outcome_and_cohort() -> None:
    cells = _cells(qbj_available=True, power_available=False)
    table = profile.development_only_calibration(cells, _labels())
    expected = {
        (rep, outcome, "development")
        for rep in contract.PROBABILITY_REPRESENTATIONS
        for outcome in contract.OUTCOME_CODES
    }
    got = set(table[["representation", "outcome", "cohort"]].itertuples(index=False, name=None))
    assert expected.issubset(got)
    unavailable = table[table["representation"] == contract.P_POWER_BJLINE]
    assert unavailable["status"].eq("UNAVAILABLE_NO_CAUSAL_LABEL_OVERLAP").all()
    assert unavailable["n"].eq(0).all()


def test_drift_and_probability_distribution_use_causal_mask() -> None:
    cells = _cells(qbj_available=False, power_available=False)
    distribution = profile.probability_distribution(cells, contract.Q_BJ_CALIBRATED)
    assert distribution["status"].eq("UNAVAILABLE_NO_CAUSAL_SUPPORT").all()
    drift = profile.drift_table(cells)
    qbj = drift[drift["representation"] == contract.Q_BJ_CALIBRATED]
    assert qbj["causally_available_cells"].eq(0).all()
    tail = profile.divergence_magnitude_tail(cells)
    assert list(tail.columns) == ["quantile", "value", "field", "status"]
    assert tail.iloc[0]["status"] == "UNAVAILABLE_NO_CAUSAL_SUPPORT"


def test_chart_source_mapping_is_complete() -> None:
    mapping = profile.chart_source_mapping()
    assert not mapping["figure"].duplicated().any()
    assert {
        "development_only_calibration.png",
        "predicted_sp_vs_settlement_sp.png",
        "drift.png",
        "intersection_coverage.png",
    }.issubset(set(mapping["figure"]))
    assert mapping["source_table"].str.len().gt(0).all()
    assessed = profile.chart_source_mapping(
        {
            "probability_distribution_qbj_calibrated": pd.DataFrame(
                {"value": [0.5]}
            ),
            "eu_vs_bj_scatter_table": pd.DataFrame(),
        }
    )
    qbj = assessed[assessed["figure"] == "prob_dist_Q_BJ_CALIBRATED.png"].iloc[0]
    eu = assessed[assessed["figure"] == "eu_vs_bj_scatter.png"].iloc[0]
    assert (qbj["status"], qbj["reason"]) == ("BOUND", "NOT_APPLICABLE")
    assert (eu["status"], eu["reason"], eu["row_count"]) == (
        "UNAVAILABLE",
        "NO_CAUSAL_SUPPORT",
        0,
    )


def test_readiness_requires_sp_backed_independent_divergence_support() -> None:
    cells = _cells(qbj_available=True, power_available=False)
    assert profile.readiness_support(cells)["qbj_anchor"] == 3
    assert profile.readiness_disposition(cells) == "BLOCKED_DATA_DEFECT"

    cells[contract.available_col(contract.Q_BJ_SP_DEVIG)] = True
    cells[contract.Q_BJ_SP_DEVIG] = [[0.5, 0.3, 0.2]] * len(cells)
    assert profile.readiness_disposition(cells) == "READY_WITH_EXPLICIT_LIMITATIONS"

    cells[contract.available_col(contract.P_POWER_BJLINE)] = True
    assert profile.readiness_disposition(cells) == "READY_FOR_209"


def test_power_source_line_mismatch_fails_closed() -> None:
    cells = _cells().drop(
        columns=[
            contract.P_POWER_BJLINE,
            contract.SOURCE_IDENTITY_POWER,
            contract.available_col(contract.P_POWER_BJLINE),
        ]
    )
    power = pd.DataFrame(
        {
            "issue": ["21001"],
            "match_idx": [1],
            "handicap_line_norm": [1.0],
            "team_primary_p3": [0.5],
            "team_primary_p1": [0.3],
            "team_primary_p0": [0.2],
            "feature_cutoff_ts": ["2021-01-01 00:00:00"],
        }
    )
    output = prob.materialize_power_bjline(cells, power)
    assert output[contract.P_POWER_BJLINE].isna().all()
    assert output[
        contract.producer_reason_col(contract.P_POWER_BJLINE)
    ].eq(contract.REASON_SOURCE_LINE_MISMATCH).all()


# Class 4: schema and package-only loader.
def test_schema_describes_every_table_with_physical_logical_contracts() -> None:
    payloads = {
        "inference_cells": ("inference_cells.parquet", _cells()),
        "development_labels": ("development_labels_through_2023.parquet", _labels()),
        "evidence": ("evidence/req_d_evidence.csv", pd.DataFrame({"requirement": ["REQ-D01"], "pass": [False], "reviewed_commit_sha": ["SELF"]})),
    }
    schema = builder.build_schema(payloads)
    assert set(schema["tables"]) == set(payloads)
    for spec in schema["tables"].values():
        assert {"path", "format", "row_count", "primary_key", "foreign_keys", "cardinality", "columns"}.issubset(spec)
        for column in spec["columns"]:
            assert {"name", "physical_type", "logical_type", "list_shape", "units", "nullable", "domain"}.issubset(column)
    inference = schema["tables"]["inference_cells"]
    qbj = next(c for c in inference["columns"] if c["name"] == contract.Q_BJ_CALIBRATED)
    assert qbj["list_shape"] == [3]
    labels = schema["tables"]["development_labels"]
    assert any(fk["column"] == "cell_key" and fk["references"] == "inference_cells.cell_key" for fk in labels["foreign_keys"])
    dictionary = builder.build_feature_dictionary(_cells())
    assert dictionary["domain"].str.len().gt(0).all()
    assert dictionary["key_role"].str.len().gt(0).all()


def test_package_loader_api_is_public() -> None:
    assert callable(handoff.load_package)
    assert callable(handoff.validate_package)
    assert "load_package" in __import__("divergence_profile").__all__


# Class 7: boundary paths preserve three cells or fail explicitly.
def test_bj214_single_observation_fills_exactly_three_cells() -> None:
    cells = _cells().drop(columns=[contract.Q_EU_RAW_1X2, contract.available_col(contract.Q_EU_RAW_1X2)])
    cells["devig_euro_probability"] = np.nan
    observation = pd.DataFrame(
        {
            "match_id": ["21001_1"],
            "eu_h": [2.0],
            "eu_d": [4.0],
            "eu_a": [4.0],
            "snapshot_ts_utc": ["2020-12-31T23:00:00Z"],
        }
    )
    out = prob.materialize_eu_raw(cells, observations=observation)
    assert len(out) == 3
    assert out[["issue", "match_idx", "outcome_code"]].duplicated().sum() == 0
    assert out[contract.Q_EU_RAW_1X2].apply(lambda value: isinstance(value, list) and len(value) == 3).all()


def test_bj214_duplicate_source_match_fails_fast() -> None:
    cells = _cells().drop(columns=[contract.Q_EU_RAW_1X2, contract.available_col(contract.Q_EU_RAW_1X2)])
    cells["devig_euro_probability"] = np.nan
    observations = pd.DataFrame(
        {
            "match_id": ["21001_1", "21001_1"],
            "eu_h": [2.0, 2.0],
            "eu_d": [4.0, 4.0],
            "eu_a": [4.0, 4.0],
            "snapshot_ts_utc": ["2020-12-31T23:00:00Z"] * 2,
        }
    )
    with pytest.raises(sources.UpstreamBindingError, match="duplicate"):
        prob.materialize_eu_raw(cells, observations=observations)


def test_bj214_snapshot_panel_selects_latest_causal_not_future() -> None:
    cells = _cells().drop(
        columns=[contract.Q_EU_RAW_1X2, contract.available_col(contract.Q_EU_RAW_1X2)]
    )
    cells["devig_euro_probability"] = np.nan
    observations = pd.DataFrame(
        {
            "match_id": ["21001_1", "21001_1", "21001_1"],
            "eu_h": [2.0, 4.0, 10.0],
            "eu_d": [4.0, 4.0, 10.0],
            "eu_a": [4.0, 2.0, 10.0],
            "snapshot_ts_utc": [
                "2020-12-31T22:00:00Z",
                "2020-12-31T23:30:00Z",
                "2021-01-01T01:00:00Z",
            ],
        }
    )
    out = prob.materialize_eu_raw(cells, observations=observations)
    selected = out.iloc[0][contract.Q_EU_RAW_1X2]
    assert selected == pytest.approx(prob.devig_normalize(np.array([4.0, 4.0, 2.0])))
    assert out[contract.observed_at_col(contract.Q_EU_RAW_1X2)].eq(
        pd.Timestamp("2020-12-31T23:30:00Z")
    ).all()


def test_partial_triplet_keeps_identity_and_explicit_reason() -> None:
    cells = _cells().drop(columns=[contract.Q_EU_RAW_1X2, contract.available_col(contract.Q_EU_RAW_1X2)])
    cells["devig_euro_probability"] = [0.5, 0.3, np.nan]
    out = prob.materialize_eu_raw(cells, observations=pd.DataFrame())
    assert len(out) == 3
    assert out[contract.Q_EU_RAW_1X2].isna().all()
    assert out[contract.producer_reason_col(contract.Q_EU_RAW_1X2)].eq(contract.REASON_PARTIAL_SOURCE_TRIPLET).all()


@pytest.mark.parametrize(
    "frame",
    [
        pd.DataFrame(columns=["issue", "match_idx", "outcome_code"]),
        pd.DataFrame(
            {"issue": ["x", "x"], "match_idx": [1, 1], "outcome_code": ["3", "1"]}
        ),
        pd.DataFrame(
            {"issue": ["x"] * 4, "match_idx": [1] * 4, "outcome_code": ["3", "1", "0", "0"]}
        ),
    ],
)
def test_canonical_source_axes_fail_fast_on_empty_partial_or_duplicate(
    frame: pd.DataFrame,
) -> None:
    with pytest.raises(sources.UpstreamBindingError):
        sources._validate_three_cell_identity(frame, "fixture", "axis")


def test_bj180_empty_and_partial_keep_three_cells_with_receipts() -> None:
    cells = _cells()
    empty = prob.materialize_power_bjline(cells, pd.DataFrame())
    assert len(empty) == 3
    assert empty[contract.P_POWER_BJLINE].isna().all()
    partial = pd.DataFrame(
        {
            "issue": ["21001"], "match_idx": [1],
            "handicap_line_norm": [0.0],
            "team_primary_p3": [0.5], "team_primary_p1": [0.3],
            "team_primary_p0": [np.nan], "feature_cutoff_ts": ["2021-01-01 07:00:00"],
        }
    )
    out = prob.materialize_power_bjline(cells, partial)
    assert len(out) == 3
    assert out[contract.producer_reason_col(contract.P_POWER_BJLINE)].eq(
        contract.REASON_PARTIAL_SOURCE_TRIPLET
    ).all()


def test_bj180_duplicate_source_match_fails_fast() -> None:
    row = {
        "issue": "21001", "match_idx": 1,
        "handicap_line_norm": 0.0,
        "team_primary_p3": 0.5, "team_primary_p1": 0.3,
        "team_primary_p0": 0.2, "feature_cutoff_ts": "2021-01-01 07:00:00",
    }
    with pytest.raises(sources.UpstreamBindingError, match="duplicate source row"):
        prob.materialize_power_bjline(_cells(), pd.DataFrame([row, row]))


def test_translation_unidentifiable_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    prob._translated_bjline_cached.cache_clear()
    monkeypatch.setattr(
        prob,
        "_fit_poisson_rates",
        lambda *_args: None,
    )
    translated, reason = prob.translate_eu_to_bjline((0.4, 0.25, 0.35), -0.5)
    assert translated is None
    assert reason == contract.REASON_TRANSLATION_NOT_IDENTIFIABLE
    prob._translated_bjline_cached.cache_clear()


def test_notebook_semantic_hash_ignores_execution_only_metadata(tmp_path: Path) -> None:
    notebook = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {"kernelspec": {"name": "python3"}},
        "cells": [
            {
                "cell_type": "code",
                "id": "stable-cell",
                "metadata": {"tags": ["parameters"], "execution": {"iopub.status.busy": "t1"}},
                "source": ["x = 1\n"],
                "execution_count": 1,
                "outputs": [{"output_type": "stream", "text": ["old\n"]}],
            }
        ],
    }
    path = tmp_path / "test.ipynb"
    path.write_text(json.dumps(notebook), encoding="utf-8")
    first = builder._notebook_semantic_hash(path)
    notebook["cells"][0]["metadata"]["execution"] = {"iopub.status.busy": "t2"}
    notebook["cells"][0]["execution_count"] = 2
    notebook["cells"][0]["outputs"] = [{"output_type": "stream", "text": ["new\n"]}]
    path.write_text(json.dumps(notebook), encoding="utf-8")
    assert builder._notebook_semantic_hash(path) == first
    notebook["cells"][0]["source"] = ["x = 2\n"]
    path.write_text(json.dumps(notebook), encoding="utf-8")
    assert builder._notebook_semantic_hash(path) != first


# Class 6: all durability failures fail closed and the correct directory is fsynced.
def test_fsync_dir_failure_is_not_swallowed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(os, "fsync", lambda _fd: (_ for _ in ()).throw(OSError("fsync fault")))
    with pytest.raises(OSError, match="fsync fault"):
        publication.fsync_dir(tmp_path)


def test_atomic_write_text_fsyncs_actual_parent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    opened: list[Path] = []
    real_open = publication.os.open

    def capture(path, flags, *args):
        opened.append(Path(path))
        return real_open(path, flags, *args)

    monkeypatch.setattr(publication.os, "open", capture)
    target = tmp_path / "nested" / "receipt.json"
    target.parent.mkdir()
    publication.atomic_write_text(target, "{}")
    assert target.parent in opened
    assert target.parent.parent not in opened


def test_atomic_directory_post_rename_fsync_fault_restores_old_package(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "package"
    target.mkdir()
    (target / "marker").write_text("old", encoding="utf-8")
    calls = 0
    real_fsync_dir = publication.fsync_dir

    def fail_after_second_rename(path: Path) -> None:
        nonlocal calls
        calls += 1
        # staging/tree fsyncs happen first; inject specifically after target install.
        if path == tmp_path and calls >= 3:
            raise OSError("post-rename parent fsync fault")
        real_fsync_dir(path)

    monkeypatch.setattr(publication, "fsync_dir", fail_after_second_rename)

    def populate(stage: Path) -> None:
        publication.atomic_write_text(stage / "marker", "new")

    with pytest.raises(OSError, match="post-rename"):
        publication.atomic_publish_directory(target, populate, force=True)
    assert (target / "marker").read_text(encoding="utf-8") == "old"
    assert not list(tmp_path.glob(".package.staging-*"))


# Class 5: independent verifier must reject remanifested semantic mutations.
@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("divergence", "divergence"),
        ("availability", "availability"),
        ("labels", "label"),
        ("schema", "schema"),
        ("schema_path", "unsafe table path"),
        ("evidence", "evidence"),
        ("report", "report"),
    ],
)
def test_remanifested_mutation_fails(
    mutation: str, expected: str, tmp_path: Path
) -> None:
    package = handoff.write_test_package(tmp_path, _cells(), _labels())
    handoff.apply_test_mutation(package, mutation)
    manifest.write_sha256sums(package)
    problems = handoff.validate_package(package, repo_root=None, expected_commit="SELF")
    assert problems, f"remanifested {mutation} mutation passed"
    assert expected.lower() in " ".join(problems).lower()


def test_tamper_source_trace_and_future_label_fail(tmp_path: Path) -> None:
    package = handoff.write_test_package(tmp_path, _cells(), _labels())
    handoff.apply_test_mutation(package, "source_trace")
    manifest.write_sha256sums(package)
    assert handoff.validate_package(package, repo_root=None, expected_commit="SELF")

    package2 = handoff.write_test_package(tmp_path / "other", _cells(), _labels())
    handoff.apply_test_mutation(package2, "future_label")
    manifest.write_sha256sums(package2)
    assert handoff.validate_package(package2, repo_root=None, expected_commit="SELF")


def test_hash_manifest_path_traversal_fails_closed(tmp_path: Path) -> None:
    package = tmp_path / "package"
    package.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    (package / "SHA256SUMS.json").write_text(
        json.dumps({"../outside.txt": sources.sha256_file(outside)}),
        encoding="utf-8",
    )
    with pytest.raises(sources.UpstreamBindingError, match="escapes root"):
        sources.verify_package_hashes(package)


def test_replay_uses_logical_package_name_not_staging_name(tmp_path: Path) -> None:
    staging = tmp_path / ".bj229_divergence_profile_v1.staging-random"
    staging.mkdir()
    receipt = type("Receipt", (), {"source_hashes": {}})()
    payload = {
        "reviewed_commit_sha": "PR_HEAD",
        "code_hash": "code",
        "notebook_hash": "notebook",
        "requirements_hash": "requirements",
    }
    manifest.write_replay(
        staging,
        receipt,
        tmp_path,
        payload,
        package_name=contract.PACKAGE_NAME,
    )
    replay = (staging / "REPLAY.md").read_text(encoding="utf-8")
    assert f"--package {contract.PACKAGE_NAME}" in replay
    assert ".staging-" not in replay
