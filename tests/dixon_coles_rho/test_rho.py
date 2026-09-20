"""Contract tests for cutoff-driven Dixon-Coles dependence selection."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.dixon_coles_rho import (
    RHO_GRID,
    DixonColesError,
    backfill_inadmissible_rho,
    _draw_probability,
    _independent_draw_probability,
    dixon_coles_history,
    freeze_rho_by_band,
    select_dixon_coles_rho,
)
from src.temporal_learning.core import (
    AvailabilityPolicy,
    Cutoff,
    TemporalContractError,
)


def _policy() -> AvailabilityPolicy:
    return AvailabilityPolicy.historical_proxy("unit-test proxy availability")


def _hashes() -> dict[str, str]:
    return {"tests/dixon_coles": "0" * 64}


def _fixtures(issues: int, *, seed: int = 3, draw_rate: float = 0.27) -> pd.DataFrame:
    """One row per fixture with fitted rates and a draw label.

    The complete-prior-years partition policy needs whole calendar years for
    fit, tune and calibration, so fixtures are spaced ~4.5 days apart starting
    in 2010: 80 issues already cross into 2011, and 200 cross into 2012.
    """
    rng = np.random.default_rng(seed)
    rows = []
    start = pd.Timestamp("2010-01-01", tz="UTC")
    for index in range(issues):
        stamp = start + pd.Timedelta(days=6 * index)
        for _ in range(3):
            lam_home = float(rng.uniform(0.7, 2.2))
            lam_away = float(rng.uniform(0.7, 2.2))
            rows.append({
                "issue": f"{stamp:%y%m%d}",
                "decision_ts": stamp,
                "lambda_home": lam_home,
                "lambda_away": lam_away,
                "is_draw": int(rng.random() < draw_rate),
            })
    return pd.DataFrame(rows)


def _cutoff_for(frame: pd.DataFrame, *, after: int, issue: str = "999999") -> Cutoff:
    """A cutoff strictly after `after` issues of history have completed.

    The target issue identity is supplied explicitly: a decision-epoch cutoff
    must name the issue it is deciding, so the contract cannot be satisfied by
    a bare timestamp.
    """
    stamps = sorted(pd.to_datetime(frame["decision_ts"], utc=True).unique())
    moment = pd.Timestamp(stamps[after - 1]) + pd.Timedelta(hours=12)
    return Cutoff.decision_epoch(issue, moment)


# --- closed form -----------------------------------------------------------

def test_independent_form_matches_poisson_product():
    lam_home = np.array([1.4])
    lam_away = np.array([1.1])
    # P(net == 0) = sum_k Pois(k; lh) * Pois(k; la)
    expected = sum(
        math.exp(-1.4) * 1.4 ** k / math.factorial(k)
        * math.exp(-1.1) * 1.1 ** k / math.factorial(k)
        for k in range(40)
    )
    assert _independent_draw_probability(lam_home, lam_away, 30)[0] == pytest.approx(
        expected, abs=1e-12
    )


def test_rho_zero_reproduces_the_independent_draw_mass():
    lam_home = np.array([1.4, 0.9, 2.3])
    lam_away = np.array([1.1, 1.6, 0.8])
    independent = _independent_draw_probability(lam_home, lam_away, 30)
    corrected = _draw_probability(lam_home, lam_away, 0.0, 30)
    assert np.allclose(independent, corrected, atol=1e-12)


def test_more_negative_rho_raises_the_draw_mass_monotonically():
    lam_home = np.array([1.4])
    lam_away = np.array([1.1])
    # RHO_GRID ascends from -0.20 to 0.0, so the draw mass must fall as rho
    # climbs towards independence.
    masses = [_draw_probability(lam_home, lam_away, rho, 30)[0] for rho in RHO_GRID]
    assert masses == sorted(masses, reverse=True)
    assert masses[0] > masses[-1]


def test_draw_mass_stays_a_probability():
    rng = np.random.default_rng(11)
    lam_home = rng.uniform(0.5, 2.5, 200)
    lam_away = rng.uniform(0.5, 2.5, 200)
    for rho in (-0.20, -0.10, 0.0):
        masses = _draw_probability(lam_home, lam_away, rho, 30)
        assert np.all(np.isfinite(masses))
        assert np.all(masses > 0)
        assert np.all(masses < 1)


# --- history contract ------------------------------------------------------

def test_history_carries_label_availability_one_day_later():
    frame = _fixtures(5)
    history = dixon_coles_history(frame)
    assert list(history.columns) == [
        "issue_code", "issue_year", "decision_ts", "data_available_ts",
        "label_available_ts", "lambda_home", "lambda_away", "is_draw",
    ]
    assert (history["label_available_ts"] - history["decision_ts"]
            == pd.Timedelta(days=1)).all()
    assert (history["data_available_ts"] == history["decision_ts"]).all()
    # Rows are ordered so a walk-forward caller cannot silently reorder them.
    assert history["decision_ts"].is_monotonic_increasing


def test_history_preserves_leading_zero_issue_codes():
    frame = pd.DataFrame({
        "issue": ["010708"],
        "decision_ts": [pd.Timestamp("2010-07-08", tz="UTC")],
        "lambda_home": [1.2],
        "lambda_away": [1.0],
        "is_draw": [1],
    })
    history = dixon_coles_history(frame)
    assert history["issue_code"].tolist() == ["010708"]


@pytest.mark.parametrize("bad_issue", ["10708", "20100708", "abcdef", ""])
def test_history_rejects_malformed_issue_codes(bad_issue):
    frame = _fixtures(3)
    frame.loc[0, "issue"] = bad_issue
    with pytest.raises(DixonColesError, match="six-digit"):
        dixon_coles_history(frame)


@pytest.mark.parametrize("bad_rate", [0.0, -1.0, np.nan, np.inf])
def test_history_rejects_unusable_rates(bad_rate):
    frame = _fixtures(3)
    frame.loc[0, "lambda_home"] = bad_rate
    with pytest.raises(DixonColesError, match="lambda_home"):
        dixon_coles_history(frame)


def test_history_rejects_unparseable_decision_time():
    frame = _fixtures(3).astype({"decision_ts": object})
    frame.loc[0, "decision_ts"] = "not-a-time"
    with pytest.raises(DixonColesError, match="decision_ts"):
        dixon_coles_history(frame)


def test_history_rejects_missing_columns():
    frame = _fixtures(3).drop(columns=["lambda_away"])
    with pytest.raises(DixonColesError, match="requires"):
        dixon_coles_history(frame)


def test_history_rejects_empty_input():
    with pytest.raises(DixonColesError, match="no fixtures"):
        dixon_coles_history(_fixtures(3).iloc[0:0])


# --- selection -------------------------------------------------------------

def test_selection_refuses_a_prospective_intended_use():
    frame = _fixtures(200)
    history = dixon_coles_history(frame)
    with pytest.raises(DixonColesError, match="diagnostic only"):
        select_dixon_coles_rho(
            history,
            cutoff=_cutoff_for(frame, after=190),
            repository_root=Path.cwd(),
            source_hashes=_hashes(),
            availability_policy=_policy(),
            intended_use="PROSPECTIVE",
        )


def test_selection_prefers_the_rho_that_removes_draw_bias():
    # Construct a world whose draws come from a known negative rho: labels are
    # drawn with the rho = -0.16 draw mass. The selector must not pick 0.
    rng = np.random.default_rng(29)
    rows = []
    start = pd.Timestamp("2010-01-01", tz="UTC")
    for index in range(200):
        stamp = start + pd.Timedelta(days=6 * index)
        for _ in range(4):
            lam_home = float(rng.uniform(0.8, 2.0))
            lam_away = float(rng.uniform(0.8, 2.0))
            p_draw = _draw_probability(
                np.array([lam_home]), np.array([lam_away]), -0.16, 30
            )[0]
            rows.append({
                "issue": f"{stamp:%y%m%d}",
                "decision_ts": stamp,
                "lambda_home": lam_home,
                "lambda_away": lam_away,
                "is_draw": int(rng.random() < p_draw),
            })
    frame = pd.DataFrame(rows)
    chosen = select_dixon_coles_rho(
        dixon_coles_history(frame),
        cutoff=_cutoff_for(frame, after=190),
        repository_root=Path.cwd(),
        source_hashes=_hashes(),
        availability_policy=_policy(),
        intended_use="HISTORICAL_DIAGNOSTIC",
    )
    assert chosen.selection < -0.02
    assert abs(chosen.calibration_score) < 0.05


def test_selection_receipt_binds_cutoff_and_policy():
    frame = _fixtures(200)
    chosen = select_dixon_coles_rho(
        dixon_coles_history(frame),
        cutoff=_cutoff_for(frame, after=190),
        repository_root=Path.cwd(),
        source_hashes=_hashes(),
        availability_policy=_policy(),
        intended_use="HISTORICAL_DIAGNOSTIC",
    )
    receipt = chosen.receipt
    assert receipt["rho_selected"] == chosen.selection
    assert receipt["model"] == "DIXON_COLES_LOW_SCORE_DEPENDENCE"
    assert receipt["selection_rule"] == "MINIMUM_ABSOLUTE_TUNE_DRAW_BIAS"
    assert receipt["target_issue_excluded_by"] == ["timestamp", "issue_identity"]
    assert receipt["rho_candidates"] == list(RHO_GRID)


def test_selection_is_causal_in_the_target_issue():
    # Flipping the labels of the newest issues must not move their own rho.
    frame = _fixtures(200)
    history = dixon_coles_history(frame)
    stamped = history.copy()
    stamped["decision_ts"] = pd.to_datetime(stamped["decision_ts"], utc=True)
    latest = stamped["issue_code"].iloc[-1]
    cutoff = Cutoff.decision_epoch(
        latest,
        stamped.loc[stamped["issue_code"] == latest, "decision_ts"].max()
        + pd.Timedelta(days=1),
    )
    first = select_dixon_coles_rho(
        history, cutoff=cutoff, repository_root=Path.cwd(),
        source_hashes=_hashes(), availability_policy=_policy(),
        intended_use="HISTORICAL_DIAGNOSTIC",
    )
    flipped = history.copy()
    mask = flipped["issue_code"] == latest
    flipped.loc[mask, "is_draw"] = 1 - flipped.loc[mask, "is_draw"]
    second = select_dixon_coles_rho(
        flipped, cutoff=cutoff, repository_root=Path.cwd(),
        source_hashes=_hashes(), availability_policy=_policy(),
        intended_use="HISTORICAL_DIAGNOSTIC",
    )
    assert first.selection == second.selection


def test_selection_fails_closed_without_a_prior_window():
    frame = _fixtures(200)
    history = dixon_coles_history(frame)
    earliest = pd.to_datetime(history["decision_ts"], utc=True).min()
    with pytest.raises((TemporalContractError, DixonColesError)):
        select_dixon_coles_rho(
            history,
            cutoff=Cutoff.decision_epoch("999999", earliest),
            repository_root=Path.cwd(),
            source_hashes=_hashes(),
            availability_policy=_policy(),
            intended_use="HISTORICAL_DIAGNOSTIC",
        )


def test_selection_rejects_unsupported_candidates():
    frame = _fixtures(200)
    history = dixon_coles_history(frame)
    with pytest.raises(DixonColesError, match="unsupported"):
        select_dixon_coles_rho(
            history,
            cutoff=_cutoff_for(frame, after=190),
            repository_root=Path.cwd(),
            source_hashes=_hashes(),
            availability_policy=_policy(),
            intended_use="HISTORICAL_DIAGNOSTIC",
            rho_grid=(-0.9,),
        )


def test_selection_rejects_an_empty_candidate_grid():
    frame = _fixtures(200)
    history = dixon_coles_history(frame)
    with pytest.raises(DixonColesError, match="must not be empty"):
        select_dixon_coles_rho(
            history,
            cutoff=_cutoff_for(frame, after=190),
            repository_root=Path.cwd(),
            source_hashes=_hashes(),
            availability_policy=_policy(),
            intended_use="HISTORICAL_DIAGNOSTIC",
            rho_grid=(),
        )


# --- banded freeze ---------------------------------------------------------

def test_freeze_marks_issues_without_history_inadmissible():
    frame = _fixtures(200)
    history = dixon_coles_history(frame)
    stamps = sorted(pd.to_datetime(history["decision_ts"], utc=True).unique())
    cutoffs = {
        "early": Cutoff.decision_epoch("early", pd.Timestamp(stamps[0])),
        "late": _cutoff_for(frame, after=190),
    }
    frozen = freeze_rho_by_band(
        history,
        cutoffs=cutoffs,
        repository_root=Path.cwd(),
        source_hashes=_hashes(),
        availability_policy=_policy(),
    )
    assert set(frozen.columns) == {
        "issue_code", "band", "rho", "admissible", "tune_rows",
        "calibration_rows", "tune_mean_draw_bias", "calibration_mean_draw_bias",
    }
    early = frozen[frozen["issue_code"] == "early"].iloc[0]
    late = frozen[frozen["issue_code"] == "late"].iloc[0]
    assert bool(early["admissible"]) is False
    assert pd.isna(early["rho"])
    assert bool(late["admissible"]) is True
    assert late["rho"] == pytest.approx(-0.16, abs=0.06)


def test_freeze_splits_by_band_when_asked():
    frame = _fixtures(200)
    frame["band"] = np.where(frame["lambda_home"] > 1.45, "high", "low")
    history = dixon_coles_history(frame)
    history["band"] = frame["band"].to_numpy()
    frozen = freeze_rho_by_band(
        history,
        cutoffs={"t": _cutoff_for(frame, after=190)},
        repository_root=Path.cwd(),
        source_hashes=_hashes(),
        availability_policy=_policy(),
        band_column="band",
    )
    assert sorted(frozen["band"].dropna().unique()) == ["high", "low"]


def test_freeze_rejects_an_unknown_band_column():
    frame = _fixtures(200)
    with pytest.raises(DixonColesError, match="band_column"):
        freeze_rho_by_band(
            dixon_coles_history(frame),
            cutoffs={"t": _cutoff_for(frame, after=190)},
            repository_root=Path.cwd(),
            source_hashes=_hashes(),
            availability_policy=_policy(),
            band_column="league",
        )


def test_freeze_requires_a_cutoff():
    frame = _fixtures(200)
    with pytest.raises(DixonColesError, match="at least one cutoff"):
        freeze_rho_by_band(
            dixon_coles_history(frame),
            cutoffs={},
            repository_root=Path.cwd(),
            source_hashes=_hashes(),
            availability_policy=_policy(),
        )


# --- backfill of inadmissible issues ---------------------------------------

def test_backfill_carries_a_later_selection_backwards_and_marks_it():
    frozen = pd.DataFrame({
        "issue_code": ["a", "b", "c", "d"],
        "band": [None] * 4,
        "rho": [None, None, -0.14, -0.12],
        "admissible": [False, False, True, True],
        "tune_rows": [0, 0, 30, 40],
        "calibration_rows": [0, 0, 20, 30],
        "tune_mean_draw_bias": [None, None, 0.01, 0.02],
        "calibration_mean_draw_bias": [None, None, 0.0, 0.01],
    })
    out = backfill_inadmissible_rho(frozen, provenance="carry-back: rho is a stable constant")
    # Every issue now carries a usable rho.
    assert out["rho"].notna().all()
    # The carried value is the EARLIEST in-window selection: reaching for the
    # latest would look furthest forward in time, the opposite of the intent.
    assert out.loc[out["issue_code"].isin(["a", "b"]), "rho"].tolist() == [-0.14, -0.14]
    # In-window selections are preserved untouched and distinguishable.
    assert out.loc[out["issue_code"] == "c", "rho_selected_in_window"].iloc[0] == -0.14
    assert out.loc[out["issue_code"] == "a", "rho_selected_in_window"].isna().all()
    assert out["rho_backfilled"].tolist() == [True, True, False, False]
    assert out.loc[out["issue_code"] == "a", "backfill_provenance"].iloc[0] is not None
    assert out.loc[out["issue_code"] == "c", "backfill_provenance"].iloc[0] is None


def test_backfill_requires_an_explicit_provenance_declaration():
    frozen = pd.DataFrame({
        "issue_code": ["a"], "rho": [None], "admissible": [False],
    })
    for bad in ("", None, 0):
        with pytest.raises(DixonColesError, match="provenance"):
            backfill_inadmissible_rho(frozen, provenance=bad)


def test_backfill_refuses_when_nothing_was_selected_in_window():
    frozen = pd.DataFrame({
        "issue_code": ["a", "b"], "rho": [None, None], "admissible": [False, False],
    })
    with pytest.raises(DixonColesError, match="no in-window selection"):
        backfill_inadmissible_rho(frozen, provenance="x")


def test_backfill_rejects_a_malformed_frame():
    with pytest.raises(DixonColesError, match="requires"):
        backfill_inadmissible_rho(
            pd.DataFrame({"issue_code": ["a"]}), provenance="x"
        )
    with pytest.raises(DixonColesError, match="no rows"):
        backfill_inadmissible_rho(
            pd.DataFrame({"issue_code": [], "rho": [], "admissible": []}),
            provenance="x",
        )


def test_backfilled_rho_is_always_a_selectable_candidate():
    frozen = pd.DataFrame({
        "issue_code": ["a", "b"], "rho": [None, -0.12], "admissible": [False, True],
    })
    out = backfill_inadmissible_rho(frozen, provenance="x")
    assert all(value in RHO_GRID for value in out["rho"])


def test_selection_is_invariant_to_all_labels_at_or_after_the_cutoff_issue():
    # Stronger than flipping one issue: mutating EVERY label from the cutoff
    # issue onward must leave the selection untouched, because none of those
    # rows may enter any partition. Flipping the whole history would legitimately
    # change it, so that case is asserted to differ.
    # 420 six-day-spaced issues span 2010-01 to ~2016-11, so the midpoint still
    # has the three complete prior years COMPLETE_PRIOR_YEARS requires; a short
    # fixture set would fail closed instead of testing invariance.
    frame = _fixtures(420)
    history = dixon_coles_history(frame)
    stamped = history.copy()
    stamped["decision_ts"] = pd.to_datetime(stamped["decision_ts"], utc=True)
    middle = stamped["issue_code"].iloc[len(stamped) // 2]
    cutoff = Cutoff.decision_epoch(
        middle,
        stamped.loc[stamped["issue_code"] == middle, "decision_ts"].max()
        + pd.Timedelta(days=1),
    )
    baseline = select_dixon_coles_rho(
        history, cutoff=cutoff, repository_root=Path.cwd(),
        source_hashes=_hashes(), availability_policy=_policy(),
        intended_use="HISTORICAL_DIAGNOSTIC",
    ).selection
    future = history.copy()
    mask = future["issue_code"] >= middle
    assert mask.any()
    future.loc[mask, "is_draw"] = 1 - future.loc[mask, "is_draw"]
    assert select_dixon_coles_rho(
        future, cutoff=cutoff, repository_root=Path.cwd(),
        source_hashes=_hashes(), availability_policy=_policy(),
        intended_use="HISTORICAL_DIAGNOSTIC",
    ).selection == baseline
    # The invariance above must come from exclusion, not inertness: mutating the
    # prior window has to change the *fit*, even when the selected grid point
    # happens to stay the same because rho is pinned at a grid edge.
    everywhere = history.assign(is_draw=1 - history["is_draw"])
    mutated = select_dixon_coles_rho(
        everywhere, cutoff=cutoff, repository_root=Path.cwd(),
        source_hashes=_hashes(), availability_policy=_policy(),
        intended_use="HISTORICAL_DIAGNOSTIC",
    )
    untouched = select_dixon_coles_rho(
        history, cutoff=cutoff, repository_root=Path.cwd(),
        source_hashes=_hashes(), availability_policy=_policy(),
        intended_use="HISTORICAL_DIAGNOSTIC",
    )
    assert mutated.calibration_score != untouched.calibration_score
    # The excluded rows contribute to neither partition of either run.
    assert mutated.fit_rows == untouched.fit_rows
    assert mutated.tune_rows == untouched.tune_rows
    assert mutated.calibration_rows == untouched.calibration_rows
