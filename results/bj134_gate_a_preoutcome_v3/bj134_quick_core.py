#!/usr/bin/env python3
"""Outcome-safe primitives for #134's quick backtestable core.

The module deliberately contains no portfolio settlement code.  It converts
strictly earlier football results and pre-kickoff market snapshots into frozen
probability vectors used by the Gate-A identity selector.
"""
from __future__ import annotations

import copy
import datetime as dt
import math
from collections import Counter, defaultdict, deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field


CODES = ("3", "1", "0")


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


def parse_ts(value: object) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(str(value or "").replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def handicap_bucket(value: object) -> str:
    line = finite(value)
    if line <= -2:
        return "LE_M2"
    if line < 0:
        return "NEG"
    if line == 0:
        return "ZERO"
    if line < 2:
        return "POS"
    return "GE_P2"


def handicap_result(home_goals: object, away_goals: object, line: object) -> str | None:
    try:
        margin = float(home_goals) + float(line) - float(away_goals)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(margin):
        return None
    if margin > 1e-9:
        return "3"
    if margin < -1e-9:
        return "0"
    return "1"


def empirical(counts: Mapping[str, int], prior: Sequence[float], alpha: float) -> tuple[float, float, float]:
    total = sum(int(counts.get(code, 0)) for code in CODES)
    return normalize([
        int(counts.get(code, 0)) + alpha * prior[index]
        for index, code in enumerate(CODES)
    ]) if total else tuple(prior)  # type: ignore[return-value]


def _movement_bucket(delta: float, tolerance: float = 0.02) -> str:
    if delta < -tolerance:
        return "DOWN"
    if delta > tolerance:
        return "UP"
    return "FLAT"


def market_signature(row: Mapping[str, object]) -> dict[str, str]:
    initial = no_vig([row.get("euro_initial_v1"), row.get("euro_initial_v2"), row.get("euro_initial_v3")])
    ten_hour = no_vig([row.get("euro_10h_v1"), row.get("euro_10h_v2"), row.get("euro_10h_v3")])
    one_hour = no_vig([row.get("euro_1h_v1"), row.get("euro_1h_v2"), row.get("euro_1h_v3")])

    def euro_phase(left: tuple[float, float, float] | None, right: tuple[float, float, float] | None) -> str:
        if left is None or right is None:
            return "MISSING"
        deltas = [right[index] - left[index] for index in range(3)]
        index = max(range(3), key=lambda item: (abs(deltas[item]), -item))
        return f"{CODES[index]}_{_movement_bucket(deltas[index], 0.015)}"

    asian_initial = row.get("asian_initial_v2")
    asian_10h = row.get("asian_10h_v2")
    ou_initial = row.get("ou_initial_v2")
    ou_10h = row.get("ou_10h_v2")
    asian_i10 = "MISSING" if asian_initial is None or asian_10h is None else _movement_bucket(
        finite(asian_10h) - finite(asian_initial), 0.10
    )
    asian_101 = "MISSING" if asian_10h is None or row.get("asian_1h_v2") is None else _movement_bucket(
        finite(row.get("asian_1h_v2")) - finite(asian_10h), 0.10
    )
    ou_i10 = "MISSING" if ou_initial is None or ou_10h is None else _movement_bucket(
        finite(ou_10h) - finite(ou_initial), 0.10
    )
    ou_101 = "MISSING" if ou_10h is None or row.get("ou_1h_v2") is None else _movement_bucket(
        finite(row.get("ou_1h_v2")) - finite(ou_10h), 0.10
    )
    breadth = min(
        int(finite(row.get("euro_1h_n"))),
        int(finite(row.get("asian_1h_n"))),
        int(finite(row.get("ou_1h_n"))),
    )
    breadth_bucket = "B00_04" if breadth < 5 else "B05_19" if breadth < 20 else "B20_PLUS"
    spreads = []
    for position in (1, 2, 3):
        avg = finite(row.get(f"euro_1h_v{position}"))
        lo = finite(row.get(f"euro_1h_min{position}"))
        hi = finite(row.get(f"euro_1h_max{position}"))
        if avg > 0 and hi >= lo:
            spreads.append((hi - lo) / avg)
    dispersion = sum(spreads) / len(spreads) if spreads else 1.0
    dispersion_bucket = "D_LOW" if dispersion <= 0.05 else "D_MID" if dispersion <= 0.15 else "D_HIGH"
    return {
        "euro_initial_10h": euro_phase(initial, ten_hour),
        "euro_10h_1h": euro_phase(ten_hour, one_hour),
        "asian_initial_10h": asian_i10,
        "asian_10h_1h": asian_101,
        "ou_initial_10h": ou_i10,
        "ou_10h_1h": ou_101,
        "breadth": breadth_bucket,
        "dispersion": dispersion_bucket,
        "handicap": handicap_bucket(row.get("handicap_line_norm")),
    }


def poisson_handicap_probabilities(
    lambda_home: float,
    lambda_away: float,
    handicap: float,
    max_goals: int = 12,
) -> tuple[float, float, float]:
    lambda_home = min(6.0, max(0.10, lambda_home))
    lambda_away = min(6.0, max(0.10, lambda_away))

    def pmf(lam: float) -> list[float]:
        values = [math.exp(-lam)]
        for goals in range(1, max_goals + 1):
            values.append(values[-1] * lam / goals)
        return values

    home_pmf, away_pmf = pmf(lambda_home), pmf(lambda_away)
    totals = Counter({"3": 0.0, "1": 0.0, "0": 0.0})
    for home_goals, hp in enumerate(home_pmf):
        for away_goals, ap in enumerate(away_pmf):
            result = handicap_result(home_goals, away_goals, handicap)
            if result is not None:
                totals[result] += hp * ap
    return normalize([totals[code] for code in CODES])


@dataclass
class TeamState:
    """Rolling state that can only be advanced by an earlier kickoff."""

    elo: dict[str, float] = field(default_factory=lambda: defaultdict(lambda: 1500.0))
    all_goals: dict[str, deque[tuple[float, float]]] = field(
        default_factory=lambda: defaultdict(lambda: deque(maxlen=12))
    )
    home_goals: dict[str, deque[tuple[float, float]]] = field(
        default_factory=lambda: defaultdict(lambda: deque(maxlen=12))
    )
    away_goals: dict[str, deque[tuple[float, float]]] = field(
        default_factory=lambda: defaultdict(lambda: deque(maxlen=12))
    )
    form: dict[str, deque[float]] = field(default_factory=lambda: defaultdict(lambda: deque(maxlen=10)))
    count: Counter[str] = field(default_factory=Counter)
    last_ts: dict[str, dt.datetime] = field(default_factory=dict)

    @staticmethod
    def _mean(values: Sequence[tuple[float, float]], index: int, fallback: float) -> float:
        return fallback if not values else sum(value[index] for value in values) / len(values)

    def update(self, row: Mapping[str, object]) -> None:
        home, away = str(row.get("home_team_id") or ""), str(row.get("away_team_id") or "")
        timestamp = parse_ts(row.get("kickoff_ts"))
        try:
            home_goals, away_goals = float(row["fthg"]), float(row["ftag"])
        except (KeyError, TypeError, ValueError):
            return
        if not home or not away or timestamp is None:
            return
        expected = 1.0 / (1.0 + 10.0 ** (-((self.elo[home] + 50.0) - self.elo[away]) / 400.0))
        actual = 1.0 if home_goals > away_goals else 0.0 if home_goals < away_goals else 0.5
        multiplier = max(1.0, min(3.0, abs(home_goals - away_goals)))
        change = 20.0 * multiplier * (actual - expected)
        self.elo[home] += change
        self.elo[away] -= change
        self.all_goals[home].append((home_goals, away_goals))
        self.all_goals[away].append((away_goals, home_goals))
        self.home_goals[home].append((home_goals, away_goals))
        self.away_goals[away].append((away_goals, home_goals))
        self.form[home].append(3.0 if actual == 1.0 else 1.0 if actual == 0.5 else 0.0)
        self.form[away].append(3.0 if actual == 0.0 else 1.0 if actual == 0.5 else 0.0)
        self.count[home] += 1
        self.count[away] += 1
        self.last_ts[home] = timestamp
        self.last_ts[away] = timestamp

    def snapshot(
        self,
        row: Mapping[str, object],
        cutoff: dt.datetime,
        league_home_goals: float,
        league_away_goals: float,
    ) -> dict[str, object]:
        home, away = str(row.get("home_team_id") or ""), str(row.get("away_team_id") or "")
        home_role = self.home_goals[home]
        away_role = self.away_goals[away]
        home_all = self.all_goals[home]
        away_all = self.all_goals[away]
        home_attack = self._mean(home_role or home_all, 0, league_home_goals)
        away_defence = self._mean(away_role or away_all, 1, league_home_goals)
        away_attack = self._mean(away_role or away_all, 0, league_away_goals)
        home_defence = self._mean(home_role or home_all, 1, league_away_goals)
        home_n, away_n = len(home_role or home_all), len(away_role or away_all)
        lambda_home = (
            home_n * home_attack + away_n * away_defence + 8.0 * league_home_goals
        ) / (home_n + away_n + 8.0)
        lambda_away = (
            away_n * away_attack + home_n * home_defence + 8.0 * league_away_goals
        ) / (home_n + away_n + 8.0)
        elo_diff = (self.elo[home] + 50.0) - self.elo[away]
        lambda_home *= math.exp(max(-0.25, min(0.25, elo_diff / 1600.0)))
        lambda_away *= math.exp(max(-0.25, min(0.25, -elo_diff / 1600.0)))

        def rest(team: str) -> float:
            if team not in self.last_ts:
                return 720.0
            return max(0.0, min(720.0, (cutoff - self.last_ts[team]).total_seconds() / 3600.0))

        rest_diff = max(-1.0, min(1.0, (rest(home) - rest(away)) / 720.0))
        lambda_home *= math.exp(0.04 * rest_diff)
        lambda_away *= math.exp(-0.04 * rest_diff)
        probabilities = poisson_handicap_probabilities(
            lambda_home, lambda_away, finite(row.get("handicap_line_norm"))
        )
        return {
            "team_p3": probabilities[0],
            "team_p1": probabilities[1],
            "team_p0": probabilities[2],
            "team_lambda_home": lambda_home,
            "team_lambda_away": lambda_away,
            "team_elo_diff": elo_diff,
            "team_home_form_points": sum(self.form[home]) / len(self.form[home]) if self.form[home] else 1.0,
            "team_away_form_points": sum(self.form[away]) / len(self.form[away]) if self.form[away] else 1.0,
            "team_rest_diff": rest_diff,
            "team_home_history_n": self.count[home],
            "team_away_history_n": self.count[away],
            "team_min_history_n": min(self.count[home], self.count[away]),
            "team_missing": int(not home or not away or min(self.count[home], self.count[away]) == 0),
        }


@dataclass
class TrainingAccumulator:
    global_counts: Counter[str] = field(default_factory=Counter)
    league_counts: dict[str, Counter[str]] = field(default_factory=lambda: defaultdict(Counter))
    league_year_counts: dict[tuple[str, int], Counter[str]] = field(default_factory=lambda: defaultdict(Counter))
    league_raw_counts: dict[str, Counter[str]] = field(default_factory=lambda: defaultdict(Counter))
    league_year_raw_counts: dict[tuple[str, int], Counter[str]] = field(default_factory=lambda: defaultdict(Counter))
    handicap_counts: dict[str, Counter[str]] = field(default_factory=lambda: defaultdict(Counter))
    odds_counts: dict[str, Counter[str]] = field(default_factory=lambda: defaultdict(Counter))
    calibration_sum: dict[tuple[str, str], list[float]] = field(default_factory=lambda: defaultdict(lambda: [0.0, 0.0, 0.0]))
    calibration_n: Counter[tuple[str, str]] = field(default_factory=Counter)
    market_residual_sum: dict[tuple[str, str], list[float]] = field(default_factory=lambda: defaultdict(lambda: [0.0, 0.0, 0.0]))
    market_residual_n: Counter[tuple[str, str]] = field(default_factory=Counter)
    league_goals: dict[str, list[float]] = field(default_factory=lambda: defaultdict(lambda: [0.0, 0.0, 0.0]))
    global_goals: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    training_rows: int = 0

    def update(self, row: Mapping[str, object]) -> None:
        result = handicap_result(row.get("fthg"), row.get("ftag"), row.get("handicap_line_norm"))
        raw_result = handicap_result(row.get("fthg"), row.get("ftag"), 0.0)
        baseline = no_vig([row.get("euro_1h_v1"), row.get("euro_1h_v2"), row.get("euro_1h_v3")])
        if result is None or raw_result is None or baseline is None:
            return
        league = str(row.get("league") or "__MISSING__")
        year = int(str(row.get("kickoff_ts"))[:4])
        hbucket = handicap_bucket(row.get("handicap_line_norm"))
        top_mass = max(baseline)
        mass_bucket = "P_LOW" if top_mass < 0.40 else "P_MID" if top_mass < 0.55 else "P_HIGH"
        total_line = finite(row.get("ou_1h_v2"))
        total_bucket = "TG_LOW" if total_line < 2.25 else "TG_MID" if total_line < 3.0 else "TG_HIGH"
        odds_bucket = f"{mass_bucket}|{total_bucket}"
        self.global_counts[result] += 1
        self.league_counts[league][result] += 1
        self.league_year_counts[(league, year)][result] += 1
        self.league_raw_counts[league][raw_result] += 1
        self.league_year_raw_counts[(league, year)][raw_result] += 1
        self.handicap_counts[hbucket][result] += 1
        self.odds_counts[odds_bucket][result] += 1
        key = (league, hbucket)
        for index, code in enumerate(CODES):
            self.calibration_sum[key][index] += (1.0 if result == code else 0.0) - baseline[index]
        self.calibration_n[key] += 1
        for family, value in market_signature(row).items():
            rkey = (family, value)
            for index, code in enumerate(CODES):
                self.market_residual_sum[rkey][index] += (1.0 if result == code else 0.0) - baseline[index]
            self.market_residual_n[rkey] += 1
        try:
            home_goals, away_goals = float(row["fthg"]), float(row["ftag"])
        except (KeyError, TypeError, ValueError):
            return
        self.league_goals[league][0] += home_goals
        self.league_goals[league][1] += away_goals
        self.league_goals[league][2] += 1.0
        self.global_goals[0] += home_goals
        self.global_goals[1] += away_goals
        self.global_goals[2] += 1.0
        self.training_rows += 1

    def frozen_copy(self) -> "TrainingAccumulator":
        return copy.deepcopy(self)

    def global_prior(self) -> tuple[float, float, float]:
        return empirical(self.global_counts, (1 / 3, 1 / 3, 1 / 3), 3.0)

    def league_probabilities(self, row: Mapping[str, object]) -> tuple[float, float, float]:
        prior = self.global_prior()
        league = str(row.get("league") or "__MISSING__")
        target_year = int(str(row.get("kickoff_ts"))[:4])
        hbucket = handicap_bucket(row.get("handicap_line_norm"))
        baseline = no_vig([row.get("euro_1h_v1"), row.get("euro_1h_v2"), row.get("euro_1h_v3")]) or prior
        mass_bucket = "P_LOW" if max(baseline) < 0.40 else "P_MID" if max(baseline) < 0.55 else "P_HIGH"
        total_line = finite(row.get("ou_1h_v2"))
        total_bucket = "TG_LOW" if total_line < 2.25 else "TG_MID" if total_line < 3.0 else "TG_HIGH"
        odds_bucket = f"{mass_bucket}|{total_bucket}"
        components = [
            prior,
            empirical(self.league_counts[league], prior, 90.0),
            empirical(self.league_year_counts[(league, target_year - 1)], prior, 45.0),
            empirical(self.league_raw_counts[league], prior, 90.0),
            empirical(self.league_year_raw_counts[(league, target_year - 1)], prior, 45.0),
            empirical(self.handicap_counts[hbucket], prior, 90.0),
            empirical(self.odds_counts[odds_bucket], prior, 90.0),
        ]
        probabilities = [sum(component[index] for component in components) / len(components) for index in range(3)]
        key = (league, hbucket)
        count = self.calibration_n[key]
        if count:
            shrink = count / (count + 120.0)
            for index in range(3):
                probabilities[index] += 0.25 * shrink * self.calibration_sum[key][index] / count
        return normalize(probabilities)

    def market_probabilities(self, row: Mapping[str, object]) -> tuple[float, float, float]:
        baseline = no_vig([row.get("euro_1h_v1"), row.get("euro_1h_v2"), row.get("euro_1h_v3")])
        if baseline is None:
            return self.global_prior()
        residuals = [0.0, 0.0, 0.0]
        families = market_signature(row)
        used = 0
        for family, value in families.items():
            key = (family, value)
            count = self.market_residual_n[key]
            if not count:
                continue
            shrink = count / (count + 120.0)
            for index in range(3):
                residuals[index] += shrink * self.market_residual_sum[key][index] / count
            used += 1
        if used:
            residuals = [value / used for value in residuals]
        return normalize([baseline[index] + 0.50 * residuals[index] for index in range(3)])

    def goal_prior(self, league: str) -> tuple[float, float]:
        global_n = self.global_goals[2]
        global_home = self.global_goals[0] / global_n if global_n else 1.45
        global_away = self.global_goals[1] / global_n if global_n else 1.15
        values = self.league_goals.get(league, [0.0, 0.0, 0.0])
        count = values[2]
        return (
            (values[0] + 60.0 * global_home) / (count + 60.0),
            (values[1] + 60.0 * global_away) / (count + 60.0),
        )

    def summary(self, target_year: int) -> dict[str, object]:
        return {
            "target_year": target_year,
            "train_year_rule": f"calendar year < {target_year}",
            "training_rows": self.training_rows,
            "global_prior": dict(zip(CODES, self.global_prior())),
            "league_count": len(self.league_counts),
            "league_handicap_calibration_cell_count": len(self.calibration_n),
            "market_residual_cell_count": len(self.market_residual_n),
        }

    def to_payload(self, target_year: int) -> dict[str, object]:
        """Return every fitted value needed to audit the frozen fold model."""
        summary = self.summary(target_year)
        summary.update({
            "global_counts": dict(sorted(self.global_counts.items())),
            "league_counts": {
                key: dict(sorted(value.items())) for key, value in sorted(self.league_counts.items())
            },
            "league_year_counts": {
                f"{key[0]}|{key[1]}": dict(sorted(value.items()))
                for key, value in sorted(self.league_year_counts.items())
            },
            "league_raw_counts": {
                key: dict(sorted(value.items())) for key, value in sorted(self.league_raw_counts.items())
            },
            "league_year_raw_counts": {
                f"{key[0]}|{key[1]}": dict(sorted(value.items()))
                for key, value in sorted(self.league_year_raw_counts.items())
            },
            "handicap_counts": {
                key: dict(sorted(value.items())) for key, value in sorted(self.handicap_counts.items())
            },
            "odds_counts": {
                key: dict(sorted(value.items())) for key, value in sorted(self.odds_counts.items())
            },
            "calibration": {
                f"{key[0]}|{key[1]}": {
                    "n": self.calibration_n[key], "residual_sum": self.calibration_sum[key]
                }
                for key in sorted(self.calibration_n)
            },
            "market_residuals": {
                f"{key[0]}|{key[1]}": {
                    "n": self.market_residual_n[key], "residual_sum": self.market_residual_sum[key]
                }
                for key in sorted(self.market_residual_n)
            },
            "league_goals": {key: value for key, value in sorted(self.league_goals.items())},
            "global_goals": self.global_goals,
        })
        return summary


def blend_probabilities(weighted: Sequence[tuple[Sequence[float], float]]) -> tuple[float, float, float]:
    logs = [0.0, 0.0, 0.0]
    for vector, weight in weighted:
        for index in range(3):
            logs[index] += weight * math.log(max(1e-12, finite(vector[index], 1 / 3)))
    maximum = max(logs)
    return normalize([math.exp(value - maximum) for value in logs])
