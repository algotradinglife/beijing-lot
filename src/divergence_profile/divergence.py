"""Divergence feature construction — per outcome cell.

Rework (2026-08-15, class-2 sweep): the audited build computed divergence as
a whole-vector total-variation distance and copied the same scalar to all
three outcome rows; ``leg_q_times_sp_pre`` used ``max(Q_BJ)`` instead of the
current cell's own Q.  Independent re-computation showed 17,291/50,904
signed-difference rows, 18,855/50,904 CLR rows, 12,570/50,904 direction rows
and 15,682/23,520 leg rows disagreed.

This implementation computes **per outcome cell** (the cell's own 3/1/0
component):

- ``divergence_eu_minus_qbj[o] = Q_EU_BJLINE[o] - Q_BJ[o]``
- ``divergence_power_minus_qbj[o] = P_POWER_BJLINE[o] - Q_BJ[o]``
- ``divergence_eu_logratio[o]`` — centered log-ratio of the ratio vector
  ``log(Q_EU[o]/Q_BJ[o]) - mean_j(log(Q_EU[j]/Q_BJ[j]))`` (per-component CLR
  difference; the audited "log(max)-log(max)" scalar is gone)
- ``divergence_eu_logodds[o]`` — logit difference
  ``logit(Q_EU[o]) - logit(Q_BJ[o])`` (added; log-odds form required by the
  contract's "centered log-ratio/log-odds differences")
- ``divergence_eu_direction[o] = sign(Q_EU_BJLINE[o] - Q_BJ[o])`` per cell
- ``divergence_magnitude[o] = |Q_EU_BJLINE[o] - Q_BJ[o]|`` per cell
- ``divergence_eu_power_agreement[o]`` — same-direction / conflict per cell
- ``leg_q_times_sp_pre[o] = Q_BJ[o] * SP_PRE`` (per cell, not max)
- ``leg_logq_plus_logsp[o] = log(Q_BJ[o]) + log(SP_PRE)``
- uncertainty-standardized divergence where a source uncertainty exists
  (``divergence_eu_uncertainty_std``, ``divergence_power_uncertainty_std``)

``Q * SP - 1`` is never labelled executable EV; it is only a raw leg
diagnostic column and the report repeats that boundary.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import contract

DIVERGENCE_EU_BJ = "divergence_eu_minus_qbj"
DIVERGENCE_POWER_BJ = "divergence_power_minus_qbj"
DIVERGENCE_EU_LOGRATIO = "divergence_eu_logratio"
DIVERGENCE_POWER_LOGRATIO = "divergence_power_logratio"
DIVERGENCE_EU_LOGOODS = "divergence_eu_logodds"
DIVERGENCE_POWER_LOGOODS = "divergence_power_logodds"
DIVERGENCE_EU_DIRECTION = "divergence_eu_direction"
DIVERGENCE_POWER_DIRECTION = "divergence_power_direction"
DIVERGENCE_MAGNITUDE = "divergence_magnitude"
DIVERGENCE_AGREEMENT = "divergence_eu_power_agreement"
DIVERGENCE_EU_UNCERTAINTY_STD = "divergence_eu_uncertainty_std"
DIVERGENCE_POWER_UNCERTAINTY_STD = "divergence_power_uncertainty_std"
LEG_Q_TIMES_SP_PRE = "leg_q_times_sp_pre"
LEG_LOGQ_PLUS_LOGSP = "leg_logq_plus_logsp"

OUTPUT_COLUMNS = (
    DIVERGENCE_EU_BJ,
    DIVERGENCE_POWER_BJ,
    DIVERGENCE_EU_LOGRATIO,
    DIVERGENCE_POWER_LOGRATIO,
    DIVERGENCE_EU_LOGOODS,
    DIVERGENCE_POWER_LOGOODS,
    DIVERGENCE_EU_DIRECTION,
    DIVERGENCE_POWER_DIRECTION,
    DIVERGENCE_MAGNITUDE,
    DIVERGENCE_AGREEMENT,
    DIVERGENCE_EU_UNCERTAINTY_STD,
    DIVERGENCE_POWER_UNCERTAINTY_STD,
    LEG_Q_TIMES_SP_PRE,
    LEG_LOGQ_PLUS_LOGSP,
)

# Outcome component index of a row given its outcome_code.
def _outcome_index(row: pd.Series) -> int | None:
    code = str(row.get("outcome_code"))
    if code not in contract.OUTCOME_ORDER:
        return None
    return contract.OUTCOME_ORDER[code]


def _vector_value(row: pd.Series, column: str) -> np.ndarray | None:
    # No raw-presence fallback: every consumer must see the published causal
    # mask.  Missing masks are unavailable and are rejected by the handoff
    # validator as a schema defect.
    if not bool(row.get(contract.available_col(column), False)):
        return None
    raw = row.get(column)
    if raw is None:
        return None
    if isinstance(raw, np.ndarray):
        array = raw
    elif isinstance(raw, (list, tuple)):
        array = np.asarray(raw, dtype=np.float64)
    else:
        return None
    if array.shape != (3,) or not np.all(np.isfinite(array)):
        return None
    return array


def _clipped_log(value: float) -> float | None:
    """log(value) or None when value <= LOG_EPSILON (epsilon policy)."""
    if not math.isfinite(value) or value <= contract.LOG_EPSILON:
        return None
    return math.log(value)


def _logit(value: float) -> float | None:
    if not math.isfinite(value) or value <= 0.0 or value >= 1.0:
        return None
    return math.log(value / (1.0 - value))


def _clr_difference(source: np.ndarray, anchor: np.ndarray, outcome_index: int) -> float | None:
    """Centered log-ratio difference for the row's own outcome component.

    clr(p)_i = log(p_i) - mean_j(log(p_j)).  The divergence is
    clr(source)[o] - clr(anchor)[o] for the cell's own component o, which is
    exactly ``log(s_o/a_o) - mean_j(log(s_j/a_j))`` — the centered log-ratio
    of the ratio vector, per component.  Degenerate components below the
    epsilon floor make the cell unavailable (never clipped).
    """
    logs = []
    for value in source:
        lv = _clipped_log(float(value))
        if lv is None:
            return None
        logs.append(lv)
    anchor_logs = []
    for value in anchor:
        lv = _clipped_log(float(value))
        if lv is None:
            return None
        anchor_logs.append(lv)
    diff = np.asarray(logs) - np.asarray(anchor_logs)
    return float(diff[outcome_index] - diff.mean())


def build_divergence_features(
    frame: pd.DataFrame,
    *,
    anchor: str = contract.DIVERGENCE_ANCHOR,
    sp_pre_column: str = "predicted_final_sp_input",
    uncertainty_column: str = "market_uncertainty",
) -> pd.DataFrame:
    """Compute per-cell divergence + leg-diagnostic columns onto ``frame``.

    The anchor (``Q_BJ_CALIBRATED`` by default) must be a list/ndarray column
    of three-outcome vectors.  EU/POWER columns may be partially missing;
    every missing input yields NaN (never a fabricated value).  EU/POWER
    comparisons are skipped when the source identity records a same-source
    alias (SAME_SOURCE_NON_INDEPENDENT) — the comparison is explicitly
    unavailable, never silently presented as independent.
    """
    out = frame.copy()
    columns = {
        DIVERGENCE_EU_BJ: np.nan,
        DIVERGENCE_POWER_BJ: np.nan,
        DIVERGENCE_EU_LOGRATIO: np.nan,
        DIVERGENCE_POWER_LOGRATIO: np.nan,
        DIVERGENCE_EU_LOGOODS: np.nan,
        DIVERGENCE_POWER_LOGOODS: np.nan,
        DIVERGENCE_EU_DIRECTION: np.nan,
        DIVERGENCE_POWER_DIRECTION: np.nan,
        DIVERGENCE_MAGNITUDE: np.nan,
        DIVERGENCE_AGREEMENT: np.nan,
        DIVERGENCE_EU_UNCERTAINTY_STD: np.nan,
        DIVERGENCE_POWER_UNCERTAINTY_STD: np.nan,
        LEG_Q_TIMES_SP_PRE: np.nan,
        LEG_LOGQ_PLUS_LOGSP: np.nan,
    }
    for name, default in columns.items():
        out[name] = default
    out[DIVERGENCE_AGREEMENT] = out[DIVERGENCE_AGREEMENT].astype(object)

    eu_raw = out.get(contract.Q_EU_BJLINE)
    power_raw = out.get(contract.P_POWER_BJLINE)
    sp_pre_raw = out.get(sp_pre_column)
    uncertainty_raw = out.get(uncertainty_column)
    qbj_source = out.get(contract.SOURCE_IDENTITY_Q_BJ)
    eu_source = out.get(contract.SOURCE_IDENTITY_EU)

    anchor_vectors = [None] * len(out)
    eu_vectors = [None] * len(out)
    power_vectors = [None] * len(out)

    for position, (_, row) in enumerate(out.iterrows()):
        anchor_vectors[position] = _vector_value(row, anchor)
        if eu_raw is not None:
            eu_vectors[position] = _vector_value(row, contract.Q_EU_BJLINE)
        if power_raw is not None:
            power_vectors[position] = _vector_value(row, contract.P_POWER_BJLINE)

    for index in range(len(out)):
        a = anchor_vectors[index]
        if a is None:
            continue
        row = out.iloc[index]
        oidx = _outcome_index(row)
        if oidx is None:
            continue
        eu = eu_vectors[index]
        power = power_vectors[index]

        # Same-source anti-alias: on #204 avg-EU cells Q_EU and Q_BJ are the
        # same market_probability value; the comparison is not independent.
        eu_independent = True
        if (
            qbj_source is not None
            and eu_source is not None
            and row.get(contract.SOURCE_IDENTITY_Q_BJ)
            == contract.SRC_BJ204_AVG_EU
            and row.get(contract.SOURCE_IDENTITY_EU)
            == contract.SRC_BJ204_AVG_EU
        ):
            eu_independent = False

        if eu is not None and eu_independent:
            diff = eu - a
            own_diff = float(diff[oidx])
            out.at[index, DIVERGENCE_EU_BJ] = own_diff
            out.at[index, DIVERGENCE_MAGNITUDE] = abs(own_diff)
            out.at[index, DIVERGENCE_EU_DIRECTION] = (
                1 if own_diff > 0 else (-1 if own_diff < 0 else 0)
            )
            clr = _clr_difference(eu, a, oidx)
            if clr is not None:
                out.at[index, DIVERGENCE_EU_LOGRATIO] = clr
            lo = _logit(float(eu[oidx]))
            la = _logit(float(a[oidx]))
            if lo is not None and la is not None:
                out.at[index, DIVERGENCE_EU_LOGOODS] = lo - la
            # uncertainty-standardized divergence (per-cell Q vs anchor)
            if uncertainty_raw is not None and bool(
                row.get(contract.available_col(uncertainty_column), False)
            ):
                unc = row.get(uncertainty_column)
                if unc is not None and np.isfinite(unc) and float(unc) > 0:
                    out.at[index, DIVERGENCE_EU_UNCERTAINTY_STD] = (
                        own_diff / float(unc)
                    )
        elif eu is not None and not eu_independent:
            # same-source alias: comparison explicitly unavailable
            out.at[index, DIVERGENCE_EU_BJ] = np.nan
            out.at[index, DIVERGENCE_EU_LOGRATIO] = np.nan
            out.at[index, DIVERGENCE_EU_LOGOODS] = np.nan
            out.at[index, DIVERGENCE_EU_DIRECTION] = np.nan
            out.at[index, DIVERGENCE_EU_UNCERTAINTY_STD] = np.nan

        if power is not None:
            diff = power - a
            own_diff = float(diff[oidx])
            out.at[index, DIVERGENCE_POWER_BJ] = own_diff
            out.at[index, DIVERGENCE_POWER_DIRECTION] = (
                1 if own_diff > 0 else (-1 if own_diff < 0 else 0)
            )
            clr = _clr_difference(power, a, oidx)
            if clr is not None:
                out.at[index, DIVERGENCE_POWER_LOGRATIO] = clr
            lp = _logit(float(power[oidx]))
            la = _logit(float(a[oidx]))
            if lp is not None and la is not None:
                out.at[index, DIVERGENCE_POWER_LOGOODS] = lp - la
            if uncertainty_raw is not None and bool(
                row.get(contract.available_col(uncertainty_column), False)
            ):
                unc = row.get(uncertainty_column)
                if unc is not None and np.isfinite(unc) and float(unc) > 0:
                    out.at[index, DIVERGENCE_POWER_UNCERTAINTY_STD] = (
                        own_diff / float(unc)
                    )

        if eu is not None and power is not None:
            eu_dir = out.at[index, DIVERGENCE_EU_DIRECTION]
            power_dir = out.at[index, DIVERGENCE_POWER_DIRECTION]
            if (
                isinstance(eu_dir, (int, float))
                and not (isinstance(eu_dir, float) and math.isnan(eu_dir))
                and isinstance(power_dir, (int, float))
                and not (isinstance(power_dir, float) and math.isnan(power_dir))
            ):
                out.at[index, DIVERGENCE_AGREEMENT] = (
                    "AGREE" if eu_dir == power_dir else "CONFLICT"
                )

        # Leg diagnostics use the calibrated anchor's OWN cell component as Q
        # and SP_PRE as SP (per outcome cell).
        sp_pre = None
        if sp_pre_raw is not None:
            sp_pre = sp_pre_raw.iloc[index]
        if (
            bool(row.get(contract.available_col(sp_pre_column), False))
            and sp_pre is not None
            and np.isfinite(sp_pre)
            and sp_pre > 1
        ):
            q_own = float(a[oidx])
            if q_own > 0:
                out.at[index, LEG_Q_TIMES_SP_PRE] = q_own * float(sp_pre)
                log_q = _clipped_log(q_own)
                log_sp = _clipped_log(float(sp_pre))
                if log_q is not None and log_sp is not None:
                    out.at[index, LEG_LOGQ_PLUS_LOGSP] = log_q + log_sp
    return out


def coverage_strata(frame: pd.DataFrame) -> pd.DataFrame:
    """Build the source-coverage stratum table: availability per source."""
    rows = []
    representations = contract.PROBABILITY_REPRESENTATIONS
    total = len(frame)
    for representation in representations:
        raw = frame.get(representation)
        raw_present = 0
        if raw is not None:
            raw_present = int(
                raw.apply(
                    lambda value: (
                        value is not None
                        and isinstance(value, (list, tuple, np.ndarray))
                        and len(value) == 3
                    )
                ).sum()
            )
        available_name = contract.available_col(representation)
        causally_available = int(
            frame.get(available_name, pd.Series(False, index=frame.index))
            .fillna(False)
            .astype(bool)
            .sum()
        )
        rows.append(
            {
                "representation": representation,
                "raw_present_cells": raw_present,
                "causally_available_cells": causally_available,
                "total_cells": total,
                "causal_coverage_fraction": causally_available / total if total else 0.0,
            }
        )
    return pd.DataFrame(rows)
