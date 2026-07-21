from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import run_sp_eff_001 as experiment  # noqa: E402


def _make_live_db(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE matches(
            match_id TEXT PRIMARY KEY, issue TEXT, match_idx INTEGER,
            league TEXT, kickoff_ts TEXT, handicap_line REAL
        );
        CREATE TABLE snapshots(
            id INTEGER PRIMARY KEY AUTOINCREMENT, match_id TEXT,
            snapshot_ts TEXT, sp_3 REAL, sp_1 REAL, sp_0 REAL
        );
        CREATE TABLE settlements(
            match_id TEXT PRIMARY KEY, result_code TEXT, settled_ts TEXT
        );
        """
    )
    for index, (issue, result) in enumerate(
        [("A", "3"), ("A", "1"), ("B", "0"), ("B", "3")], start=1
    ):
        match_id = f"m{index}"
        connection.execute(
            "INSERT INTO matches VALUES(?,?,?,?,?,?)",
            (match_id, issue, index, "test", f"2026-07-{index:02d}T12:00:00", 0.0),
        )
        connection.execute(
            "INSERT INTO settlements VALUES(?,?,?)",
            (match_id, result, f"2026-07-{index:02d}T06:00:00Z"),
        )
        # Kickoff is 04:00 UTC. Only 02:00 and 03:00 are eligible.
        connection.execute(
            "INSERT INTO snapshots(match_id,snapshot_ts,sp_3,sp_1,sp_0) VALUES(?,?,?,?,?)",
            (match_id, f"2026-07-{index:02d}T02:00:00Z", 2.5, 3.2, 3.0),
        )
        connection.execute(
            "INSERT INTO snapshots(match_id,snapshot_ts,sp_3,sp_1,sp_0) VALUES(?,?,?,?,?)",
            (match_id, f"2026-07-{index:02d}T03:00:00Z", 2.4, 3.3, 3.1),
        )
        # An incomplete later vector must not synthesize a mixed close.
        connection.execute(
            "INSERT INTO snapshots(match_id,snapshot_ts,sp_3,sp_1,sp_0) VALUES(?,?,?,?,?)",
            (match_id, f"2026-07-{index:02d}T03:30:00Z", 2.2, None, 3.3),
        )
        # Exact-kickoff and post-kickoff rows are future information.
        for hour in (4, 5):
            connection.execute(
                "INSERT INTO snapshots(match_id,snapshot_ts,sp_3,sp_1,sp_0) VALUES(?,?,?,?,?)",
                (match_id, f"2026-07-{index:02d}T{hour:02d}:00:00Z", 1.5, 4.0, 5.0),
            )
    connection.execute(
        "INSERT INTO snapshots(match_id,snapshot_ts,sp_3,sp_1,sp_0) VALUES(?,?,?,?,?)",
        ("m1", "not-a-time", 2.0, 3.0, 4.0),
    )
    connection.commit()
    connection.close()


def test_load_uses_complete_vector_strictly_before_beijing_kickoff(tmp_path: Path) -> None:
    database = tmp_path / "live.db"
    _make_live_db(database)

    frame, audit = experiment.load_experiment_frame(database)

    assert len(frame) == 4
    assert set(frame["closing_snapshot_ts"]) == {
        f"2026-07-{index:02d}T03:00:00Z" for index in range(1, 5)
    }
    assert np.allclose(frame["mtk"], 60.0)
    assert np.allclose(frame["sp_3"], 2.4)
    assert audit.invalid_timestamp_rows == 1
    assert audit.postkickoff_rows_rejected == 8
    assert audit.extract_sha256 == experiment.load_experiment_frame(database)[1].extract_sha256

    cutoff_frame, cutoff_audit = experiment.load_experiment_frame(
        database, as_of="2026-07-02T02:30:00Z"
    )
    assert len(cutoff_frame) == 1
    assert cutoff_frame.iloc[0]["closing_snapshot_ts"] == "2026-07-01T03:00:00Z"
    assert cutoff_audit.settled_matches == 1


def test_as_of_excludes_late_settlements_and_is_repeatable(tmp_path: Path) -> None:
    database = tmp_path / "live.db"
    _make_live_db(database)
    cutoff = "2026-07-02T02:30:00Z"

    first_frame, first_audit = experiment.load_experiment_frame(database, as_of=cutoff)

    connection = sqlite3.connect(database)
    connection.execute(
        "INSERT INTO matches VALUES(?,?,?,?,?,?)",
        ("late", "A", 99, "test", "2026-07-01T12:00:00", 0.0),
    )
    connection.execute(
        "INSERT INTO snapshots(match_id,snapshot_ts,sp_3,sp_1,sp_0) VALUES(?,?,?,?,?)",
        ("late", "2026-07-01T02:00:00Z", 2.5, 3.2, 3.0),
    )
    connection.execute(
        "INSERT INTO settlements VALUES(?,?,?)",
        ("late", "3", "2026-07-02T03:00:00Z"),
    )
    connection.commit()
    connection.close()

    second_frame, second_audit = experiment.load_experiment_frame(database, as_of=cutoff)

    pd.testing.assert_frame_equal(first_frame, second_frame)
    assert first_audit.settled_matches == second_audit.settled_matches == 1
    assert first_audit.extract_sha256 == second_audit.extract_sha256


def test_markdown_figure_path_is_relative_to_custom_report_directory(tmp_path: Path) -> None:
    figure = tmp_path / "assets" / "calibration.png"
    report = tmp_path / "reports" / "nested" / "SP-EFF-001.md"

    link = experiment._markdown_relative_path(figure, report)

    assert link == "../../assets/calibration.png"


def test_market_probability_is_jointly_normalized_not_naive_inverse(tmp_path: Path) -> None:
    database = tmp_path / "live.db"
    _make_live_db(database)
    frame, _ = experiment.load_experiment_frame(database)

    probabilities = experiment.market_probabilities(frame)

    assert np.allclose(probabilities.sum(axis=1), 1.0)
    assert not np.isclose(probabilities[0, 0], 1.0 / frame.loc[0, "sp_3"])
    assert (probabilities > 0).all()


def test_issue_split_is_chronological_and_disjoint() -> None:
    frame = pd.DataFrame(
        {
            "issue": ["late", "early", "middle", "early"],
            "kickoff_at": pd.to_datetime(
                ["2026-03-01", "2026-01-02", "2026-02-01", "2026-01-01"], utc=True
            ),
        }
    )

    train, test, train_issues, test_issues = experiment.chronological_issue_split(
        frame, train_fraction=2 / 3
    )

    assert train_issues == ("early", "middle")
    assert test_issues == ("late",)
    assert set(train["issue"]).isdisjoint(set(test["issue"]))


def test_metrics_and_temperature_are_valid() -> None:
    outcomes = np.eye(3)[np.array([0, 1, 2, 0, 1, 2])]
    probabilities = np.array(
        [
            [0.60, 0.20, 0.20], [0.20, 0.60, 0.20], [0.20, 0.20, 0.60],
            [0.55, 0.25, 0.20], [0.20, 0.55, 0.25], [0.25, 0.20, 0.55],
        ]
    )

    temperature = experiment.fit_temperature(probabilities, outcomes)
    scaled = experiment.temperature_scale(probabilities, temperature)
    calibration = experiment.calibration_table(outcomes, scaled)

    assert 0.25 <= temperature <= 4.0
    assert np.allclose(scaled.sum(axis=1), 1.0)
    assert experiment.multiclass_log_loss(outcomes, scaled) >= 0.0
    assert 0.0 <= experiment.multiclass_brier(outcomes, scaled) <= 2.0
    assert set(["p_value_holm", "significant_5pct"]).issubset(calibration.columns)

    predictions = {
        "B0 uniform random": np.full_like(outcomes, 1 / 3),
        "B1 normalized inverse SP": probabilities,
        "B1-T train-fitted temperature": scaled,
        "B2 historical outcome frequency": np.tile(
            np.array([0.4, 0.3, 0.3]), (len(outcomes), 1)
        ),
    }
    comparisons = experiment.paired_score_comparisons(
        outcomes,
        predictions,
        ["A", "A", "B", "B", "C", "C"],
        bootstrap_samples=100,
    )
    assert len(comparisons) == 8
    assert np.isfinite(comparisons[["Delta", "95% CI low", "95% CI high"]]).all().all()
