from __future__ import annotations

import sqlite3

import pandas as pd

import issue312.surface as surface


def test_causal_loader_opens_no_future_outcome_columns(tmp_path, monkeypatch) -> None:
    inference_rows = []
    for issue, year in (("A", 2022), ("B", 2023)):
        for outcome, probability in (("3", 0.5), ("1", 0.2), ("0", 0.3)):
            inference_rows.append(
                {
                    "issue_code": issue,
                    "match_idx": 1,
                    "snapshot_kind": "10h",
                    "issue_anchor_ts": pd.Timestamp(f"{year}-01-01"),
                    "issue_year": year,
                    "temporal_role": "tune" if year == 2022 else "calibration",
                    "native_handicap_line": 0.0,
                    "n_available_books": 10,
                    "mapping_accepted": True,
                    "outcome_code": outcome,
                    "q_eu_bjline": probability,
                    "q_line_only_control": probability,
                    "eu_vs_line_divergence": 0.0,
                }
            )
    inference = tmp_path / "inference.parquet"
    pd.DataFrame(inference_rows).to_parquet(inference, index=False)
    labels = tmp_path / "labels.parquet"
    pd.DataFrame(
        {
            "issue_code": ["A", "B"],
            "match_idx": [1, 1],
            "temporal_role": ["tune", "calibration"],
            "issue_year": [2022, 2023],
            "target_outcome": ["3", "0"],
        }
    ).to_parquet(labels, index=False)
    database = tmp_path / "labels.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE match_features (
                issue TEXT, match_idx INTEGER, winning_sp REAL, result_code TEXT
            )
            """
        )
        connection.executemany(
            "INSERT INTO match_features VALUES (?, ?, ?, ?)",
            [("A", 1, 2.2, "3"), ("B", 1, 4.0, "0")],
        )
    probabilities = tmp_path / "probabilities.parquet"
    values = tmp_path / "values.parquet"
    pd.DataFrame({"3": [0.5, 0.5], "1": [0.2, 0.2], "0": [0.3, 0.3]}).to_parquet(
        probabilities, index=False
    )
    pd.DataFrame(
        {
            "ev_raw_3": [1.0, 1.0],
            "ev_raw_1": [0.4, 0.4],
            "ev_raw_0": [0.6, 0.6],
        }
    ).to_parquet(values, index=False)
    monkeypatch.setattr(surface, "INFERENCE_VIEW", inference)
    monkeypatch.setattr(surface, "LABELS_PRE2024", labels)
    monkeypatch.setattr(surface, "LABELS_SQLITE", database)

    tensor, probability_rows, value_rows, receipt = surface.load_causal_issue209_inputs(
        probabilities,
        values,
        years=(2022,),
    )

    assert set(tensor["issue"]) == {"A"}
    assert len(probability_rows) == len(value_rows) == 1
    assert receipt["label_max_year_opened"] == 2022
    assert receipt["future_outcome_columns_opened"] == []
    assert receipt["future_label_identity_columns_opened"] == [
        "issue_code",
        "match_idx",
    ]
