import numpy as np

from issue284.pilot import (
    fit_subset_pilot,
    predict_subset_pilot,
    prepare_subset_arrays,
)


def test_subset_pilot_trains_with_original_issue_groups() -> None:
    rng = np.random.default_rng(4)
    rows = 12
    cells = rng.normal(size=(rows, 5, 3, 4))
    mask = np.ones((rows, 5), dtype=bool)
    actions = rng.normal(size=(rows, 3))
    target = rng.normal(size=rows) * 100
    issue = np.repeat(np.arange(4), 3)
    train = issue < 3
    arrays = prepare_subset_arrays(cells, mask, actions, target, issue, train)
    model, receipt = fit_subset_pilot(
        arrays, train, seed=3, epochs=2, issues_per_batch=2
    )
    prediction = predict_subset_pilot(
        model, arrays, ~train, target_scale=float(receipt["target_scale"])
    )
    assert len(prediction) == 3
    assert np.isfinite(prediction[["expected_value", "q10", "q50", "q90"]]).all().all()
    assert receipt["training_issues"] == 3
    assert receipt["final_gradient_norm"] > 0


def test_subset_pilot_rejects_row_shape_mismatch() -> None:
    with np.testing.assert_raises_regex(ValueError, "cells must have shape"):
        prepare_subset_arrays(
            np.zeros((2, 3, 4)),
            np.ones((2, 3), dtype=bool),
            np.ones((2, 2)),
            np.ones(2),
            np.arange(2),
            np.ones(2, dtype=bool),
        )
