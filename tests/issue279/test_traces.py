import numpy as np
import pandas as pd

from issue279.traces import build_cell_trace, build_ticket_traces


def _inputs():
    units = pd.DataFrame(
        {
            "issue": ["A"] * 7,
            "match_idx": range(1, 8),
            "issue_year": [2023] * 7,
            "snapshot_kind": ["10h"] * 7,
            "native_handicap_line": [0.0] * 7,
            "n_available_books": [10] * 7,
            "mapping_accepted": [True] * 7,
            "eu_vs_line_divergence_3": [0.1] * 7,
            "eu_vs_line_divergence_1": [0.0] * 7,
            "eu_vs_line_divergence_0": [-0.1] * 7,
        }
    )
    probabilities = pd.DataFrame({"3": [0.5] * 7, "1": [0.3] * 7, "0": [0.2] * 7})
    values = pd.DataFrame(
        {
            "ev_raw_3": [1.1] * 7, "value_q10_3": [1.0] * 7, "value_q90_3": [1.2] * 7,
            "ev_raw_1": [0.9] * 7, "value_q10_1": [0.8] * 7, "value_q90_1": [1.0] * 7,
            "ev_raw_0": [0.8] * 7, "value_q10_0": [0.7] * 7, "value_q90_0": [0.9] * 7,
        }
    )
    chosen = pd.DataFrame([{"issue": "A", "n": 7, "k": 8, "generator": "TOP_VALUE"}])
    return units, probabilities, values, chosen


def test_cell_trace_is_pre_outcome_and_long() -> None:
    units, probabilities, values, _ = _inputs()
    trace = build_cell_trace(units, probabilities, values, issues={"A"})
    assert len(trace) == 21
    assert not {"Y", "realized_outcome", "SP_SETTLE"}.intersection(trace.columns)


def test_ticket_expected_value_applies_point65_once() -> None:
    units, probabilities, values, chosen = _inputs()
    bundle = build_ticket_traces(
        units, probabilities, values, chosen, seeds=(1,)
    )
    ticket = bundle.tickets[bundle.tickets.arm.eq("chosen")].iloc[0]
    expected = 2.0 * (0.65 * (0.5 ** 7) * (2.2 ** 7) - 1.0)
    assert np.isclose(ticket.predicted_expected_net_cny2, expected)
    assert len(bundle.legs[bundle.legs.arm.eq("chosen")]) == 8 * 7
    assert not {"Y", "realized_outcome", "SP_SETTLE"}.intersection(bundle.legs.columns)
