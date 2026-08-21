from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from issue291.modeling import (
    apply_platt_calibrator,
    derived_ticket_ev,
    deterministic_rare_event_sample,
    fit_platt_calibrator,
    reliability_table,
    stable_random_score,
    weighted_probability_metrics,
)


def test_rare_event_sample_keeps_positives_and_normalizes_issue_weight() -> None:
    rows = []
    for issue in ("A", "B"):
        for index in range(10):
            rows.append(
                {
                    "issue": issue,
                    "action_key": "X",
                    "candidate_identity": f"{issue}-{index}",
                    "hit": int(index == 0),
                }
            )
    sample = deterministic_rare_event_sample(pd.DataFrame(rows), negative_per_action=3)
    assert sample.groupby("issue")["hit"].sum().to_dict() == {"A": 1, "B": 1}
    assert sample.groupby("issue").size().to_dict() == {"A": 4, "B": 4}
    assert sample.groupby("issue")["issue_weight"].sum().to_numpy() == pytest.approx(
        np.ones(2)
    )


def test_platt_calibration_and_ev_are_bounded() -> None:
    raw = np.array([0.05, 0.1, 0.8, 0.9])
    target = np.array([0, 0, 1, 1])
    weight = np.ones(4)
    fitted = fit_platt_calibrator(raw, target, weight)
    calibrated = apply_platt_calibrator(raw, fitted)
    assert fitted.fitted
    assert np.all((calibrated > 0) & (calibrated < 1))
    assert calibrated[-1] > calibrated[0]
    assert derived_ticket_ev(np.array([0.5]), np.array([10.0]))[0] == pytest.approx(3.0)


def test_metrics_reliability_and_random_score_are_reproducible() -> None:
    frame = pd.DataFrame(
        {
            "hit": [0, 0, 1, 1],
            "issue_weight": [0.25] * 4,
            "p": [0.1, 0.2, 0.7, 0.9],
        }
    )
    metrics = weighted_probability_metrics(
        frame["hit"].to_numpy(), frame["p"].to_numpy(), frame["issue_weight"].to_numpy()
    )
    assert metrics["brier"] < 0.1
    assert metrics["average_precision"] > metrics["weighted_event_rate"]
    assert len(reliability_table(frame, probability_column="p", bins=2)) == 2
    assert stable_random_score("1", "x") == stable_random_score("1", "x")
