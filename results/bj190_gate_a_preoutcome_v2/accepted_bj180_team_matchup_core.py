#!/usr/bin/env python3
"""Outcome-safe chronological team/matchup primitives for Issue #180."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
from collections import Counter, defaultdict, deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

CODES = ("3", "1", "0")
FAMILIES = (
    "LATENT_STRENGTH",
    "HOME_AWAY_SPLIT",
    "ROLLING_FORM",
    "REST_CONGESTION",
    "OPPONENT_ADJUSTMENT",
    "TEAM_INITIALIZATION",
    "H2H_PRIOR",
)
PRIMARY_CONFIG = "TEAM_PRIMARY"
STATE_HALF_LIFE_MATCHES = 12.0
NEW_TEAM_PRIOR_MATCHES = 10.0
CONFIGURATIONS = {
    "TEAM_PRIMARY": {
        "weights": {
            "LATENT_STRENGTH": 0.28,
            "HOME_AWAY_SPLIT": 0.18,
            "ROLLING_FORM": 0.15,
            "REST_CONGESTION": 0.12,
            "OPPONENT_ADJUSTMENT": 0.15,
            "TEAM_INITIALIZATION": 0.09,
            "H2H_PRIOR": 0.03,
        },
    },
    "TEAM_CONSERVATIVE": {
        "weights": {
            "LATENT_STRENGTH": 0.32,
            "HOME_AWAY_SPLIT": 0.16,
            "ROLLING_FORM": 0.10,
            "REST_CONGESTION": 0.08,
            "OPPONENT_ADJUSTMENT": 0.17,
            "TEAM_INITIALIZATION": 0.16,
            "H2H_PRIOR": 0.01,
        },
    },
    "TEAM_RESPONSIVE": {
        "weights": {
            "LATENT_STRENGTH": 0.22,
            "HOME_AWAY_SPLIT": 0.19,
            "ROLLING_FORM": 0.20,
            "REST_CONGESTION": 0.16,
            "OPPONENT_ADJUSTMENT": 0.13,
            "TEAM_INITIALIZATION": 0.06,
            "H2H_PRIOR": 0.04,
        },
    },
}


def validate_configurations() -> None:
    for name, config in CONFIGURATIONS.items():
        weights = config["weights"]
        if tuple(weights) != FAMILIES or abs(sum(weights.values()) - 1.0) > 1e-12:
            raise RuntimeError(f"invalid family weights: {name}")


validate_configurations()


def finite(value: object, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def normalize(values: Sequence[float]) -> tuple[float, float, float]:
    clipped = [max(1e-12, finite(value)) for value in values]
    total = sum(clipped)
    return tuple(value / total for value in clipped)  # type: ignore[return-value]


def parse_ts(value: object) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.replace(tzinfo=None)


def handicap_result(home: object, away: object, handicap: object) -> str:
    margin = finite(home) + finite(handicap) - finite(away)
    return "3" if margin > 1e-9 else "0" if margin < -1e-9 else "1"


def poisson_handicap(
    lambda_home: float, lambda_away: float, handicap: float, max_goals: int = 12
) -> tuple[float, float, float]:
    lambda_home = min(6.0, max(0.08, lambda_home))
    lambda_away = min(6.0, max(0.08, lambda_away))

    def pmf(value: float) -> list[float]:
        rows = [math.exp(-value)]
        for goals in range(1, max_goals + 1):
            rows.append(rows[-1] * value / goals)
        return rows

    counts = Counter({code: 0.0 for code in CODES})
    for home_goals, home_p in enumerate(pmf(lambda_home)):
        for away_goals, away_p in enumerate(pmf(lambda_away)):
            counts[handicap_result(home_goals, away_goals, handicap)] += home_p * away_p
    return normalize([counts[code] for code in CODES])


def log_pool(
    vectors: Mapping[str, Sequence[float]],
    weights: Mapping[str, float],
    excluded: str | None = None,
) -> tuple[float, float, float]:
    active = {name: value for name, value in weights.items() if name != excluded}
    total = sum(active.values())
    if total <= 0:
        raise RuntimeError("empty family pool")
    return normalize(
        [
            math.exp(
                sum(
                    weight / total * math.log(max(1e-12, vectors[name][index]))
                    for name, weight in active.items()
                )
            )
            for index in range(3)
        ]
    )


def blend(
    league: Sequence[float], team: Sequence[float], team_weight: float
) -> tuple[float, float, float]:
    return log_pool(
        {"league": league, "team": team},
        {"league": 1.0 - team_weight, "team": team_weight},
    )


@dataclass
class Ewma:
    value: float = 0.0
    initialized: bool = False

    def update(self, observation: float, alpha: float) -> None:
        self.value = (
            observation
            if not self.initialized
            else alpha * observation + (1.0 - alpha) * self.value
        )
        self.initialized = True


@dataclass
class TeamRecord:
    attack: Ewma = field(default_factory=Ewma)
    defence: Ewma = field(default_factory=Ewma)
    home_attack: Ewma = field(default_factory=Ewma)
    home_defence: Ewma = field(default_factory=Ewma)
    away_attack: Ewma = field(default_factory=Ewma)
    away_defence: Ewma = field(default_factory=Ewma)
    opponent_attack: Ewma = field(default_factory=Ewma)
    opponent_defence: Ewma = field(default_factory=Ewma)
    elo: float = 1500.0
    count: int = 0
    current_league: str = ""
    current_year: int = 0
    league_changes: int = 0
    form: deque[float] = field(default_factory=lambda: deque(maxlen=10))
    timestamps: deque[dt.datetime] = field(default_factory=lambda: deque(maxlen=30))


class TeamMatchupState:
    """Sequential state; callers must update only after a match is completed."""

    def __init__(self) -> None:
        self.teams: dict[str, TeamRecord] = defaultdict(TeamRecord)
        self.league_goals: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
        self.global_goals = [0.0, 0.0, 0.0]
        self.h2h: dict[tuple[str, str], deque[tuple[float, float]]] = defaultdict(
            lambda: deque(maxlen=12)
        )
        self.training_rows = 0
        self.last_update_ts: dt.datetime | None = None
        self.history_event_sha256 = "0" * 64

    @staticmethod
    def _alpha(half_life: float = 12.0) -> float:
        return 1.0 - math.exp(math.log(0.5) / half_life)

    def goal_prior(self, league: str) -> tuple[float, float]:
        global_n = self.global_goals[2]
        global_home = self.global_goals[0] / global_n if global_n else 1.45
        global_away = self.global_goals[1] / global_n if global_n else 1.15
        values = self.league_goals[league]
        return (
            (values[0] + 80.0 * global_home) / (values[2] + 80.0),
            (values[1] + 80.0 * global_away) / (values[2] + 80.0),
        )

    def _transition(self, record: TeamRecord, league: str, year: int) -> None:
        if not record.current_league:
            record.current_league, record.current_year = league, year
            return
        if record.current_year != year:
            if record.current_league != league:
                record.league_changes += 1
                record.elo = 0.75 * record.elo + 0.25 * 1500.0
                for metric in (
                    record.attack,
                    record.defence,
                    record.home_attack,
                    record.home_defence,
                    record.away_attack,
                    record.away_defence,
                    record.opponent_attack,
                    record.opponent_defence,
                ):
                    if metric.initialized:
                        metric.value *= 0.75
            record.current_league, record.current_year = league, year

    def update(self, row: Mapping[str, object]) -> None:
        timestamp = parse_ts(row["kickoff_ts"])
        if self.last_update_ts is not None and timestamp < self.last_update_ts:
            raise RuntimeError("non-chronological team-state update")
        home = str(row.get("home_team_id") or "")
        away = str(row.get("away_team_id") or "")
        if not home or not away:
            return
        home_goals = finite(row.get("fthg"), math.nan)
        away_goals = finite(row.get("ftag"), math.nan)
        if not math.isfinite(home_goals) or not math.isfinite(away_goals):
            return
        league = str(row.get("league") or "__MISSING__")
        year = int(str(row["kickoff_ts"])[:4])
        home_state, away_state = self.teams[home], self.teams[away]
        self._transition(home_state, league, year)
        self._transition(away_state, league, year)
        league_home, league_away = self.goal_prior(league)
        alpha = self._alpha(STATE_HALF_LIFE_MATCHES)
        home_attack_obs = math.log((home_goals + 0.35) / (league_home + 0.35))
        home_defence_obs = math.log((away_goals + 0.35) / (league_away + 0.35))
        away_attack_obs = math.log((away_goals + 0.35) / (league_away + 0.35))
        away_defence_obs = math.log((home_goals + 0.35) / (league_home + 0.35))
        home_state.attack.update(home_attack_obs, alpha)
        home_state.defence.update(home_defence_obs, alpha)
        away_state.attack.update(away_attack_obs, alpha)
        away_state.defence.update(away_defence_obs, alpha)
        home_state.home_attack.update(home_attack_obs, alpha)
        home_state.home_defence.update(home_defence_obs, alpha)
        away_state.away_attack.update(away_attack_obs, alpha)
        away_state.away_defence.update(away_defence_obs, alpha)
        home_state.opponent_attack.update(
            home_attack_obs - away_state.defence.value, alpha
        )
        home_state.opponent_defence.update(
            home_defence_obs - away_state.attack.value, alpha
        )
        away_state.opponent_attack.update(
            away_attack_obs - home_state.defence.value, alpha
        )
        away_state.opponent_defence.update(
            away_defence_obs - home_state.attack.value, alpha
        )
        expected = 1.0 / (
            1.0 + 10.0 ** (-((home_state.elo + 50.0) - away_state.elo) / 400.0)
        )
        actual = (
            1.0 if home_goals > away_goals else 0.0 if home_goals < away_goals else 0.5
        )
        change = (
            18.0
            * max(1.0, min(3.0, abs(home_goals - away_goals)))
            * (actual - expected)
        )
        home_state.elo += change
        away_state.elo -= change
        home_state.form.append(3.0 if actual == 1.0 else 1.0 if actual == 0.5 else 0.0)
        away_state.form.append(3.0 if actual == 0.0 else 1.0 if actual == 0.5 else 0.0)
        home_state.timestamps.append(timestamp)
        away_state.timestamps.append(timestamp)
        home_state.count += 1
        away_state.count += 1
        self.h2h[(home, away)].append((home_goals, away_goals))
        self.league_goals[league][0] += home_goals
        self.league_goals[league][1] += away_goals
        self.league_goals[league][2] += 1.0
        self.global_goals[0] += home_goals
        self.global_goals[1] += away_goals
        self.global_goals[2] += 1.0
        self.training_rows += 1
        self.last_update_ts = timestamp
        event = json.dumps(
            [
                row.get("match_id"),
                timestamp.isoformat(sep=" "),
                league,
                home,
                away,
                finite(row.get("handicap_line_norm")),
                home_goals,
                away_goals,
            ],
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode()
        self.history_event_sha256 = hashlib.sha256(
            bytes.fromhex(self.history_event_sha256) + event
        ).hexdigest()

    @staticmethod
    def _schedule(record: TeamRecord, cutoff: dt.datetime) -> tuple[float, int, int]:
        previous = [timestamp for timestamp in record.timestamps if timestamp < cutoff]
        rest_hours = (
            720.0
            if not previous
            else min(720.0, max(0.0, (cutoff - previous[-1]).total_seconds() / 3600.0))
        )
        in_7d = sum(
            (cutoff - timestamp).total_seconds() <= 7 * 86400 for timestamp in previous
        )
        in_21d = sum(
            (cutoff - timestamp).total_seconds() <= 21 * 86400 for timestamp in previous
        )
        return rest_hours, in_7d, in_21d

    @staticmethod
    def _metric(record: TeamRecord, name: str) -> float:
        metric = getattr(record, name)
        return metric.value if metric.initialized else 0.0

    def family_vectors(
        self, row: Mapping[str, object], cutoff: dt.datetime
    ) -> tuple[dict[str, tuple[float, float, float]], dict[str, object]]:
        home = str(row.get("home_team_id") or "")
        away = str(row.get("away_team_id") or "")
        handicap = finite(row.get("handicap_line_norm"))
        league = str(row.get("league") or "__MISSING__")
        home_state = self.teams[home] if home else TeamRecord()
        away_state = self.teams[away] if away else TeamRecord()
        base_home, base_away = self.goal_prior(league)
        elo_tilt = max(
            -0.28, min(0.28, ((home_state.elo + 50.0) - away_state.elo) / 1800.0)
        )

        def probabilities(home_log: float, away_log: float, tilt: float = 0.0):
            return poisson_handicap(
                base_home * math.exp(max(-0.7, min(0.7, home_log + tilt))),
                base_away * math.exp(max(-0.7, min(0.7, away_log - tilt))),
                handicap,
            )

        latent = probabilities(
            self._metric(home_state, "attack") + self._metric(away_state, "defence"),
            self._metric(away_state, "attack") + self._metric(home_state, "defence"),
            elo_tilt,
        )
        home_away = probabilities(
            self._metric(home_state, "home_attack")
            + self._metric(away_state, "away_defence"),
            self._metric(away_state, "away_attack")
            + self._metric(home_state, "home_defence"),
            elo_tilt,
        )
        home_form = (
            sum(home_state.form) / len(home_state.form) if home_state.form else 1.0
        )
        away_form = (
            sum(away_state.form) / len(away_state.form) if away_state.form else 1.0
        )
        form_tilt = max(-0.20, min(0.20, (home_form - away_form) / 15.0))
        rolling_form = probabilities(0.0, 0.0, form_tilt)
        home_rest, home_7d, home_21d = self._schedule(home_state, cutoff)
        away_rest, away_7d, away_21d = self._schedule(away_state, cutoff)
        rest_tilt = max(
            -0.16,
            min(0.16, (home_rest - away_rest) / 1200.0 - (home_7d - away_7d) * 0.025),
        )
        rest = probabilities(0.0, 0.0, rest_tilt)
        opponent = probabilities(
            self._metric(home_state, "opponent_attack")
            + self._metric(away_state, "opponent_defence"),
            self._metric(away_state, "opponent_attack")
            + self._metric(home_state, "opponent_defence"),
            0.5 * elo_tilt,
        )
        home_depth, away_depth = home_state.count, away_state.count
        init_tilt = elo_tilt * min(
            1.0, min(home_depth, away_depth) / NEW_TEAM_PRIOR_MATCHES
        )
        initialization = probabilities(0.0, 0.0, init_tilt)
        h2h_rows = list(self.h2h.get((home, away), ()))
        h2h_rows.extend(
            (away_goals, home_goals)
            for home_goals, away_goals in self.h2h.get((away, home), ())
        )
        h2h_counts = Counter(handicap_result(hg, ag, handicap) for hg, ag in h2h_rows)
        base = poisson_handicap(base_home, base_away, handicap)
        h2h = normalize(
            [h2h_counts[code] + 12.0 * base[index] for index, code in enumerate(CODES)]
        )
        vectors = {
            "LATENT_STRENGTH": latent,
            "HOME_AWAY_SPLIT": home_away,
            "ROLLING_FORM": rolling_form,
            "REST_CONGESTION": rest,
            "OPPONENT_ADJUSTMENT": opponent,
            "TEAM_INITIALIZATION": initialization,
            "H2H_PRIOR": h2h,
        }
        diagnostics = {
            "home_history_n": home_depth,
            "away_history_n": away_depth,
            "min_history_n": min(home_depth, away_depth),
            "home_elo": home_state.elo,
            "away_elo": away_state.elo,
            "elo_diff": home_state.elo - away_state.elo,
            "home_form_points": home_form,
            "away_form_points": away_form,
            "home_rest_hours": home_rest,
            "away_rest_hours": away_rest,
            "home_matches_7d": home_7d,
            "away_matches_7d": away_7d,
            "home_matches_21d": home_21d,
            "away_matches_21d": away_21d,
            "home_league_changes": home_state.league_changes,
            "away_league_changes": away_state.league_changes,
            "h2h_prior_n": len(h2h_rows),
            "new_team_fallback": int(
                not home or not away or min(home_depth, away_depth) == 0
            ),
        }
        return vectors, diagnostics

    def probabilities(
        self,
        row: Mapping[str, object],
        cutoff: dt.datetime,
        configuration: str = PRIMARY_CONFIG,
        excluded: str | None = None,
    ) -> tuple[
        tuple[float, float, float],
        dict[str, object],
        dict[str, tuple[float, float, float]],
    ]:
        config = CONFIGURATIONS[configuration]
        vectors, diagnostics = self.family_vectors(row, cutoff)
        return log_pool(vectors, config["weights"], excluded), diagnostics, vectors

    def summary(self) -> dict[str, object]:
        return {
            "training_rows": self.training_rows,
            "team_count": len(self.teams),
            "league_count": len(self.league_goals),
            "h2h_pair_count": len(self.h2h),
            "last_update_ts": self.last_update_ts.isoformat(sep=" ")
            if self.last_update_ts
            else "",
            "league_transition_count": sum(
                record.league_changes for record in self.teams.values()
            ),
            "history_event_sha256": self.history_event_sha256,
        }
