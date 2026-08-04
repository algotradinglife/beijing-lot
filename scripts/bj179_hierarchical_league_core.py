#!/usr/bin/env python3
"""Outcome-safe hierarchical league-regime primitives for Issue #179."""

from __future__ import annotations

import copy
import math
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field


CODES = ("3", "1", "0")
FAMILIES = (
    "RAW_HDA_SEASON",
    "BJ_HANDICAP_REGIME",
    "EURO_CALIBRATION",
    "ASIAN_CALIBRATION",
    "BEIJING_SP_CALIBRATION",
    "LIQUIDITY_DRIFT",
)
PRIMARY_CONFIG = "BALANCED_PRIMARY"
CONFIGURATIONS = {
    "BALANCED_PRIMARY": {
        "weights": {
            "RAW_HDA_SEASON": 0.15,
            "BJ_HANDICAP_REGIME": 0.15,
            "EURO_CALIBRATION": 0.20,
            "ASIAN_CALIBRATION": 0.15,
            "BEIJING_SP_CALIBRATION": 0.20,
            "LIQUIDITY_DRIFT": 0.15,
        },
        "shrinkage_multiplier": 1.00,
        "residual_scale_multiplier": 1.00,
    },
    "BALANCED_CONSERVATIVE": {
        "weights": {
            "RAW_HDA_SEASON": 0.15,
            "BJ_HANDICAP_REGIME": 0.15,
            "EURO_CALIBRATION": 0.20,
            "ASIAN_CALIBRATION": 0.15,
            "BEIJING_SP_CALIBRATION": 0.20,
            "LIQUIDITY_DRIFT": 0.15,
        },
        "shrinkage_multiplier": 1.50,
        "residual_scale_multiplier": 0.75,
    },
    "BALANCED_RESPONSIVE": {
        "weights": {
            "RAW_HDA_SEASON": 0.15,
            "BJ_HANDICAP_REGIME": 0.15,
            "EURO_CALIBRATION": 0.20,
            "ASIAN_CALIBRATION": 0.15,
            "BEIJING_SP_CALIBRATION": 0.20,
            "LIQUIDITY_DRIFT": 0.15,
        },
        "shrinkage_multiplier": 0.67,
        "residual_scale_multiplier": 1.25,
    },
    "PRICING_HEAVY_PRIMARY": {
        "weights": {
            "RAW_HDA_SEASON": 0.10,
            "BJ_HANDICAP_REGIME": 0.10,
            "EURO_CALIBRATION": 0.23,
            "ASIAN_CALIBRATION": 0.17,
            "BEIJING_SP_CALIBRATION": 0.25,
            "LIQUIDITY_DRIFT": 0.15,
        },
        "shrinkage_multiplier": 1.00,
        "residual_scale_multiplier": 1.00,
    },
    "REGIME_HEAVY_PRIMARY": {
        "weights": {
            "RAW_HDA_SEASON": 0.25,
            "BJ_HANDICAP_REGIME": 0.25,
            "EURO_CALIBRATION": 0.12,
            "ASIAN_CALIBRATION": 0.10,
            "BEIJING_SP_CALIBRATION": 0.13,
            "LIQUIDITY_DRIFT": 0.15,
        },
        "shrinkage_multiplier": 1.00,
        "residual_scale_multiplier": 1.00,
    },
    "PRICING_HEAVY_CONSERVATIVE": {
        "weights": {
            "RAW_HDA_SEASON": 0.10,
            "BJ_HANDICAP_REGIME": 0.15,
            "EURO_CALIBRATION": 0.20,
            "ASIAN_CALIBRATION": 0.18,
            "BEIJING_SP_CALIBRATION": 0.22,
            "LIQUIDITY_DRIFT": 0.15,
        },
        "shrinkage_multiplier": 1.50,
        "residual_scale_multiplier": 0.75,
    },
}


def validate_configurations() -> None:
    if tuple(CONFIGURATIONS[PRIMARY_CONFIG]["weights"]) != FAMILIES:
        raise RuntimeError("primary configuration family order drift")
    for name, config in CONFIGURATIONS.items():
        weights = config["weights"]
        if set(weights) != set(FAMILIES) or abs(sum(weights.values()) - 1.0) > 1e-12:
            raise RuntimeError(f"invalid configuration weights: {name}")
        if (
            config["shrinkage_multiplier"] <= 0
            or config["residual_scale_multiplier"] <= 0
        ):
            raise RuntimeError(f"invalid configuration scale: {name}")


validate_configurations()


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
    vectors: Mapping[str, Sequence[float]],
    weights: Mapping[str, float],
    excluded: str | None = None,
) -> tuple[float, float, float]:
    active = {name: weight for name, weight in weights.items() if name != excluded}
    total = sum(active.values())
    return normalize(
        [
            math.exp(
                sum(
                    (weight / total) * math.log(max(1e-12, vectors[name][index]))
                    for name, weight in active.items()
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


def asian_line_bucket(value: object) -> str:
    if value in (None, ""):
        return "A_MISSING"
    return line_bucket(value, "A", -3.0, 3.0)


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


def asian_anchor(
    row: Mapping[str, object], euro_baseline: Sequence[float]
) -> tuple[float, float, float] | None:
    home_water = finite(row.get("asian_1h_v1"), -1.0)
    line = finite(row.get("asian_1h_v2"), math.nan)
    away_water = finite(row.get("asian_1h_v3"), -1.0)
    if home_water <= 0 or away_water <= 0 or not math.isfinite(line):
        return None
    home_implied = 1.0 / (1.0 + home_water)
    away_implied = 1.0 / (1.0 + away_water)
    side_total = home_implied + away_implied
    side_home = home_implied / side_total
    side_away = away_implied / side_total
    side_tilt = math.log(max(1e-9, side_home) / max(1e-9, side_away))
    line_tilt = math.tanh(line / 1.5)
    combined_tilt = 0.45 * side_tilt + 0.35 * line_tilt
    return normalize(
        [
            euro_baseline[0] * math.exp(combined_tilt),
            euro_baseline[1],
            euro_baseline[2] * math.exp(-combined_tilt),
        ]
    )


def asian_side_bucket(row: Mapping[str, object]) -> str:
    anchor = asian_anchor(row, (1 / 3, 1 / 3, 1 / 3))
    if anchor is None:
        return "AS_MISSING"
    delta = anchor[0] - anchor[2]
    return "AS_HOME" if delta > 0.04 else "AS_AWAY" if delta < -0.04 else "AS_BALANCED"


def beijing_sp_anchor(row: Mapping[str, object]) -> tuple[float, float, float] | None:
    official = no_vig(
        [row.get("official_sp_3"), row.get("official_sp_1"), row.get("official_sp_0")]
    )
    if official is not None:
        return official
    return no_vig(
        [
            row.get("target_bj_pred_sp_3"),
            row.get("target_bj_pred_sp_1"),
            row.get("target_bj_pred_sp_0"),
        ]
    )


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


def residual_store():
    return defaultdict(lambda: [0.0, 0.0, 0.0])


@dataclass
class HierarchicalLeagueModel:
    target_year: int
    raw_global_counts: Counter[str] = field(default_factory=Counter)
    raw_league_counts: dict[str, Counter[str]] = field(
        default_factory=lambda: defaultdict(Counter)
    )
    raw_league_season_counts: dict[tuple[str, int], Counter[str]] = field(
        default_factory=lambda: defaultdict(Counter)
    )
    bj_global_counts: Counter[str] = field(default_factory=Counter)
    bj_league_counts: dict[str, Counter[str]] = field(
        default_factory=lambda: defaultdict(Counter)
    )
    bj_league_season_counts: dict[tuple[str, int], Counter[str]] = field(
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
    euro_sum: dict[tuple[str, str], list[float]] = field(default_factory=residual_store)
    euro_n: Counter[tuple[str, str]] = field(default_factory=Counter)
    euro_mass_sum: dict[tuple[str, str], list[float]] = field(
        default_factory=residual_store
    )
    euro_mass_n: Counter[tuple[str, str]] = field(default_factory=Counter)
    asian_sum: dict[tuple[str, str], list[float]] = field(
        default_factory=residual_store
    )
    asian_n: Counter[tuple[str, str]] = field(default_factory=Counter)
    asian_side_sum: dict[tuple[str, str], list[float]] = field(
        default_factory=residual_store
    )
    asian_side_n: Counter[tuple[str, str]] = field(default_factory=Counter)
    beijing_sp_sum: dict[tuple[str, str], list[float]] = field(
        default_factory=residual_store
    )
    beijing_sp_n: Counter[tuple[str, str]] = field(default_factory=Counter)
    beijing_mass_sum: dict[tuple[str, str], list[float]] = field(
        default_factory=residual_store
    )
    beijing_mass_n: Counter[tuple[str, str]] = field(default_factory=Counter)
    liquidity_sum: dict[tuple[str, str], list[float]] = field(
        default_factory=residual_store
    )
    liquidity_n: Counter[tuple[str, str]] = field(default_factory=Counter)
    drift_sum: dict[tuple[str, int], list[float]] = field(
        default_factory=residual_store
    )
    drift_n: Counter[tuple[str, int]] = field(default_factory=Counter)
    training_rows: int = 0
    bj_training_rows: int = 0
    euro_source_complete_rows: int = 0
    asian_source_complete_rows: int = 0
    beijing_sp_source_complete_rows: int = 0
    euro_complete_rows: int = 0
    asian_complete_rows: int = 0
    beijing_sp_complete_rows: int = 0

    def update(self, row: Mapping[str, object]) -> None:
        year = int(str(row.get("kickoff_ts"))[:4])
        if year >= self.target_year:
            raise RuntimeError(
                f"future-season training row: {year} >= {self.target_year}"
            )
        raw_truth = handicap_result(row.get("fthg"), row.get("ftag"), 0.0)
        bj_truth = handicap_result(
            row.get("fthg"), row.get("ftag"), row.get("handicap_line_norm")
        )
        if raw_truth is None:
            return
        league = str(row.get("league") or "__UNKNOWN__")
        hbucket = handicap_bucket(row.get("handicap_line_norm"))
        tbucket = total_bucket(row.get("ou_1h_v2"))
        self.raw_global_counts[raw_truth] += 1
        self.raw_league_counts[league][raw_truth] += 1
        self.raw_league_season_counts[(league, year)][raw_truth] += 1
        self.training_rows += 1

        euro = no_vig(
            [row.get("euro_1h_v1"), row.get("euro_1h_v2"), row.get("euro_1h_v3")]
        )
        beijing = beijing_sp_anchor(row)
        asian_baseline = euro or beijing or self.raw_global_prior()
        asian = asian_anchor(row, asian_baseline)
        self.euro_source_complete_rows += int(euro is not None)
        self.asian_source_complete_rows += int(asian is not None)
        self.beijing_sp_source_complete_rows += int(beijing is not None)

        if bj_truth is None:
            return
        self.bj_global_counts[bj_truth] += 1
        self.bj_league_counts[league][bj_truth] += 1
        self.bj_league_season_counts[(league, year)][bj_truth] += 1
        self.handicap_counts[hbucket][bj_truth] += 1
        self.league_handicap_counts[(league, hbucket)][bj_truth] += 1
        self.total_counts[tbucket][bj_truth] += 1
        self.league_total_counts[(league, tbucket)][bj_truth] += 1
        self.bj_training_rows += 1

        if euro is not None:
            self.euro_complete_rows += 1
            _add_residual(self.euro_sum, self.euro_n, (league, hbucket), bj_truth, euro)
            _add_residual(
                self.euro_mass_sum,
                self.euro_mass_n,
                (league, mass_bucket(euro)),
                bj_truth,
                euro,
            )
        if beijing is not None:
            self.beijing_sp_complete_rows += 1
            _add_residual(
                self.beijing_sp_sum,
                self.beijing_sp_n,
                (league, hbucket),
                bj_truth,
                beijing,
            )
            _add_residual(
                self.beijing_mass_sum,
                self.beijing_mass_n,
                (league, mass_bucket(beijing)),
                bj_truth,
                beijing,
            )
        if asian is not None:
            self.asian_complete_rows += 1
            _add_residual(
                self.asian_sum,
                self.asian_n,
                (league, asian_line_bucket(row.get("asian_1h_v2"))),
                bj_truth,
                asian,
            )
            _add_residual(
                self.asian_side_sum,
                self.asian_side_n,
                (league, asian_side_bucket(row)),
                bj_truth,
                asian,
            )
        if euro is not None:
            for family, value in market_signature(row).items():
                _add_residual(
                    self.liquidity_sum,
                    self.liquidity_n,
                    (family, value),
                    bj_truth,
                    euro,
                )
            _add_residual(self.drift_sum, self.drift_n, (league, year), bj_truth, euro)

    def frozen_copy(self, target_year: int) -> "HierarchicalLeagueModel":
        result = copy.deepcopy(self)
        result.target_year = target_year
        return result

    def raw_global_prior(self) -> tuple[float, float, float]:
        return empirical(self.raw_global_counts, (1 / 3, 1 / 3, 1 / 3), 3.0)

    def bj_global_prior(self) -> tuple[float, float, float]:
        return empirical(self.bj_global_counts, (1 / 3, 1 / 3, 1 / 3), 3.0)

    @staticmethod
    def _recency(
        values: Mapping[tuple[str, int], Counter[str]], league: str, target_year: int
    ) -> Counter[str]:
        output = Counter()
        for (candidate_league, year), counts in values.items():
            if candidate_league != league:
                continue
            weight = 0.65 ** max(0, target_year - 1 - year)
            for code in CODES:
                output[code] += counts[code] * weight
        return output

    def family_vectors(
        self,
        row: Mapping[str, object],
        euro_baseline: Sequence[float],
        config_name: str = PRIMARY_CONFIG,
    ) -> dict[str, tuple[float, float, float]]:
        config = CONFIGURATIONS[config_name]
        shrink = float(config["shrinkage_multiplier"])
        residual_scale = float(config["residual_scale_multiplier"])
        league = str(row.get("league") or "__UNKNOWN__")
        hbucket = handicap_bucket(row.get("handicap_line_norm"))
        tbucket = total_bucket(row.get("ou_1h_v2"))
        raw_prior = self.raw_global_prior()
        bj_prior = self.bj_global_prior()
        raw_recency = self._recency(
            self.raw_league_season_counts, league, self.target_year
        )
        bj_recency = self._recency(
            self.bj_league_season_counts, league, self.target_year
        )
        raw = normalize(
            [
                0.20 * raw_prior[index]
                + 0.45
                * empirical(self.raw_league_counts[league], raw_prior, 120.0 * shrink)[
                    index
                ]
                + 0.35 * empirical(raw_recency, raw_prior, 60.0 * shrink)[index]
                for index in range(3)
            ]
        )
        bj = normalize(
            [
                0.15
                * empirical(self.bj_league_counts[league], bj_prior, 120.0 * shrink)[
                    index
                ]
                + 0.20 * empirical(bj_recency, bj_prior, 60.0 * shrink)[index]
                + 0.20
                * empirical(self.handicap_counts[hbucket], bj_prior, 120.0 * shrink)[
                    index
                ]
                + 0.25
                * empirical(
                    self.league_handicap_counts[(league, hbucket)],
                    bj_prior,
                    80.0 * shrink,
                )[index]
                + 0.10
                * empirical(self.total_counts[tbucket], bj_prior, 100.0 * shrink)[index]
                + 0.10
                * empirical(
                    self.league_total_counts[(league, tbucket)], bj_prior, 80.0 * shrink
                )[index]
                for index in range(3)
            ]
        )
        euro = _corrected(
            euro_baseline,
            [
                (
                    self.euro_sum[(league, hbucket)],
                    self.euro_n[(league, hbucket)],
                    120.0 * shrink,
                ),
                (
                    self.euro_mass_sum[(league, mass_bucket(euro_baseline))],
                    self.euro_mass_n[(league, mass_bucket(euro_baseline))],
                    120.0 * shrink,
                ),
            ],
            0.50 * residual_scale,
        )
        target_asian = asian_anchor(row, euro_baseline) or tuple(euro_baseline)
        asian = _corrected(
            target_asian,
            [
                (
                    self.asian_sum[(league, asian_line_bucket(row.get("asian_1h_v2")))],
                    self.asian_n[(league, asian_line_bucket(row.get("asian_1h_v2")))],
                    120.0 * shrink,
                ),
                (
                    self.asian_side_sum[(league, asian_side_bucket(row))],
                    self.asian_side_n[(league, asian_side_bucket(row))],
                    120.0 * shrink,
                ),
            ],
            0.45 * residual_scale,
        )
        target_beijing = beijing_sp_anchor(row) or tuple(euro_baseline)
        beijing = _corrected(
            target_beijing,
            [
                (
                    self.beijing_sp_sum[(league, hbucket)],
                    self.beijing_sp_n[(league, hbucket)],
                    100.0 * shrink,
                ),
                (
                    self.beijing_mass_sum[(league, mass_bucket(target_beijing))],
                    self.beijing_mass_n[(league, mass_bucket(target_beijing))],
                    100.0 * shrink,
                ),
            ],
            0.40 * residual_scale,
        )
        signatures = market_signature(row)
        liquidity_components = [
            (
                self.liquidity_sum[(family, value)],
                self.liquidity_n[(family, value)],
                180.0 * shrink,
            )
            for family, value in signatures.items()
        ]
        latest_year = self.target_year - 1
        liquidity_components.append(
            (
                self.drift_sum[(league, latest_year)],
                self.drift_n[(league, latest_year)],
                100.0 * shrink,
            )
        )
        liquidity = _corrected(
            euro_baseline,
            liquidity_components,
            0.35 * residual_scale,
        )
        return {
            "RAW_HDA_SEASON": raw,
            "BJ_HANDICAP_REGIME": bj,
            "EURO_CALIBRATION": euro,
            "ASIAN_CALIBRATION": asian,
            "BEIJING_SP_CALIBRATION": beijing,
            "LIQUIDITY_DRIFT": liquidity,
        }

    def probabilities(
        self,
        row: Mapping[str, object],
        euro_baseline: Sequence[float],
        config_name: str = PRIMARY_CONFIG,
        excluded: str | None = None,
    ) -> tuple[float, float, float]:
        config = CONFIGURATIONS[config_name]
        return log_pool(
            self.family_vectors(row, euro_baseline, config_name),
            config["weights"],
            excluded,
        )

    def summary(self) -> dict[str, object]:
        def coverage(count: int, denominator: int) -> float:
            return count / denominator if denominator else 0.0

        return {
            "target_year": self.target_year,
            "training_rule": f"kickoff year < {self.target_year}",
            "training_rows": self.training_rows,
            "bj_training_rows": self.bj_training_rows,
            "raw_league_count": len(self.raw_league_counts),
            "raw_league_season_cell_count": len(self.raw_league_season_counts),
            "bj_league_count": len(self.bj_league_counts),
            "bj_league_season_cell_count": len(self.bj_league_season_counts),
            "league_handicap_cell_count": len(self.league_handicap_counts),
            "league_total_cell_count": len(self.league_total_counts),
            "euro_complete_rows": self.euro_complete_rows,
            "asian_complete_rows": self.asian_complete_rows,
            "beijing_sp_complete_rows": self.beijing_sp_complete_rows,
            "euro_source_complete_rows": self.euro_source_complete_rows,
            "asian_source_complete_rows": self.asian_source_complete_rows,
            "beijing_sp_source_complete_rows": self.beijing_sp_source_complete_rows,
            "euro_source_coverage": coverage(
                self.euro_source_complete_rows, self.training_rows
            ),
            "asian_source_coverage": coverage(
                self.asian_source_complete_rows, self.training_rows
            ),
            "beijing_sp_source_coverage": coverage(
                self.beijing_sp_source_complete_rows, self.training_rows
            ),
            "euro_calibration_coverage": coverage(
                self.euro_complete_rows, self.bj_training_rows
            ),
            "asian_calibration_coverage": coverage(
                self.asian_complete_rows, self.bj_training_rows
            ),
            "beijing_sp_calibration_coverage": coverage(
                self.beijing_sp_complete_rows, self.bj_training_rows
            ),
            "euro_cell_count": len(self.euro_n) + len(self.euro_mass_n),
            "asian_cell_count": len(self.asian_n) + len(self.asian_side_n),
            "beijing_sp_cell_count": len(self.beijing_sp_n) + len(self.beijing_mass_n),
            "liquidity_drift_cell_count": len(self.liquidity_n) + len(self.drift_n),
            "raw_global_prior": dict(zip(CODES, self.raw_global_prior())),
            "bj_global_prior": dict(zip(CODES, self.bj_global_prior())),
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
            "configurations": CONFIGURATIONS,
            "raw_global_counts": {code: self.raw_global_counts[code] for code in CODES},
            "raw_league_counts": counters(self.raw_league_counts),
            "raw_league_season_counts": counters(self.raw_league_season_counts),
            "bj_global_counts": {code: self.bj_global_counts[code] for code in CODES},
            "bj_league_counts": counters(self.bj_league_counts),
            "bj_league_season_counts": counters(self.bj_league_season_counts),
            "handicap_counts": counters(self.handicap_counts),
            "league_handicap_counts": counters(self.league_handicap_counts),
            "total_counts": counters(self.total_counts),
            "league_total_counts": counters(self.league_total_counts),
            "euro_residuals": residuals(self.euro_sum, self.euro_n),
            "euro_mass_residuals": residuals(self.euro_mass_sum, self.euro_mass_n),
            "asian_residuals": residuals(self.asian_sum, self.asian_n),
            "asian_side_residuals": residuals(self.asian_side_sum, self.asian_side_n),
            "beijing_sp_residuals": residuals(self.beijing_sp_sum, self.beijing_sp_n),
            "beijing_mass_residuals": residuals(
                self.beijing_mass_sum, self.beijing_mass_n
            ),
            "liquidity_residuals": residuals(self.liquidity_sum, self.liquidity_n),
            "drift_residuals": residuals(self.drift_sum, self.drift_n),
        }
