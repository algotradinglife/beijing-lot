"""Scientific boundary tests for Issue #238 v4."""

from __future__ import annotations

import hashlib
import json
import sqlite3

import pytest
from pathlib import Path

import numpy as np
import pandas as pd

from src.divergence_materializer.contract import HORIZONS, OUTCOMES
from src.issue_codes import SOURCE_ISSUE_DATE_SOURCE
from src.divergence_materializer.data import (
    attach_native_labels,
    load_development_labels,
    load_issue_roles,
)
from src.divergence_materializer.model import fit_horizon_models, predict_panel
from src.divergence_materializer.validate import validate_package


def _sqlite(path: Path, statements: str) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(statements)


def test_issue_roles_take_the_year_from_the_code_not_from_kickoff(tmp_path: Path) -> None:
    """The year comes from the issue code, so kickoff cannot move it and no kickoff cannot lose it.

    Both properties used to depend on the registry: a late kickoff could not override the recorded
    year, and an issue whose inventory held no usable kickoff still got its year from the table.
    The code answers both now -- a missing kickoff no longer makes the year unknown, which is
    stronger than what the table could offer.
    """
    candidate = tmp_path / "candidate.sqlite"
    registry = tmp_path / "registry.sqlite"
    with sqlite3.connect(candidate) as connection:
        connection.execute(
            "CREATE TABLE inventory(issue_code TEXT, match_idx INTEGER, kickoff_ts TEXT)"
        )
        rows = [(f"20{index:04d}", 1, "2020-01-01 12:00:00") for index in range(806)]
        rows.extend(
            [
                ("220101", 1, "2022-06-01 12:00:00"),
                ("250101", 1, None),
            ]
        )
        connection.executemany("INSERT INTO inventory VALUES(?,?,?)", rows)
    with sqlite3.connect(registry) as connection:
        connection.execute("CREATE TABLE issues(issue TEXT, year INTEGER)")
        connection.execute("INSERT INTO issues VALUES('250101', 2025)")

    roles = load_issue_roles(candidate).set_index("issue_code")

    assert roles.loc["220101", "temporal_role"] == "tune"
    assert roles.loc["220101", "issue_year"] == 2022
    assert roles.loc["250101", "temporal_role"] == "sealed_feature_only"
    assert roles.loc["250101", "issue_year"] == 2025, "the code, not the absent kickoff"
    assert roles.loc["250101", "issue_date_source"] == SOURCE_ISSUE_DATE_SOURCE


def test_an_issue_code_with_no_year_stops_the_run(tmp_path: Path) -> None:
    """A malformed code must fail rather than be dated by whatever it starts with."""
    from src.divergence_materializer.data import DataContractError

    candidate = tmp_path / "candidate.sqlite"
    with sqlite3.connect(candidate) as connection:
        connection.execute(
            "CREATE TABLE inventory(issue_code TEXT, match_idx INTEGER, kickoff_ts TEXT)"
        )
        connection.executemany(
            "INSERT INTO inventory VALUES(?,?,?)",
            [(f"20{index:04d}", 1, "2020-01-01 12:00:00") for index in range(807)]
            + [("no-kickoff-2025", 1, "2022-06-01 12:00:00")],
        )

    with pytest.raises(DataContractError):
        load_issue_roles(candidate)


def test_label_reader_physically_queries_only_allow_list(tmp_path: Path) -> None:
    labels = tmp_path / "labels.sqlite"
    _sqlite(
        labels,
        """
        CREATE TABLE matches(issue TEXT, match_idx INTEGER, score TEXT);
        INSERT INTO matches VALUES('dev', 1, '2-1');
        INSERT INTO matches VALUES('sealed', 1, '9-9');
        """,
    )

    result = load_development_labels(labels, {"dev"})

    assert result["issue_code"].tolist() == ["dev"]
    assert result[["home_goals", "away_goals"]].iloc[0].tolist() == [2, 1]


def test_native_target_uses_score_plus_beijing_handicap() -> None:
    panel = pd.DataFrame(
        {
            "canonical_fixture_key": ["a", "b", "c"],
            "issue_code": ["dev", "dev", "dev"],
            "match_idx": [1, 2, 3],
            "snapshot_kind": ["1h", "1h", "1h"],
            "temporal_role": ["fit", "fit", "fit"],
            "native_handicap_line": [-1.0, -1.0, 1.0],
            "native_line_supported": [True, True, True],
        }
    )
    labels = pd.DataFrame(
        {
            "issue_code": ["dev", "dev", "dev"],
            "match_idx": [1, 2, 3],
            "home_goals": pd.Series([2, 1, 0], dtype="Int64"),
            "away_goals": pd.Series([0, 0, 2], dtype="Int64"),
            "label_available": [True, True, True],
        }
    )

    result = attach_native_labels(panel, labels)

    assert result["target_outcome"].tolist() == ["3", "1", "0"]


def _synthetic_development() -> pd.DataFrame:
    rng = np.random.default_rng(238)
    rows: list[dict[str, object]] = []
    roles = (("fit", 10), ("tune", 4), ("calibration", 4))
    for horizon in HORIZONS:
        for role, issue_count in roles:
            for issue_index in range(issue_count):
                issue = f"{role}-{issue_index:02d}"
                for fixture in range(80):
                    probability = rng.dirichlet([1.8, 1.4, 1.6])
                    line = float(rng.choice([-2, -1, 0, 1, 2]))
                    # EU probabilities carry the true event-specific signal;
                    # the line-only control cannot reconstruct it.
                    outcome = OUTCOMES[int(np.argmax(probability))]
                    row: dict[str, object] = {
                        "canonical_fixture_key": f"{issue}:{fixture}",
                        "issue_code": issue,
                        "match_idx": fixture + 1,
                        "snapshot_kind": horizon,
                        "temporal_role": role,
                        "native_handicap_line": line,
                        "native_line_supported": True,
                        "native_handicap_line_raw": line,
                        "handicap_norm_source": "TEST",
                        "n_available_books": 10,
                        "causal_grade": "RETROSPECTIVE_RELATIVE_PROXY",
                        "target_outcome": outcome,
                    }
                    for code, value in zip(OUTCOMES, probability):
                        row[f"q_eu_{code}"] = float(value)
                        row[f"line_x_q_eu_{code}"] = float(line * value)
                    rows.append(row)
    return pd.DataFrame(rows)


def test_chronological_translator_beats_line_only_control_and_predicts_sealed() -> None:
    development = _synthetic_development()
    models = fit_horizon_models(development)
    assert [model.horizon for model in models] == list(HORIZONS)
    assert all(model.accepted for model in models)
    for model in models:
        deltas = model.bootstrap.set_index(["temporal_role", "metric"])[
            "experimental_minus_control"
        ]
        assert (deltas < 0).all()

    sealed = development.loc[development["temporal_role"].eq("tune")].copy()
    sealed["temporal_role"] = "sealed_feature_only"
    sealed["issue_year"] = 2025
    sealed["issue_anchor_ts"] = pd.Timestamp("2025-01-01")
    sealed["issue_date_source"] = "SOURCE_ISSUE_REGISTRY_YEAR"
    predicted = predict_panel(sealed.drop(columns="target_outcome"), models)
    assert predicted["mapping_accepted"].all()
    for code in OUTCOMES:
        assert predicted[f"q_eu_bjline_{code}"].notna().all()
    assert "target_outcome" not in predicted.columns


def test_package_validator_recomputes_probability_and_sealed_label_boundaries(
    tmp_path: Path,
) -> None:
    root = tmp_path / "package"
    (root / "inference").mkdir(parents=True)
    (root / "development").mkdir()
    inference = pd.DataFrame(
        {
            "canonical_fixture_key": ["a", "a", "a"],
            "snapshot_kind": ["1h", "1h", "1h"],
            "mapping_accepted": [True, True, True],
            "q_eu_raw_1x2": [0.5, 0.3, 0.2],
            "q_eu_bjline": [0.45, 0.35, 0.2],
            "q_line_only_control": [0.4, 0.3, 0.3],
            "q_bj_sp_available": [False, False, False],
            "q_bj_sp_devig": [np.nan, np.nan, np.nan],
        }
    )
    labels = pd.DataFrame(
        {
            "issue_year": [2023],
            "temporal_role": ["calibration"],
        }
    )
    inference.to_parquet(
        root / "inference" / "relative_horizon_view.parquet", index=False
    )
    labels.to_parquet(root / "development" / "labels_pre2024.parquet", index=False)
    (root / "SUMMARY.json").write_text(
        json.dumps({"inference_cell_count": 3, "sealed_label_rows_read": 0}),
        encoding="utf-8",
    )
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            files[str(path.relative_to(root))] = hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    (root / "MANIFEST.json").write_text(json.dumps({"files": files}), encoding="utf-8")

    result = validate_package(root)

    assert result["verdict"] == "PASS"
    assert result["mapped_fixture_horizons"] == 1
