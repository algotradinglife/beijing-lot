"""Fail-closed chronological research for handicap-draw probability.

The module accepts only caller-supplied, immutable historical P1/P2 rows.  It
does not discover data, open SQLite, read odds, write files, calculate returns,
or make a selection.  A missing or late provenance clock blocks the entire
run, so settled outcomes can never be quietly repurposed as prediction input.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Iterable, Literal


Outcome = Literal["3", "1", "0"]
OUTCOMES: tuple[Outcome, Outcome, Outcome] = ("3", "1", "0")
DRAW: Outcome = "1"
_EPSILON = 1e-12


@dataclass(frozen=True)
class HistoricalP1P2Row:
    """One immutable, already-settled historical record.

    ``p1_probabilities`` is the frozen three-way baseline in ``3,1,0`` order.
    ``p2_lambda_*`` is the frozen input used solely for the G1 independent-
    Poisson score-distribution projection.  ``p1`` and ``p2`` names are
    deliberately descriptive input labels, not a claim about any current
    production artifact schema.
    """

    record_id: str
    issue_id: str
    match_id: str
    handicap: int
    p1_probabilities: tuple[float, float, float]
    p2_lambda_home: float
    p2_lambda_away: float
    outcome: Outcome
    p1_as_of: datetime
    p2_as_of: datetime
    decision_at: datetime
    sale_cutoff_at: datetime
    kickoff_at: datetime
    settled_at: datetime
    p1_sha256: str
    p2_sha256: str


@dataclass(frozen=True)
class ProjectionEligibility:
    eligible: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class LoopConfig:
    """Frozen small candidate set; values must be recorded before a run."""

    min_training_rows: int = 30
    blend_weights: tuple[float, ...] = (0.25, 0.50, 0.75)
    calibration_l2: float = 4.0
    calibration_iterations: int = 20


@dataclass(frozen=True)
class PredictionRow:
    record_id: str
    issue_id: str
    decision_at: datetime
    outcome: Outcome
    candidate: str
    probabilities: tuple[float, float, float]
    training_record_ids: tuple[str, ...]


@dataclass(frozen=True)
class CandidateSummary:
    candidate: str
    n: int
    binary_draw_brier: float
    binary_draw_log_loss: float
    three_way_brier: float
    three_way_log_loss: float
    draw_ece_10bin: float


@dataclass(frozen=True)
class LoopResult:
    eligibility: ProjectionEligibility
    predictions: tuple[PredictionRow, ...]
    summaries: tuple[CandidateSummary, ...]
    selection_diagnostic: tuple[CandidateSummary, ...]


def _utc(value: datetime, field: str, reasons: list[str]) -> datetime | None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        reasons.append(f"{field}_must_be_timezone_aware")
        return None
    return value.astimezone(timezone.utc)


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def validate_historical_rows(rows: Iterable[HistoricalP1P2Row]) -> ProjectionEligibility:
    """Require immutable P1/P2 pre-cutoff provenance for every row.

    The experiment is all-or-nothing: one malformed row makes the provided
    panel ineligible.  That avoids selectively retaining the rows whose
    timing happens to be convenient after looking at outcomes.
    """

    values = tuple(rows)
    reasons: list[str] = []
    if not values:
        reasons.append("no_historical_p1_p2_rows")
    seen: set[tuple[str, str]] = set()
    for row in values:
        identity = (row.issue_id, row.match_id)
        if identity in seen:
            reasons.append("duplicate_issue_match")
        seen.add(identity)
        clocks = {
            "p1_as_of": _utc(row.p1_as_of, "p1_as_of", reasons),
            "p2_as_of": _utc(row.p2_as_of, "p2_as_of", reasons),
            "decision_at": _utc(row.decision_at, "decision_at", reasons),
            "sale_cutoff_at": _utc(row.sale_cutoff_at, "sale_cutoff_at", reasons),
            "kickoff_at": _utc(row.kickoff_at, "kickoff_at", reasons),
            "settled_at": _utc(row.settled_at, "settled_at", reasons),
        }
        if all(value is not None for value in clocks.values()):
            p1_at = clocks["p1_as_of"]
            p2_at = clocks["p2_as_of"]
            decision_at = clocks["decision_at"]
            cutoff_at = clocks["sale_cutoff_at"]
            kickoff_at = clocks["kickoff_at"]
            settled_at = clocks["settled_at"]
            assert p1_at and p2_at and decision_at and cutoff_at and kickoff_at and settled_at
            if p1_at > decision_at or p2_at > decision_at:
                reasons.append("p1_or_p2_after_decision")
            if decision_at > cutoff_at or cutoff_at >= kickoff_at:
                reasons.append("decision_or_cutoff_not_pre_kickoff")
            if settled_at < kickoff_at:
                reasons.append("settlement_before_kickoff")
        if not row.record_id or not row.issue_id or not row.match_id:
            reasons.append("missing_record_identity")
        if row.outcome not in OUTCOMES:
            reasons.append("invalid_settled_handicap_outcome")
        if not isinstance(row.handicap, int):
            reasons.append("non_integer_handicap")
        if len(row.p1_probabilities) != 3 or any(
            not math.isfinite(probability) or probability < 0 for probability in row.p1_probabilities
        ):
            reasons.append("invalid_p1_probabilities")
        elif not math.isclose(sum(row.p1_probabilities), 1.0, abs_tol=1e-9):
            reasons.append("p1_probabilities_do_not_sum_to_one")
        if not all(math.isfinite(value) and value > 0 for value in (row.p2_lambda_home, row.p2_lambda_away)):
            reasons.append("invalid_p2_poisson_rates")
        if not _is_sha256(row.p1_sha256) or not _is_sha256(row.p2_sha256):
            reasons.append("missing_or_invalid_input_checksum")
    return ProjectionEligibility(not reasons, tuple(sorted(set(reasons))))


def _poisson_probability(goals: int, rate: float) -> float:
    return math.exp(-rate) * rate**goals / math.factorial(goals)


def independent_poisson_handicap_probabilities(
    lambda_home: float, lambda_away: float, handicap: int, *, max_goals: int = 30
) -> tuple[float, float, float]:
    """Project ``3,1,0`` from an independent-Poisson score distribution.

    The sum is rejected if the finite grid leaves material tail mass.  This is
    a probability projection only, not an odds, EV, or decision function.
    """

    if lambda_home <= 0 or lambda_away <= 0 or max_goals < 1:
        raise ValueError("Poisson rates and max_goals must be positive")
    probabilities = [0.0, 0.0, 0.0]
    total_mass = 0.0
    for home_goals in range(max_goals + 1):
        home_probability = _poisson_probability(home_goals, lambda_home)
        for away_goals in range(max_goals + 1):
            mass = home_probability * _poisson_probability(away_goals, lambda_away)
            total_mass += mass
            margin = home_goals - away_goals + handicap
            probabilities[0 if margin > 0 else 1 if margin == 0 else 2] += mass
    if 1.0 - total_mass > 1e-10:
        raise ValueError("independent-Poisson grid has material omitted tail mass")
    return tuple(value / total_mass for value in probabilities)  # type: ignore[return-value]


def _clip_probability(value: float) -> float:
    return min(max(value, _EPSILON), 1.0 - _EPSILON)


def _replace_draw_probability(
    probabilities: tuple[float, float, float], draw_probability: float
) -> tuple[float, float, float]:
    draw_probability = _clip_probability(draw_probability)
    non_draw = probabilities[0] + probabilities[2]
    if non_draw <= _EPSILON:
        return ((1.0 - draw_probability) / 2.0, draw_probability, (1.0 - draw_probability) / 2.0)
    scale = (1.0 - draw_probability) / non_draw
    return (probabilities[0] * scale, draw_probability, probabilities[2] * scale)


def _logit(probability: float) -> float:
    value = _clip_probability(probability)
    return math.log(value / (1.0 - value))


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exp_value = math.exp(value)
    return exp_value / (1.0 + exp_value)


def _fit_logit_calibrator(train: tuple[HistoricalP1P2Row, ...], config: LoopConfig) -> tuple[float, float]:
    """Fit a tiny L2-regularized logit map using prior settled rows only."""

    intercept, slope = 0.0, 1.0
    for _ in range(config.calibration_iterations):
        gradient_i = config.calibration_l2 * intercept
        gradient_s = config.calibration_l2 * (slope - 1.0)
        h_ii = config.calibration_l2
        h_is = 0.0
        h_ss = config.calibration_l2
        for row in train:
            g1_draw = independent_poisson_handicap_probabilities(
                row.p2_lambda_home, row.p2_lambda_away, row.handicap
            )[1]
            feature = _logit(g1_draw)
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


def _binary_brier(rows: tuple[HistoricalP1P2Row, ...], weight: float) -> float:
    errors = []
    for row in rows:
        g1_draw = independent_poisson_handicap_probabilities(
            row.p2_lambda_home, row.p2_lambda_away, row.handicap
        )[1]
        blended = weight * g1_draw + (1.0 - weight) * row.p1_probabilities[1]
        errors.append((blended - float(row.outcome == DRAW)) ** 2)
    return sum(errors) / len(errors)


def _summary(candidate: str, values: list[PredictionRow]) -> CandidateSummary:
    draw_errors = []
    draw_losses = []
    three_way_errors = []
    three_way_losses = []
    bins: list[list[tuple[float, int]]] = [[] for _ in range(10)]
    for row in values:
        probability = row.probabilities[1]
        observed_draw = int(row.outcome == DRAW)
        draw_errors.append((probability - observed_draw) ** 2)
        draw_losses.append(
            -(
                observed_draw * math.log(_clip_probability(probability))
                + (1 - observed_draw) * math.log(_clip_probability(1 - probability))
            )
        )
        outcome_index = OUTCOMES.index(row.outcome)
        three_way_errors.append(
            sum(
                (predicted - float(index == outcome_index)) ** 2
                for index, predicted in enumerate(row.probabilities)
            )
        )
        three_way_losses.append(-math.log(_clip_probability(row.probabilities[outcome_index])))
        bins[min(int(probability * 10), 9)].append((probability, observed_draw))
    ece = sum(
        len(bucket)
        * abs(
            sum(probability for probability, _ in bucket) / len(bucket)
            - sum(observed for _, observed in bucket) / len(bucket)
        )
        for bucket in bins
        if bucket
    ) / len(values)
    return CandidateSummary(
        candidate=candidate,
        n=len(values),
        binary_draw_brier=sum(draw_errors) / len(values),
        binary_draw_log_loss=sum(draw_losses) / len(values),
        three_way_brier=sum(three_way_errors) / len(values),
        three_way_log_loss=sum(three_way_losses) / len(values),
        draw_ece_10bin=ece,
    )


def run_chronological_loop(rows: Iterable[HistoricalP1P2Row], config: LoopConfig = LoopConfig()) -> LoopResult:
    """Evaluate baseline, G1 projection, and two pre-registered prior-only candidates."""

    values = tuple(sorted(rows, key=lambda row: (row.decision_at, row.issue_id, row.match_id, row.record_id)))
    eligibility = validate_historical_rows(values)
    if not eligibility.eligible:
        return LoopResult(eligibility, (), (), ())
    if (
        config.min_training_rows < 1
        or not config.blend_weights
        or any(not 0 <= weight <= 1 for weight in config.blend_weights)
    ):
        return LoopResult(ProjectionEligibility(False, ("invalid_preregistered_config",)), (), (), ())

    predictions: list[PredictionRow] = []
    selection_rows: list[PredictionRow] = []
    for test in values:
        train = tuple(row for row in values if row.settled_at < test.decision_at)
        g1 = independent_poisson_handicap_probabilities(
            test.p2_lambda_home, test.p2_lambda_away, test.handicap
        )
        predictions.extend(
            (
                PredictionRow(test.record_id, test.issue_id, test.decision_at, test.outcome, "p1_baseline", test.p1_probabilities, tuple()),
                PredictionRow(test.record_id, test.issue_id, test.decision_at, test.outcome, "g1_independent_poisson", g1, tuple()),
            )
        )
        if len(train) < config.min_training_rows:
            continue
        predictions.extend(
            (
                PredictionRow(
                    test.record_id,
                    test.issue_id,
                    test.decision_at,
                    test.outcome,
                    "p1_baseline_holdout",
                    test.p1_probabilities,
                    tuple(row.record_id for row in train),
                ),
                PredictionRow(
                    test.record_id,
                    test.issue_id,
                    test.decision_at,
                    test.outcome,
                    "g1_independent_poisson_holdout",
                    g1,
                    tuple(row.record_id for row in train),
                ),
            )
        )
        training_ids = tuple(row.record_id for row in train)
        intercept, slope = _fit_logit_calibrator(train, config)
        calibrated = _replace_draw_probability(g1, _sigmoid(intercept + slope * _logit(g1[1])))
        calibrated_row = PredictionRow(
            test.record_id,
            test.issue_id,
            test.decision_at,
            test.outcome,
            "g1_logit_calibrated",
            calibrated,
            training_ids,
        )
        predictions.append(calibrated_row)
        weight = min(config.blend_weights, key=lambda candidate: (_binary_brier(train, candidate), candidate))
        blended = tuple(weight * g1[index] + (1.0 - weight) * test.p1_probabilities[index] for index in range(3))
        blend_name = f"p1_g1_blend_w{int(round(weight * 100)):02d}"
        blend_row = PredictionRow(
            test.record_id,
            test.issue_id,
            test.decision_at,
            test.outcome,
            blend_name,
            blended,
            training_ids,
        )
        predictions.append(blend_row)
        candidates = (
            PredictionRow(
                test.record_id,
                test.issue_id,
                test.decision_at,
                test.outcome,
                "g1_independent_poisson",
                g1,
                training_ids,
            ),
            calibrated_row,
            blend_row,
        )
        selected = min(
            candidates,
            key=lambda candidate: (
                _training_candidate_brier(train, candidate.candidate, weight, config),
                candidate.candidate,
            ),
        )
        selection_rows.append(selected)

    by_candidate: dict[str, list[PredictionRow]] = {}
    for prediction in predictions:
        by_candidate.setdefault(prediction.candidate, []).append(prediction)
    summaries = tuple(_summary(candidate, records) for candidate, records in sorted(by_candidate.items()))
    selection_by_name: dict[str, list[PredictionRow]] = {}
    for prediction in selection_rows:
        selection_by_name.setdefault(prediction.candidate, []).append(prediction)
    selection = tuple(_summary(candidate, records) for candidate, records in sorted(selection_by_name.items()))
    return LoopResult(eligibility, tuple(predictions), summaries, selection)


def _training_candidate_brier(
    train: tuple[HistoricalP1P2Row, ...], candidate: str, blend_weight: float, config: LoopConfig
) -> float:
    if candidate == "g1_independent_poisson":
        return _binary_brier(train, 1.0)
    if candidate.startswith("p1_g1_blend"):
        return _binary_brier(train, blend_weight)
    intercept, slope = _fit_logit_calibrator(train, config)
    errors = []
    for row in train:
        g1_draw = independent_poisson_handicap_probabilities(
            row.p2_lambda_home, row.p2_lambda_away, row.handicap
        )[1]
        calibrated = _sigmoid(intercept + slope * _logit(g1_draw))
        errors.append((calibrated - float(row.outcome == DRAW)) ** 2)
    return sum(errors) / len(errors)


def build_checksummed_artifact(result: LoopResult, *, evidence: dict[str, str]) -> dict[str, object]:
    """Return a canonical, non-executable research artifact and its checksum.

    The caller owns any persistence.  Keeping this as a pure function avoids
    accidental writes to shared SQLite or a production artifact directory.
    """

    payload = {
        "status": "research_only_nonselectable_roi_unauthorized",
        "eligibility": asdict(result.eligibility),
        "evidence_sha256": dict(sorted(evidence.items())),
        "summaries": [asdict(summary) for summary in result.summaries],
        "selection_diagnostic": [asdict(summary) for summary in result.selection_diagnostic],
        "prediction_count": len(result.predictions),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return {"payload": payload, "payload_sha256": hashlib.sha256(encoded).hexdigest()}
