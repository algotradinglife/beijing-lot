#!/usr/bin/env python3
"""Freeze #134's outcome-unexposed fundamental/decision-chain FULL-N7 overlay.

The upstream #132 complete-issue portfolio identities are immutable inputs.  This
runner ranks those identical FULL portfolios within each complete issue using
four pre-registered views:

* market-only E_SP/GM_E_SP;
* past-only fundamental confidence;
* existing decision-chain q_max;
* a fixed 50/25/25 market/fundamental/decision overlay.

The SQLite history query is restricted to calendar years strictly before each
target year.  Target rows are read only through identity/rank/market-safe
columns; target outcomes, final SP, settlements and payout fields are never
selected or emitted.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import sqlite3
import gzip
from collections import defaultdict, deque
from pathlib import Path
from typing import Iterable


CONTRACT = "BJ-HIST-FUNDAMENTAL-OVERLAY-N7-001"
ISSUE = 134
UPSTREAM = "results/bj132_gate_a_complete_issue_preoutcome_v1r1"
UPSTREAM_MANIFEST = "6583503ee80fd2b40bb1c000917ff094afa0551b6a3f0af4b8d175a6432872f9"
DB_RELATIVE = "data/derived/beidan_xlsm/beidan_xlsm.sqlite"
DB_SHA256 = "7f62079b18b3c028884da92aa8393f5b198246c9d7c32cd0b401562a055c5d6f"
UNIT_STAKE = 2
FULL_TICKETS = 3**7
K_GRID: tuple[str, ...] = ("1", "2", "4", "8", "16", "ALL")

VARIANTS = {
    "ESP280_GM290_LOWP20": {"e_sp_min": 2.8, "gm_e_sp_min": 2.9, "p_min_max": 0.20},
    "ESP280_GM290_LOWP25": {"e_sp_min": 2.8, "gm_e_sp_min": 2.9, "p_min_max": 0.25},
    "ESP280_GM290_LOWP30": {"e_sp_min": 2.8, "gm_e_sp_min": 2.9, "p_min_max": 0.30},
    "ESP290_GM300_LOWP20": {"e_sp_min": 2.9, "gm_e_sp_min": 3.0, "p_min_max": 0.20},
    "ESP290_GM300_LOWP25": {"e_sp_min": 2.9, "gm_e_sp_min": 3.0, "p_min_max": 0.25},
    "ESP290_GM300_LOWP30": {"e_sp_min": 2.9, "gm_e_sp_min": 3.0, "p_min_max": 0.30},
    "ESP300_GM305_LOWP20": {"e_sp_min": 3.0, "gm_e_sp_min": 3.05, "p_min_max": 0.20},
    "ESP300_GM305_LOWP25": {"e_sp_min": 3.0, "gm_e_sp_min": 3.05, "p_min_max": 0.25},
    "ESP300_GM305_LOWP30": {"e_sp_min": 3.0, "gm_e_sp_min": 3.05, "p_min_max": 0.30},
}
ARMS = (
    ("MARKET_E_SP_GM", "market_percentile", "market-only E_SP/GM_E_SP FULL baseline"),
    ("FUNDAMENTALS_ONLY", "fundamental_percentile", "past-only strength/form/rank/rest confidence"),
    ("DECISION_CHAIN_ONLY", "decision_percentile", "existing q=p*predicted_SP decision-chain score"),
    ("FUNDAMENTALS_PLUS_DECISION", "combined_percentile", "0.50 market + 0.25 fundamental + 0.25 decision"),
)
TARGET_FIELDS = (
    "match_id", "issue", "match_idx", "kickoff_ts", "year", "league",
    "home_team_id", "away_team_id", "home_rank", "away_rank", "handicap_line_norm",
)
HISTORY_FIELDS = ("match_id", "kickoff_ts", "season_year", "home_team_id", "away_team_id", "fthg", "ftag")


def find_root() -> Path:
    candidates = [Path(__file__).resolve().parents[1], Path(__file__).resolve().parents[2], Path(__file__).resolve().parents[3]]
    for candidate in candidates:
        if (candidate / ".git").exists() and (candidate / "results").is_dir():
            return candidate
    raise RuntimeError("repository root unavailable")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def write_csv(path: Path, rows: Iterable[dict[str, object]], fields: list[str] | None = None) -> int:
    rows = list(rows)
    if not rows:
        raise RuntimeError(f"empty output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = fields or sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def verify_manifest(package: Path, expected: str) -> None:
    manifest = package / "SHA256SUMS.json"
    if sha256(manifest) != expected:
        raise RuntimeError("upstream manifest hash changed")
    checksums = json.loads(manifest.read_text(encoding="utf-8"))
    for name, value in checksums.items():
        if sha256(package / name) != value:
            raise RuntimeError(f"upstream payload hash mismatch: {name}")


def parse_rank(value: object) -> float:
    text = str(value or "")
    digits = "".join(ch for ch in text if ch.isdigit() or ch == ".")
    try:
        return float(digits) if digits else 0.0
    except ValueError:
        return 0.0


def parse_ts(value: object) -> dt.datetime | None:
    text = str(value or "")
    try:
        return dt.datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def parse_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class TeamState:
    """Past-only team state; no target-year outcomes are ever fed into it."""

    def __init__(self) -> None:
        self.elo: dict[str, float] = defaultdict(lambda: 1500.0)
        self.form: dict[str, deque[tuple[float, float]]] = defaultdict(lambda: deque(maxlen=10))
        self.count: dict[str, int] = defaultdict(int)
        self.last_ts: dict[str, dt.datetime] = {}

    def snapshot(self, row: dict[str, object]) -> dict[str, float]:
        home = str(row.get("home_team_id") or "")
        away = str(row.get("away_team_id") or "")
        home_elo = self.elo[home] if home else 1500.0
        away_elo = self.elo[away] if away else 1500.0
        home_form = self.form_value(home)
        away_form = self.form_value(away)
        home_rank = parse_rank(row.get("home_rank"))
        away_rank = parse_rank(row.get("away_rank"))
        rank_diff = (away_rank - home_rank) if home_rank and away_rank else 0.0
        now = parse_ts(row.get("kickoff_ts"))
        home_rest = self.rest_hours(home, now)
        away_rest = self.rest_hours(away, now)
        rest_diff = max(-1.0, min(1.0, (home_rest - away_rest) / 720.0))
        depth = min(self.count[home], self.count[away]) if home and away else 0
        elo_diff = (home_elo + 50.0) - away_elo
        form_diff = home_form - away_form
        rank_component = max(-3.0, min(3.0, rank_diff / 10.0))
        margin = 0.70 * (elo_diff / 400.0) + 0.20 * (form_diff / 3.0) + 0.10 * rank_component + 0.05 * rest_diff
        logits = (margin, 0.0, -margin)
        exp_values = [math.exp(max(-40.0, min(40.0, value))) for value in logits]
        total = sum(exp_values)
        probs = [value / total for value in exp_values]
        entropy = -sum(p * math.log(p) for p in probs if p > 0) / math.log(3.0)
        confidence = max(probs)
        return {
            "elo_diff": elo_diff,
            "form_diff": form_diff,
            "rank_diff": rank_diff,
            "rest_diff": rest_diff,
            "history_depth": float(depth),
            "fundamental_p3": probs[0],
            "fundamental_p1": probs[1],
            "fundamental_p0": probs[2],
            "fundamental_confidence": confidence,
            "fundamental_entropy": entropy,
            "fundamental_missing": 1.0 if not home or not away or depth == 0 else 0.0,
        }

    def form_value(self, team: str) -> float:
        values = self.form[team]
        if not values:
            return 0.0
        return sum(points + goal_diff / 3.0 for points, goal_diff in values) / len(values)

    def rest_hours(self, team: str, now: dt.datetime | None) -> float:
        if not team or now is None or team not in self.last_ts:
            return 720.0
        return max(0.0, min(720.0, (now - self.last_ts[team]).total_seconds() / 3600.0))

    def update(self, row: dict[str, object]) -> None:
        home = str(row.get("home_team_id") or "")
        away = str(row.get("away_team_id") or "")
        if not home or not away:
            return
        try:
            home_goals, away_goals = int(float(row["fthg"])), int(float(row["ftag"]))
        except (KeyError, TypeError, ValueError):
            return
        margin = max(-3, min(3, home_goals - away_goals))
        expected = 1.0 / (1.0 + 10.0 ** (-((self.elo[home] + 50.0) - self.elo[away]) / 400.0))
        actual = 1.0 if home_goals > away_goals else 0.0 if home_goals < away_goals else 0.5
        multiplier = max(1.0, float(abs(margin)))
        self.elo[home] += 20.0 * multiplier * (actual - expected)
        self.elo[away] -= 20.0 * multiplier * (actual - expected)
        home_points = 3.0 if actual == 1.0 else 0.0 if actual == 0.0 else 1.0
        away_points = 3.0 - home_points if actual != 0.5 else 1.0
        self.form[home].append((home_points, max(-3, min(3, home_goals - away_goals))))
        self.form[away].append((away_points, max(-3, min(3, away_goals - home_goals))))
        self.count[home] += 1
        self.count[away] += 1
        timestamp = parse_ts(row.get("kickoff_ts"))
        if timestamp is not None:
            self.last_ts[home] = timestamp
            self.last_ts[away] = timestamp


def read_role_rows(package: Path) -> tuple[dict[tuple[str, str], dict[str, object]], set[int]]:
    groups: dict[tuple[str, str], dict[str, object]] = {}
    match_ids: set[int] = set()
    with gzip.open(package / "portfolio_role_assignments.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            variant = row["variant_id"]
            if variant not in VARIANTS:
                raise RuntimeError(f"unexpected variant {variant}")
            key = (variant, row["portfolio_id"])
            group = groups.setdefault(key, {"variant_id": variant, "portfolio_id": row["portfolio_id"], "issue": row["issue"], "fold": row["fold"], "year": int(row["year"]), "issue_instance": row["issue_instance"], "legs": []})
            group["legs"].append({
                "match_id": int(row["match_id"]),
                "match_idx": int(row["match_idx"]),
                "e_sp": float(row["e_sp"]),
                "q_max": max(float(row["q3"]), float(row["q1"]), float(row["q0"])),
            })
            match_ids.add(int(row["match_id"]))
    if not groups or any(len(group["legs"]) != 7 for group in groups.values()):
        raise RuntimeError("role assignments are not complete N7 identities")
    return groups, match_ids


def ro_connection(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path.resolve()}?mode=ro&immutable=1", uri=True)


def read_target_features(db: Path, match_ids: set[int]) -> dict[int, dict[str, object]]:
    connection = ro_connection(db)
    rows: dict[int, dict[str, object]] = {}
    ids = sorted(match_ids)
    for start in range(0, len(ids), 800):
        chunk = ids[start:start + 800]
        placeholders = ",".join("?" for _ in chunk)
        query = f"""
            SELECT m.match_id, m.issue, m.match_idx, m.kickoff_ts, mf.season_year,
                   m.league, m.home_team_id, m.away_team_id, m.home_rank, m.away_rank,
                   mf.handicap_line_norm
              FROM matches m JOIN match_features mf ON mf.match_id=m.match_id
             WHERE m.match_id IN ({placeholders})
        """
        for row in connection.execute(query, chunk):
            rows[int(row[0])] = dict(zip(TARGET_FIELDS, row))
    connection.close()
    if set(rows) != match_ids:
        raise RuntimeError(f"target safe-feature join drift: {len(rows)} / {len(match_ids)}")
    return rows


def history_for_year(db: Path, year: int) -> list[dict[str, object]]:
    connection = ro_connection(db)
    query = """
        SELECT m.match_id, m.kickoff_ts, mf.season_year, m.home_team_id,
               m.away_team_id, mf.fthg, mf.ftag
          FROM matches m JOIN match_features mf ON mf.match_id=m.match_id
         WHERE mf.season_year IS NOT NULL AND mf.season_year < ?
           AND m.home_team_id IS NOT NULL AND m.away_team_id IS NOT NULL
         ORDER BY m.kickoff_ts, m.match_id
    """
    rows = [dict(zip(HISTORY_FIELDS, row)) for row in connection.execute(query, (year,))]
    connection.close()
    return rows


def build_feature_scores(db: Path, target: dict[int, dict[str, object]]) -> dict[int, dict[str, object]]:
    by_year: dict[int, list[dict[str, object]]] = defaultdict(list)
    for row in target.values():
        by_year[int(row["year"])].append(row)
    output: dict[int, dict[str, object]] = {}
    for year in sorted(by_year):
        state = TeamState()
        for history in history_for_year(db, year):
            state.update(history)
        for row in by_year[year]:
            features = state.snapshot(row)
            output[int(row["match_id"])] = {**row, **features}
    if set(output) != set(target):
        raise RuntimeError("fundamental feature output drift")
    return output


def validate_identity_join(groups: dict[tuple[str, str], dict[str, object]], target: dict[int, dict[str, object]]) -> None:
    for group in groups.values():
        for leg in group["legs"]:
            row = target[leg["match_id"]]
            if str(row["issue"]) != str(group["issue"]):
                raise RuntimeError("target issue identity drift")
            if int(row["match_idx"]) != int(leg["match_idx"]):
                raise RuntimeError("target match_idx identity drift")
            if int(row["year"]) != int(group["year"]):
                raise RuntimeError("target year identity drift")


def geometric(values: list[float]) -> float:
    if not values or any(value <= 0 for value in values):
        return 0.0
    return math.exp(sum(math.log(value) for value in values) / len(values))


def percentile(values: list[tuple[str, float]]) -> dict[str, float]:
    ordered = sorted(values, key=lambda item: (-item[1], item[0]))
    denominator = max(1, len(ordered) - 1)
    return {key: 1.0 - index / denominator for index, (key, _) in enumerate(ordered)}


def compact(value: float) -> str:
    return f"{value:.12f}"


def build_portfolio_scores(groups: dict[tuple[str, str], dict[str, object]], features: dict[int, dict[str, object]]) -> list[dict[str, object]]:
    by_issue: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for group in groups.values():
        legs = group["legs"]
        fundamental = [float(features[leg["match_id"]]["fundamental_confidence"]) for leg in legs]
        market = geometric([float(leg["e_sp"]) for leg in legs])
        decision = geometric([float(leg["q_max"]) for leg in legs])
        fundamental_raw = geometric(fundamental)
        group["market_raw"] = market
        group["fundamental_raw"] = fundamental_raw
        group["decision_raw"] = decision
        group["fundamental_missing_fraction"] = sum(float(features[leg["match_id"]]["fundamental_missing"]) for leg in legs) / 7.0
        by_issue[(str(group["variant_id"]), str(group["issue_instance"]))].append(group)
    rows: list[dict[str, object]] = []
    for (variant, issue_instance), issue_groups in sorted(by_issue.items()):
        market_rank = percentile([(str(group["portfolio_id"]), float(group["market_raw"])) for group in issue_groups])
        fundamental_rank = percentile([(str(group["portfolio_id"]), float(group["fundamental_raw"])) for group in issue_groups])
        decision_rank = percentile([(str(group["portfolio_id"]), float(group["decision_raw"])) for group in issue_groups])
        for group in issue_groups:
            pid = str(group["portfolio_id"])
            combined = 0.50 * market_rank[pid] + 0.25 * fundamental_rank[pid] + 0.25 * decision_rank[pid]
            group["market_percentile"] = market_rank[pid]
            group["fundamental_percentile"] = fundamental_rank[pid]
            group["decision_percentile"] = decision_rank[pid]
            group["combined_percentile"] = combined
            legs = group["legs"]
            row = {
                "variant_id": variant, "portfolio_id": pid, "issue": group["issue"], "fold": group["fold"],
                "year": group["year"], "issue_instance": issue_instance, "candidate_count_complete_issue": len(issue_groups),
                "selected_match_ids": ";".join(str(leg["match_id"]) for leg in sorted(legs, key=lambda x: x["match_idx"])),
                "market_gm_e_sp": compact(float(group["market_raw"])),
                "fundamental_gm_confidence": compact(float(group["fundamental_raw"])),
                "decision_gm_q_max": compact(float(group["decision_raw"])),
                "fundamental_missing_fraction": compact(float(group["fundamental_missing_fraction"])),
                "market_percentile": compact(float(group["market_percentile"])),
                "fundamental_percentile": compact(float(group["fundamental_percentile"])),
                "decision_percentile": compact(float(group["decision_percentile"])),
                "combined_percentile": compact(float(group["combined_percentile"])),
                "full_ticket_count": FULL_TICKETS, "full_stake_yuan": FULL_TICKETS * UNIT_STAKE,
                "outcome_boundary": "NO_TARGET_OUTCOME_OR_SETTLEMENT",
            }
            rows.append(row)
    return rows


def build_frontier(scores: list[dict[str, object]]) -> list[dict[str, object]]:
    by_issue: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
    for row in scores:
        by_issue[(str(row["variant_id"]), str(row["issue_instance"]))].append(row)
    frontier: list[dict[str, object]] = []
    for variant, issue_instance in sorted(by_issue):
        rows = by_issue[(variant, issue_instance)]
        for arm, score_field, _ in ARMS:
            ordered = sorted(rows, key=lambda row: (-float(row[score_field]), str(row["portfolio_id"])))
            for k_text in K_GRID:
                requested = len(ordered) if k_text == "ALL" else int(k_text)
                available = k_text == "ALL" or len(ordered) >= requested
                selected = ordered if k_text == "ALL" else ordered[:requested] if available else []
                ids = ";".join(str(row["portfolio_id"]) for row in selected)
                plan_id = hashlib.sha256(f"{CONTRACT}|{variant}|{issue_instance}|{arm}|K{k_text}".encode()).hexdigest()
                frontier.append({
                    "plan_id": plan_id, "variant_id": variant, "issue_instance": issue_instance,
                    "issue": rows[0]["issue"], "fold": rows[0]["fold"], "year": rows[0]["year"],
                    "arm": arm, "k": k_text, "candidate_count_complete_issue": len(ordered),
                    "selected_count": len(selected), "selected_portfolio_ids": ids,
                    "stake_yuan": len(selected) * FULL_TICKETS * UNIT_STAKE,
                    "status": "AVAILABLE" if available else "NO_BET_K_UNSATISFIED",
                    "selection_rule": score_field, "matched_budget": "same K FULL identities and stake across arms",
                    "outcome_boundary": "NO_TARGET_OUTCOME_OR_SETTLEMENT",
                })
    return frontier


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    root = find_root()
    output = args.output.resolve() if args.output else root / "results/bj134_gate_a_preoutcome_v1"
    if output.exists():
        raise RuntimeError(f"refusing overwrite: {output}")
    output.mkdir(parents=True)
    upstream = root / UPSTREAM
    verify_manifest(upstream, UPSTREAM_MANIFEST)
    db_candidates = [root / DB_RELATIVE]
    if len(root.parents) > 3:
        db_candidates.append(root.parents[3] / DB_RELATIVE)
    db = next((candidate for candidate in db_candidates if candidate.exists()), None)
    if db is None:
        raise RuntimeError("source database unavailable")
    if sha256(db) != DB_SHA256:
        raise RuntimeError("source database hash changed")
    groups, match_ids = read_role_rows(upstream)
    target = read_target_features(db, match_ids)
    validate_identity_join(groups, target)
    features = build_feature_scores(db, target)
    scores = build_portfolio_scores(groups, features)
    frontier = build_frontier(scores)
    feature_rows = []
    for match_id in sorted(features):
        row = features[match_id]
        feature_rows.append({
            "match_id": match_id, "issue": row["issue"], "match_idx": row["match_idx"], "kickoff_ts": row["kickoff_ts"],
            "year": row["year"], "league": row["league"], "home_team_id": row["home_team_id"], "away_team_id": row["away_team_id"],
            "home_rank": row["home_rank"], "away_rank": row["away_rank"], "handicap_line_norm": row["handicap_line_norm"],
            **{key: compact(float(row[key])) for key in ("elo_diff", "form_diff", "rank_diff", "rest_diff", "history_depth", "fundamental_p3", "fundamental_p1", "fundamental_p0", "fundamental_confidence", "fundamental_entropy", "fundamental_missing")},
            "feature_boundary": "prior calendar years only; target outcomes not selected",
        })
    write_csv(output / "match_feature_scores.csv", feature_rows)
    write_csv(output / "portfolio_scores.csv", scores)
    write_csv(output / "selection_frontier.csv", frontier)
    ablation_rows = [{"arm": arm, "score_field": field, "definition": definition, "market_component": "yes" if arm in ("MARKET_E_SP_GM", "FUNDAMENTALS_PLUS_DECISION") else "no", "fundamental_component": "yes" if arm in ("FUNDAMENTALS_ONLY", "FUNDAMENTALS_PLUS_DECISION") else "no", "decision_chain_component": "yes" if arm in ("DECISION_CHAIN_ONLY", "FUNDAMENTALS_PLUS_DECISION") else "no"} for arm, field, definition in ARMS]
    write_csv(output / "feature_family_ablation.csv", ablation_rows)
    threshold_rows = []
    for variant, rule in VARIANTS.items():
        subset = [row for row in scores if row["variant_id"] == variant]
        issue_count = len({row["issue_instance"] for row in subset})
        threshold_rows.append({"variant_id": variant, **rule, "portfolio_rows": len(subset), "issue_instances": issue_count, "k_grid": ";".join(K_GRID), "arms": len(ARMS), "outcome_boundary": "NO_TARGET_OUTCOME_OR_SETTLEMENT"})
    write_csv(output / "threshold_census.csv", threshold_rows)
    source_rows = [
        {"source": UPSTREAM, "role": "immutable complete-issue candidate roles", "sha256": sha256(upstream / "SHA256SUMS.json"), "rows": len(scores), "boundary": "outcome-unexposed upstream package"},
        {"source": DB_RELATIVE, "role": "target safe identity/rank plus strictly-prior history state", "sha256": DB_SHA256, "rows": len(target), "boundary": "target selects no result/score/SP/settlement columns; history query uses season_year < target year"},
    ]
    write_csv(output / "source_census.csv", source_rows)
    card = {
        "issue": ISSUE, "contract": CONTRACT, "stage": "GATE_A_OUTCOME_UNEXPOSED_FULL_N7_OVERLAY_FREEZE", "generator_version": "bj134-gate-a-v1",
        "upstream": {"package": UPSTREAM, "manifest_sha256": UPSTREAM_MANIFEST, "identity_scope": "#132 complete-issue matched FULL N7 identities; no candidate search or allocation rewrite"},
        "arms": {arm: {"score_field": field, "definition": definition} for arm, field, definition in ARMS},
        "candidate_contract": {"primary_unit": "complete (issue, fold) issue instance", "candidate_universe": "all #132 complete-issue FULL N7 identities within each frozen threshold variant", "rank_scope": "within variant × complete issue; no source segment is a selection unit", "k_grid": list(K_GRID), "insufficient_k": "explicit NO_BET_K_UNSATISFIED; no borrowing or cap relaxation", "stake": f"K × {FULL_TICKETS} FULL tickets × ¥{UNIT_STAKE}; identical across arms"},
        "feature_contract": {"fundamental": "past-only Elo, rolling points/goal-difference, rank differential, rest and history-depth confidence; fixed constants, no target-year outcomes", "decision_chain": "existing #132 q=p×predicted_SP q_max geometric mean", "market": "existing #132 E_SP geometric mean", "combined": "within-issue percentile score = 0.50 market + 0.25 fundamental + 0.25 decision", "missing_data": "missing team IDs/history yields neutral fundamental probabilities and retained explicit missingness; no silent drop"},
        "threshold_grid": VARIANTS,
        "chronology": {"target_years": sorted({int(row["year"]) for row in target.values()}), "history_rule": "for target year y, history query is season_year < y; no target-year result is read or used", "same_issue": "all frozen identities for an issue remain intact; selection is issue-level"},
        "output_boundary": "No target result, score, final SP, winning SP, payout, tax, ROI, settlement, or post-kickoff field is selected or emitted. Gate B is unauthorized pending PI review.",
        "scope": "historical paper research only; no purchase, production, betting or promotion authority",
        "counts": {"portfolio_rows": len(scores), "unique_target_matches": len(features), "frontier_rows": len(frontier), "feature_rows": len(feature_rows)},
    }
    (output / "gate_a_card.json").write_text(dump(card), encoding="utf-8")
    readme = "# #134 Gate A: fundamental and decision-chain overlay\n\nThis package freezes an outcome-unexposed, issue-level matched FULL N7 comparison on the immutable #132 candidate identities. Gate B is unauthorized. Replay with `python3 freeze_runner.py --output <new-dir>`; staging stays beside the output and never uses `/tmp`.\n"
    (output / "README.md").write_text(readme, encoding="utf-8")
    content = {"contract": CONTRACT, "card_sha256": sha256(output / "gate_a_card.json"), "portfolio_rows": len(scores), "frontier_rows": len(frontier), "feature_rows": len(feature_rows)}
    (output / "CONTENT_IDENTITY.json").write_text(dump(content), encoding="utf-8")
    shutil_copy = output / "freeze_runner.py"
    source = Path(__file__).resolve()
    shutil_copy.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    payloads = [path for path in sorted(output.iterdir()) if path.name != "SHA256SUMS.json"]
    checksums = {path.name: sha256(path) for path in payloads}
    (output / "SHA256SUMS.json").write_text(dump(checksums), encoding="utf-8")
    print(dump({"output": str(output), "manifest_sha256": sha256(output / "SHA256SUMS.json"), "counts": card["counts"], "target_years": card["chronology"]["target_years"]}))


if __name__ == "__main__":
    main()
