"""Versioned schema contract for the #203 causal tensor package."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Final


CONTRACT_VERSION: Final = "bj203-causal-tensor-v2"
OUTCOME_ORDER: Final = ("3", "1", "0")
SOURCE_TIMEZONE: Final = "Asia/Hong_Kong"
HELDOUT_2026_ISSUES: Final = (
    "26011", "26012", "26013", "26014", "26015", "26016", "26017",
    "26018", "26019", "26021", "26022", "26023", "26024", "26025",
    "26026", "26031", "26032", "26033", "26034", "26035", "26036",
    "26037", "26038", "26039", "26041", "26042", "26043", "26044",
    "26045", "26046", "26047", "26048", "26049", "26051", "26052",
    "26053", "26054", "26055", "26056", "26057", "26058", "26061",
    "26062", "26063", "26064", "26065", "26066", "26067", "26068",
    "26069",
)
HELDOUT_ISSUES: Final = ("25041", "25042", *HELDOUT_2026_ISSUES)
HELDOUT_POLICY: Final = (
    "Whole-issue embargo beginning with 25041, the first canonical issue whose "
    "eligible match window begins in 2025-04, through the complete frozen local "
    "post-boundary inventory ending at 26069.  The 2026 extension is identity "
    "only; no held-out result, final-SP or settlement row is emitted."
)
DATABASE_SHA256: Final = (
    "7f62079b18b3c028884da92aa8393f5b198246c9d7c32cd0b401562a055c5d6f"
)

FORBIDDEN_INFERENCE_PARTS: Final = (
    "result",
    "score",
    "fthg",
    "ftag",
    "final_sp",
    "official_sp",
    "winning_sp",
    "settlement",
    "payout",
    "tax",
    "roi",
    "hit",
    "profit",
)


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    dtype: str
    minimum: float | None
    maximum: float | None
    source: str
    timing_rule: str
    admissible_use: str
    missingness: str


_CUTOFF = "source observation is available at or before feature_cutoff_ts_utc"
_IDENTITY = "immutable identity known before the issue cutoff"
_ONE_HOUR = (
    "1h snapshot cutoff (kickoff_ts_utc - 1h) is at or before "
    "feature_cutoff_ts_utc"
)
_TEN_HOUR = (
    "10h predictor input cutoff (kickoff_ts_utc - 10h) is at or before "
    "feature_cutoff_ts_utc"
)

FEATURE_SPECS: Final = (
    FeatureSpec(
        "outcome_code_numeric", "float32", 0, 3, "canonical outcome axis",
        _IDENTITY, "inference", "never missing",
    ),
    FeatureSpec(
        "calibrated_market_probability", "float32", 0, 1,
        "#190 calibrated match-safe 1h market estimator", _ONE_HOUR, "inference",
        "masked where unavailable or the 1h snapshot follows issue cutoff",
    ),
    FeatureSpec(
        "devig_euro_probability", "float32", 0, 1,
        "1h EURO consensus reciprocal odds normalized within match", _ONE_HOUR,
        "inference", "masked unless all odds are valid and cutoff-safe",
    ),
    FeatureSpec(
        "euro_1h_odds", "float32", 1, None, "1h EURO consensus", _ONE_HOUR,
        "inference", "masked unless finite, >1 and cutoff-safe",
    ),
    FeatureSpec(
        "fundamental_probability", "float32", 0, 1,
        "#190 independent T1 score-distribution estimator", _CUTOFF, "inference",
        "masked where the target-safe estimator is unavailable",
    ),
    FeatureSpec(
        "probability_residual", "float32", -1, 1,
        "#190 calibrated probability minus its frozen target-safe consensus_p "
        "baseline (not package devig_euro_probability)",
        _ONE_HOUR, "inference",
        "masked where calibrated or frozen consensus input is unavailable/cutoff-late",
    ),
    FeatureSpec(
        "probability_residual_z", "float32", None, None,
        "#190 calibrated residual standardized by frozen uncertainty", _ONE_HOUR,
        "inference", "masked where unavailable or the 1h snapshot is cutoff-late",
    ),
    FeatureSpec(
        "predicted_final_sp", "float32", 1, None,
        "#90 chronological deployed 10h SP predictor", _TEN_HOUR, "inference",
        "masked where unavailable, outside SP domain or cutoff-late",
    ),
    FeatureSpec(
        "bj_sp_snapshot", "float32", 1, None,
        "timestamped pre-event Beijing SP snapshot", _CUTOFF, "inference",
        "all masked: historical source has no trustworthy snapshot timestamp",
    ),
    FeatureSpec(
        "bj_sp_snapshot_age_minutes", "float32", 0, None,
        "cutoff minus timestamped Beijing SP observation", _CUTOFF, "inference",
        "all masked with bj_sp_snapshot",
    ),
    FeatureSpec(
        "native_handicap_line", "float32", -3, 3,
        "native Beijing handicap normalized by accepted source", _IDENTITY,
        "inference", "masked and row retained when native line is absent",
    ),
    FeatureSpec(
        "line_residual_mu", "float32", None, None,
        "#190 expected raw margin plus native line", _CUTOFF, "inference",
        "masked where line or T1 distribution is unavailable",
    ),
    FeatureSpec(
        "line_residual_z", "float32", None, None,
        "#190 line residual standardized by frozen uncertainty", _CUTOFF,
        "inference", "masked where line residual is unavailable",
    ),
    FeatureSpec(
        "market_uncertainty", "float32", 0, None,
        "#190 frozen 1h market uncertainty proxy", _ONE_HOUR, "inference",
        "masked where unavailable or the 1h snapshot is cutoff-late",
    ),
    FeatureSpec(
        "market_signature_breadth", "float32", 0, None,
        "deterministic sorted dictionary index of #190 1h breadth bucket", _ONE_HOUR,
        "inference", "masked where unavailable or the 1h snapshot is cutoff-late",
    ),
    FeatureSpec(
        "market_signature_dispersion", "float32", 0, None,
        "ordinal encoding of #190 1h D_LOW/D_MID/D_HIGH", _ONE_HOUR, "inference",
        "masked for unknown or cutoff-late dispersion strata",
    ),
    FeatureSpec(
        "history_training_rows_log1p", "float32", 0, None,
        "log1p of #190 strictly prior training-row count", _CUTOFF, "inference",
        "masked where chronological model state is unavailable",
    ),
    FeatureSpec(
        "min_history_n_log1p", "float32", 0, None,
        "log1p of minimum home/away prior history depth", _CUTOFF, "inference",
        "masked where team history state is unavailable",
    ),
    FeatureSpec(
        "league_index", "float32", 0, None,
        "deterministic sorted league dictionary", _IDENTITY, "inference",
        "masked only for a blank league",
    ),
    FeatureSpec(
        "home_team_index", "float32", 0, None,
        "deterministic sorted team dictionary", _IDENTITY, "inference",
        "masked only for a blank home team identity",
    ),
    FeatureSpec(
        "away_team_index", "float32", 0, None,
        "deterministic sorted team dictionary", _IDENTITY, "inference",
        "masked only for a blank away team identity",
    ),
    FeatureSpec(
        "kickoff_delay_hours", "float32", 0, None,
        "kickoff_ts_utc minus issue feature_cutoff_ts_utc", _IDENTITY,
        "inference", "masked if either timestamp is unavailable",
    ),
    FeatureSpec(
        "match_position_fraction", "float32", 0, 1,
        "zero-based deterministic match order divided by max(J_i-1,1)",
        _IDENTITY, "inference", "never missing",
    ),
    FeatureSpec(
        "calendar_year", "float32", 2018, 2026,
        "canonical reporting year", _IDENTITY, "inference", "never missing",
    ),
)

FEATURE_NAMES: Final = tuple(spec.name for spec in FEATURE_SPECS)


def cell_join_key(issue_instance: str, match_id: str, outcome_code: str) -> str:
    if outcome_code not in OUTCOME_ORDER:
        raise ValueError(f"unsupported outcome code: {outcome_code}")
    payload = (
        f"{CONTRACT_VERSION}|{issue_instance}|{match_id}|{outcome_code}"
    ).encode("utf-8")
    return sha256(payload).hexdigest()


def forbidden_inference_names(names: object) -> list[str]:
    """Return field names whose normalized spelling crosses the outcome boundary."""

    failures: list[str] = []
    for value in names:  # type: ignore[union-attr]
        name = str(value).lower()
        # Predicted final SP is a preregistered pre-event feature.  Only this
        # exact contract field is exempt; observed/final settlement SP remains
        # forbidden everywhere in the inference namespace.
        if name in {
            "predicted_final_sp",
            "t1_score_estimator_identity_sha256",
        }:
            continue
        if any(part in name for part in FORBIDDEN_INFERENCE_PARTS):
            failures.append(str(value))
    return sorted(failures)
