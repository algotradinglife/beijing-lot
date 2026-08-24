"""Generic chronology, partition, weighting, receipt, cache and runner primitives.

#388 hardening:
- Cutoff carries a structured target_identity; decision-epoch learning must
  exclude every row of the target issue, not merely rows whose availability
  timestamp precedes the cutoff.
- AvailabilityFilter declares a policy identity and a conservative safe
  boundary for proxy policies; receipts bind policy identity and
  margin-to-cutoff, and prospective proxy claims fail closed without one.
- RECENT_STATE_BLEND (per-row boost) is replaced by RECENT_STATE_MIXTURE, a
  long-history/recent-state convex mixture with aggregate mass, row/issue
  mass, ESS and shrinkage bound in the weight receipt. No compatibility
  wrapper.
"""

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
    target_identity: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "cutoff_ts", utc(self.cutoff_ts))
        if not self.identity or not self.kind:
            raise TemporalContractError("cutoff identity and kind are required")
        if self.kind == "DECISION_EPOCH" and not self.target_identity:
            raise TemporalContractError("decision-epoch cutoff requires a target identity")
        if self.target_identity is not None and str(self.target_identity).strip() == "":
            raise TemporalContractError("cutoff target identity must not be blank")

    @classmethod
    def evaluation_year(cls, year: int, cutoff_ts: object) -> "Cutoff":
        return cls(f"EVALUATION_YEAR_{year}", utc(cutoff_ts), "EVALUATION_YEAR")

    @classmethod
    def last_issue(cls, issue: str, cutoff_ts: object) -> "Cutoff":
        return cls(f"LAST_AVAILABLE_ISSUE_{issue}", utc(cutoff_ts), "LAST_AVAILABLE_ISSUE")

    @classmethod
    def decision_epoch(cls, issue: str, cutoff_ts: object) -> "Cutoff":
        return cls(
            f"DECISION_EPOCH_{issue}",
            utc(cutoff_ts),
            "DECISION_EPOCH",
            target_identity=str(issue),
        )


@dataclass(frozen=True)
class AvailabilityFilter:
    label_available_column: str = "label_available_ts"
    data_available_column: str | None = None
    source_issue_column: str = "issue_code"
    issue_year_column: str = "issue_year"
    # #388: explicit availability policy identity. OBSERVED_* means availability
    # was actually observed; PROXY_* means a deterministic proxy policy (e.g.
    # kickoff+4h) that must carry a preregistered conservative safe boundary.
    policy_identity: str = "OBSERVED_LABEL_AVAILABILITY"
    proxy_safe_boundary_ts: pd.Timestamp | None = None

    def __post_init__(self) -> None:
        identity = self.policy_identity.strip()
        object.__setattr__(self, "policy_identity", identity)
        if not identity:
            raise TemporalContractError("availability policy identity is required")
        if not identity.startswith("OBSERVED_") and not identity.startswith("PROXY_"):
            raise TemporalContractError(
                "availability policy identity must start with OBSERVED_ or PROXY_"
            )
        if identity.startswith("PROXY_"):
            if self.proxy_safe_boundary_ts is None:
                raise TemporalContractError(
                    "proxy availability policy requires a conservative safe boundary"
                )
            object.__setattr__(
                self,
                "proxy_safe_boundary_ts",
                utc(self.proxy_safe_boundary_ts),
            )


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
    def recent_state_mixture(
        cls,
        rolling_window_issues: int,
        recent_blend: float,
        *,
        minimum_ess: float = 100.0,
    ) -> "WeightingPolicy":
        """Long-history/recent-state convex mixture.

        alpha = recent_blend must lie in (0, 0.5], so the long-history prior
        carries at least as much aggregate mass as the recent state. This
        replaces the old per-row RECENT_STATE_BLEND boost.
        """
        return cls(
            "RECENT_STATE_MIXTURE",
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
            "target_identity": cutoff.target_identity,
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
) -> tuple[pd.DataFrame, dict[str, Any]]:
    columns = [availability.source_issue_column, availability.label_available_column]
    frame = eligible[columns].copy()
    frame[availability.label_available_column] = pd.to_datetime(
        frame[availability.label_available_column], utc=True
    )
    age_days = (
        cutoff.cutoff_ts - frame[availability.label_available_column]
    ).dt.total_seconds().to_numpy(float) / 86_400
    issue_ids = frame[availability.source_issue_column].astype(str).to_numpy()
    alpha: float = 0.0
    long_part_mass: float = 0.0
    recent_part_mass: float = 0.0
    recent_rows: np.ndarray = np.zeros(len(frame), dtype=bool)
    recent_count: int = 0
    mixture: dict[str, Any] | None = None
    if policy.kind == "EXPANDING_EQUAL":
        raw = np.ones(len(frame), dtype=float)
    elif policy.kind == "EXPANDING_EXPONENTIAL":
        if policy.half_life_days is None or policy.half_life_days <= 0:
            raise TemporalContractError("exponential weighting requires positive half life")
        raw = np.power(0.5, age_days / policy.half_life_days)
    elif policy.kind == "RECENT_STATE_MIXTURE":
        if policy.rolling_window_issues is None or policy.rolling_window_issues <= 0:
            raise TemporalContractError("recent-state mixture requires a positive issue window")
        alpha = policy.recent_blend
        if alpha is None or not 0.0 < alpha <= 0.5:
            raise TemporalContractError(
                "recent-state mixture blend must lie in (0, 0.5] so the long-history "
                "prior retains at least as much aggregate mass as the recent state"
            )
        alpha = float(alpha)
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
        recent_rows = np.isin(issue_ids, list(recent))
        recent_count = int(recent_rows.sum())
        if recent_count == 0:
            raise TemporalContractError("recent-state mixture has no recent rows")
        # Mathematically explicit convex mixture w = (1-alpha)*u + alpha*v,
        # u uniform over every eligible row, v uniform over recent-state rows.
        # Raw scale sums to one (mass); mean-normalization to a weight scale
        # preserves the exact (1-alpha):alpha aggregate mass split.
        raw = np.full(len(frame), (1.0 - alpha) / len(frame), dtype=float)
        raw[recent_rows] += alpha / recent_count
        recent_part_mass = alpha
        long_part_mass = 1.0 - alpha
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
    issue_mass = (
        pd.Series(weights, index=issue_ids)
        .groupby(level=0)
        .sum()
        .to_dict()
    )
    if policy.kind == "RECENT_STATE_MIXTURE":
        # Mean-normalization multiplies every raw mass by rows/1, so the
        # normalized recent-part aggregate mass is alpha * rows. To bind the
        # declared coefficient exactly, report the raw mass split (which sums
        # to 1.0) alongside the normalized row aggregate.
        mixture = {
            "declared_recent_blend": alpha,
            "long_part_mass": round(long_part_mass, 12),
            "recent_part_mass": round(recent_part_mass, 12),
            "mass_sum": round(float(raw.sum()), 12),
            "normalized_recent_row_aggregate": float(weights[recent_rows].sum()),
            "recent_rows": recent_count,
            "long_rows": int(len(frame) - recent_count),
            "ess": ess,
            "shrinkage_toward_long_prior": round(float(long_part_mass), 12),
        }
    else:
        mixture = None
    ledger = frame.assign(
        cutoff_identity=cutoff.identity,
        cutoff_ts=cutoff.cutoff_ts,
        age_days=age_days,
        weight=weights,
    )
    meta = {"mixture": mixture, "issue_mass": issue_mass}
    return ledger, meta


def _excluded_target_rows(
    admitted: pd.DataFrame,
    cutoff: Cutoff,
    availability: AvailabilityFilter,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Exclude every row of the target issue, receipting the count.

    Fail-closed on ambiguous identity: when a decision-epoch cutoff names a
    target issue, the history must unambiguously identify rows by that issue,
    otherwise admissibility cannot be proven.
    """
    if cutoff.target_identity is None:
        return admitted, {"enabled": False, "target_identity": None, "excluded_rows": 0}
    column = availability.source_issue_column
    if column not in admitted:
        raise TemporalContractError(
            "decision-epoch target exclusion requires a source issue column"
        )
    codes = admitted[column].astype(str)
    if codes.isna().any() or codes.str.strip().eq("").any():
        raise TemporalContractError(
            "ambiguous target identity: history contains blank or missing issue codes"
        )
    target = str(cutoff.target_identity)
    mask = codes.eq(target)
    excluded = int(mask.sum())
    if excluded == 0:
        # The target issue may legitimately be absent from history, but a
        # decision-epoch cutoff cannot prove exclusion of a missing target;
        # fail closed rather than silently admit a neighbour row.
        raise TemporalContractError(
            f"decision-epoch cutoff {cutoff.identity} names target issue {target} "
            "but history contains no such row; cannot prove target exclusion"
        )
    return admitted.loc[~mask].copy(), {
        "enabled": True,
        "target_identity": target,
        "excluded_rows": excluded,
    }


def prepare_learning_context(
    history: pd.DataFrame,
    cutoff: Cutoff,
    *,
    source_hashes: Mapping[str, str],
    implementation_hashes: Mapping[str, str],
    availability: AvailabilityFilter = AvailabilityFilter(),
    partition_policy: PartitionPolicy = PartitionPolicy(),
    weighting_policy: WeightingPolicy = WeightingPolicy.expanding_equal(),
    prospective_capable: bool = False,
) -> LearningContext:
    """Filter, partition, weight and receipt-bind historical observations.

    #388: `prospective_capable=True` fails closed unless the availability
    policy is OBSERVED or a conservative proxy safe boundary sits strictly
    before the cutoff. The frozen kickoff+4h proxy pilot is historical-only and
    cannot claim prospective readiness through the default boundary (which
    equals the cutoff).
    """

    required = {
        availability.label_available_column,
        availability.source_issue_column,
        availability.issue_year_column,
    }
    if availability.data_available_column is not None:
        required.add(availability.data_available_column)
    if not required.issubset(history):
        raise TemporalContractError("history lacks availability columns")
    if prospective_capable:
        if availability.policy_identity.startswith("PROXY_"):
            boundary = availability.proxy_safe_boundary_ts
            if boundary is None or not boundary < cutoff.cutoff_ts:
                raise TemporalContractError(
                    "prospective claim requires observed availability or a "
                    "preregistered conservative safe boundary strictly before cutoff"
                )
        elif not availability.policy_identity.startswith("OBSERVED_"):
            raise TemporalContractError(
                "prospective claim requires an observed or proxy availability policy"
            )
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
    admitted = admitted[admitted_mask].copy()
    # #388: target identity exclusion before any partition is derived.
    admitted, target_exclusion = _excluded_target_rows(admitted, cutoff, availability)
    eligible = admitted.copy()
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
    ledger, weight_meta = _weight_ledger(eligible, cutoff, availability, weighting_policy)
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
    margin_days = (
        cutoff.cutoff_ts - eligible[availability.label_available_column]
    ).dt.total_seconds().to_numpy(float) / 86_400
    if availability.data_available_column is not None:
        data_margin = (
            cutoff.cutoff_ts - eligible[availability.data_available_column]
        ).dt.total_seconds().to_numpy(float) / 86_400
        margin_days = np.minimum(margin_days, data_margin)
    receipt = LearningReceipt({
        "cutoff_identity": cutoff.identity,
        "cutoff_kind": cutoff.kind,
        "cutoff_target_identity": cutoff.target_identity,
        "cutoff_ts": cutoff.cutoff_ts.isoformat(),
        "availability_policy": {
            "identity": availability.policy_identity,
            "proxy_safe_boundary_ts": (
                availability.proxy_safe_boundary_ts.isoformat()
                if availability.proxy_safe_boundary_ts is not None
                else None
            ),
            "prospective_capable": prospective_capable,
        },
        "margin_to_cutoff_days": {
            "minimum": float(np.min(margin_days)),
            "maximum": float(np.max(margin_days)),
            "median": float(np.median(margin_days)),
        },
        "target_exclusion": target_exclusion,
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
            "mixture": weight_meta["mixture"],
            "issue_mass": dict(sorted(weight_meta["issue_mass"].items(), key=lambda item: str(item[0]))),
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