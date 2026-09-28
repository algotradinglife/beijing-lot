"""Contract tests for the #501 incremental QMD squared-error diagnostic.

Deterministic, in-memory, and offline: no network, no database, no files.
They cover normal rows, partial/all missing labels, empty input, duplicate
identifiers, wrong types, and range/non-finite failures.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from qmd_incremental_mvp import squared_errors  # noqa: E402


def test_normal_rows_preserve_order_and_exact_values():
    out = squared_errors(["001", "002", "003"], [0.25, 0.5, 1.0], [0, 1, 1])
    assert out == [
        {"fixture_id": "001", "squared_error": 0.0625},
        {"fixture_id": "002", "squared_error": 0.25},
        {"fixture_id": "003", "squared_error": 0.0},
    ]
    assert all(isinstance(row["fixture_id"], str) for row in out)


def test_none_label_yields_none_not_zero():
    out = squared_errors(["a", "b"], [0.4, 0.4], [None, 0])
    assert out[0]["squared_error"] is None
    assert out[1]["squared_error"] == pytest.approx(0.16)


def test_partial_and_all_missing_labels():
    partial = squared_errors(["a", "b", "c"], [0.2, 0.8, 0.5], [None, 1, None])
    assert [row["squared_error"] for row in partial] == [None, pytest.approx(0.04), None]

    all_missing = squared_errors(["a", "b"], [0.2, 0.8], [None, None])
    assert all(row["squared_error"] is None for row in all_missing)


def test_empty_input_returns_empty_list():
    assert squared_errors([], [], []) == []


def test_boundary_probabilities_are_accepted():
    out = squared_errors(["lo", "hi"], [0.0, 1.0], [0, 1])
    assert out == [
        {"fixture_id": "lo", "squared_error": 0.0},
        {"fixture_id": "hi", "squared_error": 0.0},
    ]


def test_integer_inputs_are_accepted_and_returned_as_float():
    out = squared_errors(["a"], [1], [0])
    assert out[0]["squared_error"] == 1.0
    assert isinstance(out[0]["squared_error"], float)


def test_duplicate_ids_are_rejected():
    with pytest.raises(ValueError, match="duplicated"):
        squared_errors(["a", "a"], [0.1, 0.2], [0, 1])


def test_empty_id_is_rejected():
    with pytest.raises(ValueError, match="nonempty"):
        squared_errors([""], [0.1], [0])


def test_non_string_id_is_rejected():
    with pytest.raises(TypeError, match="ids\\[0\\]"):
        squared_errors([1], [0.1], [0])


def test_unequal_lengths_are_rejected():
    with pytest.raises(ValueError, match="equal lengths"):
        squared_errors(["a", "b"], [0.1], [0])


def test_bool_predicted_is_rejected():
    with pytest.raises(TypeError, match="predicted\\[0\\]"):
        squared_errors(["a"], [True], [0])


def test_bool_label_is_rejected():
    with pytest.raises(TypeError, match="observed\\[0\\]"):
        squared_errors(["a"], [0.5], [False])


def test_non_numeric_predicted_is_rejected():
    with pytest.raises(TypeError, match="predicted\\[0\\]"):
        squared_errors(["a"], ["0.5"], [0])


def test_string_label_is_rejected():
    with pytest.raises(TypeError, match="observed\\[0\\]"):
        squared_errors(["a"], [0.5], ["1"])


@pytest.mark.parametrize("bad", [-0.0001, 1.0001, -1.0, 2.0])
def test_out_of_range_probability_is_rejected(bad):
    with pytest.raises(ValueError, match="\\[0, 1\\]"):
        squared_errors(["a"], [bad], [0])


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_probability_is_rejected(bad):
    with pytest.raises(ValueError, match="finite"):
        squared_errors(["a"], [bad], [0])


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_label_is_rejected(bad):
    with pytest.raises(ValueError, match="finite"):
        squared_errors(["a"], [0.5], [bad])


@pytest.mark.parametrize("bad", [2, -1, 0.5])
def test_non_binary_label_is_rejected(bad):
    with pytest.raises(ValueError, match="0, 1, or None"):
        squared_errors(["a"], [0.5], [bad])


def test_non_sequence_input_is_rejected():
    with pytest.raises(TypeError, match="sequence"):
        squared_errors("abc", [0.1], [0])


def test_all_missing_output_has_no_nan():
    out = squared_errors(["a"], [0.5], [None])
    assert out[0]["squared_error"] is None
    assert not isinstance(out[0]["squared_error"], float)


def test_error_does_not_leak_partial_results():
    # A bad row anywhere fails the whole call rather than silently dropping rows.
    with pytest.raises(ValueError):
        squared_errors(["a", "b"], [0.5, 1.5], [0, 1])
    assert not math.isnan(0.0)
