"""#252 formal vocabulary and fail-closed temporal selection rules.

This module is intentionally small and data-source agnostic.  Adapters must
normalise a source into the observation contract below before temporal analysis.
It refuses to reinterpret labelled retrospective proxy rows as wall-clock
snapshots and refuses unzoned timestamps for strict observations.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import pandas as pd

STRICT_NAMESPACE: Final = "strict_forward"
PROXY_NAMESPACE: Final = "historical_proxy"
STRICT_GRADE: Final = "OBSERVED_AGAINST_CURRENT_SCHEDULE_REFERENCE"
PROXY_GRADE: Final = "HISTORICAL_PROXY_LABEL_ONLY"
STRICT_SEMANTICS: Final = "OBSERVED_AT_UTC"
PROXY_SEMANTICS: Final = "SOURCE_RELATIVE_LABEL"
ACCEPTED_PROXY_HORIZONS: Final = ("initial", "10h", "1h")
REQUIRED_COLUMNS: Final = (
    "fixture_id",
    "issue_code",
    "match_idx",
    "snapshot_horizon",
    "time_semantics",
    "causal_grade",
    "source_id",
    "availability_mask",
    "available_cell_count",
    "observed_at_utc",
    "kickoff_at_utc",
)


class TemporalSemanticsError(ValueError):
    """Raised when an input cannot support the requested causal claim."""


@dataclass(frozen=True)
class DecisionView:
    """A declared common issue/segment decision epoch and selected rows."""

    issue_code: str
    decision_at_utc: pd.Timestamp
    rows: pd.DataFrame


def _require_columns(frame: pd.DataFrame) -> None:
    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise TemporalSemanticsError(f"observation contract missing columns: {', '.join(missing)}")
    if frame.empty:
        raise TemporalSemanticsError("observation contract is empty")
    if frame["fixture_id"].isna().any() or frame["fixture_id"].astype(str).eq("").any():
        raise TemporalSemanticsError("fixture_id is required")
    if frame["availability_mask"].isna().any():
        raise TemporalSemanticsError("availability_mask is required")
    if not pd.api.types.is_bool_dtype(frame["availability_mask"].dtype):
        raise TemporalSemanticsError("availability_mask must use an exact boolean dtype")
    cells = pd.to_numeric(frame["available_cell_count"], errors="coerce")
    if cells.isna().any() or (~cells.isin([0, 1, 2, 3])).any():
        raise TemporalSemanticsError("available_cell_count must be an integer in [0, 3]")
    if (frame["availability_mask"] & cells.ne(3)).any():
        raise TemporalSemanticsError("available observations require all three cells")


def _parse_utc(series: pd.Series, *, field: str, allow_null: bool) -> pd.Series:
    raw = series.astype("string")
    non_null = raw.notna()
    # Strict rows must carry an unambiguous UTC representation.  Native
    # timezone-aware pandas values are already canonical; raw strings must
    # carry a literal Z rather than relying on a local-machine assumption.
    already_aware = isinstance(series.dtype, pd.DatetimeTZDtype)
    if not already_aware and non_null.any() and (~raw[non_null].str.endswith("Z")).any():
        raise TemporalSemanticsError(f"{field} must be explicit UTC (Z suffix)")
    if not allow_null and (~non_null).any():
        raise TemporalSemanticsError(f"{field} is required")
    parsed = pd.to_datetime(series, utc=True, errors="coerce")
    if non_null.any() and parsed[non_null].isna().any():
        raise TemporalSemanticsError(f"{field} has invalid UTC timestamp")
    return parsed


def validate_observations(frame: pd.DataFrame, *, namespace: str) -> pd.DataFrame:
    """Validate and normalise one explicitly named temporal namespace.

    ``strict_forward`` is only for sealed, observed-at wall-clock rows;
    ``historical_proxy`` is only for the three source-relative labels.  The
    caller must choose one namespace, preventing silent pooled research panels.
    """
    _require_columns(frame)
    if namespace not in {STRICT_NAMESPACE, PROXY_NAMESPACE}:
        raise TemporalSemanticsError(f"unknown namespace: {namespace}")
    out = frame.copy()
    if namespace == STRICT_NAMESPACE:
        incompatible = (
            out["time_semantics"].ne(STRICT_SEMANTICS)
            | out["causal_grade"].ne(STRICT_GRADE)
        )
        if incompatible.any():
            raise TemporalSemanticsError("strict_forward cannot pool proxy or unsealed rows")
        out["observed_at_utc"] = _parse_utc(
            out["observed_at_utc"], field="observed_at_utc", allow_null=False
        )
    else:
        incompatible = (
            out["time_semantics"].ne(PROXY_SEMANTICS)
            | out["causal_grade"].ne(PROXY_GRADE)
        )
        if incompatible.any():
            raise TemporalSemanticsError("historical_proxy cannot pool strict rows")
        if (~out["snapshot_horizon"].isin(ACCEPTED_PROXY_HORIZONS)).any():
            raise TemporalSemanticsError(
                "historical_proxy contains horizons outside accepted proxy horizons"
            )
        if out["observed_at_utc"].notna().any():
            raise TemporalSemanticsError("historical_proxy must not claim observed_at_utc")
        out["observed_at_utc"] = pd.NaT
    out["kickoff_at_utc"] = _parse_utc(
        out["kickoff_at_utc"], field="kickoff_at_utc", allow_null=False
    )
    if namespace == STRICT_NAMESPACE and (
        out.loc[out["availability_mask"], "observed_at_utc"]
        >= out.loc[out["availability_mask"], "kickoff_at_utc"]
    ).any():
        raise TemporalSemanticsError("available strict observation at or after kickoff")
    key_columns = ["fixture_id", "issue_code", "match_idx", "kickoff_at_utc"]
    inconsistent = out.groupby("fixture_id", dropna=False)[key_columns[1:]].nunique(dropna=False)
    if (inconsistent > 1).any().any():
        raise TemporalSemanticsError("fixture identity/kickoff is inconsistent across observations")
    return out.sort_values(["fixture_id", "observed_at_utc"], kind="stable").reset_index(drop=True)


def build_issue_view(
    strict_rows: pd.DataFrame, *, issue_code: str, decision_at_utc: str | pd.Timestamp
) -> pd.DataFrame:
    """Select the latest available strict snapshot per fixture at one epoch.

    Rows after the declared epoch are never considered; the result retains a
    fixture row and a reason even where no observation was available.
    """
    rows = validate_observations(strict_rows, namespace=STRICT_NAMESPACE)
    decision = _parse_utc(pd.Series([decision_at_utc]), field="decision_at_utc", allow_null=False).iloc[0]
    subset = rows.loc[rows["issue_code"].astype(str).eq(str(issue_code))].copy()
    if subset.empty:
        raise TemporalSemanticsError(f"issue has no strict observations: {issue_code}")
    fixture_columns = ["fixture_id", "issue_code", "match_idx", "kickoff_at_utc"]
    fixtures = subset[fixture_columns].drop_duplicates("fixture_id").sort_values("match_idx")
    eligible_by_clock = subset.loc[subset["observed_at_utc"].le(decision)].sort_values(
        ["fixture_id", "observed_at_utc"], kind="stable"
    )
    latest_clock = eligible_by_clock.groupby("fixture_id", as_index=False).tail(1)
    latest_clock = latest_clock[
        ["fixture_id", "observed_at_utc", "available_cell_count"]
    ].rename(
        columns={
            "observed_at_utc": "latest_observed_at_utc_by_cutoff",
            "available_cell_count": "observed_cell_count_by_cutoff",
        }
    )
    selected = eligible_by_clock.loc[eligible_by_clock["availability_mask"]]
    selected = selected.groupby("fixture_id", as_index=False).tail(1)
    selected = selected[[
        "fixture_id", "observed_at_utc", "snapshot_horizon", "time_semantics",
        "causal_grade", "source_id", "availability_mask", "available_cell_count",
    ]].rename(columns={"observed_at_utc": "selected_observed_at_utc"})
    out = fixtures.merge(latest_clock, on="fixture_id", how="left", validate="one_to_one")
    out = out.merge(selected, on="fixture_id", how="left", validate="one_to_one")
    out["availability_mask"] = out["availability_mask"].fillna(False).astype(bool)
    out["available_cell_count"] = pd.to_numeric(
        out["available_cell_count"], errors="coerce"
    ).fillna(0).astype(int)
    out["observed_cell_count_by_cutoff"] = pd.to_numeric(
        out["observed_cell_count_by_cutoff"], errors="coerce"
    ).fillna(0).astype(int)
    out["decision_at_utc"] = decision
    out["staleness_minutes"] = (
        (decision - out["selected_observed_at_utc"]).dt.total_seconds() / 60.0
    )
    out["drop_reason"] = "AVAILABLE"
    no_selected = out["selected_observed_at_utc"].isna()
    out.loc[
        no_selected & out["latest_observed_at_utc_by_cutoff"].notna(), "drop_reason"
    ] = "OBSERVATION_UNAVAILABLE_OR_INCOMPLETE"
    out.loc[
        no_selected & out["latest_observed_at_utc_by_cutoff"].isna(), "drop_reason"
    ] = "NO_OBSERVATION_BY_CUTOFF"
    out.loc[decision >= out["kickoff_at_utc"], "drop_reason"] = "CUTOFF_NOT_PRE_KICKOFF"
    out.loc[out["drop_reason"].ne("AVAILABLE"), "selected_observed_at_utc"] = pd.NaT
    out.loc[out["drop_reason"].ne("AVAILABLE"), "staleness_minutes"] = float("nan")
    out["model_available_cell_count"] = 0
    out.loc[out["drop_reason"].eq("AVAILABLE"), "model_available_cell_count"] = 3
    return out.sort_values("match_idx", kind="stable").reset_index(drop=True)


def build_segment_views(
    strict_rows: pd.DataFrame,
    *,
    issue_code: str,
    lead_minutes: int,
    timezone_name: str,
) -> pd.DataFrame:
    """Partition an issue by local kickoff date and apply the identical cutoff rule.

    A segment cutoff is ``min(segment kickoff) - lead_minutes``.  No observation
    after that cutoff is eligible, and no fixture from a later local-date segment
    joins the earlier decision view.  The rule is deterministic for timezone,
    multi-day issues, reschedules, and sparse/missing observation histories.
    """
    if lead_minutes < 0:
        raise TemporalSemanticsError("lead_minutes must be non-negative")
    rows = validate_observations(strict_rows, namespace=STRICT_NAMESPACE)
    subset = rows.loc[rows["issue_code"].astype(str).eq(str(issue_code))].copy()
    if subset.empty:
        raise TemporalSemanticsError(f"issue has no strict observations: {issue_code}")
    fixture_clock = subset[["fixture_id", "match_idx", "kickoff_at_utc"]].drop_duplicates("fixture_id")
    fixture_clock["segment_date"] = fixture_clock["kickoff_at_utc"].dt.tz_convert(timezone_name).dt.date.astype(str)
    dates = sorted(fixture_clock["segment_date"].unique())
    outputs: list[pd.DataFrame] = []
    for segment_idx, segment_date in enumerate(dates):
        fixture_ids = fixture_clock.loc[
            fixture_clock["segment_date"].eq(segment_date), "fixture_id"
        ].tolist()
        segment_rows = subset.loc[subset["fixture_id"].isin(fixture_ids)]
        decision = segment_rows["kickoff_at_utc"].min() - pd.Timedelta(minutes=lead_minutes)
        view = build_issue_view(segment_rows, issue_code=issue_code, decision_at_utc=decision)
        view["segment_idx"] = segment_idx
        view["segment_date"] = segment_date
        outputs.append(view)
    return pd.concat(outputs, ignore_index=True).sort_values(
        ["segment_idx", "match_idx"], kind="stable"
    ).reset_index(drop=True)
