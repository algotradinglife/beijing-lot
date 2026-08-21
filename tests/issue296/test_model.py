from __future__ import annotations

import numpy as np
import pandas as pd

from issue296.model import fit_gate_ensemble, predict_weights


def _table() -> pd.DataFrame:
    rows = []
    for year, count in [(2019, 8), (2020, 8), (2021, 8), (2022, 6), (2023, 6)]:
        for index in range(count):
            feature = float(index % 2)
            rows.append(
                {
                    "issue": year * 100 + index,
                    "issue_year": year,
                    "x": feature,
                    "return_A": 0.20 if feature else -0.10,
                    "return_B": -0.10 if feature else 0.20,
                    "available_A": True,
                    "available_B": True,
                }
            )
    return pd.DataFrame(rows)


def test_gate_outputs_available_simplex_weights() -> None:
    table = _table()
    fits = fit_gate_ensemble(
        table,
        feature_columns=["x"],
        expert_ids=["A", "B"],
        condition="candidate_warm",
        seeds=(1,),
        epochs=150,
    )
    predicted = predict_weights(fits, table.query("issue_year == 2023"))
    columns = ["weight_A", "weight_B", "weight_CASH"]
    assert np.allclose(predicted[columns].sum(axis=1), 1.0)
    assert (predicted[columns] >= 0).all(axis=None)
    assert (
        predicted.loc[1::2, "weight_A"].mean() > predicted.loc[1::2, "weight_B"].mean()
    )


def test_gate_masks_unavailable_expert() -> None:
    table = _table()
    fits = fit_gate_ensemble(
        table,
        feature_columns=["x"],
        expert_ids=["A", "B"],
        condition="neutral",
        seeds=(2,),
        epochs=20,
    )
    test = table.query("issue_year == 2023").copy()
    test["available_A"] = False
    predicted = predict_weights(fits, test)
    assert predicted["weight_A"].eq(0.0).all()


def test_gate_rejects_opening_sealed_rows() -> None:
    table = _table()
    table.loc[0, "issue_year"] = 2024
    try:
        fit_gate_ensemble(
            table,
            feature_columns=["x"],
            expert_ids=["A", "B"],
            condition="neutral",
            seeds=(3,),
            epochs=5,
        )
    except AssertionError as error:
        assert "2024+" in str(error)
    else:
        raise AssertionError("sealed rows must fail closed")
