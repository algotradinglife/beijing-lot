from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.low_n_match_selector.contract import (
    DEVELOPMENT_YEARS,
    FUNDED_UNITS,
    ISSUE_STAKE_CNY,
    LABEL_RELATIVE,
    PAYOUT_FACTOR,
)
from src.low_n_match_selector.pipeline import (
    ContractError,
    _load_features,
    _load_labels,
    construct_preoutcome,
    fit_development_oof,
    refit_transfer_scores,
    settle,
)


REPO = Path(__file__).resolve().parents[2]


def _surface() -> pd.DataFrame:
    rows = []
    for arm in ("S0_RAW_MASS", "SELECTED_MODEL"):
        for match_idx in range(1, 7):
            rows.append(
                {
                    "issue": "x",
                    "issue_year": 2024,
                    "issue_anchor_ts": pd.Timestamp("2024-01-01", tz="UTC"),
                    "arm": arm,
                    "match_idx": match_idx,
                    "baseline_support": "31",
                    "selector_score": 1 - match_idx / 100,
                    "retained_mass": 1 - match_idx / 100,
                }
            )
    return pd.DataFrame(rows)


def test_full_cartesian_and_fixed_budget() -> None:
    _, bundles, tickets = construct_preoutcome(_surface())
    for row in bundles.itertuples(index=False):
        group = tickets[
            tickets["arm"].eq(row.arm) & tickets["n"].eq(row.n)
        ]
        assert len(group) == 2**row.n
        assert group["ticket_key"].nunique() == 2**row.n
        assert group["units"].sum() == FUNDED_UNITS
        assert group["stake_cny"].sum() == ISSUE_STAKE_CNY


def test_ticket_level_once_payout_and_untrusted_fail_closed() -> None:
    _, frozen, _ = construct_preoutcome(_surface())
    target = frozen[(frozen["arm"].eq("S0_RAW_MASS")) & frozen["n"].eq(3)]
    settlement = pd.DataFrame(
        [
            {
                "issue": "x",
                "match_idx": match_idx,
                "result_code": "3",
                "winning_sp": 2.0,
                "settlement_available": True,
            }
            for match_idx in (1, 2, 3)
        ]
    )
    bundles, _ = settle(target, settlement)
    row = bundles.iloc[0]
    expected = row["units_per_ticket"] * 2.0 * PAYOUT_FACTOR * (2.0**3)
    assert row["gross_cny"] == expected
    settlement.loc[0, "settlement_available"] = False
    rejected, _ = settle(target, settlement)
    assert rejected.iloc[0]["settlement_status"] == "UNTRUSTED_SELECTED_LEG"
    assert np.isnan(rejected.iloc[0]["pnl_cny"])


def test_oof_scores_every_preoutcome_fixture_and_is_strictly_prior() -> None:
    features = _load_features(REPO)
    labels = _load_labels(REPO, tuple(range(2017, 2022)))
    oof, _, selected = fit_development_oof(features, labels)
    for year in DEVELOPMENT_YEARS:
        expected = features[features["issue_year"].eq(year)][["issue", "match_idx"]]
        for _, group in oof[oof["issue_year"].eq(year)].groupby("family", observed=True):
            assert len(group) == len(expected)
            assert set(map(tuple, group[["issue", "match_idx"]].to_numpy())) == set(
                map(tuple, expected.to_numpy())
            )
            assert group["train_year_max"].eq(year - 1).all()
            assert (
                group["training_label_available_max_ts"]
                < group["target_decision_min_ts"]
            ).all()
    transfer, receipt = refit_transfer_scores(features, labels, selected)
    assert (
        transfer["training_label_available_max_ts"]
        < transfer["target_decision_min_ts"]
    ).all()
    assert (
        pd.Timestamp(receipt["training_label_available_max_ts"])
        < pd.Timestamp(receipt["target_decision_min_ts"])
    )


def test_non_boolean_availability_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / LABEL_RELATIVE
    path.parent.mkdir(parents=True)
    pd.DataFrame(
        {
            "issue_year": [2021],
            "issue": ["x"],
            "match_idx": [1],
            "label_available": ["yes"],
            "top2_hit": [True],
        }
    ).to_parquet(path, index=False)
    with pytest.raises(ContractError, match="strict boolean"):
        _load_labels(tmp_path, (2021,))


def test_manifest_is_nonempty_and_binds_delivery() -> None:
    manifest = json.loads((REPO / "results/low_n_match_selector/MANIFEST.json").read_text())
    assert len(manifest["files"]) >= 20
    assert "docs/research/Issue-355-LowN-Match-Selector.md" in manifest["files"]
    assert (
        "notebooks/research/low-n-match-selector/low_n_match_selector.ipynb"
        in manifest["files"]
    )
