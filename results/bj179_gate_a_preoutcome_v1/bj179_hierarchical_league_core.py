#!/usr/bin/env python3
"""Outcome-safe hierarchical league-regime primitives for Issue #179."""

from __future__ import annotations

import copy
import math
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field


CODES = ("3", "1", "0")
FAMILY_WEIGHTS = {
    "BASE_SEASON": 0.25,
    "GOAL_HANDICAP": 0.20,
    "PRICING_CALIBRATION": 0.35,
    "LIQUIDITY_DRIFT": 0.20,
}


def finite(value: object, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def normalize(values: Sequence[float]) -> tuple[float, float, float]:
    clipped = [max(1e-9, finite(value)) for value in values]
    total = sum(clipped)
    return tuple(value / total for value in clipped)  # type: ignore[return-value]


def no_vig(odds: Sequence[object]) -> tuple[float, float, float] | None:
    parsed = [finite(value) for value in odds]
    if any(value <= 1.0 for value in parsed):
        return None
    return normalize([1.0 / value for value in parsed])


def handicap_result(home_goals: object, away_goals: object, line: object) -> str | None:
    try:
        margin = float(home_goals) + float(line) - float(away_goals)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(margin):
        return None
    return "3" if margin > 1e-9 else "0" if margin < -1e-9 else "1"


def empirical(
    counts: Mapping[str, float], prior: Sequence[float], alpha: float
) -> tuple[float, float, float]:
    total = sum(float(counts.get(code, 0.0)) for code in CODES)
    if not total:
        return tuple(prior)  # type: ignore[return-value]
    return normalize(
        [
            float(counts.get(code, 0.0)) + alpha * prior[index]
            for index, code in enumerate(CODES)
        ]
    )


def log_pool(
    vectors: Mapping[str, Sequence[float]], excluded: str | None = None
) -> tuple[float, float, float]:
    weights = {
        name: value for name, value in FAMILY_WEIGHTS.items() if name != excluded
    }
    total = sum(weights.values())
    return normalize(
        [
            math.exp(
                sum(
                    (weight / total) * math.log(max(1e-12, vectors[name][index]))
                    for name, weight in weights.items()
                )
            )
            for index in range(3)
        ]
    )


def line_bucket(value: object, prefix: str, lower: float, upper: float) -> str:
    parsed = min(upper, max(lower, finite(value)))
    rounded = round(parsed * 4.0) / 4.0
    return f"{prefix}_{rounded:+.2f}"


def handicap_bucket(value: object) -> str:
    if value in (None, ""):
        return "H_MISSING"
    return line_bucket(value, "H", -3.0, 3.0)


def total_bucket(value: object) -> str:
    if value in (None, ""):
        return "T_MISSING"
    return line_bucket(value, "T", 1.5, 4.5)


def mass_bucket(probabilities: Sequence[float]) -> str:
    value = max(probabilities)
    return (
        "M_LT35"
        if value < 0.35
        else "M_35_40"
        if value < 0.40
        else "M_40_45"
        if value < 0.45
        else "M_45_55"
        if value < 0.55
        else "M_GE55"
    )


def movement(left: object, right: object, tolerance: float) -> str:
    if left in (None, "") or right in (None, ""):
        return "MISSING"
    delta = finite(right) - finite(left)
    return "DOWN" if delta < -tolerance else "UP" if delta > tolerance else "FLAT"


def market_signature(row: Mapping[str, object]) -> dict[str, str]:
    breadth_values = [
        int(finite(row.get("euro_1h_n"))),
        int(finite(row.get("asian_1h_n"))),
        int(finite(row.get("ou_1h_n"))),
    ]
    if any(value <= 0 for value in breadth_values):
        breadth_bucket = "MISSING"
    else:
        breadth = min(breadth_values)
        breadth_bucket = (
            "B00_04" if breadth < 5 else "B05_19" if breadth < 20 else "B20_PLUS"
        )
    spreads = []
    for index in (1, 2, 3):
        raw_avg = row.get(f"euro_1h_v{index}")
        raw_lo = row.get(f"euro_1h_min{index}")
        raw_hi = row.get(f"euro_1h_max{index}")
        if raw_avg in (None, "") or raw_lo in (None, "") or raw_hi in (None, ""):
            continue
        avg = finite(raw_avg)
        lo = finite(raw_lo)
        hi = finite(raw_hi)
        if avg > 0 and hi >= lo:
            spreads.append((hi - lo) / avg)
    if not spreads:
        dispersion_bucket = "MISSING"
    else:
        dispersion = sum(spreads) / len(spreads)
        dispersion_bucket = (
            "D_LOW"
            if dispersion <= 0.05
            else "D_MID"
            if dispersion <= 0.15
            else "D_HIGH"
        )
    initial = no_vig(
        [
            row.get("euro_initial_v1"),
            row.get("euro_initial_v2"),
            row.get("euro_initial_v3"),
        ]
    )
    close = no_vig(
        [row.get("euro_1h_v1"), row.get("euro_1h_v2"), row.get("euro_1h_v3")]
    )
    if initial is None or close is None:
        euro_move = "MISSING"
    else:
        deltas = [close[index] - initial[index] for index in range(3)]
        index = max(range(3), key=lambda item: (abs(deltas[item]), -item))
        direction = (
            "DOWN"
            if deltas[index] < -0.015
            else "UP"
            if deltas[index] > 0.015
            else "FLAT"
        )
        euro_move = f"{CODES[index]}_{direction}"
    return {
        "breadth": breadth_bucket,
        "dispersion": dispersion_bucket,
        "euro_move": euro_move,
        "asian_move": movement(
            row.get("asian_initial_v2"), row.get("asian_1h_v2"), 0.10
        ),
        "ou_move": movement(row.get("ou_initial_v2"), row.get("ou_1h_v2"), 0.10),
    }


def _add_residual(
    store: dict[object, list[float]],
    counts: Counter[object],
    key: object,
    truth: str,
    baseline: Sequence[float],
) -> None:
    for index, code in enumerate(CODES):
        store[key][index] += (1.0 if truth == code else 0.0) - baseline[index]
    counts[key] += 1


def _corrected(
    baseline: Sequence[float],
    components: Sequence[tuple[list[float], int, float]],
    scale: float,
) -> tuple[float, float, float]:
    residual = [0.0, 0.0, 0.0]
    used = 0
    for sums, count, alpha in components:
        if not count:
            continue
        shrink = count / (count + alpha)
        for index in range(3):
            residual[index] += shrink * sums[index] / count
        used += 1
    if used:
        residual = [value / used for value in residual]
    return normalize([baseline[index] + scale * residual[index] for index in range(3)])


@dataclass
class HierarchicalLeagueModel:
    target_year: int
    global_counts: Counter[str] = field(default_factory=Counter)
    league_counts: dict[str, Counter[str]] = field(
        default_factory=lambda: defaultdict(Counter)
    )
    league_season_counts: dict[tuple[str, int], Counter[str]] = field(
        default_factory=lambda: defaultdict(Counter)
    )
    handicap_counts: dict[str, Counter[str]] = field(
        default_factory=lambda: defaultdict(Counter)
    )
    league_handicap_counts: dict[tuple[str, str], Counter[str]] = field(
        default_factory=lambda: defaultdict(Counter)
    )
    total_counts: dict[str, Counter[str]] = field(
        default_factory=lambda: defaultdict(Counter)
    )
    league_total_counts: dict[tuple[str, str], Counter[str]] = field(
        default_factory=lambda: defaultdict(Counter)
    )
    pricing_sum: dict[tuple[str, str], list[float]] = field(
        default_factory=lambda: defaultdict(lambda: [0.0, 0.0, 0.0])
    )
    pricing_n: Counter[tuple[str, str]] = field(default_factory=Counter)
    mass_sum: dict[tuple[str, str], list[float]] = field(
        default_factory=lambda: defaultdict(lambda: [0.0, 0.0, 0.0])
    )
    mass_n: Counter[tuple[str, str]] = field(default_factory=Counter)
    liquidity_sum: dict[tuple[str, str], list[float]] = field(
        default_factory=lambda: defaultdict(lambda: [0.0, 0.0, 0.0])
    )
    liquidity_n: Counter[tuple[str, str]] = field(default_factory=Counter)
    drift_sum: dict[tuple[str, int], list[float]] = field(
        default_factory=lambda: defaultdict(lambda: [0.0, 0.0, 0.0])
    )
    drift_n: Counter[tuple[str, int]] = field(default_factory=Counter)
    training_rows: int = 0

    def update(self, row: Mapping[str, object]) -> None:
        year = int(str(row.get("kickoff_ts"))[:4])
        if year >= self.target_year:
            raise RuntimeError(
                f"future-season training row: {year} >= {self.target_year}"
            )
        truth = handicap_result(
            row.get("fthg"), row.get("ftag"), row.get("handicap_line_norm")
        )
        baseline = no_vig(
            [row.get("euro_1h_v1"), row.get("euro_1h_v2"), row.get("euro_1h_v3")]
        )
        if truth is None or baseline is None:
            return
        league = str(row.get("league") or "__UNKNOWN__")
        hbucket = handicap_bucket(row.get("handicap_line_norm"))
        tbucket = total_bucket(row.get("ou_1h_v2"))
        mbucket = mass_bucket(baseline)
        self.global_counts[truth] += 1
        self.league_counts[league][truth] += 1
        self.league_season_counts[(league, year)][truth] += 1
        self.handicap_counts[hbucket][truth] += 1
        self.league_handicap_counts[(league, hbucket)][truth] += 1
        self.total_counts[tbucket][truth] += 1
        self.league_total_counts[(league, tbucket)][truth] += 1
        _add_residual(
            self.pricing_sum, self.pricing_n, (league, hbucket), truth, baseline
        )
        _add_residual(self.mass_sum, self.mass_n, (league, mbucket), truth, baseline)
        for family, value in market_signature(row).items():
            _add_residual(
                self.liquidity_sum, self.liquidity_n, (family, value), truth, baseline
            )
        _add_residual(self.drift_sum, self.drift_n, (league, year), truth, baseline)
        self.training_rows += 1

    def frozen_copy(self, target_year: int) -> "HierarchicalLeagueModel":
        result = copy.deepcopy(self)
        result.target_year = target_year
        return result

    def global_prior(self) -> tuple[float, float, float]:
        return empirical(self.global_counts, (1 / 3, 1 / 3, 1 / 3), 3.0)

    def family_vectors(
        self, row: Mapping[str, object], baseline: Sequence[float]
    ) -> dict[str, tuple[float, float, float]]:
        league = str(row.get("league") or "__UNKNOWN__")
        hbucket = handicap_bucket(row.get("handicap_line_norm"))
        tbucket = total_bucket(row.get("ou_1h_v2"))
        mbucket = mass_bucket(baseline)
        prior = self.global_prior()
        recency = Counter()
        for (candidate_league, year), counts in self.league_season_counts.items():
            if candidate_league != league:
                continue
            weight = 0.65 ** max(0, self.target_year - 1 - year)
            for code in CODES:
                recency[code] += counts[code] * weight
        base = normalize(
            [
                0.20 * prior[index]
                + 0.45 * empirical(self.league_counts[league], prior, 120.0)[index]
                + 0.35 * empirical(recency, prior, 60.0)[index]
                for index in range(3)
            ]
        )
        goal = normalize(
            [
                0.20 * empirical(self.handicap_counts[hbucket], prior, 120.0)[index]
                + 0.35
                * empirical(
                    self.league_handicap_counts[(league, hbucket)], prior, 80.0
                )[index]
                + 0.15 * empirical(self.total_counts[tbucket], prior, 100.0)[index]
                + 0.30
                * empirical(self.league_total_counts[(league, tbucket)], prior, 80.0)[
                    index
                ]
                for index in range(3)
            ]
        )
        pricing = _corrected(
            baseline,
            [
                (
                    self.pricing_sum[(league, hbucket)],
                    self.pricing_n[(league, hbucket)],
                    120.0,
                ),
                (
                    self.mass_sum[(league, mbucket)],
                    self.mass_n[(league, mbucket)],
                    120.0,
                ),
            ],
            0.50,
        )
        signatures = market_signature(row)
        liquidity_components = [
            (
                self.liquidity_sum[(family, value)],
                self.liquidity_n[(family, value)],
                180.0,
            )
            for family, value in signatures.items()
        ]
        latest_year = self.target_year - 1
        liquidity_components.append(
            (
                self.drift_sum[(league, latest_year)],
                self.drift_n[(league, latest_year)],
                100.0,
            )
        )
        liquidity = _corrected(baseline, liquidity_components, 0.35)
        return {
            "BASE_SEASON": base,
            "GOAL_HANDICAP": goal,
            "PRICING_CALIBRATION": pricing,
            "LIQUIDITY_DRIFT": liquidity,
        }

    def probabilities(
        self,
        row: Mapping[str, object],
        baseline: Sequence[float],
        excluded: str | None = None,
    ) -> tuple[float, float, float]:
        return log_pool(self.family_vectors(row, baseline), excluded)

    def summary(self) -> dict[str, object]:
        return {
            "target_year": self.target_year,
            "training_rule": f"kickoff year < {self.target_year}",
            "training_rows": self.training_rows,
            "league_count": len(self.league_counts),
            "league_season_cell_count": len(self.league_season_counts),
            "league_handicap_cell_count": len(self.league_handicap_counts),
            "league_total_cell_count": len(self.league_total_counts),
            "pricing_cell_count": len(self.pricing_n) + len(self.mass_n),
            "liquidity_drift_cell_count": len(self.liquidity_n) + len(self.drift_n),
            "global_prior": dict(zip(CODES, self.global_prior())),
        }

    def to_payload(self) -> dict[str, object]:
        def counters(
            values: Mapping[object, Counter[str]],
        ) -> dict[str, dict[str, float]]:
            return {
                "|".join(map(str, key)) if isinstance(key, tuple) else str(key): {
                    code: float(value[code]) for code in CODES
                }
                for key, value in sorted(values.items(), key=lambda item: str(item[0]))
            }

        def residuals(
            sums: Mapping[object, list[float]], counts: Mapping[object, int]
        ) -> dict[str, object]:
            return {
                "|".join(map(str, key)) if isinstance(key, tuple) else str(key): {
                    "n": int(counts[key]),
                    "sum": [float(value) for value in values],
                }
                for key, values in sorted(sums.items(), key=lambda item: str(item[0]))
            }

        return {
            **self.summary(),
            "global_counts": {code: self.global_counts[code] for code in CODES},
            "league_counts": counters(self.league_counts),
            "league_season_counts": counters(self.league_season_counts),
            "handicap_counts": counters(self.handicap_counts),
            "league_handicap_counts": counters(self.league_handicap_counts),
            "total_counts": counters(self.total_counts),
            "league_total_counts": counters(self.league_total_counts),
            "pricing_residuals": residuals(self.pricing_sum, self.pricing_n),
            "mass_residuals": residuals(self.mass_sum, self.mass_n),
            "liquidity_residuals": residuals(self.liquidity_sum, self.liquidity_n),
            "drift_residuals": residuals(self.drift_sum, self.drift_n),
        }
