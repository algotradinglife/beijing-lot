"""Generic chronology, partition, weighting, receipt, cache and runner primitives."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Generic, Mapping, Protocol, TypeVar

import numpy as np
import pandas as pd


class TemporalContractError(ValueError):
    """Raised when historical learning cannot prove temporal admissibility."""


@dataclass(frozen=True)
class Cutoff:
    identity: str
    cutoff_ts: pd.Timestamp
    kind: str
    target_issue: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "cutoff_ts", utc(self.cutoff_ts))
        if not self.identity or not self.kind:
            raise TemporalContractError("cutoff identity and kind are required")
        if self.kind == "DECISION_EPOCH" and not self.target_issue:
            raise TemporalContractError(
                "decision-epoch cutoff requires target issue identity"
            )
        if self.kind != "DECISION_EPOCH" and self.target_issue is not None:
            raise TemporalContractError(
                "target issue identity is only valid for decision epoch"
            )

    @classmethod
    def evaluation_year(cls, year: int, cutoff_ts: object) -> "Cutoff":
        return cls(f"EVALUATION_YEAR_{year}", utc(cutoff_ts), "EVALUATION_YEAR")

    @classmethod
    def last_issue(cls, issue: str, cutoff_ts: object) -> "Cutoff":
        return cls(
            f"LAST_AVAILABLE_ISSUE_{issue}", utc(cutoff_ts), "LAST_AVAILABLE_ISSUE"
        )

    @classmethod
    def decision_epoch(cls, issue: str, cutoff_ts: object) -> "Cutoff":
        issue = str(issue)
        if not issue:
            raise TemporalContractError("decision epoch requires non-empty issue")
        return cls(f"DECISION_EPOCH_{issue}", utc(cutoff_ts), "DECISION_EPOCH", issue)


@dataclass(frozen=True)
class AvailabilityPolicy:
    identity: str
    kind: str
    prospective_capable: bool
    safety_margin_seconds: float = 0.0

    def __post_init__(self) -> None:
        if not self.identity:
            raise TemporalContractError("availability policy identity is required")
        if self.kind not in {
            "OBSERVED_AVAILABILITY",
            "CONSERVATIVE_SAFE_BOUNDARY",
            "HISTORICAL_PROXY",
        }:
            raise TemporalContractError(
                f"unsupported availability policy kind: {self.kind}"
            )
        if self.kind == "HISTORICAL_PROXY" and self.prospective_capable:
            raise TemporalContractError(
                "historical proxy cannot authorize prospective use"
            )
        if self.safety_margin_seconds < 0:
            raise TemporalContractError("availability safety margin cannot be negative")

    @classmethod
    def observed(cls, identity: str) -> "AvailabilityPolicy":
        return cls(identity, "OBSERVED_AVAILABILITY", True)

    @classmethod
    def conservative_boundary(
        cls, identity: str, safety_margin_seconds: float
    ) -> "AvailabilityPolicy":
        if safety_margin_seconds <= 0:
            raise TemporalContractError(
                "conservative boundary requires a positive margin"
            )
        return cls(
            identity, "CONSERVATIVE_SAFE_BOUNDARY", True, float(safety_margin_seconds)
        )

    @classmethod
    def historical_proxy(cls, identity: str) -> "AvailabilityPolicy":
        return cls(identity, "HISTORICAL_PROXY", False)


@dataclass(frozen=True)
class AvailabilityFilter:
    policy: AvailabilityPolicy
    label_available_column: str = "label_available_ts"
    data_available_column: str | None = None
    source_issue_column: str = "issue_code"
    issue_year_column: str = "issue_year"


@dataclass(frozen=True)
class PartitionPolicy:
    kind: str = "COMPLETE_PRIOR_YEARS"
    tune_years: int = 1
    calibration_years: int = 1
    minimum_fit_years: int = 1


@dataclass(frozen=True)
class EffectiveSamplePolicy:
    minimum: float = 100.0
    on_insufficient: str = "FAIL_CLOSED"


@dataclass(frozen=True)
class WeightingPolicy:
    kind: str
    half_life_days: float | None = None
    rolling_window_issues: int | None = None
    recent_blend: float | None = None
    effective_sample: EffectiveSamplePolicy = EffectiveSamplePolicy()

    @classmethod
    def expanding_equal(cls, *, minimum_ess: float = 100.0) -> "WeightingPolicy":
        return cls(
            "EXPANDING_EQUAL", effective_sample=EffectiveSamplePolicy(minimum_ess)
        )

    @classmethod
    def expanding_exponential(
        cls, half_life_days: float, *, minimum_ess: float = 100.0
    ) -> "WeightingPolicy":
        return cls(
            "EXPANDING_EXPONENTIAL",
            half_life_days=float(half_life_days),
            effective_sample=EffectiveSamplePolicy(minimum_ess),
        )

    @classmethod
    def recent_state_blend(
        cls,
        rolling_window_issues: int,
        recent_blend: float,
        *,
        minimum_ess: float = 100.0,
    ) -> "WeightingPolicy":
        return cls(
            "RECENT_STATE_BLEND",
            rolling_window_issues=int(rolling_window_issues),
            recent_blend=float(recent_blend),
            effective_sample=EffectiveSamplePolicy(minimum_ess),
        )


@dataclass(frozen=True)
class LearningReceipt:
    payload: dict[str, Any]


@dataclass
class LearningContext:
    cutoff: Cutoff
    eligible: pd.DataFrame
    partitions: dict[str, pd.DataFrame]
    weights: pd.Series
    weight_ledger: pd.DataFrame
    receipt: LearningReceipt


class FitResult(Protocol):
    artifact: Any
    receipt: Mapping[str, Any]


class SelectionResult(Protocol):
    selection: Any
    receipt: Mapping[str, Any]


T = TypeVar("T")


def temporal_client(function: Callable[..., T]) -> Callable[..., T]:
    """Mark a decision-facing callback whose chronology is owned by this module."""

    setattr(function, "__temporal_learning_client__", True)
    return function


def utc(value: object) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return (
        timestamp.tz_localize("UTC")
        if timestamp.tzinfo is None
        else timestamp.tz_convert("UTC")
    )


def stable_json_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def stable_frame_hash(frame: pd.DataFrame) -> str:
    values = pd.util.hash_pandas_object(frame, index=False).to_numpy(np.uint64)
    return hashlib.sha256(values.tobytes()).hexdigest()


def effective_sample_size(weights: np.ndarray) -> float:
    return float(np.square(weights.sum()) / np.square(weights).sum())


def temporal_cache_key(
    cutoff: Cutoff,
    source_hashes: Mapping[str, str],
    implementation_hashes: Mapping[str, str],
    availability_policy: AvailabilityPolicy,
    intended_use: str,
    partition_policy: PartitionPolicy,
    weighting_policy: WeightingPolicy,
) -> str:
    if not source_hashes or not implementation_hashes:
        raise TemporalContractError(
            "cache identity requires source and implementation hashes"
        )
    if any(
        not str(value)
        for value in [*source_hashes.values(), *implementation_hashes.values()]
    ):
        raise TemporalContractError("cache identity contains empty hash")
    return stable_json_hash(
        {
            "cutoff": {
                "identity": cutoff.identity,
                "kind": cutoff.kind,
                "cutoff_ts": cutoff.cutoff_ts.isoformat(),
                "target_issue": cutoff.target_issue,
            },
            "source_hashes": dict(sorted(source_hashes.items())),
            "implementation_hashes": dict(sorted(implementation_hashes.items())),
            "availability_policy": asdict(availability_policy),
            "intended_use": intended_use,
            "partition_policy": asdict(partition_policy),
            "weighting_policy": asdict(weighting_policy),
        }
    )


def _weight_ledger(
    eligible: pd.DataFrame,
    cutoff: Cutoff,
    availability: AvailabilityFilter,
    policy: WeightingPolicy,
) -> pd.DataFrame:
    columns = [availability.source_issue_column, availability.label_available_column]
    frame = eligible[columns].copy()
    frame[availability.label_available_column] = pd.to_datetime(
        frame[availability.label_available_column], utc=True
    )
    age_days = (
        cutoff.cutoff_ts - frame[availability.label_available_column]
    ).dt.total_seconds().to_numpy(float) / 86_400
    long_mass = np.zeros(len(frame), dtype=float)
    recent_mass = np.zeros(len(frame), dtype=float)
    if policy.kind == "EXPANDING_EQUAL":
        long_mass[:] = 1.0 / len(frame)
    elif policy.kind == "EXPANDING_EXPONENTIAL":
        if policy.half_life_days is None or policy.half_life_days <= 0:
            raise TemporalContractError(
                "exponential weighting requires positive half life"
            )
        raw = np.power(0.5, age_days / policy.half_life_days)
        long_mass = raw / raw.sum()
    elif policy.kind == "RECENT_STATE_BLEND":
        if policy.rolling_window_issues is None or policy.rolling_window_issues <= 0:
            raise TemporalContractError(
                "recent-state blend requires a positive issue window"
            )
        if policy.recent_blend is None or not 0 < policy.recent_blend < 1:
            raise TemporalContractError(
                "recent-state blend must retain long and recent history"
            )
        issue_order = (
            frame.groupby(availability.source_issue_column, as_index=False)[
                availability.label_available_column
            ]
            .max()
            .sort_values(
                [availability.label_available_column, availability.source_issue_column],
                kind="stable",
            )
        )
        recent = set(
            issue_order.tail(policy.rolling_window_issues)[
                availability.source_issue_column
            ].astype(str)
        )
        issue_values = frame[availability.source_issue_column].astype(str)
        long_mass[:] = (1.0 - policy.recent_blend) / len(frame)
        recent_issue_count = len(recent)
        for issue in recent:
            mask = issue_values.eq(issue).to_numpy()
            rows = int(mask.sum())
            if rows <= 0:
                raise TemporalContractError("recent-state issue has no rows")
            recent_mass[mask] = policy.recent_blend / recent_issue_count / rows
    else:
        raise TemporalContractError(f"unsupported weighting policy: {policy.kind}")
    total_mass = long_mass + recent_mass
    if not np.isfinite(total_mass).all() or (total_mass <= 0).any():
        raise TemporalContractError("weighting policy emitted invalid weights")
    if not np.isclose(total_mass.sum(), 1.0, rtol=0, atol=1e-12):
        raise TemporalContractError("weighting policy mass does not sum to one")
    weights = total_mass * len(frame)
    ess = effective_sample_size(weights)
    if ess < policy.effective_sample.minimum:
        if policy.effective_sample.on_insufficient != "FAIL_CLOSED":
            raise TemporalContractError("unsupported insufficient-sample behavior")
        raise TemporalContractError(
            f"effective sample size {ess:.3f} below floor {policy.effective_sample.minimum:.3f}"
        )
    return frame.assign(
        cutoff_identity=cutoff.identity,
        cutoff_ts=cutoff.cutoff_ts,
        age_days=age_days,
        long_mass=long_mass,
        recent_mass=recent_mass,
        total_mass=total_mass,
        weight=weights,
    )


def prepare_learning_context(
    history: pd.DataFrame,
    cutoff: Cutoff,
    *,
    source_hashes: Mapping[str, str],
    repository_root: Path,
    implementation_modules: tuple[str, ...],
    implementation_distributions: tuple[str, ...] = (),
    availability: AvailabilityFilter,
    intended_use: str,
    partition_policy: PartitionPolicy = PartitionPolicy(),
    weighting_policy: WeightingPolicy = WeightingPolicy.expanding_equal(),
) -> LearningContext:
    """Filter, partition, weight and receipt-bind historical observations."""

    if intended_use not in {"HISTORICAL_DIAGNOSTIC", "PROSPECTIVE_DECISION"}:
        raise TemporalContractError(f"unsupported intended use: {intended_use}")
    if (
        intended_use == "PROSPECTIVE_DECISION"
        and not availability.policy.prospective_capable
    ):
        raise TemporalContractError(
            "availability policy cannot authorize prospective use"
        )

    required = {
        availability.label_available_column,
        availability.source_issue_column,
        availability.issue_year_column,
    }
    if availability.data_available_column is not None:
        required.add(availability.data_available_column)
    if not required.issubset(history):
        raise TemporalContractError("history lacks availability columns")
    admitted = history.copy()
    if admitted[availability.source_issue_column].isna().any():
        raise TemporalContractError("history has ambiguous source issue identity")
    admitted[availability.source_issue_column] = admitted[
        availability.source_issue_column
    ].astype(str)
    admitted[availability.label_available_column] = pd.to_datetime(
        admitted[availability.label_available_column], utc=True
    )
    if admitted[availability.label_available_column].isna().any():
        raise TemporalContractError("history has missing label availability")
    availability_boundary_ts = cutoff.cutoff_ts - pd.Timedelta(
        seconds=availability.policy.safety_margin_seconds
    )
    admitted_mask = admitted[availability.label_available_column].lt(
        availability_boundary_ts
    )
    row_source_time = admitted[availability.label_available_column].copy()
    if availability.data_available_column is not None:
        admitted[availability.data_available_column] = pd.to_datetime(
            admitted[availability.data_available_column], utc=True
        )
        if admitted[availability.data_available_column].isna().any():
            raise TemporalContractError("history has missing data availability")
        admitted_mask &= admitted[availability.data_available_column].lt(
            availability_boundary_ts
        )
        row_source_time = pd.concat(
            [row_source_time, admitted[availability.data_available_column]], axis=1
        ).max(axis=1)
    target_rows_seen = 0
    target_rows_excluded = 0
    if cutoff.target_issue is not None:
        target_mask = admitted[availability.source_issue_column].eq(cutoff.target_issue)
        target_rows_seen = int(target_mask.sum())
        target_rows_excluded = int(target_mask.sum())
        admitted_mask &= ~target_mask
    eligible = admitted[admitted_mask].copy()
    if eligible.empty:
        raise TemporalContractError("cutoff admits no prior observations")
    if (
        not eligible[availability.label_available_column]
        .lt(availability_boundary_ts)
        .all()
    ):
        raise TemporalContractError("availability filter crossed cutoff")
    years = sorted(eligible[availability.issue_year_column].astype(int).unique())
    if partition_policy.kind == "FIXED_PRIOR_FIT":
        # A fixed diagnostic fit has no parameter search or calibration split.
        # It still uses the common strict availability, weights and receipts.
        if intended_use != "HISTORICAL_DIAGNOSTIC":
            raise TemporalContractError("fixed prior fit is diagnostic only")
        if (partition_policy.tune_years != 0 or
                partition_policy.calibration_years != 0 or
                partition_policy.minimum_fit_years < 1 or
                len(years) < partition_policy.minimum_fit_years):
            raise TemporalContractError("fixed prior fit requires zero tuning/calibration and sufficient history")
        fit_years, tune_years, calibration_years = years, [], []
        partitions = {"fit": eligible.copy(), "tune": eligible.iloc[:0].copy(),
                      "calibration": eligible.iloc[:0].copy(), "final_refit": eligible}
    elif partition_policy.kind == "COMPLETE_PRIOR_YEARS":
        if (
            partition_policy.minimum_fit_years < 1
            or partition_policy.tune_years < 1
            or partition_policy.calibration_years < 1
        ):
            raise TemporalContractError(
                "partition policy requires positive fit/tune/calibration years"
            )
        complete_years = [year for year in years if year < cutoff.cutoff_ts.year]
        tail = partition_policy.tune_years + partition_policy.calibration_years
        if len(complete_years) < partition_policy.minimum_fit_years + tail:
            raise TemporalContractError("insufficient complete prior years for partitions")
        fit_years = complete_years[:-tail]
        tune_years = complete_years[-tail : -partition_policy.calibration_years]
        calibration_years = complete_years[-partition_policy.calibration_years :]
        partitions = {
            "fit": eligible[
                eligible[availability.issue_year_column].isin(fit_years)
            ].copy(),
            "tune": eligible[
                eligible[availability.issue_year_column].isin(tune_years)
            ].copy(),
            "calibration": eligible[
                eligible[availability.issue_year_column].isin(calibration_years)
            ].copy(),
            "final_refit": eligible,
        }
        if any(frame.empty for frame in partitions.values()):
            raise TemporalContractError("derived partition is empty")
    else:
        raise TemporalContractError(f"unsupported partition policy: {partition_policy.kind}")
    ledger = _weight_ledger(eligible, cutoff, availability, weighting_policy)
    weights = pd.Series(ledger["weight"].to_numpy(float), index=eligible.index)
    from .provenance import implementation_closure

    implementation_receipt = implementation_closure(
        repository_root,
        implementation_modules,
        distributions=implementation_distributions,
    )
    implementation_hashes = dict(implementation_receipt["files"])
    cache_key = temporal_cache_key(
        cutoff,
        source_hashes,
        implementation_hashes,
        availability.policy,
        intended_use,
        partition_policy,
        weighting_policy,
    )
    eligible_source_time = row_source_time.loc[eligible.index]
    maximum_source_index = eligible_source_time.idxmax()
    maximum_source_time = eligible_source_time.loc[maximum_source_index]
    maximum_source_issue = eligible.loc[
        maximum_source_index, availability.source_issue_column
    ]
    maximum_label_time = eligible[availability.label_available_column].max()
    receipt = LearningReceipt(
        {
            "cutoff_identity": cutoff.identity,
            "cutoff_kind": cutoff.kind,
            "cutoff_ts": cutoff.cutoff_ts.isoformat(),
            "target_issue": cutoff.target_issue,
            "target_rows_seen": target_rows_seen,
            "target_rows_excluded": target_rows_excluded,
            "maximum_source_issue": str(maximum_source_issue),
            "maximum_source_time": maximum_source_time.isoformat(),
            "maximum_training_label_timestamp": maximum_label_time.isoformat(),
            "partition": {
                "fit_years": [int(year) for year in fit_years],
                "tune_years": [int(year) for year in tune_years],
                "calibration_years": [int(year) for year in calibration_years],
                "eligible_years": [int(year) for year in years],
                **{f"{name}_rows": len(frame) for name, frame in partitions.items()},
            },
            "source_hashes": dict(sorted(source_hashes.items())),
            "admitted_history_sha256": stable_frame_hash(
                eligible.reset_index(drop=True)
            ),
            "implementation": implementation_receipt,
            "implementation_hashes": implementation_hashes,
            "availability": {
                "policy": asdict(availability.policy),
                "intended_use": intended_use,
                "admissibility_boundary_ts": availability_boundary_ts.isoformat(),
                "label_available_column": availability.label_available_column,
                "data_available_column": availability.data_available_column,
                "minimum_label_margin_to_cutoff_seconds": float(
                    (cutoff.cutoff_ts - maximum_label_time).total_seconds()
                ),
                "minimum_source_margin_to_cutoff_seconds": float(
                    (cutoff.cutoff_ts - maximum_source_time).total_seconds()
                ),
            },
            "partition_policy": asdict(partition_policy),
            "weight_receipt": {
                "policy": asdict(weighting_policy),
                "rows": len(ledger),
                "sum": float(ledger["weight"].sum()),
                "minimum": float(ledger["weight"].min()),
                "maximum": float(ledger["weight"].max()),
                "effective_sample_size": effective_sample_size(
                    ledger["weight"].to_numpy(float)
                ),
                "long_history_mass": float(ledger["long_mass"].sum()),
                "recent_state_mass": float(ledger["recent_mass"].sum()),
                "issue_mass_sha256": stable_frame_hash(
                    ledger.groupby(availability.source_issue_column, as_index=False)[
                        ["long_mass", "recent_mass", "total_mass"]
                    ].sum()
                ),
                "weight_frame_sha256": stable_frame_hash(ledger),
            },
            "cache_key": cache_key,
        }
    )
    return LearningContext(cutoff, eligible, partitions, weights, ledger, receipt)


class WalkForwardRunner(Generic[T]):
    """Run one model-specific callback per target issue under generic chronology."""

    def __init__(
        self,
        issue_column: str = "issue_code",
        decision_column: str = "fixture_decision_ts",
    ) -> None:
        self.issue_column = issue_column
        self.decision_column = decision_column

    def run(
        self,
        targets: pd.DataFrame,
        callback: Callable[[Cutoff, pd.DataFrame], T],
    ) -> list[T]:
        if not {self.issue_column, self.decision_column}.issubset(targets):
            raise TemporalContractError(
                "walk-forward targets lack issue/decision columns"
            )
        frame = targets.copy()
        frame[self.decision_column] = pd.to_datetime(
            frame[self.decision_column], utc=True
        )
        if frame[self.decision_column].isna().any():
            raise TemporalContractError("walk-forward target decision epoch is missing")
        epochs = (
            frame.groupby(self.issue_column, as_index=False)[self.decision_column]
            .min()
            .sort_values([self.decision_column, self.issue_column], kind="stable")
        )
        results: list[T] = []
        for row in epochs.itertuples(index=False):
            issue = str(getattr(row, self.issue_column))
            cutoff_ts = getattr(row, self.decision_column)
            cutoff = Cutoff.decision_epoch(issue, cutoff_ts)
            target = frame[frame[self.issue_column].astype(str).eq(issue)].copy()
            results.append(callback(cutoff, target))
        if not results:
            raise TemporalContractError("walk-forward target set is empty")
        return results
