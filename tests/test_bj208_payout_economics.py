"""Issue #208 REWORK v3 (PI payout-economics): payout semantics tests.

PI adversarial review (2026-08-15) established the controlling pre-tax
convention:

    pre_tax_gross_multiple = hit * 0.65 * product(official_final_sp_i)

The Beijing 0.65 is a ticket PAYOUT COEFFICIENT applied exactly once per
winning N-fold ticket — never divided out, never applied per leg, never
compounded as 0.65^N.  These tests attack the PRODUCTION entry points
(tickets.settle_tickets, incumbent.build_incumbent_paths, and the production
verify_package path) for the three failure modes named by PI:
  - omission        (multiple = product(SP), coefficient missing)
  - division-out    (payout inflated by /0.65)
  - 0.65^N          (coefficient compounded per leg)
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from parlay_policy.contract import (  # noqa: E402
    PAYOUT_COEFFICIENT,
    TICKET_STAKE_YUAN,
)
from parlay_policy.census import (  # noqa: E402
    IssuePanel,
)
from parlay_policy.incumbent import build_incumbent_paths  # noqa: E402
from parlay_policy.tickets import (  # noqa: E402
    _rows_to_frame,
    _ticket_row,
    settle_tickets,
)
from parlay_policy.verify import (  # noqa: E402
    verify_payout_economics,
)


# --- helpers ----------------------------------------------------------------


def _synthetic_panel(hit_legs: int = 3) -> IssuePanel:
    """Small M=4 x 3 panel; first `hit_legs` matches all hit with SP 2.0/3.0/4.0.

    Chosen ticket rows are [0,1,2] with outcomes all '3' (rank 0).  The
    official SP product for that ticket is 2.0*3.0*4.0 = 24.0, so the
    corrected pre-tax gross multiple must be 0.65*24.0 = 15.6.
    """
    m = 4
    control = np.full((m, 3), 0.333333, dtype=float)
    control[:, 2] = 0.333334
    control = control / control.sum(axis=1, keepdims=True)
    # Each row has distinct outcome-0 SP (2.0 / 3.0 / 4.0 / 5.0) so a 3-leg
    # ticket over rows [0,1,2] all outcome '3' has prod(official_sp) = 24.0.
    sp_rows = np.array([[2.0, 3.0, 4.0], [3.0, 4.0, 2.0], [4.0, 2.0, 3.0], [5.0, 2.0, 2.0]])
    predicted_sp = sp_rows.astype(float)
    official_sp = sp_rows.astype(float)
    realized = np.zeros((m, 3), dtype=bool)
    for row in range(hit_legs):
        realized[row, 0] = True  # outcome '3' hits
    for row in range(hit_legs, m):
        realized[row, 1] = True  # outcome '1' hits -> ticket misses
    return IssuePanel(
        split="CV_2023",
        issue="23999",
        year=2023,
        match_idx=np.arange(m),
        control_probability=control,
        experimental_probability=control.copy(),
        predicted_sp=predicted_sp,
        sp_seed_std=np.zeros((m, 3)),
        official_sp=official_sp,
        realized=realized,
        labels_available=True,
        match_ids=np.arange(m).astype(str),
    )


# --- golden payout formula (production entries) ------------------------------


def test_pre_tax_gross_multiple_applies_coefficient_once():
    """Production _rows_to_frame: hit multiple = 0.65 * prod(official_sp)."""
    panel = _synthetic_panel(hit_legs=3)
    selected = np.array([0, 1, 2])
    outcomes = np.array([0, 0, 0])  # all '3'
    rows = _rows_to_frame(panel, [selected], [outcomes], ["TEST"])
    assert len(rows) == 1
    row = rows.iloc[0]
    assert bool(row["realized_hit"]) is True
    assert float(row["official_sp_product"]) == pytest.approx(24.0, abs=1e-9)
    assert float(row["pre_tax_gross_multiple"]) == pytest.approx(
        PAYOUT_COEFFICIENT * 24.0, abs=1e-9
    )
    # raw diagnostic product is retained unadjusted (explicitly named).
    assert float(row["pre_tax_gross_multiple"]) != pytest.approx(24.0, abs=1e-9)


def test_pre_tax_gross_multiple_zero_on_miss():
    """Miss ticket multiple is 0.0 (hit flag False)."""
    panel = _synthetic_panel(hit_legs=3)
    selected = np.array([0, 1, 3])  # leg 3 misses ('1' realized)
    outcomes = np.array([0, 0, 0])
    rows = _rows_to_frame(panel, [selected], [outcomes], ["TEST"])
    row = rows.iloc[0]
    assert bool(row["realized_hit"]) is False
    assert float(row["pre_tax_gross_multiple"]) == 0.0


def test_expected_pre_tax_net_applies_coefficient_once():
    """expected_pre_tax_net = 0.65 * prod(p*SP) - 1 (executable economics)."""
    panel = _synthetic_panel(hit_legs=3)
    selected = np.array([0, 1, 2])
    outcomes = np.array([0, 0, 0])
    rows = _rows_to_frame(panel, [selected], [outcomes], ["TEST"])
    p = panel.control_probability[selected, outcomes]
    sp = panel.predicted_sp[selected, outcomes]
    expected = PAYOUT_COEFFICIENT * float(np.prod(p * sp)) - 1.0
    assert float(rows.iloc[0]["expected_pre_tax_net"]) == pytest.approx(
        expected, abs=1e-9
    )
    # The superseded omission value (prod(p*SP)-1 without 0.65) must NOT match.
    assert float(rows.iloc[0]["expected_pre_tax_net"]) != pytest.approx(
        float(np.prod(p * sp)) - 1.0, abs=1e-6
    )


def test_ticket_row_consistency():
    """_ticket_row uses the same corrected formula as _rows_to_frame."""
    panel = _synthetic_panel(hit_legs=3)
    selected = np.array([0, 1, 2])
    outcomes = np.array([0, 0, 0])
    row = _ticket_row(panel, selected, outcomes, "TEST")
    assert row["pre_tax_gross_multiple"] == pytest.approx(
        PAYOUT_COEFFICIENT * 24.0, abs=1e-9
    )
    p = panel.control_probability[selected, outcomes]
    sp = panel.predicted_sp[selected, outcomes]
    assert row["expected_pre_tax_net"] == pytest.approx(
        PAYOUT_COEFFICIENT * float(np.prod(p * sp)) - 1.0, abs=1e-9
    )


def test_settle_tickets_payout_uses_corrected_multiple():
    """Native ¥2 settlement: payout = multiple * ¥2 (coefficient once)."""
    panel = _synthetic_panel(hit_legs=3)
    # Build a selected frame directly (N=3 ticket rows [0,1,2] all '3').
    row = _ticket_row(panel, np.array([0, 1, 2]), np.array([0, 0, 0]), "TEST")
    selected = pd.DataFrame(
        [
            {
                **row,
                "ticket_order": 1,
                "lane": "MARKET_WOR",
                "k": 8,
                "seed": 1,
                "requested_stake_yuan": TICKET_STAKE_YUAN,
            }
        ]
    )
    hit = bool(selected["realized_hit"].iloc[0])
    multiple = float(selected["pre_tax_gross_multiple"].iloc[0])
    assert hit is True
    assert multiple == pytest.approx(PAYOUT_COEFFICIENT * 24.0, abs=1e-9)
    settled = settle_tickets(selected)
    assert float(settled["payout_yuan"].iloc[0]) == pytest.approx(
        multiple * TICKET_STAKE_YUAN, abs=1e-9
    )


# --- production-entry failure modes (PI REQUIRED #3) -------------------------


def _mini_package(tmp_path: Path, panels, upstream_tickets) -> Path:
    """Build a minimal immutable package with ticket_economics + incumbent."""
    econ = pd.DataFrame(
        [
            {
                "split": "CV_2023",
                "issue": "23999",
                "n": 3,
                "k": 8,
                "lane": "MARKET_WOR",
                "seed": 1,
                "ticket_identity": "t-hit",
                "match_indices": "0|1|2",
                "outcomes": "3|3|3",
                "realized_hit": True,
                "pre_tax_gross_multiple": PAYOUT_COEFFICIENT * 24.0,
                "payout_yuan": PAYOUT_COEFFICIENT * 24.0 * 2.0,
            },
            {
                "split": "CV_2023",
                "issue": "23999",
                "n": 3,
                "k": 8,
                "lane": "MARKET_WOR",
                "seed": 1,
                "ticket_identity": "t-miss",
                "match_indices": "0|1|3",
                "outcomes": "3|3|3",
                "realized_hit": False,
                "pre_tax_gross_multiple": 0.0,
                "payout_yuan": 0.0,
            },
        ]
    )
    econ.to_parquet(tmp_path / "ticket_economics.parquet", index=False)
    inc = pd.DataFrame(
        [
            {
                "split": "CV_2023",
                "issue": "23999",
                "year": 2023,
                "pre_issue_bankroll_yuan": 100_000.0,
                "funded_stake_yuan": 16.0,
                "gross_payout_yuan": PAYOUT_COEFFICIENT * 24.0 * 2.0,
                "post_issue_bankroll_yuan": 100_000.0 - 16.0
                + PAYOUT_COEFFICIENT * 24.0 * 2.0,
                "source": "RECONSTRUCTED_CORRECTED_ECONOMICS",
            }
        ]
    )
    inc.to_parquet(tmp_path / "incumbent_paths.parquet", index=False)
    return tmp_path


@pytest.fixture()
def mini_package(tmp_path: Path):
    panels = {("CV_2023", "23999"): _synthetic_panel(hit_legs=3)}
    upstream_tickets = pd.DataFrame(
        [
            {
                "split": "CV_2023",
                "issue": "23999",
                "panel_role": "CONTROLLING",
                "policy": "MARKET_WOR",
                "k": 8,
                "realized_gross": PAYOUT_COEFFICIENT * 24.0,
            },
            {
                "split": "CV_2023",
                "issue": "23999",
                "panel_role": "CONTROLLING",
                "policy": "MARKET_WOR",
                "k": 8,
                "realized_gross": 0.0,
            },
        ]
    )
    package = _mini_package(tmp_path, panels, upstream_tickets)
    return package, panels, upstream_tickets


def test_verify_payout_economics_passes_clean(mini_package):
    package, panels, upstream_tickets = mini_package
    failures = verify_payout_economics(package, panels, upstream_tickets)
    assert failures == []


def test_verify_detects_omission(mini_package):
    """Omission: hit multiple = product(SP) without 0.65 must FAIL."""
    package, panels, upstream_tickets = mini_package
    econ = pd.read_parquet(package / "ticket_economics.parquet")
    econ.loc[0, "pre_tax_gross_multiple"] = 24.0  # omit coefficient
    econ.to_parquet(package / "ticket_economics.parquet", index=False)
    failures = verify_payout_economics(package, panels, upstream_tickets)
    assert any("payout coefficient violation" in f for f in failures)


def test_verify_detects_division_out(mini_package):
    """Division-out: incumbent payout inflated by /0.65 must FAIL."""
    package, panels, upstream_tickets = mini_package
    inc = pd.read_parquet(package / "incumbent_paths.parquet")
    inc.loc[0, "gross_payout_yuan"] = (
        PAYOUT_COEFFICIENT * 24.0 * 2.0 / PAYOUT_COEFFICIENT  # inflate
    )
    inc.loc[0, "post_issue_bankroll_yuan"] = (
        100_000.0 - 16.0 + PAYOUT_COEFFICIENT * 24.0 * 2.0 / PAYOUT_COEFFICIENT
    )
    inc.to_parquet(package / "incumbent_paths.parquet", index=False)
    failures = verify_payout_economics(package, panels, upstream_tickets)
    assert any("division-out" in f for f in failures)


def test_verify_detects_compound_0_65_n(mini_package):
    """0.65^N: hit multiple = 0.65^N * prod(SP) (N=4) must FAIL."""
    package, panels, upstream_tickets = mini_package
    econ = pd.read_parquet(package / "ticket_economics.parquet")
    # 0.65^4 * 24.0 = coefficient^3 * (0.65*24.0)
    econ.loc[0, "pre_tax_gross_multiple"] = (
        PAYOUT_COEFFICIENT**3 * PAYOUT_COEFFICIENT * 24.0
    )
    econ.to_parquet(package / "ticket_economics.parquet", index=False)
    failures = verify_payout_economics(package, panels, upstream_tickets)
    assert any("payout coefficient violation" in f for f in failures)


# --- production tamper functions (REQ-E06 through production entry) ---------


def test_tamper_omit_payout_coefficient_detected(mini_package):
    """tamper_omit_payout_coefficient() mutation must FAIL the verifier."""
    from parlay_policy.verify import tamper_omit_payout_coefficient

    package, panels, upstream_tickets = mini_package
    tamper_omit_payout_coefficient(package / "ticket_economics.parquet")
    failures = verify_payout_economics(package, panels, upstream_tickets)
    assert any("payout coefficient violation" in f for f in failures)


def test_tamper_divide_out_payout_detected(mini_package):
    """tamper_divide_out_payout() inflation must FAIL the verifier."""
    from parlay_policy.verify import tamper_divide_out_payout

    package, panels, upstream_tickets = mini_package
    tamper_divide_out_payout(package / "incumbent_paths.parquet")
    failures = verify_payout_economics(package, panels, upstream_tickets)
    assert any("division-out" in f for f in failures)


def test_tamper_compound_coefficient_detected(mini_package):
    """tamper_compound_coefficient() 0.65^N mutation must FAIL."""
    from parlay_policy.verify import tamper_compound_coefficient

    package, panels, upstream_tickets = mini_package
    tamper_compound_coefficient(package / "ticket_economics.parquet", n=4)
    failures = verify_payout_economics(package, panels, upstream_tickets)
    assert any("payout coefficient violation" in f for f in failures)


# --- incumbent reconstruction under corrected formula ------------------------


def test_incumbent_reconstruction_corrected_economics():
    """REWORK v3: incumbent payout = sum(realized_gross) * ¥2, never /0.65."""
    upstream_tickets = pd.DataFrame(
        [
            {
                "split": "CV_2023",
                "issue": "23999",
                "year": 2023,
                "panel_role": "CONTROLLING",
                "policy": "MARKET_WOR",
                "k": 8,
                "realized_gross": PAYOUT_COEFFICIENT * 24.0,
            },
            {
                "split": "CV_2023",
                "issue": "23999",
                "year": 2023,
                "panel_role": "CONTROLLING",
                "policy": "MARKET_WOR",
                "k": 8,
                "realized_gross": 0.0,
            },
        ]
    )
    upstream_ledger = pd.DataFrame()
    paths = build_incumbent_paths(upstream_ledger, upstream_tickets)
    assert len(paths) == 1
    row = paths.iloc[0]
    assert row["gross_payout_yuan"] == pytest.approx(
        PAYOUT_COEFFICIENT * 24.0 * 2.0, abs=1e-9
    )
    # The superseded division-out value (24.0*2.0) must NOT match.
    assert row["gross_payout_yuan"] != pytest.approx(24.0 * 2.0, abs=1e-6)
    assert row["source"] == "RECONSTRUCTED_CORRECTED_ECONOMICS"
