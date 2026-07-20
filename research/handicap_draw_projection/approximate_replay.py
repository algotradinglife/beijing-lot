"""Issue-chronological, proxy-only handicap-draw probability replay.

This module deliberately does *not* assert the stricter ``HistoricalP1P2Row``
clock contract used by :mod:`research.handicap_draw_projection.loop`.  It is
for reconstruction evidence whose reliable ordering is the issue sequence,
not a per-row frozen decision timestamp.  It has no I/O, odds, payout,
ticket, selection, or execution integration.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from typing import Iterable, Literal


Outcome = Literal["3", "1", "0"]
OUTCOMES: tuple[Outcome, Outcome, Outcome] = ("3", "1", "0")
DRAW: Outcome = "1"
_EPSILON = 1e-12


@dataclass(frozen=True)
class ApproximateReplayRow:
    """A settled row from the permitted reconstructed score-margin evidence."""

    issue_id: str
    match_id: str
    match_index: int
    baseline_probabilities: tuple[float, float, float]
    g1_probabilities: tuple[float, float, float]
    outcome: Outcome


@dataclass(frozen=True)
class ApproximateReplayConfig:
    """Pre-registered small candidate set; alter only in a new experiment."""

    min_training_issues: int = 20
    min_training_rows: int = 5_000
    blend_weights: tuple[float, ...] = (0.25, 0.50, 0.75)
    calibration_l2: float = 4.0
    calibration_iterations: int = 4
    refit_interval_issues: int = 10
    retain_common_predictions: bool = True


@dataclass(frozen=True)
class ReplayEligibility:
    eligible: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ApproximatePrediction:
    issue_id: str
    match_id: str
    match_index: int
    outcome: Outcome
    candidate: str
    probabilities: tuple[float, float, float]
    training_issue_ids: tuple[str, ...]
    blend_weight: float | None = None


@dataclass(frozen=True)
class ProperScoreSummary:
    candidate: str
    n: int
    binary_draw_brier: float
    binary_draw_log_loss: float
    three_way_brier: float
    three_way_log_loss: float
    draw_ece_10bin: float


@dataclass(frozen=True)
class ApproximateReplayResult:
    eligibility: ReplayEligibility
    all_panel_summaries: tuple[ProperScoreSummary, ...]
    common_cohort_summaries: tuple[ProperScoreSummary, ...]
    common_cohort_predictions: tuple[ApproximatePrediction, ...]


def _issue_key(issue_id: str) -> int:
    if not issue_id.isdigit():
        raise ValueError("issue_id_must_be_numeric_for_proxy_chronology")
    return int(issue_id)


def _valid_probabilities(values: tuple[float, float, float]) -> bool:
    return all(math.isfinite(value) and value >= 0 for value in values) and math.isclose(
        sum(values), 1.0, abs_tol=1e-9
    )


def validate_approximate_rows(rows: Iterable[ApproximateReplayRow]) -> ReplayEligibility:
    """Validate identities and probabilities without inventing missing clocks."""

    values = tuple(rows)
    reasons: list[str] = []
    if not values:
        reasons.append("no_proxy_rows")
    seen: set[tuple[str, int]] = set()
    for row in values:
        identity = (row.issue_id, row.match_index)
        if identity in seen:
            reasons.append("duplicate_issue_match_index")
        seen.add(identity)
        try:
            _issue_key(row.issue_id)
        except ValueError:
            reasons.append("non_numeric_issue_proxy_clock")
        if not row.match_id or row.match_index < 1:
            reasons.append("invalid_match_identity")
        if row.outcome not in OUTCOMES:
            reasons.append("invalid_settled_handicap_outcome")
        if not _valid_probabilities(row.baseline_probabilities):
            reasons.append("invalid_baseline_probabilities")
        if not _valid_probabilities(row.g1_probabilities):
            reasons.append("invalid_g1_probabilities")
    return ReplayEligibility(not reasons, tuple(sorted(set(reasons))))


def _clip(value: float) -> float:
    return min(max(value, _EPSILON), 1.0 - _EPSILON)


def _logit(value: float) -> float:
    value = _clip(value)
    return math.log(value / (1.0 - value))


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exponent = math.exp(value)
    return exponent / (1.0 + exponent)


def _replace_draw_probability(
    probabilities: tuple[float, float, float], draw_probability: float
) -> tuple[float, float, float]:
    """Calibrate only draw mass and retain the G1 win/loss ratio."""

    draw_probability = _clip(draw_probability)
    non_draw = probabilities[0] + probabilities[2]
    if non_draw <= _EPSILON:
        return ((1.0 - draw_probability) / 2.0, draw_probability, (1.0 - draw_probability) / 2.0)
    scale = (1.0 - draw_probability) / non_draw
    return probabilities[0] * scale, draw_probability, probabilities[2] * scale


def _fit_g1_draw_calibrator(
    train: tuple[ApproximateReplayRow, ...], config: ApproximateReplayConfig
) -> tuple[float, float]:
    """Fit the pre-registered L2 logistic map using only earlier issues."""

    intercept, slope = 0.0, 1.0
    for _ in range(config.calibration_iterations):
        gradient_i = config.calibration_l2 * intercept
        gradient_s = config.calibration_l2 * (slope - 1.0)
        h_ii = config.calibration_l2
        h_is = 0.0
        h_ss = config.calibration_l2
        for row in train:
            feature = _logit(row.g1_probabilities[1])
            fitted = _sigmoid(intercept + slope * feature)
            residual = fitted - float(row.outcome == DRAW)
            curvature = fitted * (1.0 - fitted)
            gradient_i += residual
            gradient_s += residual * feature
            h_ii += curvature
            h_is += curvature * feature
            h_ss += curvature * feature * feature
        determinant = h_ii * h_ss - h_is * h_is
        if determinant <= _EPSILON:
            break
        delta_i = (h_ss * gradient_i - h_is * gradient_s) / determinant
        delta_s = (-h_is * gradient_i + h_ii * gradient_s) / determinant
        intercept -= delta_i
        slope -= delta_s
        if max(abs(delta_i), abs(delta_s)) < 1e-8:
            break
    return intercept, slope


def _draw_brier(rows: tuple[ApproximateReplayRow, ...], weight: float) -> float:
    return sum(
        (
            weight * row.g1_probabilities[1]
            + (1.0 - weight) * row.baseline_probabilities[1]
            - float(row.outcome == DRAW)
        )
        ** 2
        for row in rows
    ) / len(rows)


def _select_preregistered_blend_weight(
    train: tuple[ApproximateReplayRow, ...], config: ApproximateReplayConfig
) -> float:
    """Use the declared grid and deterministic tie-break; this is not a bet selection."""

    return min(config.blend_weights, key=lambda weight: (_draw_brier(train, weight), weight))


class _SummaryAccumulator:
    """Streaming proper-score accumulator used to avoid retaining a large panel."""

    def __init__(self, candidate: str) -> None:
        self.candidate = candidate
        self.n = 0
        self.draw_error = 0.0
        self.draw_loss = 0.0
        self.three_way_error = 0.0
        self.three_way_loss = 0.0
        self.bins = [[0, 0.0, 0] for _ in range(10)]

    def add(self, prediction: ApproximatePrediction) -> None:
        draw_probability = prediction.probabilities[1]
        observed_draw = int(prediction.outcome == DRAW)
        self.n += 1
        self.draw_error += (draw_probability - observed_draw) ** 2
        self.draw_loss += (
            -(
                observed_draw * math.log(_clip(draw_probability))
                + (1 - observed_draw) * math.log(_clip(1.0 - draw_probability))
            )
        )
        outcome_index = OUTCOMES.index(prediction.outcome)
        self.three_way_error += sum(
            (probability - float(index == outcome_index)) ** 2
            for index, probability in enumerate(prediction.probabilities)
        )
        self.three_way_loss += -math.log(_clip(prediction.probabilities[outcome_index]))
        bucket = self.bins[min(int(draw_probability * 10), 9)]
        bucket[0] += 1
        bucket[1] += draw_probability
        bucket[2] += observed_draw

    def summary(self) -> ProperScoreSummary:
        ece = sum(
            count * abs(probability_total / count - observed_total / count)
            for count, probability_total, observed_total in self.bins
            if count
        ) / self.n
        return ProperScoreSummary(
            candidate=self.candidate,
            n=self.n,
            binary_draw_brier=self.draw_error / self.n,
            binary_draw_log_loss=self.draw_loss / self.n,
            three_way_brier=self.three_way_error / self.n,
            three_way_log_loss=self.three_way_loss / self.n,
            draw_ece_10bin=ece,
        )


def summarize_predictions(predictions: Iterable[ApproximatePrediction]) -> tuple[ProperScoreSummary, ...]:
    grouped: dict[str, _SummaryAccumulator] = {}
    for prediction in predictions:
        grouped.setdefault(prediction.candidate, _SummaryAccumulator(prediction.candidate)).add(prediction)
    return tuple(accumulator.summary() for _, accumulator in sorted(grouped.items()))


def _predict_candidates(
    test: ApproximateReplayRow,
    train_issue_ids: tuple[str, ...],
    intercept: float,
    slope: float,
    weight: float,
) -> tuple[ApproximatePrediction, ...]:
    calibrated = _replace_draw_probability(
        test.g1_probabilities, _sigmoid(intercept + slope * _logit(test.g1_probabilities[1]))
    )
    blended = tuple(
        weight * test.g1_probabilities[index] + (1.0 - weight) * test.baseline_probabilities[index]
        for index in range(3)
    )
    common = dict(
        issue_id=test.issue_id,
        match_id=test.match_id,
        match_index=test.match_index,
        outcome=test.outcome,
        training_issue_ids=train_issue_ids,
    )
    return (
        ApproximatePrediction(candidate="baseline_handicap_probability", probabilities=test.baseline_probabilities, **common),
        ApproximatePrediction(candidate="g1_score_projection", probabilities=test.g1_probabilities, **common),
        ApproximatePrediction(candidate="g1_logit_calibrated_draw", probabilities=calibrated, **common),
        ApproximatePrediction(
            candidate="baseline_g1_chronological_blend",
            probabilities=blended,
            blend_weight=weight,
            **common,
        ),
    )


def run_approximate_issue_replay(
    rows: Iterable[ApproximateReplayRow], config: ApproximateReplayConfig = ApproximateReplayConfig()
) -> ApproximateReplayResult:
    """Run a strictly earlier-*issue* walk-forward comparison.

    The raw baseline and G1 summaries use every eligible row.  The common
    cohort compares all four candidates only after the pre-registered warm-up;
    no outcome from the target issue is in either fitted candidate's training
    data.
    """

    values = tuple(sorted(rows, key=lambda row: (_issue_key(row.issue_id), row.match_index, row.match_id)))
    eligibility = validate_approximate_rows(values)
    if not eligibility.eligible:
        return ApproximateReplayResult(eligibility, (), (), ())
    if (
        config.min_training_issues < 1
        or config.min_training_rows < 1
        or config.refit_interval_issues < 1
        or not config.blend_weights
        or any(not 0.0 <= weight <= 1.0 for weight in config.blend_weights)
    ):
        return ApproximateReplayResult(
            ReplayEligibility(False, ("invalid_preregistered_config",)), (), (), ()
        )

    by_issue: dict[str, list[ApproximateReplayRow]] = {}
    for row in values:
        by_issue.setdefault(row.issue_id, []).append(row)
    ordered_issue_ids = tuple(sorted(by_issue, key=_issue_key))
    raw_accumulators: dict[str, _SummaryAccumulator] = {}
    common_accumulators: dict[str, _SummaryAccumulator] = {}
    common_predictions: list[ApproximatePrediction] = []
    train: list[ApproximateReplayRow] = []
    prior_issue_ids: list[str] = []
    fitted_parameters: tuple[float, float, float, tuple[str, ...]] | None = None
    for issue_id in ordered_issue_ids:
        tests = by_issue[issue_id]
        for test in tests:
            baseline = ApproximatePrediction(
                test.issue_id, test.match_id, test.match_index, test.outcome,
                "baseline_handicap_probability", test.baseline_probabilities, (),
            )
            g1 = ApproximatePrediction(
                test.issue_id, test.match_id, test.match_index, test.outcome,
                "g1_score_projection", test.g1_probabilities, (),
            )
            raw_accumulators.setdefault(baseline.candidate, _SummaryAccumulator(baseline.candidate)).add(baseline)
            raw_accumulators.setdefault(g1.candidate, _SummaryAccumulator(g1.candidate)).add(g1)
        if len(prior_issue_ids) >= config.min_training_issues and len(train) >= config.min_training_rows:
            if fitted_parameters is None or len(prior_issue_ids) % config.refit_interval_issues == 0:
                frozen_train = tuple(train)
                frozen_issue_ids = tuple(prior_issue_ids)
                fitted_parameters = (
                    *_fit_g1_draw_calibrator(frozen_train, config),
                    _select_preregistered_blend_weight(frozen_train, config),
                    frozen_issue_ids,
                )
            assert fitted_parameters is not None
            intercept, slope, weight, frozen_issue_ids = fitted_parameters
            for test in tests:
                candidates = _predict_candidates(test, frozen_issue_ids, intercept, slope, weight)
                for candidate in candidates:
                    common_accumulators.setdefault(
                        candidate.candidate, _SummaryAccumulator(candidate.candidate)
                    ).add(candidate)
                if config.retain_common_predictions:
                    common_predictions.extend(candidates)
        train.extend(tests)
        prior_issue_ids.append(issue_id)
    return ApproximateReplayResult(
        eligibility,
        tuple(accumulator.summary() for _, accumulator in sorted(raw_accumulators.items())),
        tuple(accumulator.summary() for _, accumulator in sorted(common_accumulators.items())),
        tuple(common_predictions),
    )


def fit_final_proxy_candidates(
    historical_rows: Iterable[ApproximateReplayRow],
    diagnostic_rows: Iterable[ApproximateReplayRow],
    config: ApproximateReplayConfig = ApproximateReplayConfig(),
) -> tuple[ApproximatePrediction, ...]:
    """Fit once on historical rows and score an explicitly untouched diagnostic."""

    historical = tuple(historical_rows)
    diagnostic = tuple(diagnostic_rows)
    eligibility = validate_approximate_rows(historical)
    diagnostic_eligibility = validate_approximate_rows(diagnostic)
    if not eligibility.eligible or not diagnostic_eligibility.eligible:
        raise ValueError("ineligible_proxy_rows")
    historical_issues = {row.issue_id for row in historical}
    if historical_issues.intersection(row.issue_id for row in diagnostic):
        raise ValueError("diagnostic_issue_overlaps_historical_training")
    ordered_historical_issues = tuple(sorted(historical_issues, key=_issue_key))
    if len(ordered_historical_issues) < config.min_training_issues or len(historical) < config.min_training_rows:
        raise ValueError("insufficient_historical_proxy_training")
    train = tuple(sorted(historical, key=lambda row: (_issue_key(row.issue_id), row.match_index, row.match_id)))
    intercept, slope = _fit_g1_draw_calibrator(train, config)
    weight = _select_preregistered_blend_weight(train, config)
    predictions: list[ApproximatePrediction] = []
    for row in sorted(diagnostic, key=lambda item: (_issue_key(item.issue_id), item.match_index, item.match_id)):
        predictions.extend(_predict_candidates(row, ordered_historical_issues, intercept, slope, weight))
    return tuple(predictions)


def build_checksummed_approximate_artifact(
    result: ApproximateReplayResult, *, evidence: dict[str, str], config: ApproximateReplayConfig
) -> dict[str, object]:
    """Create a canonical, non-executable, non-selectable evidence payload."""

    payload = {
        "status": "research_only_approximate_non_executable_non_selectable_roi_unauthorized",
        "chronology": "strict_numeric_issue_sequence_proxy_not_p1_p2_clock_contract",
        "eligibility": asdict(result.eligibility),
        "pre_registered_config": asdict(config),
        "evidence_sha256": dict(sorted(evidence.items())),
        "all_panel_summaries": [asdict(summary) for summary in result.all_panel_summaries],
        "common_cohort_summaries": [asdict(summary) for summary in result.common_cohort_summaries],
        "common_cohort_prediction_count": len(result.common_cohort_predictions),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return {"payload": payload, "payload_sha256": hashlib.sha256(encoded).hexdigest()}
