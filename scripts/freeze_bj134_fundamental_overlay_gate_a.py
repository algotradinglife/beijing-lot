#!/usr/bin/env python3
"""Freeze #134's replacement outcome-unexposed FULL-N7 overlay Gate A.

The immutable #167 K_ALL selector is the common issue-level candidate universe.
Its K1 rank-1 identity is the exact BEST_FULL market incumbent.  Three overlay
views re-rank only those same candidates; all four views retain the same 189
participating issues, 159 frozen no-bet issues, K1 identity count, FULL ticket
enumeration, and stake.  #170 Gate B is hash-bound but never parsed.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import math
import os
import shutil
import sqlite3
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Iterable, Sequence


CONTRACT = "BJ-HIST-FUNDAMENTAL-OVERLAY-N7-001"
VERSION = "bj134-gate-a-v2"
ISSUE = 134
UNIT_STAKE_YUAN = 2
FULL_TICKETS = 3 ** 7
FULL_STAKE_YUAN = UNIT_STAKE_YUAN * FULL_TICKETS
DB_REPOSITORY_PATH = Path("data/derived/beidan_xlsm/beidan_xlsm.sqlite")
DB_SHA256 = "7f62079b18b3c028884da92aa8393f5b198246c9d7c32cd0b401562a055c5d6f"

SOURCE_167 = "bj167_gate_a_strategy_atlas_v3r1"
SOURCE_167_MANIFEST = "5a82422755723453638d25c90f91213da046a9e7bed87a851b2e5700faa9c724"
SOURCE_167_CONTENT = "0806185a7a68b99fd2a6a465308d11e2886995f992bfa722adb287a4e6a4d147"
SOURCE_170_A = "bj170_gate_a_preoutcome_v2"
SOURCE_170_A_MANIFEST = "bb60ac5638d29674ad8c1c05f1ffe3ab9cdf12acb70ebdae6cea679743136d87"
SOURCE_170_A_CONTENT = "adc4d0f96628c784149da998a20e8830cde26db4001fe457eaf9ca4b7bb74223"
SOURCE_170_B = "bj170_gate_b_selector_allocator_stack_v1"
SOURCE_170_B_MANIFEST = "08e83353ad483e5d75911116a413186f007385f5dd37b8c4b757ac903221e512"
SOURCE_170_B_CONTENT = "75325aa0f60e277ad3fbf9d90116450833106bc3863b412ea3efcad9948a47b2"

K1_SELECTOR = "S2_ESP290_GM300_MARKET_WF_CAL_MIN_LOWP20_COLD_FIRST_K1"
KALL_SELECTOR = "S2_ESP290_GM300_MARKET_WF_CAL_MIN_LOWP20_COLD_FIRST_K_ALL"
OUTCOME_BOUNDARY = (
    "Gate A outcome-unexposed: target result/final-SP/payout/tax/ROI/settlement "
    "fields are neither selected nor emitted"
)

ARMS = (
    ("MARKET_BEST_FULL", "market_percentile", "exact #167 K_ALL COLD_FIRST rank; reproduces BEST_FULL K1"),
    ("FUNDAMENTALS_ONLY", "fundamental_percentile", "strictly-prior-year Elo/form/rank/rest confidence"),
    ("DECISION_CHAIN_ONLY", "decision_percentile", "existing q=p×predicted_SP role-product confidence"),
    ("FUNDAMENTALS_PLUS_DECISION", "combined_percentile", "fixed 0.50 market + 0.25 fundamental + 0.25 decision percentile overlay"),
)
TARGET_FIELDS = (
    "match_id", "issue", "match_idx", "kickoff_ts", "year", "league",
    "home_team_id", "away_team_id", "home_rank", "away_rank", "handicap_line_norm",
)
HISTORY_FIELDS = (
    "match_id", "kickoff_ts", "season_year", "home_team_id", "away_team_id", "fthg", "ftag",
)


def repo_root() -> Path:
    for candidate in (Path(__file__).resolve().parent, *Path(__file__).resolve().parents):
        if (candidate / ".git").exists() and (candidate / "results").is_dir():
            return candidate
    raise RuntimeError("repository root unavailable")


ROOT = repo_root()
GATE_A_167 = ROOT / "results" / SOURCE_167
GATE_A_170 = ROOT / "results" / SOURCE_170_A
GATE_B_170 = ROOT / "results" / SOURCE_170_B
DEFAULT_OUTPUT = ROOT / "results" / "bj134_gate_a_preoutcome_v2"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def dump_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fields: Sequence[str], rows: Iterable[dict[str, object]]) -> int:
    materialized = list(rows)
    if not materialized:
        raise RuntimeError(f"refusing empty CSV: {path.name}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise", lineterminator="\n")
        writer.writeheader()
        writer.writerows(materialized)
    return len(materialized)


def write_gzip(path: Path, fields: Sequence[str], rows: Iterable[dict[str, object]]) -> int:
    materialized = list(rows)
    if not materialized:
        raise RuntimeError(f"refusing empty gzip CSV: {path.name}")
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            text = io.TextIOWrapper(zipped, encoding="utf-8", newline="")
            writer = csv.DictWriter(text, fieldnames=fields, extrasaction="raise", lineterminator="\n")
            writer.writeheader()
            writer.writerows(materialized)
            text.flush()
            text.detach()
    return len(materialized)


def verify_package(directory: Path, expected_manifest: str, expected_content: str) -> dict[str, str]:
    manifest_path = directory / "SHA256SUMS.json"
    content_path = directory / "CONTENT_IDENTITY.json"
    if sha256_file(manifest_path) != expected_manifest:
        raise RuntimeError(f"manifest drift: {directory.name}")
    if sha256_file(content_path) != expected_content:
        raise RuntimeError(f"content identity drift: {directory.name}")
    declared = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = sorted(path.name for path in directory.iterdir() if path.is_file() and path.name != "SHA256SUMS.json")
    if sorted(declared) != actual:
        raise RuntimeError(f"manifest coverage drift: {directory.name}")
    for name, expected in declared.items():
        if sha256_file(directory / name) != expected:
            raise RuntimeError(f"payload drift: {directory.name}/{name}")
    return declared


def locate_database(root: Path = ROOT) -> Path:
    candidates = [root / DB_REPOSITORY_PATH]
    candidates.extend(parent / DB_REPOSITORY_PATH for parent in root.parents)
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    raise RuntimeError("canonical source database unavailable")


def ro_connection(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path.resolve()}?mode=ro&immutable=1", uri=True)


def parse_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_rank(value: object) -> float:
    text = str(value or "")
    digits = "".join(ch for ch in text if ch.isdigit() or ch == ".")
    return parse_float(digits)


def parse_ts(value: object) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(str(value or "").replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def geometric(values: Sequence[float]) -> float:
    if not values or any(value <= 0 or not math.isfinite(value) for value in values):
        return 0.0
    return math.exp(sum(math.log(value) for value in values) / len(values))


def percentile(values: Sequence[tuple[str, float]]) -> dict[str, float]:
    ordered = sorted(values, key=lambda item: (-item[1], item[0]))
    denominator = max(1, len(ordered) - 1)
    return {key: 1.0 - index / denominator for index, (key, _) in enumerate(ordered)}


def compact(value: float) -> str:
    return f"{value:.12f}"


class TeamState:
    """Deterministic team state updated only from strictly prior calendar years."""

    def __init__(self) -> None:
        self.elo: dict[str, float] = defaultdict(lambda: 1500.0)
        self.form: dict[str, deque[tuple[float, float]]] = defaultdict(lambda: deque(maxlen=10))
        self.count: dict[str, int] = defaultdict(int)
        self.last_ts: dict[str, dt.datetime] = {}

    def form_value(self, team: str) -> float:
        values = self.form[team]
        return 0.0 if not values else sum(points + goal_diff / 3.0 for points, goal_diff in values) / len(values)

    def rest_hours(self, team: str, now: dt.datetime | None) -> float:
        if not team or now is None or team not in self.last_ts:
            return 720.0
        return max(0.0, min(720.0, (now - self.last_ts[team]).total_seconds() / 3600.0))

    def snapshot(self, row: dict[str, object]) -> dict[str, float]:
        home, away = str(row.get("home_team_id") or ""), str(row.get("away_team_id") or "")
        home_elo, away_elo = self.elo[home] if home else 1500.0, self.elo[away] if away else 1500.0
        home_rank, away_rank = parse_rank(row.get("home_rank")), parse_rank(row.get("away_rank"))
        rank_diff = away_rank - home_rank if home_rank and away_rank else 0.0
        now = parse_ts(row.get("kickoff_ts"))
        rest_diff = max(-1.0, min(1.0, (self.rest_hours(home, now) - self.rest_hours(away, now)) / 720.0))
        depth = min(self.count[home], self.count[away]) if home and away else 0
        elo_diff = (home_elo + 50.0) - away_elo
        form_diff = self.form_value(home) - self.form_value(away)
        rank_component = max(-3.0, min(3.0, rank_diff / 10.0))
        margin = 0.70 * (elo_diff / 400.0) + 0.20 * (form_diff / 3.0) + 0.10 * rank_component + 0.05 * rest_diff
        exp_values = [math.exp(max(-40.0, min(40.0, value))) for value in (margin, 0.0, -margin)]
        total = sum(exp_values)
        probs = [value / total for value in exp_values]
        entropy = -sum(p * math.log(p) for p in probs if p > 0) / math.log(3.0)
        return {
            "elo_diff": elo_diff, "form_diff": form_diff, "rank_diff": rank_diff,
            "rest_diff": rest_diff, "history_depth": float(depth),
            "fundamental_p3": probs[0], "fundamental_p1": probs[1], "fundamental_p0": probs[2],
            "fundamental_confidence": max(probs), "fundamental_entropy": entropy,
            "fundamental_missing": 1.0 if not home or not away or depth == 0 else 0.0,
        }

    def update(self, row: dict[str, object]) -> None:
        home, away = str(row.get("home_team_id") or ""), str(row.get("away_team_id") or "")
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
        self.form[home].append((home_points, float(margin)))
        self.form[away].append((away_points, float(-margin)))
        self.count[home] += 1
        self.count[away] += 1
        timestamp = parse_ts(row.get("kickoff_ts"))
        if timestamp is not None:
            self.last_ts[home] = timestamp
            self.last_ts[away] = timestamp


def relevant_shards(kind: str) -> list[Path]:
    paths = [
        GATE_A_167 / row["filename"]
        for row in read_csv(GATE_A_167 / "shard_index.csv")
        if row["kind"] == kind
    ]
    if not paths:
        raise RuntimeError(f"no {kind} shards")
    return paths


def load_frozen_inputs() -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    selector_grid = [row for row in read_csv(GATE_A_167 / "selector_grid.csv") if row["selector_id"] in {K1_SELECTOR, KALL_SELECTOR}]
    if {row["selector_id"] for row in selector_grid} != {K1_SELECTOR, KALL_SELECTOR}:
        raise RuntimeError("selector registry incomplete")
    census = [row for row in read_csv(GATE_A_167 / "selector_census.csv") if row["selector_id"] in {K1_SELECTOR, KALL_SELECTOR}]
    if Counter(row["selector_id"] for row in census) != {K1_SELECTOR: 348, KALL_SELECTOR: 348}:
        raise RuntimeError("selector census drift")

    identities: list[dict[str, str]] = []
    for path in relevant_shards("selector_identities"):
        with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
            identities.extend(row for row in csv.DictReader(handle) if row["selector_id"] in {K1_SELECTOR, KALL_SELECTOR})
    k1 = [row for row in identities if row["selector_id"] == K1_SELECTOR]
    kall = [row for row in identities if row["selector_id"] == KALL_SELECTOR]
    if len(k1) != 189 or len(kall) != 424:
        raise RuntimeError(f"identity denominator drift: K1={len(k1)} KALL={len(kall)}")
    k1_keys = {(row["issue_instance"], row["portfolio_id"]) for row in k1}
    rank1_keys = {(row["issue_instance"], row["portfolio_id"]) for row in kall if row["selector_rank"] == "1"}
    if k1_keys != rank1_keys:
        raise RuntimeError("K1 does not reproduce K_ALL rank 1")

    candidate_keys = {(row["issue_instance"], row["portfolio_id"]) for row in kall}
    roles: list[dict[str, str]] = []
    for path in relevant_shards("selector_role_vectors"):
        with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
            roles.extend(
                row for row in csv.DictReader(handle)
                if row["selector_id"] == KALL_SELECTOR and (row["issue_instance"], row["portfolio_id"]) in candidate_keys
            )
    if len(roles) != len(kall) * 7:
        raise RuntimeError(f"role denominator drift: {len(roles)}")

    with gzip.open(GATE_A_170 / "identity_freeze.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        best170 = [row for row in csv.DictReader(handle) if row["selector_alias"] == "BEST_FULL"]
    participation170 = [row for row in read_csv(GATE_A_170 / "selector_issue_participation.csv") if row["selector_alias"] == "BEST_FULL"]
    if len(best170) != 189 or len(participation170) != 348:
        raise RuntimeError("#170 BEST_FULL denominator drift")
    best170_keys = {(row["issue_instance"], row["portfolio_id"]) for row in best170}
    if best170_keys != k1_keys:
        raise RuntimeError("#170 BEST_FULL identity drift from #167 K1")
    if Counter(row["frozen_policy_status"] for row in participation170) != {"SELECTED_PREOUTCOME": 189, "NO_BET_FROZEN": 159}:
        raise RuntimeError("#170 BEST_FULL participation drift")
    return selector_grid, census, sorted(kall, key=lambda row: (row["issue_instance"], int(row["selector_rank"]), row["portfolio_id"])), sorted(roles, key=lambda row: (row["issue_instance"], row["portfolio_id"], int(row["selection_rank"])))


def read_target_features(db: Path, match_ids: set[int]) -> dict[int, dict[str, object]]:
    connection = ro_connection(db)
    output: dict[int, dict[str, object]] = {}
    for start in range(0, len(match_ids), 800):
        chunk = sorted(match_ids)[start:start + 800]
        placeholders = ",".join("?" for _ in chunk)
        query = f"""
            SELECT m.match_id, m.issue, m.match_idx, m.kickoff_ts, mf.season_year,
                   m.league, m.home_team_id, m.away_team_id, m.home_rank, m.away_rank,
                   mf.handicap_line_norm
              FROM matches m JOIN match_features mf ON mf.match_id=m.match_id
             WHERE m.match_id IN ({placeholders})
        """
        for row in connection.execute(query, chunk):
            output[int(row[0])] = dict(zip(TARGET_FIELDS, row))
    connection.close()
    if set(output) != match_ids:
        raise RuntimeError(f"target safe-feature join drift: {len(output)} != {len(match_ids)}")
    return output


def history_for_year(db: Path, target_year: int) -> list[dict[str, object]]:
    connection = ro_connection(db)
    query = """
        SELECT m.match_id, m.kickoff_ts, mf.season_year, m.home_team_id,
               m.away_team_id, mf.fthg, mf.ftag
          FROM matches m JOIN match_features mf ON mf.match_id=m.match_id
         WHERE mf.season_year IS NOT NULL AND mf.season_year < ?
           AND m.home_team_id IS NOT NULL AND m.away_team_id IS NOT NULL
         ORDER BY m.kickoff_ts, m.match_id
    """
    rows = [dict(zip(HISTORY_FIELDS, row)) for row in connection.execute(query, (target_year,))]
    connection.close()
    return rows


def build_match_features(db: Path, target: dict[int, dict[str, object]]) -> dict[int, dict[str, object]]:
    by_year: dict[int, list[dict[str, object]]] = defaultdict(list)
    for row in target.values():
        by_year[int(row["year"])].append(row)
    output: dict[int, dict[str, object]] = {}
    for year in sorted(by_year):
        state = TeamState()
        for history in history_for_year(db, year):
            state.update(history)
        for row in sorted(by_year[year], key=lambda value: (str(value["kickoff_ts"]), int(value["match_id"]))):
            output[int(row["match_id"])] = {**row, **state.snapshot(row)}
    if set(output) != set(target):
        raise RuntimeError("fundamental feature output drift")
    return output


def build_portfolio_scores(
    identities: Sequence[dict[str, str]],
    roles: Sequence[dict[str, str]],
    features: dict[int, dict[str, object]],
) -> list[dict[str, object]]:
    roles_by_key: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for role in roles:
        roles_by_key[(role["issue_instance"], role["portfolio_id"])].append(role)
    by_issue: dict[str, list[dict[str, object]]] = defaultdict(list)
    for identity in identities:
        key = (identity["issue_instance"], identity["portfolio_id"])
        frozen_roles = sorted(roles_by_key[key], key=lambda row: int(row["selection_rank"]))
        selected_ids = identity["selected_match_ids"].split("|")
        if len(frozen_roles) != 7 or [row["match_id"] for row in frozen_roles] != selected_ids:
            raise RuntimeError(f"identity/role drift: {key}")
        fundamental = [float(features[int(role["match_id"])]["fundamental_confidence"]) for role in frozen_roles]
        decision = [max(float(role["q_weight3"]), float(role["q_weight1"]), float(role["q_weight0"])) for role in frozen_roles]
        missing = [float(features[int(role["match_id"])]["fundamental_missing"]) for role in frozen_roles]
        depths = [float(features[int(role["match_id"])]["history_depth"]) for role in frozen_roles]
        by_issue[identity["issue_instance"]].append({
            **identity,
            "market_raw": -float(identity["selector_rank"]),
            "fundamental_raw": geometric(fundamental),
            "decision_raw": geometric(decision),
            "fundamental_missing_fraction": sum(missing) / 7.0,
            "mean_history_depth": sum(depths) / 7.0,
            "min_history_depth": min(depths),
        })

    output: list[dict[str, object]] = []
    for issue_instance, candidates in sorted(by_issue.items()):
        ranks = {
            "market_percentile": percentile([(str(row["portfolio_id"]), float(row["market_raw"])) for row in candidates]),
            "fundamental_percentile": percentile([(str(row["portfolio_id"]), float(row["fundamental_raw"])) for row in candidates]),
            "decision_percentile": percentile([(str(row["portfolio_id"]), float(row["decision_raw"])) for row in candidates]),
        }
        for row in candidates:
            pid = str(row["portfolio_id"])
            market = ranks["market_percentile"][pid]
            fundamental = ranks["fundamental_percentile"][pid]
            decision = ranks["decision_percentile"][pid]
            output.append({
                "issue": row["issue"], "year": row["year"], "fold": row["fold"], "issue_instance": issue_instance,
                "portfolio_id": pid, "source_selector_rank": row["selector_rank"],
                "candidate_match_id": row["candidate_match_id"], "selected_match_ids": row["selected_match_ids"],
                "identity_fingerprint": row["identity_fingerprint"], "candidate_count_complete_issue": len(candidates),
                "market_rank_raw": int(row["selector_rank"]), "fundamental_gm_confidence": compact(float(row["fundamental_raw"])),
                "decision_gm_q_max": compact(float(row["decision_raw"])),
                "fundamental_missing_fraction": compact(float(row["fundamental_missing_fraction"])),
                "mean_history_depth": compact(float(row["mean_history_depth"])), "min_history_depth": compact(float(row["min_history_depth"])),
                "market_percentile": compact(market), "fundamental_percentile": compact(fundamental),
                "decision_percentile": compact(decision), "combined_percentile": compact(0.50 * market + 0.25 * fundamental + 0.25 * decision),
                "full_ticket_count": FULL_TICKETS, "full_stake_yuan": FULL_STAKE_YUAN,
                "outcome_boundary": OUTCOME_BOUNDARY,
            })
    return sorted(output, key=lambda row: (str(row["issue_instance"]), int(row["source_selector_rank"]), str(row["portfolio_id"])))


def build_selection(census: Sequence[dict[str, str]], scores: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    kall_census = sorted((row for row in census if row["selector_id"] == KALL_SELECTOR), key=lambda row: row["issue_instance"])
    by_issue: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in scores:
        by_issue[str(row["issue_instance"])].append(row)
    output: list[dict[str, object]] = []
    for census_row in kall_census:
        issue_instance = census_row["issue_instance"]
        candidates = by_issue.get(issue_instance, [])
        if len(candidates) != int(census_row["candidate_identity_count"]):
            raise RuntimeError(f"candidate census drift: {issue_instance}")
        for arm, field, definition in ARMS:
            selected = min(candidates, key=lambda row: (-float(row[field]), str(row["portfolio_id"]))) if candidates else None
            output.append({
                "arm": arm, "score_field": field, "arm_definition": definition,
                "issue": census_row["issue"], "year": census_row["year"], "fold": census_row["fold"],
                "issue_instance": issue_instance, "candidate_count_complete_issue": len(candidates),
                "policy_status": "SELECTED_PREOUTCOME" if selected else "NO_BET_FROZEN",
                "selected_identity_count": 1 if selected else 0,
                "selected_portfolio_id": selected["portfolio_id"] if selected else "",
                "selected_identity_fingerprint": selected["identity_fingerprint"] if selected else "",
                "selected_match_ids": selected["selected_match_ids"] if selected else "",
                "selected_score": selected[field] if selected else "",
                "full_ticket_count": FULL_TICKETS if selected else 0,
                "planned_stake_yuan": FULL_STAKE_YUAN if selected else 0,
                "no_bet_reason": "" if selected else "NO_QUALIFYING_COLD_ANCHOR",
                "tie_break": "score descending, then portfolio_id ascending",
                "outcome_boundary": OUTCOME_BOUNDARY,
            })
    expected = {"SELECTED_PREOUTCOME": 189, "NO_BET_FROZEN": 159}
    for arm, _, _ in ARMS:
        if Counter(row["policy_status"] for row in output if row["arm"] == arm) != expected:
            raise RuntimeError(f"participation drift: {arm}")
    market = [row for row in output if row["arm"] == "MARKET_BEST_FULL" and row["policy_status"] == "SELECTED_PREOUTCOME"]
    if any(int(next(score for score in scores if score["portfolio_id"] == row["selected_portfolio_id"] and score["issue_instance"] == row["issue_instance"])["source_selector_rank"]) != 1 for row in market):
        raise RuntimeError("market arm failed to reproduce K1")
    return output


def overlap_rows(selection: Sequence[dict[str, object]]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    by_issue: dict[str, dict[str, dict[str, object]]] = defaultdict(dict)
    for row in selection:
        by_issue[str(row["issue_instance"])][str(row["arm"])] = row
    issue_rows = []
    arms = [arm for arm, _, _ in ARMS]
    for issue_instance, rows in sorted(by_issue.items()):
        selected = {arm: str(rows[arm]["selected_portfolio_id"]) for arm in arms}
        nonempty = [value for value in selected.values() if value]
        issue_rows.append({
            "issue_instance": issue_instance, "issue": rows[arms[0]]["issue"], "year": rows[arms[0]]["year"], "fold": rows[arms[0]]["fold"],
            **{f"{arm.lower()}_portfolio_id": selected[arm] for arm in arms},
            "distinct_selected_identity_count": len(set(nonempty)),
            "all_four_same_identity": "1" if len(nonempty) == 4 and len(set(nonempty)) == 1 else "0",
            "policy_status": rows[arms[0]]["policy_status"], "outcome_boundary": OUTCOME_BOUNDARY,
        })
    pair_rows = []
    for left_index, left in enumerate(arms):
        for right in arms[left_index + 1:]:
            comparable = [row for row in issue_rows if row["policy_status"] == "SELECTED_PREOUTCOME"]
            same = sum(row[f"{left.lower()}_portfolio_id"] == row[f"{right.lower()}_portfolio_id"] for row in comparable)
            pair_rows.append({
                "left_arm": left, "right_arm": right, "comparable_issue_count": len(comparable),
                "same_identity_issue_count": same, "different_identity_issue_count": len(comparable) - same,
                "identity_overlap_rate": compact(same / len(comparable)),
                "comparison_unit": "complete issue; one K1 FULL identity per arm", "outcome_boundary": OUTCOME_BOUNDARY,
            })
    return issue_rows, pair_rows


def empirical_quantile(values: Sequence[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise RuntimeError("empty threshold source")
    return ordered[math.ceil(q * (len(ordered) - 1))]


def threshold_registry(selection: Sequence[dict[str, object]], scores: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    by_key = {(str(row["issue_instance"]), str(row["portfolio_id"])): row for row in scores}
    rows: list[dict[str, object]] = []
    for arm, field, _ in ARMS:
        selected = [row for row in selection if row["arm"] == arm and row["policy_status"] == "SELECTED_PREOUTCOME"]
        selected_scores = [float(row["selected_score"]) for row in selected]
        for quantile in (0.00, 0.25, 0.50, 0.75):
            cutoff = empirical_quantile(selected_scores, quantile)
            rows.append({
                "threshold_family": "SELECTED_SCORE_QUANTILE", "arm": arm, "metric": field,
                "operator": ">=", "threshold_label": f"Q{int(quantile * 100):02d}", "threshold_value": compact(cutoff),
                "source_issue_count": len(selected), "scientific_role": "secondary threshold sensitivity; primary K1 participation remains fixed",
                "missing_rule": "no implicit drop", "outcome_boundary": OUTCOME_BOUNDARY,
            })
    market_selected = [row for row in selection if row["arm"] == "MARKET_BEST_FULL" and row["policy_status"] == "SELECTED_PREOUTCOME"]
    selected_portfolios = [by_key[(str(row["issue_instance"]), str(row["selected_portfolio_id"]))] for row in market_selected]
    for metric, operator, values in (
        ("fundamental_missing_fraction", "<=", (0.00, 0.25, 0.50, 1.00)),
        ("mean_history_depth", ">=", (0.0, 5.0, 10.0, 20.0)),
    ):
        for value in values:
            rows.append({
                "threshold_family": "FUNDAMENTAL_DATA_QUALITY", "arm": "ALL_OVERLAY_ARMS", "metric": metric,
                "operator": operator, "threshold_label": str(value), "threshold_value": compact(value),
                "source_issue_count": len(selected_portfolios), "scientific_role": "secondary missing-data sensitivity only",
                "missing_rule": "neutral score retained and explicit missingness measured", "outcome_boundary": OUTCOME_BOUNDARY,
            })
    return rows


def build_match_feature_rows(features: dict[int, dict[str, object]]) -> list[dict[str, object]]:
    fields = (
        "elo_diff", "form_diff", "rank_diff", "rest_diff", "history_depth", "fundamental_p3",
        "fundamental_p1", "fundamental_p0", "fundamental_confidence", "fundamental_entropy", "fundamental_missing",
    )
    return [{
        "match_id": match_id, "issue": row["issue"], "match_idx": row["match_idx"], "kickoff_ts": row["kickoff_ts"],
        "year": row["year"], "league": row["league"], "home_team_id": row["home_team_id"], "away_team_id": row["away_team_id"],
        "home_rank": row["home_rank"], "away_rank": row["away_rank"], "handicap_line_norm": row["handicap_line_norm"],
        **{field: compact(float(row[field])) for field in fields},
        "feature_boundary": "strictly prior calendar years only; target outcomes are not selected",
    } for match_id, row in sorted(features.items())]


def copy_candidate_roles(roles: Sequence[dict[str, str]]) -> list[dict[str, object]]:
    fields = [field for field in roles[0] if field != "outcome_boundary"]
    return [{**{field: row[field] for field in fields}, "source_role_row_sha256": canonical_hash(row), "outcome_boundary": OUTCOME_BOUNDARY} for row in roles]


def atomic_generate(output: Path, db: Path) -> dict[str, object]:
    output = output.resolve()
    if output.exists():
        raise RuntimeError(f"refusing overwrite: {output}")
    stage = output.with_name(f".{output.name}.stage-{os.getpid()}")
    if stage.exists():
        raise RuntimeError(f"staging path already exists: {stage}")
    stage.mkdir(parents=True)
    try:
        payload_167 = verify_package(GATE_A_167, SOURCE_167_MANIFEST, SOURCE_167_CONTENT)
        payload_170a = verify_package(GATE_A_170, SOURCE_170_A_MANIFEST, SOURCE_170_A_CONTENT)
        payload_170b = verify_package(GATE_B_170, SOURCE_170_B_MANIFEST, SOURCE_170_B_CONTENT)
        if sha256_file(db) != DB_SHA256:
            raise RuntimeError("canonical database hash drift")
        selector_grid, census, identities, roles = load_frozen_inputs()
        match_ids = {int(role["match_id"]) for role in roles}
        target = read_target_features(db, match_ids)
        features = build_match_features(db, target)
        scores = build_portfolio_scores(identities, roles, features)
        selection = build_selection(census, scores)
        issue_overlap, pair_overlap = overlap_rows(selection)
        thresholds = threshold_registry(selection, scores)
        feature_rows = build_match_feature_rows(features)
        role_rows = copy_candidate_roles(roles)

        candidate_fields = list(scores[0])
        selection_fields = list(selection[0])
        write_gzip(stage / "candidate_universe_scores.csv.gz", candidate_fields, scores)
        write_gzip(stage / "candidate_role_vectors.csv.gz", list(role_rows[0]), role_rows)
        write_gzip(stage / "match_feature_scores.csv.gz", list(feature_rows[0]), feature_rows)
        write_csv(stage / "selection_freeze.csv", selection_fields, selection)
        write_csv(stage / "issue_identity_overlap.csv", list(issue_overlap[0]), issue_overlap)
        write_csv(stage / "pairwise_identity_overlap.csv", list(pair_overlap[0]), pair_overlap)
        write_csv(stage / "threshold_registry.csv", list(thresholds[0]), thresholds)

        selector_rows = [{
            "arm": arm, "score_field": field, "definition": definition,
            "candidate_selector_id": KALL_SELECTOR, "incumbent_selector_id": K1_SELECTOR,
            "selection_scope": "complete issue K1", "allocation": "FULL_ENUMERATED",
            "ticket_count_per_selected_identity": FULL_TICKETS, "stake_per_selected_identity_yuan": FULL_STAKE_YUAN,
            "participating_issue_count": 189, "frozen_no_bet_issue_count": 159,
            "missing_rule": "neutral fundamental probabilities; retained explicit missingness; no candidate drop",
            "outcome_boundary": OUTCOME_BOUNDARY,
        } for arm, field, definition in ARMS]
        write_csv(stage / "arm_registry.csv", list(selector_rows[0]), selector_rows)

        segment_rows = [
            {"segment_id": "YEAR", "definition": "target calendar year 2020..2025", "controlling": "0", "use": "Gate B stability"},
            {"segment_id": "FOLD", "definition": "frozen OOS fold from #167", "controlling": "0", "use": "Gate B stability"},
            {"segment_id": "CANDIDATE_COUNT", "definition": "1 versus 2+ complete-issue candidates", "controlling": "0", "use": "selection opportunity sensitivity"},
            {"segment_id": "FUNDAMENTAL_MISSING", "definition": "selected identity missing fraction 0 versus >0", "controlling": "0", "use": "missing-data bias"},
            {"segment_id": "PRIMARY", "definition": "all 348 frozen issues; 189 selected and 159 no-bet", "controlling": "1", "use": "primary matched comparison"},
        ]
        for row in segment_rows:
            row["outcome_boundary"] = OUTCOME_BOUNDARY
        write_csv(stage / "segment_registry.csv", list(segment_rows[0]), segment_rows)

        source_rows = [
            {"source": SOURCE_167, "role": "accepted candidate/identity/role-vector definition", "manifest_sha256": SOURCE_167_MANIFEST, "content_identity_sha256": SOURCE_167_CONTENT, "parsed": "selector registry/census/identity/role payloads only", "payload_count": len(payload_167)},
            {"source": SOURCE_170_A, "role": "accepted BEST_FULL incumbent identity and participation reproduction", "manifest_sha256": SOURCE_170_A_MANIFEST, "content_identity_sha256": SOURCE_170_A_CONTENT, "parsed": "Gate-A identity and participation only", "payload_count": len(payload_170a)},
            {"source": SOURCE_170_B, "role": "terminal attribution evidence durability binding", "manifest_sha256": SOURCE_170_B_MANIFEST, "content_identity_sha256": SOURCE_170_B_CONTENT, "parsed": "NO; manifest/content/payload hashes only", "payload_count": len(payload_170b)},
            {"source": str(DB_REPOSITORY_PATH), "role": "target identity-safe features and strictly-prior-year team history", "manifest_sha256": DB_SHA256, "content_identity_sha256": DB_SHA256, "parsed": "target safe columns; prior-year historical scores only", "payload_count": 1},
        ]
        for row in source_rows:
            row["outcome_boundary"] = OUTCOME_BOUNDARY
        write_csv(stage / "source_census.csv", list(source_rows[0]), source_rows)

        selected_counts = Counter(row["arm"] for row in selection if row["policy_status"] == "SELECTED_PREOUTCOME")
        no_bet_counts = Counter(row["arm"] for row in selection if row["policy_status"] == "NO_BET_FROZEN")
        source_binding = {
            "contract": CONTRACT, "version": VERSION, "outcome_boundary": OUTCOME_BOUNDARY,
            "source_167_gate_a": {"package": SOURCE_167, "manifest_sha256": SOURCE_167_MANIFEST, "content_identity_sha256": SOURCE_167_CONTENT, "payload_count": len(payload_167)},
            "source_170_gate_a": {"package": SOURCE_170_A, "manifest_sha256": SOURCE_170_A_MANIFEST, "content_identity_sha256": SOURCE_170_A_CONTENT, "payload_count": len(payload_170a)},
            "source_170_gate_b": {"package": SOURCE_170_B, "manifest_sha256": SOURCE_170_B_MANIFEST, "content_identity_sha256": SOURCE_170_B_CONTENT, "payload_count": len(payload_170b), "access": "hash verification only; no semantic payload parsing"},
            "database": {"repository_path": str(DB_REPOSITORY_PATH), "resolved_path_not_persisted": True, "sha256": DB_SHA256, "target_query_columns": list(TARGET_FIELDS), "history_query_rule": "season_year < target year"},
            "candidate_selector_id": KALL_SELECTOR, "incumbent_selector_id": K1_SELECTOR,
        }
        (stage / "source_binding.json").write_text(dump_json(source_binding), encoding="utf-8")
        card = {
            "issue": ISSUE, "contract": CONTRACT, "version": VERSION,
            "stage": "REPLACEMENT_GATE_A_OUTCOME_UNEXPOSED_FOUR_ARM_K1_FULL_FREEZE",
            "supersedes": {"pr": 158, "head": "f2e5d427a71d74b7b789a0e594eda1c55569ab73", "reason": "obsolete #132 threshold surface; historical evidence only"},
            "incumbent": {"alias": "BEST_FULL", "selector_id": K1_SELECTOR, "allocation": "FULL_ENUMERATED", "tickets": FULL_TICKETS, "stake_yuan": FULL_STAKE_YUAN, "selected_issue_count": 189, "frozen_no_bet_issue_count": 159, "controlling_baseline_no_tax_roi": -0.0947, "attribution_only_common_full_roi": -0.0909},
            "candidate_universe": {"selector_id": KALL_SELECTOR, "issue_census": 348, "participating_issues": 189, "frozen_no_bet_issues": 159, "identity_count": 424, "candidate_count_range": [0, 7], "fixed_participation": True},
            "arms": [{"arm": arm, "score_field": field, "definition": definition} for arm, field, definition in ARMS],
            "scoring": {"market": "exact #167 K_ALL COLD_FIRST rank", "fundamental": "geometric mean of seven past-only fundamental confidences", "decision": "geometric mean of seven max(q_weight3,q_weight1,q_weight0)", "combined": "within-issue 0.50 market + 0.25 fundamental + 0.25 decision percentile", "tie_break": "score descending then portfolio_id ascending"},
            "missing_data": "retain identity; neutral default team state and explicit missing fraction; no silent drop",
            "thresholds": "primary K1 has no post-score rejection; secondary pre-registered score-quantile and fundamental data-quality thresholds are diagnostic only",
            "segments": "primary complete-issue denominator; year/fold/candidate-count/missingness are non-controlling diagnostics",
            "denominator": {"issue_rows": len(selection), "issue_census": 348, "candidate_identity_rows": len(scores), "candidate_role_rows": len(role_rows), "unique_match_feature_rows": len(feature_rows), "selected_by_arm": dict(selected_counts), "no_bet_by_arm": dict(no_bet_counts), "planned_stake_per_arm_yuan": 189 * FULL_STAKE_YUAN},
            "gate_b_status": "NOT_AUTHORIZED_PENDING_PI_GATE_A_REVIEW",
            "gate_b_required": ["pre-tax ROI primary and per-ticket tax secondary", "participation/support/calibration/hit/GM expected SP", "ablation and threshold frontiers", "drawdown/concentration/largest-event/missing-data bias", "pairwise identity overlap and diagnostic sleeve only after FULL"],
            "promotion_boundary": "historical research only; a positive result requires strict independent EV and held-out/forward validation; a negative result cannot demote BEST_FULL",
            "outcome_boundary": OUTCOME_BOUNDARY,
        }
        (stage / "gate_a_card.json").write_text(dump_json(card), encoding="utf-8")
        readme = (
            "# #134 replacement Gate A\n\n"
            "Outcome-unexposed four-arm K1 FULL freeze on the accepted #167/#170 BEST_FULL candidate universe. "
            "All four arms share 348 issues, 189 selected identities, 159 frozen no-bet issues, 2,187 distinct FULL tickets, and ¥4,374 per selected issue. "
            "#170 Gate B is cryptographically bound but not parsed. Gate B for #134 is not authorized.\n"
        )
        (stage / "README.md").write_text(readme, encoding="utf-8")
        shutil.copyfile(Path(__file__).resolve(), stage / "freeze_runner.py")

        payloads = sorted(path for path in stage.iterdir() if path.is_file())
        content = {
            "contract_version": VERSION,
            "denominator": card["denominator"],
            "controls": {
                "candidate_selector_id": KALL_SELECTOR, "incumbent_selector_id": K1_SELECTOR,
                "source_167_manifest_sha256": SOURCE_167_MANIFEST, "source_170_gate_a_manifest_sha256": SOURCE_170_A_MANIFEST,
                "source_170_gate_b_manifest_sha256": SOURCE_170_B_MANIFEST, "database_sha256": DB_SHA256,
                "market_selected_identity_sha256": canonical_hash(sorted((row["issue_instance"], row["selected_portfolio_id"]) for row in selection if row["arm"] == "MARKET_BEST_FULL" and row["policy_status"] == "SELECTED_PREOUTCOME")),
            },
            "payloads": {path.name: sha256_file(path) for path in payloads},
        }
        (stage / "CONTENT_IDENTITY.json").write_text(dump_json(content), encoding="utf-8")
        payloads = sorted(path for path in stage.iterdir() if path.is_file())
        (stage / "SHA256SUMS.json").write_text(dump_json({path.name: sha256_file(path) for path in payloads}), encoding="utf-8")
        os.replace(stage, output)
        return {"output": str(output), "manifest_sha256": sha256_file(output / "SHA256SUMS.json"), "content_identity_sha256": sha256_file(output / "CONTENT_IDENTITY.json"), "denominator": card["denominator"]}
    except BaseException:
        if stage.exists():
            shutil.rmtree(stage)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--db", type=Path, default=None)
    args = parser.parse_args()
    db = args.db.resolve() if args.db else locate_database()
    print(dump_json(atomic_generate(args.output, db)), end="")


if __name__ == "__main__":
    main()
