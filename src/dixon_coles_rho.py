"""Cutoff-driven selection of the Dixon-Coles low-score dependence parameter.

Why this is a historical-learning client rather than a constant: `rho` decides
how much draw mass the score grid carries, so choosing it from the data that
will later be scored would leak the answer into the question. It is therefore
selected on a prior window only, frozen, and reported with a machine-readable
receipt. Target issues never contribute to the selection.

The whole chronology apparatus (cutoff, availability, partitions, effective
sample size, weighting, receipt) comes from ``src.temporal_learning``; this
module supplies only the domain fit/tune/calibration callbacks.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from src.temporal_learning import (
    AvailabilityFilter,
    AvailabilityPolicy,
    Cutoff,
    PartitionPolicy,
    TemporalContractError,
    WeightingPolicy,
    prepare_learning_context,
    temporal_client,
)

# Accepted Dixon-Coles range. Values outside it are not a valid probability
# model once the tau multipliers are applied, so the grid is defined only here.
RHO_GRID: tuple[float, ...] = (
    -0.20, -0.18, -0.16, -0.14, -0.12, -0.10, -0.08, -0.06, -0.04, -0.02, 0.0,
)


class DixonColesError(ValueError):
    """Raised when the dependence parameter cannot be selected honestly."""


@dataclass(frozen=True)
class RhoSelection:
    selection: float
    receipt: dict[str, Any]
    fit_rows: int
    tune_rows: int
    calibration_rows: int
    tune_scores: tuple[tuple[float, float], ...]
    calibration_score: float


def _independent_draw_probability(lambda_home: np.ndarray, lambda_away: np.ndarray,
                                  max_goals: int) -> np.ndarray:
    """P(net == 0) under the independent product, vectorized over fixtures."""
    goals = np.arange(max_goals + 1)
    # (n, K) per-side masses
    from math import lgamma
    log_fact = np.array([lgamma(k + 1) for k in goals], dtype=np.float64)
    home = np.exp(-lambda_home[:, None] + goals[None, :] * np.log(lambda_home)[:, None]
                  - log_fact[None, :])
    away = np.exp(-lambda_away[:, None] + goals[None, :] * np.log(lambda_away)[:, None]
                  - log_fact[None, :])
    # Exact P(net == 0) = sum_k home[k] * away[k]
    return np.sum(home * away, axis=1)


def _draw_probability(lambda_home: np.ndarray, lambda_away: np.ndarray,
                      rho: float, max_goals: int) -> np.ndarray:
    """P(net == 0) at handicap 0 under the Dixon-Coles model.

    Only the four corrected cells change the diagonal sum, so the draw mass is
    the independent diagonal plus the four tau corrections. Normalizing by the
    total mass matters because tau does not preserve it.
    """
    from math import lgamma
    goals = np.arange(max_goals + 1)
    log_fact = np.array([lgamma(k + 1) for k in goals], dtype=np.float64)
    home = np.exp(-lambda_home[:, None] + goals[None, :] * np.log(lambda_home)[:, None]
                  - log_fact[None, :])
    away = np.exp(-lambda_away[:, None] + goals[None, :] * np.log(lambda_away)[:, None]
                  - log_fact[None, :])
    grid = home[:, :, None] * away[:, None, :]
    total = np.sum(grid, axis=(1, 2))
    diagonal = np.sum(home * away, axis=1)
    # tau corrections on (0,0), (0,1), (1,0), (1,1); only (0,0) and (1,1) are draws
    tau_00 = 1.0 - lambda_home * lambda_away * rho
    tau_11 = 1.0 - rho
    cell_00 = home[:, 0] * away[:, 0]
    cell_11 = home[:, 1] * away[:, 1]
    corrected_diagonal = (diagonal - cell_00 - cell_11
                          + cell_00 * tau_00 + cell_11 * tau_11)
    corrected_total = (
        total
        - cell_00 - home[:, 0] * away[:, 1] - home[:, 1] * away[:, 0] - cell_11
        + cell_00 * tau_00
        + home[:, 0] * away[:, 1] * (1.0 + lambda_home * rho)
        + home[:, 1] * away[:, 0] * (1.0 + lambda_away * rho)
        + cell_11 * tau_11
    )
    return corrected_diagonal / corrected_total


def dixon_coles_history(
    fixtures: pd.DataFrame,
    *,
    issue_column: str = "issue",
    lambda_home_column: str = "lambda_home",
    lambda_away_column: str = "lambda_away",
    is_draw_column: str = "is_draw",
) -> pd.DataFrame:
    """Build the cutoff-keyed history the selector partitions.

    Each row is one prior fixture carrying the fitted rates and whether the
    match actually finished level. Availability is the next midnight after the
    fixture's decision instant, so a target issue can never admit its own
    result.
    """
    need = {issue_column, lambda_home_column, lambda_away_column, is_draw_column,
            "decision_ts"}
    if not need.issubset(fixtures.columns):
        raise DixonColesError(
            "dixon_coles_history requires " + ", ".join(sorted(need))
        )
    frame = fixtures.loc[:, list(need)].copy()
    if frame.empty:
        raise DixonColesError("dixon_coles_history received no fixtures")
    if frame[issue_column].isna().any():
        raise DixonColesError("dixon_coles_history requires a non-null issue")
    codes = frame[issue_column].astype(str)
    if not codes.str.fullmatch(r"\d{6}").all():
        raise DixonColesError("dixon_coles_history requires six-digit issue codes")
    for column in (lambda_home_column, lambda_away_column):
        values = pd.to_numeric(frame[column], errors="coerce")
        if values.isna().any() or not np.isfinite(values.to_numpy(float)).all() \
                or (values <= 0).any():
            raise DixonColesError(f"{column} must be finite and strictly positive")
    decision = pd.to_datetime(frame["decision_ts"], errors="coerce", utc=True)
    if decision.isna().any():
        raise DixonColesError("dixon_coles_history requires parseable decision_ts")
    label_available = decision + pd.Timedelta(days=1)
    out = pd.DataFrame({
        "issue_code": codes,
        "issue_year": codes.str[:2].astype(int) + 2000,
        "decision_ts": decision,
        "data_available_ts": decision,
        "label_available_ts": label_available,
        "lambda_home": pd.to_numeric(frame[lambda_home_column]),
        "lambda_away": pd.to_numeric(frame[lambda_away_column]),
        "is_draw": frame[is_draw_column].astype(int),
    })
    return out.sort_values(["decision_ts", "issue_code"], kind="stable").reset_index(drop=True)


@temporal_client
def select_dixon_coles_rho(
    history: pd.DataFrame,
    *,
    cutoff: Cutoff,
    repository_root: Path,
    source_hashes: Mapping[str, str],
    availability_policy: AvailabilityPolicy,
    intended_use: str,
    rho_grid: Sequence[float] = RHO_GRID,
    max_goals: int = 15,
) -> RhoSelection:
    """Select rho on the tune partition and score it on calibration."""

    if intended_use != "HISTORICAL_DIAGNOSTIC":
        raise DixonColesError(
            "select_dixon_coles_rho is diagnostic only; prospective selection "
            "requires observed availability evidence"
        )
    grid = tuple(float(value) for value in rho_grid)
    if not grid:
        raise DixonColesError("rho_grid must not be empty")
    if any(not np.isfinite(value) or value < -0.5 or value > 0.5 for value in grid):
        raise DixonColesError("rho_grid contains an unsupported value")
    if max_goals < 2:
        raise DixonColesError("max_goals must be at least 2")

    context = prepare_learning_context(
        history,
        cutoff,
        source_hashes=source_hashes,
        repository_root=repository_root,
        implementation_modules=(
            "src.temporal_learning",
            "src.dixon_coles_rho",
        ),
        implementation_distributions=("numpy", "pandas"),
        availability=AvailabilityFilter(policy=availability_policy),
        intended_use=intended_use,
        partition_policy=PartitionPolicy(),
        weighting_policy=WeightingPolicy.expanding_equal(),
    )
    fit = context.partitions["fit"]
    tune = context.partitions["tune"]
    calibration = context.partitions["calibration"]
    if fit.empty:
        raise TemporalContractError("dixon-coles selection has an empty fit partition")
    if tune.empty:
        raise TemporalContractError("dixon-coles selection has an empty tune partition")

    def mean_draw_bias(frame: pd.DataFrame, rho: float) -> float:
        """Mean (predicted - actual) draw probability; zero is unbiased."""
        if frame.empty:
            return float("nan")
        predicted = _draw_probability(
            frame["lambda_home"].to_numpy(float),
            frame["lambda_away"].to_numpy(float),
            rho,
            max_goals,
        )
        actual = frame["is_draw"].to_numpy(float)
        return float(np.mean(predicted - actual))

    tune_scores = tuple((value, mean_draw_bias(tune, value)) for value in grid)

    def severity(score: float) -> float:
        return abs(score) if np.isfinite(score) else float("inf")

    selection, tune_score = min(tune_scores, key=lambda item: (severity(item[1]), item[0]))
    if not np.isfinite(tune_score):
        raise DixonColesError("dixon-coles selection produced no finite tune score")
    calibration_score = mean_draw_bias(calibration, selection)

    receipt = dict(context.receipt.payload)
    receipt.update({
        "model": "DIXON_COLES_LOW_SCORE_DEPENDENCE",
        "rho_candidates": list(grid),
        "rho_selected": selection,
        "tune_rows": int(len(tune)),
        "calibration_rows": int(len(calibration)),
        "tune_mean_draw_bias": tune_score,
        "calibration_mean_draw_bias": (
            None if not np.isfinite(calibration_score) else calibration_score
        ),
        "selection_rule": "MINIMUM_ABSOLUTE_TUNE_DRAW_BIAS",
        "target_issue_excluded_by": ["timestamp", "issue_identity"],
    })
    return RhoSelection(
        selection=selection,
        receipt=receipt,
        fit_rows=int(len(fit)),
        tune_rows=int(len(tune)),
        calibration_rows=int(len(calibration)),
        tune_scores=tune_scores,
        calibration_score=calibration_score,
    )


def freeze_rho_by_band(
    history: pd.DataFrame,
    *,
    cutoffs: Mapping[str, Cutoff],
    repository_root: Path,
    source_hashes: Mapping[str, str],
    availability_policy: AvailabilityPolicy,
    band_column: str | None = None,
    intended_use: str = "HISTORICAL_DIAGNOSTIC",
    rho_grid: Sequence[float] = RHO_GRID,
    max_goals: int = 15,
) -> pd.DataFrame:
    """Select rho once per cutoff (optionally once per band within it).

    Returns one row per (issue_code, band) carrying the frozen rho, so a caller
    can join the value onto target fixtures without ever re-fitting on them.
    """
    if band_column is not None and band_column not in history.columns:
        raise DixonColesError(f"band_column {band_column!r} is not in the history")
    if not cutoffs:
        raise DixonColesError("freeze_rho_by_band requires at least one cutoff")
    rows: list[dict[str, Any]] = []
    for issue_code, cutoff in cutoffs.items():
        subset = history if band_column is None else history
        bands = [None] if band_column is None else sorted(
            history[band_column].dropna().unique()
        )
        for band in bands:
            frame = subset if band is None else subset[subset[band_column] == band]
            if frame.empty:
                continue
            try:
                chosen = select_dixon_coles_rho(
                    frame,
                    cutoff=cutoff,
                    repository_root=repository_root,
                    source_hashes=source_hashes,
                    availability_policy=availability_policy,
                    intended_use=intended_use,
                    rho_grid=rho_grid,
                    max_goals=max_goals,
                )
            except (TemporalContractError, DixonColesError):
                # An issue whose prior window cannot support a selection is
                # reported as inadmissible rather than silently given rho=0.
                rows.append({
                    "issue_code": str(issue_code),
                    "band": band,
                    "rho": None,
                    "admissible": False,
                    "tune_rows": 0,
                    "calibration_rows": 0,
                    "tune_mean_draw_bias": None,
                    "calibration_mean_draw_bias": None,
                })
                continue
            rows.append({
                "issue_code": str(issue_code),
                "band": band,
                "rho": chosen.selection,
                "admissible": True,
                "tune_rows": chosen.tune_rows,
                "calibration_rows": chosen.calibration_rows,
                "tune_mean_draw_bias": dict(chosen.tune_scores)[chosen.selection],
                "calibration_mean_draw_bias": (
                    None if not np.isfinite(chosen.calibration_score)
                    else chosen.calibration_score
                ),
            })
    return pd.DataFrame(rows)


def backfill_inadmissible_rho(
    frozen: pd.DataFrame,
    *,
    provenance: str,
) -> pd.DataFrame:
    """Fill issues whose prior window was too short from a later frozen value.

    Why this exists and why it is a separate step: the complete-prior-years
    partition needs three whole prior years, so the earliest issues cannot
    support a selection at all. Leaving them on an independent grid re-imposes
    the draw compression this work removes, and `rho` is a single stable
    dependence constant (its selected values move by at most a few hundredths),
    so carrying the realized value backwards is a materially smaller error than
    dropping the correction on those issues.

    The caller must state `provenance` — an explicit availability-evidence
    declaration — because a backfilled value is chosen from data that postdates
    its target issue. Rows filled here are marked so a receipt can never
    present them as if they had been selected in-window.
    """
    if not provenance or not isinstance(provenance, str):
        raise DixonColesError(
            "backfill_inadmissible_rho requires a provenance declaration"
        )
    required = {"issue_code", "rho", "admissible"}
    if not required.issubset(frozen.columns):
        raise DixonColesError(
            "backfill_inadmissible_rho requires " + ", ".join(sorted(required))
        )
    if frozen.empty:
        raise DixonColesError("backfill_inadmissible_rho received no rows")
    selected = frozen.loc[frozen["admissible"], "rho"].dropna()
    if selected.empty:
        raise DixonColesError(
            "backfill_inadmissible_rho has no in-window selection to carry backwards"
        )
    # One stable constant, taken from the EARLIEST in-window selection. Using
    # the latest value instead would reach furthest forward in time, which is
    # the opposite of what a backfill should minimize; the earliest realized
    # estimate is the closest defensible stand-in for the parameter.
    carried = float(selected.iloc[0])
    out = frozen.copy()
    out["rho_selected_in_window"] = out["rho"].where(out["admissible"])
    out["rho_backfilled"] = False
    pending = ~out["admissible"]
    out.loc[pending, "rho"] = carried
    out.loc[pending, "rho_backfilled"] = True
    out["backfill_provenance"] = None
    out.loc[pending, "backfill_provenance"] = provenance
    return out
