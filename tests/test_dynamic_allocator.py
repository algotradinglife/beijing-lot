from __future__ import annotations

import sqlite3

import numpy as np
import pandas as pd

from src.dynamic_allocator.contract import FUNDED_UNITS
from src.dynamic_allocator.pipeline import (
    _lambda_from_prediction,
    _load_labels_exact,
    _settlement_reason_ledger,
    blend_units,
    build_allocations,
    decide,
)


def test_blend_endpoints_and_budget() -> None:
    u0 = np.array([64, 64, 0])
    u1 = np.array([0, 32, 96])
    keys = np.array(["a", "b", "c"])
    assert np.array_equal(blend_units(u0, u1, 0.0, keys), u0)
    assert np.array_equal(blend_units(u0, u1, 1.0, keys), u1)
    middle = blend_units(u0, u1, 0.5, keys)
    assert middle.sum() == FUNDED_UNITS
    assert (middle >= 0).all()


def test_lambda_mapping_is_bounded_and_prefers_a0_at_nonpositive_delta() -> None:
    output = _lambda_from_prediction(np.array([-10.0, 0.0, 5.0, 20.0]), 10.0)
    assert np.allclose(output, [0.0, 0.0, 0.5, 1.0])


def test_build_allocations_keeps_integer_budget() -> None:
    rows = []
    for cell, units in (("S1O1A0", [64, 64]), ("S1O1A1", [32, 96])):
        for ticket, value, unit in zip(("a", "b"), (1.0, 2.0), units, strict=True):
            rows.append({
                "issue_code": "23001", "issue_year": 2023, "horizon": "10h",
                "cell": cell, "ticket_key": ticket, "stake_units": unit,
                "stake": unit * 2.0, "predicted_ticket_value": value,
            })
    policies = pd.DataFrame({"issue_code": ["23001"], "arm": ["L050"], "lam": [0.5]})
    output = build_allocations(pd.DataFrame(rows), policies)
    assert output.stake_units.sum() == FUNDED_UNITS
    assert output.stake.eq(output.stake_units * 2).all()


def test_decision_prefers_learned_only_when_it_beats_endpoints() -> None:
    matched_rows, risk_rows = [], []
    for year in (2023, 2024):
        for arm in ("L000", "L025", "L050", "L075", "L100", "DYN_RIDGE", "DYN_HGBR"):
            lift = 20.0 if arm == "DYN_HGBR" else 10.0 if arm == "L100" else 5.0
            matched_rows.append({"issue_year": year, "arm": arm, "total_lift": lift})
            risk_rows.append({
                "issue_year": year, "arm": arm, "max_drawdown_pct": 0.03,
                "longest_losing_run": 5, "payout_hhi": 0.1,
            })
    result = decide({"matched": pd.DataFrame(matched_rows), "risk": pd.DataFrame(risk_rows)})
    assert result["disposition"] == "DYNAMIC_ALLOCATOR_INCREMENT"


def test_exact_issue_loader_does_not_assume_calendar_prefix(tmp_path) -> None:
    database = tmp_path / "settlement.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """CREATE TABLE match_features (
                issue TEXT, match_idx INTEGER, result_code TEXT, winning_sp REAL,
                official_sp_3 REAL, official_sp_1 REAL, official_sp_0 REAL,
                has_trusted_settlement INTEGER, settlement_quality TEXT
            )"""
        )
        connection.execute(
            "INSERT INTO match_features VALUES ('22112', 1, '3', 2.1, 2.1, 3.2, 4.0, 1, 'trusted')"
        )
    output = _load_labels_exact(database, ["22112"])
    assert output.issue_code.tolist() == ["22112"]
    assert output.canonical_fixture_key.tolist() == ["bjslot:22112:001"]


def test_reason_ledger_distinguishes_untrusted_from_absent() -> None:
    support = '{"bjslot:22112:001":["3","1"],"bjslot:22112:002":["3","1"]}'
    cells = pd.DataFrame([{
        "issue_code": "22112", "issue_year": 2023,
        "issue_anchor_ts": "2023-02-26T23:59:00", "horizon": "10h",
        "cell": "S1O1A0", "status_preoutcome": "ACTIVE", "support_json": support,
    }])
    labels = pd.DataFrame([{
        "issue_code": "22112", "canonical_fixture_key": "bjslot:22112:001",
        "has_trusted_settlement": 0, "result_code": "3", "winning_sp": 2.1,
    }])
    ledger = _settlement_reason_ledger(cells, labels)
    assert ledger.settlement_reason.tolist() == [
        "UNTRUSTED_SETTLEMENT", "SOURCE_ROW_ABSENT"
    ]
