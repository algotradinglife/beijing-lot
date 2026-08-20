import numpy as np
import pandas as pd

from issue282.data import PackedIssues
from issue282.training import (
    fit_controls,
    fit_deep_set,
    predict_controls,
    predict_deep_set,
    prepare_arrays,
)


def _training_inputs():
    rng = np.random.default_rng(282)
    issue_ids = tuple(f"22{i:03d}" for i in range(6))
    cells = rng.normal(size=(6, 4, 3, 3))
    mask = np.array([[1, 1, 1, 1]] * 5 + [[1, 1, 1, 0]], dtype=bool)
    cells[~np.repeat(mask[:, :, None], 3, axis=2)] = np.nan
    packed = PackedIssues(
        issue_ids=issue_ids,
        match_ids=tuple(("a", "b", "c", "d") for _ in issue_ids),
        cells=cells,
        match_mask=mask,
        feature_names=("p", "value", "divergence"),
    )
    rows = []
    for issue_index, issue in enumerate(issue_ids):
        for action in range(4):
            rows.append(
                {
                    "issue": issue,
                    "normalized_pnl_cny100": float((action - 2) * 50 + issue_index),
                }
            )
    labels = pd.DataFrame(rows)
    features = pd.DataFrame(
        rng.normal(size=(len(labels), 5)), columns=[f"x{i}" for i in range(5)]
    )
    development = labels["issue"].isin(issue_ids[:5]).to_numpy()
    return packed, labels, features, development


def test_controls_and_deep_set_train_on_chronological_arrays() -> None:
    packed, labels, features, development = _training_inputs()
    arrays = prepare_arrays(
        packed, features, labels, development_mask=development
    )
    controls = fit_controls(arrays, development, seed=1)
    control_predictions = predict_controls(controls, arrays.actions[~development])
    assert len(control_predictions) == 4
    assert np.isfinite(control_predictions.to_numpy()).all()

    model, receipt = fit_deep_set(
        arrays,
        development,
        seed=1,
        epochs=2,
        actions_per_issue=4,
        issues_per_batch=2,
    )
    predictions = predict_deep_set(
        model,
        arrays,
        ~development,
        target_scale=float(receipt["target_scale"]),
        issues_per_batch=2,
    )
    assert len(predictions) == 4
    assert np.isfinite(predictions.to_numpy()).all()
