from __future__ import annotations

import csv

import numpy as np
import pandas as pd

from unified_model.gate_b import (
    CLASS_CODES,
    FEATURE_COLUMNS,
    MODEL_ORDER,
    GateBError,
    _anchored_probabilities,
    _assert_matching_market_completeness,
    _evaluate_family,
    _estimator_delta,
    _fallback_predictions,
    _feature_matrix,
    _is_reserved_210_issue,
    _metrics,
    _read_official_labels,
    _selection,
    _source_ood,
)


def _write_labels(path) -> None:
    fields = ["expect", "match_no", "match_uid", "result_code", "sp_3", "sp_1", "sp_0"]
    rows = [
        ["25043", "1", "7", "3", "2.2", "3.3", "4.4"],
        # This label row must never be parsed because #210 is not in the
        # Gate-A whitelist.  A non-numeric SP makes accidental parsing fail.
        ["26051", "1", "8", "0", "not-a-number", "not-a-number", "not-a-number"],
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(fields)
        writer.writerows(rows)


def test_official_label_reader_parses_only_frozen_identity_rows(tmp_path) -> None:
    source = tmp_path / "labels.csv"
    _write_labels(source)

    labels = _read_official_labels(source, {("25043", 1)})

    assert labels[["issue", "match_idx", "result_code"]].to_dict("records") == [
        {"issue": "25043", "match_idx": 1, "result_code": "3"}
    ]
    assert bool(labels.loc[0, "sp_target_available"])


def test_issue_context_representation_is_permutation_invariant() -> None:
    rows: list[dict[str, float | str]] = []
    for issue, offset in (("24011", 0.0), ("24012", 1.0)):
        for index in range(3):
            row: dict[str, float | str] = {"issue": issue}
            for feature_index, name in enumerate(FEATURE_COLUMNS):
                row[name] = offset + index + feature_index / 10.0
            rows.append(row)
    panel = pd.DataFrame(rows)
    original = _feature_matrix(panel, context=True)
    permuted = _feature_matrix(panel.sample(frac=1.0, random_state=7).reset_index(drop=True), context=True)

    original_context = sorted(tuple(np.round(row[len(FEATURE_COLUMNS):], 12)) for row in original)
    permuted_context = sorted(tuple(np.round(row[len(FEATURE_COLUMNS):], 12)) for row in permuted)
    assert original_context == permuted_context


def test_fallback_and_metrics_keep_market_and_model_views_distinct() -> None:
    market = np.array([[0.50, 0.30, 0.20], [0.40, 0.35, 0.25]])
    model = np.array([[0.45, 0.35, 0.20], [0.20, 0.30, 0.50]])
    mixed, used_model = _fallback_predictions(market, model, np.array([False, True]))

    assert used_model.tolist() == [True, False]
    assert np.allclose(mixed[0], model[0])
    assert np.allclose(mixed[1], market[1])
    scores = _metrics(model, np.array([0, 2]))
    assert set(scores) == {"log_loss", "brier", "ece_equal_mass", "top1", "top2", "sp_mae"}
    assert np.isfinite(scores["log_loss"])
    assert tuple(CLASS_CODES) == ("3", "1", "0")


def test_reserved_issue_check_is_year_aware() -> None:
    assert not _is_reserved_210_issue("190101", 2019)
    assert not _is_reserved_210_issue("26049", 2026)
    assert _is_reserved_210_issue("26051", 2026)


def test_common_panel_refuses_completeness_mask_disagreement() -> None:
    registry = pd.DataFrame({"issue": ["25043"], "match_idx": [1], "market_proxy_complete": [True]})
    static = pd.DataFrame(
        {"native_handicap_line": [0.0], "market_proxy_complete": [False]},
        index=pd.MultiIndex.from_tuples([("25043", 1)], names=["issue", "match_idx"]),
    )
    with np.testing.assert_raises_regex(GateBError, "completeness masks disagree"):
        _assert_matching_market_completeness(registry, static)


def test_market_only_emits_m_by_three_fallback_vectors() -> None:
    panel = pd.DataFrame(
        {
            "market_probability_3": [0.50, 0.40],
            "market_probability_1": [0.30, 0.35],
            "market_probability_0": [0.20, 0.25],
        }
    )
    market, model, mixed, used_model, delta = _evaluate_family("MARKET_ONLY", panel, panel, 204001)
    assert market.shape == model.shape == mixed.shape == (2, 3)
    assert np.allclose(mixed, market)
    assert not used_model.any()
    assert np.allclose(delta, 0.0)


def test_anchored_zero_delta_is_exact_market_identity() -> None:
    market = np.array([[0.50, 0.30, 0.20], [0.40, 0.35, 0.25]])
    actual = _anchored_probabilities(market, np.zeros_like(market))
    assert np.allclose(actual, market, atol=1e-14, rtol=0)


def test_probability_only_package_estimator_becomes_centered_delta() -> None:
    class _ProbabilityOnlyEstimator:
        classes_ = np.array([0, 1, 2])

        def predict_proba(self, features):
            return np.tile(np.array([[0.50, 0.30, 0.20]]), (len(features), 1))

    delta = _estimator_delta(_ProbabilityOnlyEstimator(), np.zeros((2, 1)))
    assert np.allclose(delta.mean(axis=1), 0.0, atol=1e-14)
    assert np.isfinite(delta).all()


def test_known_grade_and_expected_missingness_do_not_force_ood_or_fallback(monkeypatch) -> None:
    train = pd.DataFrame({"source_grade": ["RETROSPECTIVE_PROXY_PCLOSE"] * 3})
    evaluation = pd.DataFrame({"source_grade": ["RETROSPECTIVE_PROXY"]})
    train_features = np.array([[0.5, np.nan], [0.4, np.nan], [0.6, np.nan]])
    evaluation_features = np.array([[0.55, np.nan]])
    ood = _source_ood(train, evaluation, train_features, evaluation_features)
    market = np.array([[0.50, 0.30, 0.20]])
    model = _anchored_probabilities(market, np.array([[0.1, -0.1, 0.0]]))
    _, used_model = _fallback_predictions(market, model, ood)
    assert not ood[0]
    assert used_model.tolist() == [True]

    class _ZeroDeltaEstimator:
        classes_ = np.array([0, 1, 2])

        def fit(self, features, target):
            assert len(features) == len(target)
            return self

        def predict_log_proba(self, features):
            return np.zeros((len(features), 3))

    import unified_model.gate_b as gate_b

    def _panel(rows, grade):
        frame = pd.DataFrame({name: np.full(rows, 0.25 + index / 100.0) for index, name in enumerate(FEATURE_COLUMNS)})
        frame["market_probability_3"] = 0.50
        frame["market_probability_1"] = 0.30
        frame["market_probability_0"] = 0.20
        frame["predicted_final_sp_input_3"] = np.nan
        frame["predicted_final_sp_input_1"] = np.nan
        frame["predicted_final_sp_input_0"] = np.nan
        frame["market_eligible"] = True
        frame["result_code"] = np.resize(np.array(["3", "1", "0"]), rows)
        frame["source_grade"] = grade
        frame["issue"] = [f"i{index // 3}" for index in range(rows)]
        return frame

    monkeypatch.setattr(gate_b, "_make_estimator", lambda model_id, seed: _ZeroDeltaEstimator())
    _, actual_model, _, actual_used, actual_delta = _evaluate_family(
        "LOGISTIC_RESIDUAL", _panel(120, "RETROSPECTIVE_PROXY_PCLOSE"), _panel(1, "RETROSPECTIVE_PROXY"), 204001
    )
    assert actual_used.tolist() == [True]
    assert np.allclose(actual_model, np.array([[0.50, 0.30, 0.20]]), atol=1e-14, rtol=0)
    assert np.allclose(actual_delta, 0.0)


def test_selection_includes_market_and_prefers_it_without_material_residual_gain() -> None:
    rows = []
    for year in (2021, 2022, 2023):
        rows.extend(
            [
                {"split": f"CV_{year}", "model_id": "MARKET_ONLY", "view": "PURE_MARKET", "log_loss": 1.0, "matched_label_rows": 100},
                {"split": f"CV_{year}", "model_id": "LOGISTIC_RESIDUAL", "view": "MODEL_ONLY_COVERED", "log_loss": 1.0000005, "matched_label_rows": 100},
            ]
        )
    selected = _selection(pd.DataFrame(rows))
    assert set(selected.model_id) == {"MARKET_ONLY", "LOGISTIC_RESIDUAL"}
    assert selected.loc[selected.selected_for_primary, "model_id"].tolist() == ["MARKET_ONLY"]


def test_only_honest_issue_summary_mlp_identifier_remains() -> None:
    assert "ISSUE_CONTEXT_SUMMARY_MLP_RESIDUAL" in MODEL_ORDER
    assert all("SET_MLP" not in model and "DEEP" not in model for model in MODEL_ORDER)
