"""Probability-representation materialization and validation.

Implements the six accepted representations from the #229 contract:

- ``Q_BJ_SP_DEVIG``     normalized inverse decision-epoch Beijing 3/1/0 SP
- ``Q_BJ_CALIBRATED``   accepted causal market-anchor probability (#204)
- ``BJ_LINE_BOUNDARY``  native handicap line as a pricing boundary
- ``Q_EU_RAW_1X2``      de-vigged average European straight-result probability
- ``Q_EU_BJLINE``       EU probability translated to native BJ space through an
                        explicit score/goal-difference distribution
- ``P_POWER_BJLINE``    power/team model probability in native BJ space

Every valid three-outcome vector is finite, bounded in [0,1] and sums to one
within the frozen tolerance.  Raw and calibrated variants stay separate.

Rework changes (2026-08-15, class-2 sweep):
- **Float handicap**: ``translate_eu_to_bjline`` and the Poisson projection
  accept *half-goal* native lines (0, ±0.5, ±1, ±1.5, ...) without rounding.
  The audited ``int(round(native_line))`` silently turned ±0.5 into 0 and
  ±1.5 into ±2 (REQ-D04).  The projection margin arithmetic already handles
  float lines; the round is removed everywhere.
- **Per-feature observed-at / availability masks**: every representation is
  materialized together with its own ``observed_at_utc`` and availability
  reason so REQ-D01 can be audited per feature, not just per issue.
- **Source identity**: each representation records which upstream value
  produced it (anti-alias registry, class-3 sweep).  On #204 avg-EU cells the
  same ``market_probability`` value would feed both Q_BJ and Q_EU; that
  same-source alias is recorded so divergence builders can refuse it.
"""

from __future__ import annotations

import functools
import math

import numpy as np
import pandas as pd
from scipy.optimize import least_squares

from . import contract
from .sources import UpstreamBindingError

# Independent-Poisson score grid bound (matches research/handicap_draw_projection).
_MAX_GOALS = 30
# Factorial table reused by the vectorized Poisson mass computation.
_FACTORIALS = np.array(
    [math.factorial(k) for k in range(_MAX_GOALS + 1)], dtype=np.float64
)


def _poisson_mass(lam: np.ndarray) -> np.ndarray:
    """Vectorized Poisson PMF rows ``P(K=k)`` for each rate in ``lam``.

    Returns shape ``(len(lam), _MAX_GOALS + 1)``.
    """
    lam = np.atleast_1d(np.asarray(lam, dtype=np.float64))
    k = np.arange(_MAX_GOALS + 1)
    return np.exp(-lam)[:, None] * lam[:, None] ** k[None, :] / _FACTORIALS[None, :]


def independent_poisson_handicap_probabilities(
    lambda_home: float, lambda_away: float, handicap: float
) -> tuple[float, float, float]:
    """Project 3/1/0 from an independent-Poisson score distribution.

    ``handicap`` is a float native Beijing line (integer or half-goal).
    For a half-goal line the draw mass is exactly zero by construction
    (margin never equals zero), which is the correct Beijing semantics.
    Mirrors the accepted projection in
    ``research/handicap_draw_projection.loop.independent_poisson_handicap_probabilities``.
    """
    if lambda_home <= 0 or lambda_away <= 0:
        raise ValueError("Poisson rates must be positive")
    home_mass = _poisson_mass(np.array([lambda_home]))[0]
    away_mass = _poisson_mass(np.array([lambda_away]))[0]
    mass = home_mass[:, None] * away_mass[None, :]  # (31, 31)
    goals = np.arange(_MAX_GOALS + 1)
    margin = goals[:, None] - goals[None, :] + float(handicap)
    sign = np.where(margin > 0, 0, np.where(margin == 0, 1, 2))
    probabilities = np.zeros(3)
    for outcome in range(3):
        probabilities[outcome] = mass[sign == outcome].sum()
    total = probabilities.sum()
    if 1.0 - total > 1e-10:
        raise ValueError("independent-Poisson grid has material omitted tail mass")
    return (float(probabilities[0] / total),
            float(probabilities[1] / total),
            float(probabilities[2] / total))


def is_legal_handicap(line: float) -> bool:
    """A legal Beijing native line is an integer or half-goal value."""
    return bool(np.isfinite(line)) and bool(
        np.isclose(line * 2.0, round(line * 2.0), atol=1e-6)
    )


def _fit_poisson_rates(target: np.ndarray) -> tuple[float, float] | None:
    """Fit (lambda_home, lambda_away) reproducing the straight 1X2 ``target``.

    Uses a deterministic coarse warm start followed by a bounded
    least-squares refinement.  Returns ``None`` when no rate pair within the
    frozen tolerance (1e-4 max-abs) is found.
    """
    target = np.asarray(target, dtype=np.float64)
    if target.shape != (3,) or not np.all(np.isfinite(target)) or target.min() <= 0:
        return None
    if abs(float(target.sum()) - 1.0) > contract.PROBABILITY_SUM_TOLERANCE:
        return None

    def residual(x: np.ndarray) -> np.ndarray:
        p = independent_poisson_handicap_probabilities(x[0], x[1], 0.0)
        return np.asarray(p, dtype=np.float64) - target

    best: tuple[float, float] | None = None
    best_error = np.inf
    for lh0 in (0.4, 0.8, 1.4, 2.0, 3.0):
        for la0 in (0.4, 0.8, 1.4, 2.0, 3.0):
            try:
                result = least_squares(
                    residual,
                    [lh0, la0],
                    bounds=([0.01, 0.01], [8.0, 8.0]),
                    xtol=1e-12,
                    ftol=1e-12,
                    gtol=1e-12,
                    max_nfev=150,
                )
                error = float(np.max(np.abs(result.fun)))
                if error < best_error:
                    best_error = error
                    best = (float(result.x[0]), float(result.x[1]))
            except (ValueError, TypeError, RuntimeError):
                continue
    if best is None or best_error > 1e-4:
        return None
    return best


@functools.lru_cache(maxsize=1 << 16)
def _translated_bjline_cached(
    p3: float, p1: float, p0: float, handicap: float
) -> tuple[tuple[float, float, float] | None, str | None]:
    """Cached translation for one exact (vector, line) pair (deterministic)."""
    eu = (p3, p1, p0)
    if handicap == 0.0:
        return eu, None
    if not is_legal_handicap(handicap):
        return None, contract.REASON_INVALID_LINE
    rates = _fit_poisson_rates(np.asarray(eu, dtype=np.float64))
    if rates is None:
        return None, contract.REASON_TRANSLATION_NOT_IDENTIFIABLE
    try:
        translated = independent_poisson_handicap_probabilities(
            rates[0], rates[1], float(handicap)
        )
    except ValueError:
        return None, contract.REASON_TRANSLATION_NOT_IDENTIFIABLE
    ok, reason = validate_probability_vector(np.asarray(translated))
    if not ok:
        return None, reason
    return translated, None


def translate_eu_to_bjline(
    eu_probability: tuple[float, float, float], handicap: float
) -> tuple[tuple[float, float, float] | None, str | None]:
    """Translate a de-vigged EU 1X2 vector to native BJ handicap space.

    For zero handicap the straight 1X2 space coincides with the native
    handicap-result space (margin > 0 / == 0 / < 0), so the translation is the
    identity.  For non-zero handicap an explicit score distribution is needed:
    we fit independent Poisson rates that reproduce the straight 1X2
    probabilities, then project through the line.  Half-goal lines are passed
    through unchanged (no rounding).  When the fit is not identifiable within
    the frozen tolerance, the result is
    ``(None, REASON_TRANSLATION_NOT_IDENTIFIABLE)``.
    """
    if handicap == 0.0:
        return eu_probability, None
    return _translated_bjline_cached(
        float(eu_probability[0]),
        float(eu_probability[1]),
        float(eu_probability[2]),
        float(handicap),
    )


def devig_normalize(triplet: np.ndarray) -> np.ndarray:
    """Normalize inverse-odds / inverse-SP triplets to a probability vector."""
    array = np.asarray(triplet, dtype=np.float64)
    if array.shape != (3,):
        raise ValueError("devig input must be a length-3 vector")
    if not np.all(np.isfinite(array)):
        raise ValueError("devig input contains non-finite values")
    if np.any(array <= 0):
        raise ValueError("devig input must be strictly positive")
    inverse = 1.0 / array
    total = inverse.sum()
    if total <= 0:
        raise ValueError("devig input has non-positive inverse sum")
    return inverse / total


def normalize_sp_triplet(sp_3: float, sp_1: float, sp_0: float) -> np.ndarray:
    """Decision-epoch Beijing 3/1/0 SP -> normalized inverse probability."""
    return devig_normalize(np.asarray([sp_3, sp_1, sp_0], dtype=np.float64))


def validate_probability_vector(
    vector: np.ndarray, tolerance: float = contract.PROBABILITY_SUM_TOLERANCE
) -> tuple[bool, str | None]:
    """Return (ok, reason).  ``None`` reason means valid."""
    array = np.asarray(vector, dtype=np.float64)
    if array.shape != (3,):
        return False, "NOT_LENGTH_3"
    if not np.all(np.isfinite(array)):
        return False, "NON_FINITE"
    if np.any(array < 0.0) or np.any(array > 1.0):
        return False, "OUT_OF_BOUNDS"
    if abs(float(array.sum()) - 1.0) > tolerance:
        return False, "SUM_DEVIATION"
    return True, None


def validate_sp(sp: float) -> tuple[bool, str | None]:
    """Impossible-SP check: finite and > 1 for decimal Beijing SP."""
    if not np.isfinite(sp):
        return False, "NON_FINITE"
    if sp <= 1.0:
        return False, "SP_NOT_GT_1"
    return True, None


# ---------------------------------------------------------------------------
# Vector helpers shared by the materializers
# ---------------------------------------------------------------------------
def _per_match_vector(
    cells: pd.DataFrame, scalar_column: str
) -> pd.DataFrame:
    """Rebuild per-match 3/1/0 vectors from a long-format scalar column.

    Returns a DataFrame with one row per (issue, match_idx) and the three
    vector columns ``_v3/_v1/_v0``.  Matches missing any outcome scalar are
    omitted (their representation stays NaN).
    """
    vector_rows = []
    for (issue, match_idx), group in cells.groupby(["issue", "match_idx"]):
        triplet: dict[str, float] = {}
        for _, row in group.iterrows():
            code = str(row["outcome_code"])
            if code in contract.OUTCOME_CODES and pd.notna(row.get(scalar_column)):
                triplet[code] = float(row[scalar_column])
        if len(triplet) == 3:
            vector_rows.append(
                {
                    "issue": issue,
                    "match_idx": match_idx,
                    "_v3": triplet["3"],
                    "_v1": triplet["1"],
                    "_v0": triplet["0"],
                }
            )
    if not vector_rows:
        return pd.DataFrame(columns=["issue", "match_idx", "_v3", "_v1", "_v0"])
    return pd.DataFrame(vector_rows)


def _broadcast_vector(
    cells: pd.DataFrame, vector_frame: pd.DataFrame, representation: str
) -> pd.DataFrame:
    """Merge per-match vector columns and pack them into one list column.

    Matches absent from ``vector_frame`` (or with a partially missing
    triplet) keep ``NaN`` — never a ``[nan, nan, nan]`` vector.
    """
    out = cells.copy()
    out[representation] = np.nan
    if vector_frame is None or vector_frame.empty:
        return out
    vector_frame = vector_frame.copy()
    vector_frame["_ok"] = (
        vector_frame[["_v3", "_v1", "_v0"]].notna().all(axis=1)
    )
    vector_frame.loc[~vector_frame["_ok"], ["_v3", "_v1", "_v0"]] = np.nan
    out = out.merge(vector_frame, on=["issue", "match_idx"], how="left")
    out[representation] = out.apply(
        lambda row: (
            [row["_v3"], row["_v1"], row["_v0"]]
            if row["_ok"] is True
            else np.nan
        ),
        axis=1,
    )
    out = out.drop(columns=["_v3", "_v1", "_v0", "_ok"], errors="ignore")
    return out


def _is_list_vector(value: object) -> bool:
    return isinstance(value, (list, tuple, np.ndarray)) and len(value) == 3


def _parse_observation_keys(observations: pd.DataFrame) -> pd.DataFrame:
    """Parse ``issue_match`` identity or raise an explicit source error."""
    if "match_id" not in observations.columns:
        raise UpstreamBindingError("#214 observation missing match_id")
    out = observations.copy()
    parts = out["match_id"].astype(str).str.extract(
        r"^(?P<_issue>[^_]+)_(?P<_match_idx>\d+)$"
    )
    if parts.isna().any().any():
        raise UpstreamBindingError("#214 unidentifiable match_id source row")
    out["_issue"] = parts["_issue"].astype(str)
    out["_match_idx"] = parts["_match_idx"].astype(int)
    return out


def _latest_causal_observations(
    cells: pd.DataFrame, observations: pd.DataFrame
) -> pd.DataFrame:
    """Select the latest #214 snapshot at/before each exact decision epoch."""
    obs = _parse_observation_keys(observations)
    obs["_observed"] = pd.to_datetime(
        obs["snapshot_ts_utc"], errors="raise", utc=True
    )
    identity = ["_issue", "_match_idx", "_observed"]
    if obs.duplicated(identity, keep=False).any():
        raise UpstreamBindingError("#214 duplicate source row at one snapshot")
    epoch_col = contract.DECISION_EPOCH_COLUMN
    epochs = cells[["issue", "match_idx", epoch_col]].copy()
    epochs["issue"] = epochs["issue"].astype(str)
    epochs["match_idx"] = epochs["match_idx"].astype(int)
    epochs[epoch_col] = pd.to_datetime(epochs[epoch_col], errors="coerce", utc=True)
    consistency = epochs.groupby(["issue", "match_idx"])[epoch_col].nunique(dropna=False)
    if (consistency > 1).any():
        raise UpstreamBindingError("cell axis has multiple decision epochs for one match")
    epochs = epochs.drop_duplicates(["issue", "match_idx"])
    selected = obs.merge(
        epochs,
        left_on=["_issue", "_match_idx"],
        right_on=["issue", "match_idx"],
        how="inner",
        validate="many_to_one",
    )
    selected = selected[
        selected["_observed"].notna()
        & selected[epoch_col].notna()
        & selected["_observed"].le(selected[epoch_col])
    ]
    if selected.empty:
        return selected
    return (
        selected.sort_values("_observed", kind="stable")
        .groupby(["_issue", "_match_idx"], as_index=False, sort=False)
        .tail(1)
        .reset_index(drop=True)
    )


# ---------------------------------------------------------------------------
# Representation materialization on the cell frame
# ---------------------------------------------------------------------------
REPRESENTATION_COLUMNS = [
    contract.Q_BJ_SP_DEVIG,
    contract.Q_BJ_CALIBRATED,
    contract.BJ_LINE_BOUNDARY,
    contract.Q_EU_RAW_1X2,
    contract.Q_EU_BJLINE,
    contract.P_POWER_BJLINE,
]


def materialize_calibrated_and_line(
    cells: pd.DataFrame,
) -> pd.DataFrame:
    """Rebuild Q_BJ_CALIBRATED as a per-match vector from #204 scalars.

    The #204 common-cell axis is long format: ``market_probability`` is the
    scalar probability of that cell's own outcome.  This materializer rebuilds
    the full 3/1/0 vector per match and broadcasts it to the match's three
    outcome rows; ``BJ_LINE_BOUNDARY`` is the per-match scalar line.

    Source identity: pclose cells -> ``bj204_retrospective_proxy_pclose``;
    avg-EU cells -> ``bj204_retrospective_proxy_avg_eu``.  On avg-EU cells the
    same market_probability value is what would feed Q_EU_RAW_1X2, so the
    anti-alias registry must treat EU-vs-BJ on those cells as
    SAME_SOURCE_NON_INDEPENDENT.
    """
    out = cells.copy()
    vector_frame = _per_match_vector(out, "market_probability")
    out = _broadcast_vector(out, vector_frame, contract.Q_BJ_CALIBRATED)
    out[contract.BJ_LINE_BOUNDARY] = pd.to_numeric(
        out.get("native_handicap_line"), errors="coerce"
    )
    out[contract.SOURCE_IDENTITY_Q_BJ] = np.where(
        out.get("source_is_average_eu", 0).fillna(0).astype(float) == 1.0,
        contract.SRC_BJ204_AVG_EU,
        np.where(
            out.get("source_is_pclose", 0).fillna(0).astype(float) == 1.0,
            contract.SRC_BJ204_PCLOSE,
            contract.SRC_NONE,
        ),
    )
    out[contract.SOURCE_IDENTITY_LINE] = out[contract.SOURCE_IDENTITY_Q_BJ]

    # #204 pclose is explicitly graded RETROSPECTIVE_PROXY and its freeze card
    # says no source timestamp proves a live pre-event capture.  Never invent
    # one from the decision epoch.  The avg-EU branch does have #203's
    # euro_1h observed-at and may therefore become causally available.
    avg_eu = out.get("source_is_average_eu", pd.Series(0, index=out.index)).fillna(0).astype(float).eq(1.0)
    euro_observed = pd.to_datetime(
        out.get("euro_1h_available_ts_utc", pd.Series(pd.NaT, index=out.index)),
        errors="coerce",
        utc=True,
    )
    qbj_observed = pd.Series(pd.NaT, index=out.index, dtype="datetime64[ns, UTC]")
    qbj_observed.loc[avg_eu] = euro_observed.loc[avg_eu]
    out[contract.observed_at_col(contract.Q_BJ_CALIBRATED)] = qbj_observed
    out[contract.observed_at_col(contract.BJ_LINE_BOUNDARY)] = qbj_observed

    grouped_present = out.groupby(["issue", "match_idx"])["market_probability"].transform("count")
    qbj_present = out[contract.Q_BJ_CALIBRATED].apply(
        lambda value: isinstance(value, (list, tuple, np.ndarray)) and len(value) == 3
    )
    out[contract.producer_reason_col(contract.Q_BJ_CALIBRATED)] = np.where(
        qbj_present,
        None,
        np.where(grouped_present.between(1, 2), contract.REASON_PARTIAL_SOURCE_TRIPLET, contract.REASON_MISSING_CALIBRATED_Q),
    )
    line = pd.to_numeric(out[contract.BJ_LINE_BOUNDARY], errors="coerce")
    out[contract.producer_reason_col(contract.BJ_LINE_BOUNDARY)] = np.where(
        line.isna(),
        contract.REASON_MISSING_NATIVE_LINE,
        np.where(line.map(is_legal_handicap), None, contract.REASON_INVALID_LINE),
    )
    return out


def materialize_sp_devig(
    cells: pd.DataFrame,
    observations: pd.DataFrame,
) -> pd.DataFrame:
    """Bind decision-epoch SP with source trace and explicit partial receipts."""
    out = cells.copy()
    representation = contract.Q_BJ_SP_DEVIG
    observed_name = contract.observed_at_col(representation)
    producer_reason = contract.producer_reason_col(representation)
    out[representation] = pd.Series([np.nan] * len(out), dtype=object)
    out[observed_name] = pd.Series(pd.NaT, index=out.index, dtype="datetime64[ns, UTC]")
    out[contract.SOURCE_IDENTITY_SP] = contract.SRC_NONE
    out[producer_reason] = "NO_SP_SOURCE"
    if observations is None or observations.empty:
        return out

    obs = _latest_causal_observations(out, observations)
    complete = obs[["sp_3", "sp_1", "sp_0"]].notna().all(axis=1)
    partial_keys = set(
        zip(obs.loc[~complete, "_issue"].astype(str), obs.loc[~complete, "_match_idx"].astype(int))
    )
    valid: list[dict[str, object]] = []
    for _, row in obs.loc[complete].iterrows():
        try:
            vector = normalize_sp_triplet(
                float(row["sp_3"]), float(row["sp_1"]), float(row["sp_0"])
            )
            ok, _ = validate_probability_vector(vector)
            timestamp = row["_observed"]
        except (ValueError, TypeError):
            continue
        if ok:
            valid.append(
                {
                    "issue": str(row["_issue"]),
                    "match_idx": int(row["_match_idx"]),
                    "_vector": vector.tolist(),
                    "_observed": timestamp,
                }
            )
    if valid:
        bound = pd.DataFrame(valid)
        out = out.merge(
            bound, on=["issue", "match_idx"], how="left", validate="many_to_one"
        )
        out[representation] = pd.Series(
            [value if _is_list_vector(value) else np.nan for value in out["_vector"]],
            index=out.index,
            dtype=object,
        )
        out[observed_name] = pd.to_datetime(out["_observed"], errors="coerce", utc=True)
        out = out.drop(columns=["_vector", "_observed"])
    present = out[representation].apply(_is_list_vector)
    out.loc[present, contract.SOURCE_IDENTITY_SP] = contract.SRC_BJ214_OBSERVATION
    out.loc[present, producer_reason] = None
    keys = list(zip(out["issue"].astype(str), out["match_idx"].astype(int)))
    out.loc[
        ~present & pd.Series([key in partial_keys for key in keys], index=out.index),
        producer_reason,
    ] = contract.REASON_PARTIAL_SOURCE_TRIPLET
    return out


def materialize_eu_raw(
    cells: pd.DataFrame,
    feature_values: pd.DataFrame | None = None,
    observations: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Compute Q_EU_RAW_1X2 from committed accepted sources.

    Rework (class-3 sweep): the independent EU source is **#203
    ``devig_euro_probability``** (accepted causal per-cell de-vigged average
    European straight-result probability, with per-feature observed-at
    ``euro_1h_available_ts_utc`` carried by #203 identity).  The #204 avg-EU
    ``market_probability`` cells are NOT used as an EU source: on those cells
    the same value feeds Q_BJ_CALIBRATED, so an EU-vs-BJ comparison there is
    SAME_SOURCE_NON_INDEPENDENT.  #214 observations (decision-epoch EU odds)
    are used only where neither #203 nor the alias rule applies.
    """
    out = cells.copy()
    representation = contract.Q_EU_RAW_1X2
    observed_name = contract.observed_at_col(representation)
    producer_reason = contract.producer_reason_col(representation)
    out[representation] = pd.Series([np.nan] * len(out), dtype=object)
    out[observed_name] = pd.Series(pd.NaT, index=out.index, dtype="datetime64[ns, UTC]")
    out[contract.SOURCE_IDENTITY_EU] = contract.SRC_NONE
    out[producer_reason] = contract.REASON_NO_EU_SOURCE

    # Source 1: #203 devig scalar triplets.  Partial triplets remain three
    # identity rows with an explicit receipt; nothing is silently dropped.
    if "devig_euro_probability" in out.columns:
        counts = out.groupby(["issue", "match_idx"])["devig_euro_probability"].transform("count")
        out.loc[counts.between(1, 2), producer_reason] = contract.REASON_PARTIAL_SOURCE_TRIPLET
        vectors = _per_match_vector(out, "devig_euro_probability")
        if not vectors.empty:
            vector_map = {
                (str(row["issue"]), int(row["match_idx"])): [
                    float(row["_v3"]), float(row["_v1"]), float(row["_v0"])
                ]
                for _, row in vectors.iterrows()
            }
            keys = list(zip(out["issue"].astype(str), out["match_idx"].astype(int)))
            out[representation] = pd.Series([vector_map.get(key, np.nan) for key in keys], index=out.index, dtype=object)
            has_203 = out[representation].apply(_is_list_vector)
            out.loc[has_203, contract.SOURCE_IDENTITY_EU] = contract.SRC_BJ203_DEVIG_EURO
            out.loc[has_203, producer_reason] = None
            if "euro_1h_available_ts_utc" in out.columns:
                observed = pd.to_datetime(out["euro_1h_available_ts_utc"], errors="coerce", utc=True)
                out.loc[has_203, observed_name] = observed.loc[has_203]

    # Source 2: latest causal #214 snapshot per match.
    if observations is not None and not observations.empty:
        obs = _latest_causal_observations(out, observations)
        complete = obs[["eu_h", "eu_d", "eu_a"]].notna().all(axis=1)
        obs_vectors: dict[tuple[str, int], tuple[list[float], pd.Timestamp]] = {}
        for _, row in obs.loc[complete].iterrows():
            try:
                vector = devig_normalize(
                    np.asarray([row["eu_h"], row["eu_d"], row["eu_a"]], dtype=np.float64)
                )
                ok, _ = validate_probability_vector(vector)
                timestamp = row["_observed"]
            except (ValueError, TypeError):
                continue
            if ok:
                obs_vectors[(str(row["_issue"]), int(row["_match_idx"]))] = (
                    vector.tolist(), timestamp
                )

        keys = list(zip(out["issue"].astype(str), out["match_idx"].astype(int)))
        current = out[representation].tolist()
        for position, key in enumerate(keys):
            if _is_list_vector(current[position]):
                continue
            if key in obs_vectors:
                vector, timestamp = obs_vectors[key]
                current[position] = vector
                out.iat[position, out.columns.get_loc(observed_name)] = timestamp
                out.iat[position, out.columns.get_loc(contract.SOURCE_IDENTITY_EU)] = contract.SRC_BJ214_OBSERVATION
                out.iat[position, out.columns.get_loc(producer_reason)] = None
        out[representation] = pd.Series(current, index=out.index, dtype=object)

        partial_keys = set(
            zip(obs.loc[~complete, "_issue"].astype(str), obs.loc[~complete, "_match_idx"].astype(int))
        )
        no_vector = ~out[representation].apply(_is_list_vector)
        out.loc[
            no_vector & pd.Series([key in partial_keys for key in keys], index=out.index),
            producer_reason,
        ] = contract.REASON_PARTIAL_SOURCE_TRIPLET
    return out


def _rebuild_vector_from_scalar(
    frame: pd.DataFrame, scalar_column: str
) -> pd.DataFrame:
    """Rebuild a per-match vector from a long-format scalar column.

    After merging #203 devig_euro_probability (a scalar per cell), build the
    per-match 3-vector and broadcast it back; matches missing any outcome keep
    NaN.  This is a small helper distinct from ``_per_match_vector`` because
    the scalar is already a column on the frame.
    """
    out = frame.copy()
    scalar = out.get(scalar_column)
    if scalar is None:
        return out
    vector_frame = _per_match_vector(out, scalar_column)
    if vector_frame is None or vector_frame.empty:
        out[scalar_column] = np.nan
        return out
    out = _broadcast_vector(out, vector_frame, scalar_column)
    return out


def materialize_eu_bjline(cells: pd.DataFrame) -> pd.DataFrame:
    """Translate Q_EU_RAW_1X2 into Q_EU_BJLINE via explicit score distribution.

    Zero-handicap rows use the identity; non-zero rows use the fitted
    independent-Poisson projection with the exact float line (half-goal lines
    included).  Unidentifiable translations are NaN with a stable reason in
    ``eu_bjline_reason``.  The observed-at and source identity of the
    translation are inherited from Q_EU_RAW_1X2.
    """
    out = cells.copy()
    out[contract.Q_EU_BJLINE] = np.nan
    out["eu_bjline_reason"] = None
    out[contract.producer_reason_col(contract.Q_EU_BJLINE)] = contract.REASON_NO_EU_SOURCE
    out[contract.observed_at_col(contract.Q_EU_BJLINE)] = pd.NaT

    raw = out.get(contract.Q_EU_RAW_1X2)
    line = pd.to_numeric(out.get(contract.BJ_LINE_BOUNDARY), errors="coerce")
    if raw is None or line is None:
        return out

    def _translate(row: pd.Series) -> tuple[object, str | None]:
        value = row.get(contract.Q_EU_RAW_1X2)
        native_line = row.get(contract.BJ_LINE_BOUNDARY)
        if value is None or not isinstance(value, (list, tuple, np.ndarray)):
            return np.nan, contract.REASON_NO_EU_SOURCE
        if native_line is None or not np.isfinite(native_line):
            return np.nan, contract.REASON_MISSING_NATIVE_LINE
        if not is_legal_handicap(float(native_line)):
            return np.nan, contract.REASON_INVALID_LINE
        try:
            vector = tuple(float(v) for v in value)
            translated, reason = translate_eu_to_bjline(
                vector, float(native_line)
            )
        except (ValueError, TypeError):
            return np.nan, contract.REASON_TRANSLATION_NOT_IDENTIFIABLE
        if translated is None:
            return np.nan, reason
        ok, reason = validate_probability_vector(np.asarray(translated))
        if not ok:
            return np.nan, reason
        return list(translated), None

    match_frame = (
        out[
            [
                "issue",
                "match_idx",
                contract.Q_EU_RAW_1X2,
                contract.BJ_LINE_BOUNDARY,
                contract.observed_at_col(contract.Q_EU_RAW_1X2),
            ]
        ]
        .groupby(["issue", "match_idx"], sort=False)
        .first()
        .reset_index()
    )
    translated = match_frame.apply(_translate, axis=1, result_type="expand")
    match_frame["_translated"] = translated[0]
    match_frame["_reason"] = translated[1]
    out = out.merge(
        match_frame[
            [
                "issue",
                "match_idx",
                "_translated",
                "_reason",
                contract.observed_at_col(contract.Q_EU_RAW_1X2),
            ]
        ],
        on=["issue", "match_idx"],
        how="left",
        suffixes=("", "_src"),
    )
    out[contract.Q_EU_BJLINE] = out["_translated"]
    out["eu_bjline_reason"] = out["_reason"]
    out[contract.producer_reason_col(contract.Q_EU_BJLINE)] = out["_reason"]
    raw_observed = pd.to_datetime(
        out[contract.observed_at_col(contract.Q_EU_RAW_1X2) + "_src"],
        errors="coerce",
        utc=True,
    )
    line_observed = pd.to_datetime(
        out.get(
            contract.observed_at_col(contract.BJ_LINE_BOUNDARY),
            pd.Series(pd.NaT, index=out.index),
        ),
        errors="coerce",
        utc=True,
    )
    translated_observed = pd.Series(pd.NaT, index=out.index, dtype="datetime64[ns, UTC]")
    both_observed = raw_observed.notna() & line_observed.notna()
    translated_observed.loc[both_observed] = pd.concat(
        [raw_observed.loc[both_observed], line_observed.loc[both_observed]], axis=1
    ).max(axis=1)
    out[contract.observed_at_col(contract.Q_EU_BJLINE)] = translated_observed
    out = out.drop(
        columns=[
            "_translated",
            "_reason",
            contract.observed_at_col(contract.Q_EU_RAW_1X2) + "_src",
        ],
        errors="ignore",
    )
    return out


def materialize_power_bjline(
    cells: pd.DataFrame,
    power_freeze: pd.DataFrame,
) -> pd.DataFrame:
    """Bind P_POWER_BJLINE from the #180 team-model freeze (native space).

    The observed-at of the POWER representation is #180's own
    ``feature_cutoff_ts`` (per-match, = the #180 common issue cutoff, which is
    the first kickoff of the issue — verified 189/189).  The builder compares
    it against the #203 decision epoch for REQ-D01.
    """
    out = cells.copy()
    out[contract.P_POWER_BJLINE] = np.nan
    out[contract.observed_at_col(contract.P_POWER_BJLINE)] = pd.NaT
    out[contract.SOURCE_IDENTITY_POWER] = contract.SRC_NONE
    producer_reason = contract.producer_reason_col(contract.P_POWER_BJLINE)
    out[producer_reason] = "NO_POWER_SOURCE"
    if power_freeze is None or power_freeze.empty:
        return out
    power = power_freeze[
        [
            "issue",
            "match_idx",
            "team_primary_p3",
            "team_primary_p1",
            "team_primary_p0",
            "feature_cutoff_ts",
        ]
    ].copy()
    power["issue"] = power["issue"].astype(str)
    power["match_idx"] = power["match_idx"].astype(int)
    if power.duplicated(["issue", "match_idx"], keep=False).any():
        raise UpstreamBindingError("#180 duplicate source row for POWER")
    complete = power[
        ["team_primary_p3", "team_primary_p1", "team_primary_p0"]
    ].notna().all(axis=1)
    partial_keys = set(
        zip(power.loc[~complete, "issue"], power.loc[~complete, "match_idx"])
    )
    power = power[complete].copy()
    if power.empty:
        keys = list(zip(out["issue"].astype(str), out["match_idx"].astype(int)))
        out.loc[
            pd.Series([key in partial_keys for key in keys], index=out.index),
            producer_reason,
        ] = contract.REASON_PARTIAL_SOURCE_TRIPLET
        return out
    vectors = np.stack(
        [
            power["team_primary_p3"].to_numpy(dtype=np.float64),
            power["team_primary_p1"].to_numpy(dtype=np.float64),
            power["team_primary_p0"].to_numpy(dtype=np.float64),
        ],
        axis=1,
    )
    valid = np.array(
        [validate_probability_vector(v)[0] for v in vectors]
    )
    power = power[valid].copy()
    power["_v3"] = vectors[valid, 0]
    power["_v1"] = vectors[valid, 1]
    power["_v0"] = vectors[valid, 2]
    out = out.merge(
        power[
            [
                "issue",
                "match_idx",
                "_v3",
                "_v1",
                "_v0",
                "feature_cutoff_ts",
            ]
        ],
        on=["issue", "match_idx"],
        how="left",
        suffixes=("", "_power"),
        validate="many_to_one",
    )
    out[contract.P_POWER_BJLINE] = out.apply(
        lambda row: (
            [row["_v3"], row["_v1"], row["_v0"]]
            if pd.notna(row["_v3"]) and pd.notna(row["_v1"]) and pd.notna(row["_v0"])
            else np.nan
        ),
        axis=1,
    )
    # #180 freeze timestamps are naive Beijing time (+08:00, verified: its
    # kickoff_ts equals #203 kickoff_ts_utc + 8h).  Convert to UTC properly.
    power_ts_raw = pd.to_datetime(out.get("feature_cutoff_ts"), errors="coerce")
    power_ts = power_ts_raw.dt.tz_localize("Asia/Shanghai").dt.tz_convert("UTC")
    out[contract.observed_at_col(contract.P_POWER_BJLINE)] = power_ts
    out.loc[
        out[contract.P_POWER_BJLINE].notna(), contract.SOURCE_IDENTITY_POWER
    ] = contract.SRC_BJ180_TEAM_MODEL
    present = out[contract.P_POWER_BJLINE].apply(_is_list_vector)
    out.loc[present, producer_reason] = None
    keys = list(zip(out["issue"].astype(str), out["match_idx"].astype(int)))
    out.loc[
        ~present & pd.Series([key in partial_keys for key in keys], index=out.index),
        producer_reason,
    ] = contract.REASON_PARTIAL_SOURCE_TRIPLET
    out = out.drop(
        columns=["_v3", "_v1", "_v0", "feature_cutoff_ts"], errors="ignore"
    )
    return out


def vector_to_frame(
    frame: pd.DataFrame, representation: str
) -> pd.DataFrame:
    """Explode one list-typed representation column into 3/1/0 columns."""
    out = frame.copy()
    exploded = out[representation].apply(pd.Series)
    exploded.columns = [f"{representation}_{code}" for code in contract.OUTCOME_CODES]
    return pd.concat([out, exploded], axis=1)
