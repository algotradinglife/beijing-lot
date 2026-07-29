"""Auditable reference implementation of the supplied V7.7.1 score model.

This module intentionally has no dependency on the production decision chain.
It preserves the supplied strategy as an analysis reference: callers provide
one match's five odds surfaces and receive a 45-score distribution, diagnostics,
the ranked top 15, main top 3, and two auxiliary selections.

The source manual leaves two details underspecified.  This implementation makes
them deterministic and exposes them as documented interpretation choices:

* market probability assigned to an ``other`` bucket is distributed across its
  internal exact scores in proportion to the post-tail model distribution;
* in the 10%-20% large-score band, the large and small auxiliary pairs are
  compared by their combined Bayes score.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Iterable, Mapping

Score = tuple[int, int]

GRID: tuple[Score, ...] = tuple(
    (home, away) for home in range(9) for away in range(9) if home + away <= 8
)

EXPLICIT_HOME: frozenset[Score] = frozenset(
    {
        (1, 0),
        (2, 0),
        (2, 1),
        (3, 0),
        (3, 1),
        (3, 2),
        (4, 0),
        (4, 1),
        (4, 2),
        (5, 0),
        (5, 1),
        (5, 2),
    }
)
EXPLICIT_DRAW: frozenset[Score] = frozenset({(0, 0), (1, 1), (2, 2), (3, 3)})
EXPLICIT_AWAY: frozenset[Score] = frozenset(
    {
        (0, 1),
        (0, 2),
        (1, 2),
        (0, 3),
        (1, 3),
        (2, 3),
        (0, 4),
        (1, 4),
        (2, 4),
        (0, 5),
        (1, 5),
        (2, 5),
    }
)
EXPLICIT_SCORES: frozenset[Score] = EXPLICIT_HOME | EXPLICIT_DRAW | EXPLICIT_AWAY

OTHER_HOME = "胜其它"
OTHER_DRAW = "平其它"
OTHER_AWAY = "负其它"
OTHER_LABELS = (OTHER_HOME, OTHER_DRAW, OTHER_AWAY)


class AuxiliaryMode(str, Enum):
    """Reason attached to the two auxiliary selections."""

    LARGE = "大球"
    LARGE_WITH_FILL = "大球+补位"
    SMALL = "小球"


@dataclass(frozen=True)
class ThreeWayOdds:
    """Positive decimal odds ordered as home/draw/away."""

    home: float
    draw: float
    away: float

    def __post_init__(self) -> None:
        _require_positive((self.home, self.draw, self.away), "three-way odds")


@dataclass(frozen=True)
class MatchOdds:
    """Five market inputs required by the V7.7.1 strategy.

    ``handicap_line`` records the market direction for traceability.  As the
    manual requires, ``handicap.home`` is always used as the home cover price
    and is never inverted for a positive line.

    Score-odds keys may be ``(home, away)``, ``"2:1"``, ``"2-1"``, or one of
    ``胜其它/平其它/负其它``. Missing/non-positive prices may be represented by
    ``None`` and are excluded.
    """

    one_x_two: ThreeWayOdds
    handicap: ThreeWayOdds
    handicap_line: int
    half_full: ThreeWayOdds
    total_goals: tuple[float, float, float, float, float, float, float, float]
    score_odds: Mapping[Score | str, float | None]

    def __post_init__(self) -> None:
        if self.handicap_line not in {-2, -1, 1, 2}:
            raise ValueError("handicap_line must be one of -2, -1, 1, 2")
        if len(self.total_goals) != 8:
            raise ValueError("total_goals must contain prices for 0..7+")
        _require_positive(self.total_goals, "total-goals odds")
        if not _canonical_score_odds(self.score_odds):
            raise ValueError("score_odds must contain at least one positive price")


@dataclass(frozen=True)
class Candidate:
    score: Score
    probability: float
    bayes_score: float
    status: str

    @property
    def label(self) -> str:
        return f"{self.score[0]}-{self.score[1]}"


@dataclass(frozen=True)
class Diagnostics:
    mu: float
    mu_adjusted: float
    p_win: float
    p_half_full_home: float
    p_cover: float
    delta: float
    delta_half_full: float
    delta_spread_raw: float
    delta_spread_used: float
    delta_total: float
    delta_adjusted: float
    direction_conflict: bool
    lambda_home: float
    lambda_away: float
    zero_multiplier: float
    draw_hijack_applied: bool
    tail_multiplier: float
    tail_side: str
    score_odds_count: int
    market_weight: float
    p_big: float
    auxiliary_mode: AuxiliaryMode


@dataclass(frozen=True)
class PredictionResult:
    distribution: Mapping[Score, float]
    candidates: tuple[Candidate, ...]
    main: tuple[Candidate, ...]
    auxiliary: tuple[Candidate, ...]
    diagnostics: Diagnostics


def _require_positive(values: Iterable[float], name: str) -> None:
    if any(not math.isfinite(value) or value <= 0 for value in values):
        raise ValueError(f"{name} must all be finite and positive")


def _normalize(values: Mapping[Score, float]) -> dict[Score, float]:
    total = sum(values.values())
    if not math.isfinite(total) or total <= 0:
        raise ValueError("probability mass must be finite and positive")
    return {score: max(0.0, value) / total for score, value in values.items()}


def _devig(odds: ThreeWayOdds, reduction: float) -> tuple[float, float, float]:
    weights = (reduction / odds.home, reduction / odds.draw, reduction / odds.away)
    total = sum(weights)
    return tuple(weight / total for weight in weights)  # type: ignore[return-value]


def _parse_score_key(key: Score | str) -> Score | str:
    if isinstance(key, tuple):
        if len(key) != 2 or any(not isinstance(value, int) for value in key):
            raise ValueError(f"invalid score key: {key!r}")
        score = key
    else:
        text = key.strip()
        if text in OTHER_LABELS:
            return text
        separator = ":" if ":" in text else "-"
        pieces = text.split(separator)
        if len(pieces) != 2 or not all(piece.strip().isdigit() for piece in pieces):
            raise ValueError(f"invalid score key: {key!r}")
        score = (int(pieces[0]), int(pieces[1]))
    if score not in GRID:
        raise ValueError(f"score key is outside the 0..8, total<=8 grid: {score!r}")
    if score not in EXPLICIT_SCORES:
        raise ValueError(
            f"{score!r} belongs to an aggregate 'other' market bucket; "
            "use 胜其它/平其它/负其它"
        )
    return score


def _canonical_score_odds(
    score_odds: Mapping[Score | str, float | None],
) -> dict[Score | str, float]:
    canonical: dict[Score | str, float] = {}
    for raw_key, raw_value in score_odds.items():
        if raw_value is None or raw_value <= 0:
            continue
        if not math.isfinite(raw_value):
            raise ValueError(f"score odd for {raw_key!r} must be finite")
        key = _parse_score_key(raw_key)
        if key in canonical:
            raise ValueError(f"duplicate score-odds key after normalization: {key!r}")
        canonical[key] = float(raw_value)
    return canonical


def _poisson_mix(k: int, rate: float) -> float:
    def poisson(component_rate: float) -> float:
        return math.exp(-component_rate) * component_rate**k / math.factorial(k)

    return 0.88 * poisson(rate) + 0.12 * poisson(1.5 * rate)


def _other_bucket(label: str) -> tuple[Score, ...]:
    if label == OTHER_HOME:
        return tuple(
            score
            for score in GRID
            if score[0] > score[1] and score not in EXPLICIT_HOME
        )
    if label == OTHER_DRAW:
        return tuple(
            score
            for score in GRID
            if score[0] == score[1] and score not in EXPLICIT_DRAW
        )
    if label == OTHER_AWAY:
        return tuple(
            score
            for score in GRID
            if score[0] < score[1] and score not in EXPLICIT_AWAY
        )
    raise ValueError(f"unknown other-score label: {label}")


def _expand_market_distribution(
    market_labels: Mapping[Score | str, float],
    model: Mapping[Score, float],
) -> dict[Score, float]:
    """Expand three aggregate market labels onto the internal exact-score grid."""

    expanded = {score: 0.0 for score in GRID}
    for label, probability in market_labels.items():
        if isinstance(label, tuple):
            expanded[label] += probability
            continue
        bucket = _other_bucket(label)
        model_mass = sum(model[score] for score in bucket)
        if model_mass > 0:
            for score in bucket:
                expanded[score] += probability * model[score] / model_mass
        else:
            for score in bucket:
                expanded[score] += probability / len(bucket)
    return _normalize(expanded)


def _rank(distribution: Mapping[Score, float]) -> list[Score]:
    return sorted(GRID, key=lambda score: (-distribution[score], score[0], score[1]))


def _candidate(score: Score, probability: float, status: str) -> Candidate:
    return Candidate(
        score=score,
        probability=probability,
        bayes_score=probability * 10_000.0,
        status=status,
    )


def _large_auxiliary(
    remaining: list[Score],
    distribution: Mapping[Score, float],
) -> tuple[list[Score], AuxiliaryMode]:
    large = [score for score in remaining if sum(score) >= 4][:2]
    if len(large) < 2:
        raise ValueError("not enough large-score candidates for auxiliary board")
    global_fourth = remaining[0]
    if (
        distribution[large[1]] * 10_000.0
        <= distribution[global_fourth] * 10_000.0 - 100
    ):
        pair = [large[0], global_fourth]
        if pair[0] == pair[1]:
            pair[1] = large[1]
        return pair, AuxiliaryMode.LARGE_WITH_FILL
    return large, AuxiliaryMode.LARGE


def _small_auxiliary(remaining: list[Score]) -> list[Score]:
    small = [score for score in remaining if sum(score) <= 3][:2]
    if len(small) < 2:
        raise ValueError("not enough small-score candidates for auxiliary board")
    return small


def _auxiliary_board(
    ranked: list[Score],
    distribution: Mapping[Score, float],
) -> tuple[list[Score], AuxiliaryMode, float]:
    main = set(ranked[:3])
    remaining = [score for score in ranked if score not in main]
    p_big = sum(
        probability for score, probability in distribution.items() if sum(score) >= 4
    )
    large_pair, large_mode = _large_auxiliary(remaining, distribution)
    small_pair = _small_auxiliary(remaining)
    if p_big >= 0.20:
        return large_pair, large_mode, p_big
    if p_big <= 0.10:
        return small_pair, AuxiliaryMode.SMALL, p_big

    large_score = sum(distribution[score] for score in large_pair)
    small_score = sum(distribution[score] for score in small_pair)
    if large_score > small_score:
        return large_pair, large_mode, p_big
    return small_pair, AuxiliaryMode.SMALL, p_big


def predict(inputs: MatchOdds) -> PredictionResult:
    """Run the supplied V7.7.1 decision chain for one match."""

    # Steps 1-4: derive total-goal and directional parameters.
    total_goal_weights = [0.85 / odd for odd in inputs.total_goals]
    total_goal_weight_sum = sum(total_goal_weights)
    mu = (
        sum(goal * weight for goal, weight in enumerate(total_goal_weights))
        / total_goal_weight_sum
    )

    p_win, _p_draw, _p_loss = _devig(inputs.one_x_two, 0.92)
    delta = 0.8 * math.log(p_win / (1.0 - p_win))

    p_half_full_home, _p_half_full_draw, _p_half_full_away = _devig(
        inputs.half_full, 0.92
    )
    delta_half_full = 0.15 * math.tanh(2.0 * (p_half_full_home - 0.5))

    p_cover, _p_handicap_draw, _p_handicap_away = _devig(inputs.handicap, 0.92)
    delta_spread_raw = 0.08 * math.tanh(2.0 * (p_cover - 0.5))
    direction_conflict = abs(p_win - p_cover) > 0.15
    delta_spread_used = delta_spread_raw * (0.5 if direction_conflict else 1.0)
    delta_total = (
        delta_half_full
        if abs(delta_half_full) >= abs(delta_spread_used)
        else delta_spread_used
    )
    delta_adjusted = delta + delta_total
    mu_adjusted = mu * (1.0 + 0.15 * math.tanh(2.0 * (p_cover - 0.5)))
    lambda_home = max((mu_adjusted + delta_adjusted) / 2.0, 0.2)
    lambda_away = max((mu_adjusted - delta_adjusted) / 2.0, 0.2)

    # Steps 5-6: mixture-Poisson grid and implicit other-score aggregates.
    distribution = _normalize(
        {
            score: _poisson_mix(score[0], lambda_home)
            * _poisson_mix(score[1], lambda_away)
            for score in GRID
        }
    )

    # Step 7: dynamic zero correction.
    zero_multiplier = 1.0 + 0.15 * math.tanh(abs(delta_adjusted) / 2.0) * math.exp(
        -0.2 * mu
    )
    old_zero = distribution[(0, 0)]
    new_zero = old_zero * zero_multiplier
    if not 0 <= new_zero < 1:
        raise ValueError("dynamic zero correction produced invalid probability")
    nonzero_scale = (1.0 - new_zero) / (1.0 - old_zero)
    distribution = {
        score: (new_zero if score == (0, 0) else probability * nonzero_scale)
        for score, probability in distribution.items()
    }
    distribution = _normalize(distribution)

    # Step 7.5: draw hijack.
    draw_hijack_applied = inputs.one_x_two.draw <= 3.50
    if draw_hijack_applied:
        transfer = 0.0
        for donor in ((0, 0), (2, 0), (0, 2)):
            old = distribution[donor]
            distribution[donor] = old * 0.90
            transfer += old * 0.10
        distribution[(1, 1)] += transfer
        distribution = _normalize(distribution)

    # Step 8: strengthen the high-score tail for the stronger side and draws.
    lambda_high = max(lambda_home, lambda_away)
    if lambda_high < 1.5:
        tail_multiplier = 1.0
    elif lambda_high < 2.5:
        tail_multiplier = 1.0 + 0.15 * (lambda_high - 1.5)
    else:
        tail_multiplier = 1.15 + 0.10 * (lambda_high - 2.5)
    tail_multiplier = min(tail_multiplier, 1.40)
    tail_side = "home" if lambda_home >= lambda_away else "away"
    if tail_multiplier > 1.0:
        for score in GRID:
            strong_side = (
                score[0] > score[1] if tail_side == "home" else score[1] > score[0]
            )
            if sum(score) >= 4 and (strong_side or score[0] == score[1]):
                distribution[score] *= tail_multiplier
        distribution = _normalize(distribution)

    # Step 9: blend the score-price surface.
    canonical_score_odds = _canonical_score_odds(inputs.score_odds)
    market_raw = {key: 0.78 / odd for key, odd in canonical_score_odds.items()}
    market_total = sum(market_raw.values())
    market_labels = {key: value / market_total for key, value in market_raw.items()}
    market_distribution = _expand_market_distribution(market_labels, distribution)
    score_odds_count = min(len(canonical_score_odds), 15)
    base_weight = 0.40 + 0.25 * (1.0 - math.exp(-score_odds_count / 8.0))
    decay = 0.15 * math.tanh(2.0 * abs(delta_total))
    market_weight = max(0.20, base_weight - decay)
    distribution = _normalize(
        {
            score: (1.0 - market_weight) * distribution[score]
            + market_weight * market_distribution[score]
            for score in GRID
        }
    )

    # Step 10: final empirical corrections.
    if inputs.half_full.home + inputs.half_full.away < inputs.half_full.draw:
        distribution[(1, 1)] *= 0.92
        distribution[(2, 0)] *= 1.06
        distribution[(0, 2)] *= 1.06
    if mu <= 2.5 and abs(delta) >= 0.4:
        distribution[(0, 1)] *= 1.05
        distribution[(1, 0)] *= 1.05
        distribution[(1, 1)] *= 0.95
    distribution = _normalize(distribution)

    # Step 11: rank and form the main/auxiliary boards.
    ranked = _rank(distribution)
    auxiliary_scores, auxiliary_mode, p_big = _auxiliary_board(ranked, distribution)
    main_scores = ranked[:3]
    status: dict[Score, str] = {score: "淘汰" for score in ranked[:15]}
    for index, score in enumerate(main_scores, start=1):
        status[score] = f"主榜TOP{index}"
    for score in auxiliary_scores:
        status[score] = auxiliary_mode.value

    candidates = tuple(
        _candidate(score, distribution[score], status.get(score, "淘汰"))
        for score in ranked[:15]
    )
    main = tuple(
        _candidate(score, distribution[score], f"主榜TOP{index}")
        for index, score in enumerate(main_scores, 1)
    )
    auxiliary = tuple(
        _candidate(score, distribution[score], auxiliary_mode.value)
        for score in auxiliary_scores
    )
    diagnostics = Diagnostics(
        mu=mu,
        mu_adjusted=mu_adjusted,
        p_win=p_win,
        p_half_full_home=p_half_full_home,
        p_cover=p_cover,
        delta=delta,
        delta_half_full=delta_half_full,
        delta_spread_raw=delta_spread_raw,
        delta_spread_used=delta_spread_used,
        delta_total=delta_total,
        delta_adjusted=delta_adjusted,
        direction_conflict=direction_conflict,
        lambda_home=lambda_home,
        lambda_away=lambda_away,
        zero_multiplier=zero_multiplier,
        draw_hijack_applied=draw_hijack_applied,
        tail_multiplier=tail_multiplier,
        tail_side=tail_side,
        score_odds_count=score_odds_count,
        market_weight=market_weight,
        p_big=p_big,
        auxiliary_mode=auxiliary_mode,
    )
    return PredictionResult(
        distribution=MappingProxyType(distribution),
        candidates=candidates,
        main=main,
        auxiliary=auxiliary,
        diagnostics=diagnostics,
    )
