"""Generic chronology, partition, weighting, receipt, cache and runner primitives."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
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

    def __post_init__(self) -> None:
        object.__setattr__(self, "cutoff_ts", utc(self.cutoff_ts))
        if not self.identity or not self.kind:
            raise TemporalContractError("cutoff identity and kind are required")

    @classmethod
    def evaluation_year(cls, year: int, cutoff_ts: object) -> "Cutoff":
        return cls(f"EVALUATION_YEAR_{year}", utc(cutoff_ts), "EVALUATION_YEAR")

    @classmethod
    def last_issue(cls, issue: str, cutoff_ts: object) -> "Cutoff":
        return cls(f"LAST_AVAILABLE_ISSUE_{issue}", utc(cutoff_ts), "LAST_AVAILABLE_ISSUE")

    @classmethod
    def decision_epoch(cls, issue: str, cutoff_ts: object) -> "Cutoff":
        return cls(f"DECISION_EPOCH_{issue}", utc(cutoff_ts), "DECISION_EPOCH")


@dataclass(frozen=True)
class AvailabilityFilter:
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
        return cls("EXPANDING_EQUAL", effective_sample=EffectiveSamplePolicy(minimum_ess))

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


def utc(value: object) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    return timestamp.tz_localize("UTC") if timestamp.tzinfo is None else timestamp.tz_convert("UTC")


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
    partition_policy: PartitionPolicy,
    weighting_policy: WeightingPolicy,
) -> str:
    if not source_hashes or not implementation_hashes:
        raise TemporalContractError("cache identity requires source and implementation hashes")
    if any(not str(value) for value in [*source_hashes.values(), *implementation_hashes.values()]):
        raise TemporalContractError("cache identity contains empty hash")
    return stable_json_hash({
        "cutoff": {
            "identity": cutoff.identity,
            "kind": cutoff.kind,
            "cutoff_ts": cutoff.cutoff_ts.isoformat(),
        },
        "source_hashes": dict(sorted(source_hashes.items())),
        "implementation_hashes": dict(sorted(implementation_hashes.items())),
        "partition_policy": asdict(partition_policy),
        "weighting_policy": asdict(weighting_policy),
    })


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
    if policy.kind == "EXPANDING_EQUAL":
        raw = np.ones(len(frame), dtype=float)
    elif policy.kind == "EXPANDING_EXPONENTIAL":
        if policy.half_life_days is None or policy.half_life_days <= 0:
            raise TemporalContractError("exponential weighting requires positive half life")
        raw = np.power(0.5, age_days / policy.half_life_days)
    elif policy.kind == "RECENT_STATE_BLEND":
        if policy.rolling_window_issues is None or policy.rolling_window_issues <= 0:
            raise TemporalContractError("recent-state blend requires a positive issue window")
        if policy.recent_blend is None or not 0 < policy.recent_blend < 1:
            raise TemporalContractError("recent-state blend must retain long and recent history")
        issue_order = (
            frame.groupby(availability.source_issue_column, as_index=False)[availability.label_available_column]
            .max()
            .sort_values(
                [availability.label_available_column, availability.source_issue_column],
                kind="stable",
            )
        )
        recent = set(
            issue_order.tail(policy.rolling_window_issues)[availability.source_issue_column].astype(str)
        )
        raw = np.full(len(frame), 1.0 - policy.recent_blend, dtype=float)
        mask = frame[availability.source_issue_column].astype(str).isin(recent).to_numpy()
        raw[mask] += policy.recent_blend
    else:
        raise TemporalContractError(f"unsupported weighting policy: {policy.kind}")
    if not np.isfinite(raw).all() or (raw <= 0).any():
        raise TemporalContractError("weighting policy emitted invalid weights")
    weights = raw / raw.mean()
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
        weight=weights,
    )


def prepare_learning_context(
    history: pd.DataFrame,
    cutoff: Cutoff,
    *,
    source_hashes: Mapping[str, str],
    implementation_hashes: Mapping[str, str],
    availability: AvailabilityFilter = AvailabilityFilter(),
    partition_policy: PartitionPolicy = PartitionPolicy(),
    weighting_policy: WeightingPolicy = WeightingPolicy.expanding_equal(),
) -> LearningContext:
    """Filter, partition, weight and receipt-bind historical observations."""

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
    admitted[availability.label_available_column] = pd.to_datetime(
        admitted[availability.label_available_column], utc=True
    )
    if admitted[availability.label_available_column].isna().any():
        raise TemporalContractError("history has missing label availability")
    admitted_mask = admitted[availability.label_available_column].lt(cutoff.cutoff_ts)
    if availability.data_available_column is not None:
        admitted[availability.data_available_column] = pd.to_datetime(
            admitted[availability.data_available_column], utc=True
        )
        if admitted[availability.data_available_column].isna().any():
            raise TemporalContractError("history has missing data availability")
        admitted_mask &= admitted[availability.data_available_column].lt(cutoff.cutoff_ts)
    eligible = admitted[admitted_mask].copy()
    if eligible.empty:
        raise TemporalContractError("cutoff admits no prior observations")
    if not eligible[availability.label_available_column].lt(cutoff.cutoff_ts).all():
        raise TemporalContractError("availability filter crossed cutoff")
    if partition_policy.kind != "COMPLETE_PRIOR_YEARS":
        raise TemporalContractError(f"unsupported partition policy: {partition_policy.kind}")
    if (
        partition_policy.minimum_fit_years < 1
        or partition_policy.tune_years < 1
        or partition_policy.calibration_years < 1
    ):
        raise TemporalContractError("partition policy requires positive fit/tune/calibration years")
    years = sorted(eligible[availability.issue_year_column].astype(int).unique())
    complete_years = [year for year in years if year < cutoff.cutoff_ts.year]
    tail = partition_policy.tune_years + partition_policy.calibration_years
    if len(complete_years) < partition_policy.minimum_fit_years + tail:
        raise TemporalContractError("insufficient complete prior years for partitions")
    fit_years = complete_years[:-tail]
    tune_years = complete_years[-tail:-partition_policy.calibration_years]
    calibration_years = complete_years[-partition_policy.calibration_years:]
    partitions = {
        "fit": eligible[eligible[availability.issue_year_column].isin(fit_years)].copy(),
        "tune": eligible[eligible[availability.issue_year_column].isin(tune_years)].copy(),
        "calibration": eligible[eligible[availability.issue_year_column].isin(calibration_years)].copy(),
        "final_refit": eligible,
    }
    if any(frame.empty for frame in partitions.values()):
        raise TemporalContractError("derived partition is empty")
    ledger = _weight_ledger(eligible, cutoff, availability, weighting_policy)
    weights = pd.Series(ledger["weight"].to_numpy(float), index=eligible.index)
    implementation_hashes = dict(sorted(implementation_hashes.items()))
    cache_key = temporal_cache_key(
        cutoff,
        source_hashes,
        implementation_hashes,
        partition_policy,
        weighting_policy,
    )
    max_row = eligible.sort_values(availability.label_available_column, kind="stable").iloc[-1]
    maximum_source_time = (
        eligible[availability.data_available_column].max()
        if availability.data_available_column is not None
        else eligible[availability.label_available_column].max()
    )
    receipt = LearningReceipt({
        "cutoff_identity": cutoff.identity,
        "cutoff_kind": cutoff.kind,
        "cutoff_ts": cutoff.cutoff_ts.isoformat(),
        "maximum_source_issue": str(max_row[availability.source_issue_column]),
        "maximum_source_time": maximum_source_time.isoformat(),
        "maximum_training_label_timestamp": max_row[availability.label_available_column].isoformat(),
        "partition": {
            "fit_years": [int(year) for year in fit_years],
            "tune_years": [int(year) for year in tune_years],
            "calibration_years": [int(year) for year in calibration_years],
            "eligible_years": [int(year) for year in years],
            **{f"{name}_rows": len(frame) for name, frame in partitions.items()},
        },
        "source_hashes": dict(sorted(source_hashes.items())),
        "admitted_history_sha256": stable_frame_hash(eligible.reset_index(drop=True)),
        "implementation_hashes": implementation_hashes,
        "partition_policy": asdict(partition_policy),
        "weight_receipt": {
            "policy": asdict(weighting_policy),
            "rows": len(ledger),
            "sum": float(ledger["weight"].sum()),
            "minimum": float(ledger["weight"].min()),
            "maximum": float(ledger["weight"].max()),
            "effective_sample_size": effective_sample_size(ledger["weight"].to_numpy(float)),
            "weight_frame_sha256": stable_frame_hash(ledger),
        },
        "cache_key": cache_key,
    })
    return LearningContext(cutoff, eligible, partitions, weights, ledger, receipt)


class WalkForwardRunner(Generic[T]):
    """Run one model-specific callback per target issue under generic chronology."""

    def __init__(self, issue_column: str = "issue_code", decision_column: str = "fixture_decision_ts") -> None:
        self.issue_column = issue_column
        self.decision_column = decision_column

    def run(
        self,
        targets: pd.DataFrame,
        callback: Callable[[Cutoff, pd.DataFrame], T],
    ) -> list[T]:
        if not {self.issue_column, self.decision_column}.issubset(targets):
            raise TemporalContractError("walk-forward targets lack issue/decision columns")
        frame = targets.copy()
        frame[self.decision_column] = pd.to_datetime(frame[self.decision_column], utc=True)
        if frame[self.decision_column].isna().any():
            raise TemporalContractError("walk-forward target decision epoch is missing")
        epochs = (
            frame.groupby(self.issue_column, as_index=False)[self.decision_column]
            .min().sort_values([self.decision_column, self.issue_column], kind="stable")
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
