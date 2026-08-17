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
import importlib.util
import io
import json
import math
import os
import shutil
import sqlite3
import sys
from collections import Counter, defaultdict, deque
from collections.abc import Iterable, Sequence
from pathlib import Path
from types import ModuleType


CONTRACT = "BJ-HIST-FUNDAMENTAL-OVERLAY-N7-001"
VERSION = "bj134-gate-a-v2r2"
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

DECISION_CHAIN_SOURCE_PATH = Path("scripts/evaluate_structured_decision_chain_shadow.py")
DECISION_CHAIN_SOURCE_SHA256 = "50c523ae5441a3018fcc5a175b884a0d887416c99f6b34f9dc72903695adcf92"
DECISION_CHAIN_VERSION = "active_v3.3.3"

K1_SELECTOR = "S2_ESP290_GM300_MARKET_WF_CAL_MIN_LOWP20_COLD_FIRST_K1"
KALL_SELECTOR = "S2_ESP290_GM300_MARKET_WF_CAL_MIN_LOWP20_COLD_FIRST_K_ALL"
OUTCOME_BOUNDARY = (
    "Gate A outcome-unexposed: target result/final-SP/payout/tax/ROI/settlement "
    "fields are neither selected nor emitted"
)

ARMS = (
    ("MARKET_BEST_FULL", "market_percentile", "exact #167 K_ALL COLD_FIRST rank; reproduces BEST_FULL K1"),
    ("FUNDAMENTALS_ONLY", "fundamental_percentile", "strict pre-issue-cutoff rolling Elo/form/rest confidence"),
    ("DECISION_CHAIN_ONLY", "decision_percentile", "exact active_v3.3.3 core over frozen MODEL_P_CAL and reconstructed predicted-SP"),
    ("FUNDAMENTALS_PLUS_DECISION", "combined_percentile", "fixed 0.50 market + 0.25 rolling fundamental + 0.25 active_v3.3.3 percentile overlay"),
)
TARGET_FIELDS = (
    "match_id", "issue", "match_idx", "kickoff_ts", "year", "league",
    "home_team_id", "away_team_id", "home_rank", "away_rank", "handicap_line_norm",
)
HISTORY_FIELDS = (
    "match_id", "kickoff_ts", "season_year", "home_team_id", "away_team_id", "fthg", "ftag",
)

ABLATIONS = (
    ("A0_MARKET_ONLY", "market_percentile", "1", "0", "0", "0", "exact BEST_FULL incumbent"),
    ("A1_FUNDAMENTALS_FULL", "fundamental_percentile", "0", "1", "0", "0", "rolling Elo + form + rest"),
    ("A2_DECISION_ONLY", "decision_percentile", "0", "0", "1", "0", "exact active_v3.3.3 reduced-input replay"),
    ("A3_COMBINED_FULL", "combined_percentile", "1", "1", "1", "0", "market + rolling fundamental + decision chain"),
    ("A4_FUND_MINUS_STRENGTH", "fundamental_no_strength_percentile", "0", "1", "0", "0", "rolling fundamental leaving out Elo strength"),
    ("A5_FUND_MINUS_FORM", "fundamental_no_form_percentile", "0", "1", "0", "0", "rolling fundamental leaving out form"),
    ("A6_FUND_MINUS_REST", "fundamental_no_rest_percentile", "0", "1", "0", "0", "rolling fundamental leaving out rest"),
    ("A7_COMBINED_MINUS_STRENGTH", "combined_no_strength_percentile", "1", "1", "1", "0", "combined overlay leaving out Elo strength"),
    ("A8_COMBINED_MINUS_FORM", "combined_no_form_percentile", "1", "1", "1", "0", "combined overlay leaving out form"),
    ("A9_COMBINED_MINUS_REST", "combined_no_rest_percentile", "1", "1", "1", "0", "combined overlay leaving out rest"),
    ("D1_RANK_PROXY_ONLY", "rank_proxy_percentile", "0", "1", "0", "1", "historical timing proxy; non-controlling diagnostic"),
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


def decision_chain_source() -> Path:
    """Return the immutable decision core bundled beside a packaged runner.

    The development runner binds the repository source by byte hash.  Once the
    Gate-A package is written, its copied runner replays against the sibling
    manifest-covered copy instead, so later repository edits cannot change the
    frozen decision semantics.
    """
    bundled = Path(__file__).resolve().with_name("decision_chain_runner.py")
    return bundled if bundled.is_file() else ROOT / DECISION_CHAIN_SOURCE_PATH


def load_decision_chain() -> ModuleType:
    path = decision_chain_source()
    actual = sha256_file(path)
    if actual != DECISION_CHAIN_SOURCE_SHA256:
        raise RuntimeError(
            f"active_v3.3.3 decision-chain source drift: {actual} != {DECISION_CHAIN_SOURCE_SHA256}"
        )
    spec = importlib.util.spec_from_file_location("bj134_active_v3_3_3", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load active_v3.3.3 decision-chain source")
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    if getattr(module, "SHADOW_ARM", None) != DECISION_CHAIN_VERSION:
        raise RuntimeError("active_v3.3.3 decision-chain version drift")
    return module


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
    with (
        path.open("wb") as raw,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped,
    ):
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
    """Deterministic team state updated only from matches before an issue cutoff."""

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

    @staticmethod
    def probabilities(margin: float) -> tuple[list[float], float]:
        exp_values = [math.exp(max(-40.0, min(40.0, value))) for value in (margin, 0.0, -margin)]
        total = sum(exp_values)
        probabilities = [value / total for value in exp_values]
        entropy = -sum(probability * math.log(probability) for probability in probabilities if probability > 0) / math.log(3.0)
        return probabilities, entropy

    def snapshot(self, row: dict[str, object], cutoff: dt.datetime) -> dict[str, float | str]:
        home, away = str(row.get("home_team_id") or ""), str(row.get("away_team_id") or "")
        home_elo, away_elo = self.elo[home] if home else 1500.0, self.elo[away] if away else 1500.0
        home_rank, away_rank = parse_rank(row.get("home_rank")), parse_rank(row.get("away_rank"))
        rank_diff = away_rank - home_rank if home_rank and away_rank else 0.0
        rest_diff = max(-1.0, min(1.0, (self.rest_hours(home, cutoff) - self.rest_hours(away, cutoff)) / 720.0))
        depth = min(self.count[home], self.count[away]) if home and away else 0
        elo_diff = (home_elo + 50.0) - away_elo
        form_diff = self.form_value(home) - self.form_value(away)
        rank_component = max(-3.0, min(3.0, rank_diff / 10.0))
        strength_margin = 0.70 * (elo_diff / 400.0)
        form_margin = 0.20 * (form_diff / 3.0)
        rest_margin = 0.05 * rest_diff
        asof_margin = strength_margin + form_margin + rest_margin
        proxy_margin = asof_margin + 0.10 * rank_component
        no_strength_probs, _ = self.probabilities(form_margin + rest_margin)
        no_form_probs, _ = self.probabilities(strength_margin + rest_margin)
        no_rest_probs, _ = self.probabilities(strength_margin + form_margin)
        probs, entropy = self.probabilities(asof_margin)
        proxy_probs, proxy_entropy = self.probabilities(proxy_margin)
        return {
            "feature_cutoff_ts": cutoff.isoformat(sep=" "),
            "elo_diff": elo_diff, "form_diff": form_diff, "rank_diff": rank_diff,
            "rest_diff": rest_diff, "history_depth": float(depth),
            "fundamental_p3": probs[0], "fundamental_p1": probs[1], "fundamental_p0": probs[2],
            "fundamental_confidence": max(probs), "fundamental_entropy": entropy,
            "fundamental_no_strength_confidence": max(no_strength_probs),
            "fundamental_no_form_confidence": max(no_form_probs),
            "fundamental_no_rest_confidence": max(no_rest_probs),
            "rank_proxy_p3": proxy_probs[0], "rank_proxy_p1": proxy_probs[1], "rank_proxy_p0": proxy_probs[2],
            "rank_proxy_confidence": max(proxy_probs), "rank_proxy_entropy": proxy_entropy,
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


def rolling_history(db: Path, max_cutoff: dt.datetime) -> list[dict[str, object]]:
    connection = ro_connection(db)
    query = """
        SELECT m.match_id, m.kickoff_ts, mf.season_year, m.home_team_id,
               m.away_team_id, mf.fthg, mf.ftag
          FROM matches m JOIN match_features mf ON mf.match_id=m.match_id
         WHERE m.kickoff_ts IS NOT NULL AND m.kickoff_ts < ?
           AND m.home_team_id IS NOT NULL AND m.away_team_id IS NOT NULL
           AND mf.fthg IS NOT NULL AND mf.ftag IS NOT NULL
         ORDER BY m.kickoff_ts, m.match_id
    """
    rows = [dict(zip(HISTORY_FIELDS, row)) for row in connection.execute(query, (max_cutoff.isoformat(sep=" "),))]
    connection.close()
    return rows


def frozen_issue_cutoffs(roles: Sequence[dict[str, str]]) -> tuple[dict[str, dt.datetime], dict[int, dt.datetime]]:
    by_issue: dict[str, list[dt.datetime]] = defaultdict(list)
    match_issue_instances: dict[int, set[str]] = defaultdict(set)
    for role in roles:
        timestamp = parse_ts(role["kickoff_ts"])
        if timestamp is None:
            raise RuntimeError(f"missing frozen kickoff: {role['match_id']}")
        by_issue[role["issue_instance"]].append(timestamp)
        match_issue_instances[int(role["match_id"])].add(role["issue_instance"])
    issue_cutoffs = {issue_instance: min(values) for issue_instance, values in by_issue.items()}
    match_cutoffs: dict[int, dt.datetime] = {}
    for match_id, issue_instances in match_issue_instances.items():
        values = {issue_cutoffs[issue_instance] for issue_instance in issue_instances}
        if len(values) != 1:
            raise RuntimeError(f"match mapped to inconsistent issue cutoffs: {match_id}")
        match_cutoffs[match_id] = values.pop()
    return issue_cutoffs, match_cutoffs


def build_match_features(
    db: Path,
    target: dict[int, dict[str, object]],
    roles: Sequence[dict[str, str]],
) -> tuple[dict[int, dict[str, object]], dict[str, dt.datetime]]:
    issue_cutoffs, match_cutoffs = frozen_issue_cutoffs(roles)
    if set(match_cutoffs) != set(target):
        raise RuntimeError("target/cutoff match coverage drift")
    history = rolling_history(db, max(issue_cutoffs.values()))
    parsed_history: list[tuple[dt.datetime, dict[str, object]]] = []
    for row in history:
        timestamp = parse_ts(row["kickoff_ts"])
        if timestamp is None:
            raise RuntimeError(f"invalid history kickoff: {row['match_id']}")
        parsed_history.append((timestamp, row))

    target_by_cutoff: dict[dt.datetime, list[int]] = defaultdict(list)
    for match_id, cutoff in match_cutoffs.items():
        target_by_cutoff[cutoff].append(match_id)
    output: dict[int, dict[str, object]] = {}
    state = TeamState()
    history_index = 0
    for cutoff in sorted(target_by_cutoff):
        while history_index < len(parsed_history) and parsed_history[history_index][0] < cutoff:
            state.update(parsed_history[history_index][1])
            history_index += 1
        for match_id in sorted(target_by_cutoff[cutoff]):
            row = target[match_id]
            output[match_id] = {**row, **state.snapshot(row, cutoff)}
    if set(output) != set(target):
        raise RuntimeError("fundamental feature output drift")
    return output, issue_cutoffs


def role_decision_trace(
    role: dict[str, str],
    feature: dict[str, object],
    decision_chain: ModuleType,
) -> dict[str, object]:
    codes = ("3", "1", "0")
    probabilities = {code: float(role[f"p_model{code}"]) for code in codes}
    market_probabilities = {code: float(role[f"p_market_cal{code}"]) for code in codes}
    expected_sp = float(role["e_sp"])
    q = {code: expected_sp * float(role[f"q_weight{code}"]) for code in codes}
    predicted_sp = {code: q[code] / probabilities[code] for code in codes}
    if abs(sum(q.values()) - expected_sp) > 2e-9:
        raise RuntimeError(f"q/E_SP reconstruction drift: {role['match_id']}")
    payload = {
        "match": {
            "match_id": role["match_id"],
            "match_idx": role["match_idx"],
            "home": feature["home_team_id"],
            "away": feature["away_team_id"],
            "handicap_line": parse_float(feature["handicap_line_norm"]),
        },
        "model": {
            "probabilities": probabilities,
            "market_probabilities": market_probabilities,
        },
        "sp": predicted_sp,
        "analysis": {"status": "unavailable_historical_input"},
        "intelligence": {"status": "unavailable_historical_input"},
    }
    result = decision_chain.structured_decision_for_payload(payload)
    if result.get("decision_version") != decision_chain.SHADOW_VERSION:
        raise RuntimeError("decision-chain result version drift")
    selection_codes = [str(code) for code in result.get("selection_codes", [])]
    if not selection_codes or any(code not in codes for code in selection_codes):
        raise RuntimeError(f"decision-chain produced invalid selection: {role['match_id']}")
    return {
        "match_id": role["match_id"],
        "issue_instance": role["issue_instance"],
        "feature_cutoff_ts": feature["feature_cutoff_ts"],
        "decision_version": DECISION_CHAIN_VERSION,
        "input_sha256": canonical_hash(payload),
        **{f"p_model{code}": compact(probabilities[code]) for code in codes},
        **{f"q_reconstructed{code}": compact(q[code]) for code in codes},
        **{f"predicted_sp{code}": compact(predicted_sp[code]) for code in codes},
        "primary_pick": result["primary_pick"],
        "selection_codes": "+".join(selection_codes),
        "selection_width": len(selection_codes),
        "advisory_stop_flag": int(result["stop_flag"]),
        "decision_confidence": compact(float(result["confidence"])),
        "risk_tags": "|".join(str(tag) for tag in result.get("risk_tags", [])),
        "outcome_boundary": OUTCOME_BOUNDARY,
    }


def build_portfolio_scores(
    identities: Sequence[dict[str, str]],
    roles: Sequence[dict[str, str]],
    features: dict[int, dict[str, object]],
    decision_chain: ModuleType,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    roles_by_key: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for role in roles:
        roles_by_key[(role["issue_instance"], role["portfolio_id"])].append(role)
    decision_by_match: dict[int, dict[str, object]] = {}
    by_issue: dict[str, list[dict[str, object]]] = defaultdict(list)
    for identity in identities:
        key = (identity["issue_instance"], identity["portfolio_id"])
        frozen_roles = sorted(roles_by_key[key], key=lambda row: int(row["selection_rank"]))
        selected_ids = identity["selected_match_ids"].split("|")
        if len(frozen_roles) != 7 or [row["match_id"] for row in frozen_roles] != selected_ids:
            raise RuntimeError(f"identity/role drift: {key}")
        fundamental = [float(features[int(role["match_id"])]["fundamental_confidence"]) for role in frozen_roles]
        fundamental_no_strength = [float(features[int(role["match_id"])]["fundamental_no_strength_confidence"]) for role in frozen_roles]
        fundamental_no_form = [float(features[int(role["match_id"])]["fundamental_no_form_confidence"]) for role in frozen_roles]
        fundamental_no_rest = [float(features[int(role["match_id"])]["fundamental_no_rest_confidence"]) for role in frozen_roles]
        rank_proxy = [float(features[int(role["match_id"])]["rank_proxy_confidence"]) for role in frozen_roles]
        decision: list[float] = []
        for role in frozen_roles:
            match_id = int(role["match_id"])
            trace = role_decision_trace(role, features[match_id], decision_chain)
            existing = decision_by_match.setdefault(match_id, trace)
            if existing["input_sha256"] != trace["input_sha256"]:
                raise RuntimeError(f"decision input drift across identities: {match_id}")
            decision.append(float(trace["decision_confidence"]))
        missing = [float(features[int(role["match_id"])]["fundamental_missing"]) for role in frozen_roles]
        depths = [float(features[int(role["match_id"])]["history_depth"]) for role in frozen_roles]
        by_issue[identity["issue_instance"]].append({
            **identity,
            "market_raw": -float(identity["selector_rank"]),
            "fundamental_raw": geometric(fundamental),
            "fundamental_no_strength_raw": geometric(fundamental_no_strength),
            "fundamental_no_form_raw": geometric(fundamental_no_form),
            "fundamental_no_rest_raw": geometric(fundamental_no_rest),
            "rank_proxy_raw": geometric(rank_proxy),
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
            "fundamental_no_strength_percentile": percentile([(str(row["portfolio_id"]), float(row["fundamental_no_strength_raw"])) for row in candidates]),
            "fundamental_no_form_percentile": percentile([(str(row["portfolio_id"]), float(row["fundamental_no_form_raw"])) for row in candidates]),
            "fundamental_no_rest_percentile": percentile([(str(row["portfolio_id"]), float(row["fundamental_no_rest_raw"])) for row in candidates]),
            "rank_proxy_percentile": percentile([(str(row["portfolio_id"]), float(row["rank_proxy_raw"])) for row in candidates]),
            "decision_percentile": percentile([(str(row["portfolio_id"]), float(row["decision_raw"])) for row in candidates]),
        }
        for row in candidates:
            pid = str(row["portfolio_id"])
            market = ranks["market_percentile"][pid]
            fundamental = ranks["fundamental_percentile"][pid]
            fundamental_no_strength = ranks["fundamental_no_strength_percentile"][pid]
            fundamental_no_form = ranks["fundamental_no_form_percentile"][pid]
            fundamental_no_rest = ranks["fundamental_no_rest_percentile"][pid]
            rank_proxy = ranks["rank_proxy_percentile"][pid]
            decision = ranks["decision_percentile"][pid]
            market_quality = min(1.0, max(0.0, float(row["gm_e_sp"]) / 5.0))
            output.append({
                "issue": row["issue"], "year": row["year"], "fold": row["fold"], "issue_instance": issue_instance,
                "portfolio_id": pid, "source_selector_rank": row["selector_rank"],
                "candidate_match_id": row["candidate_match_id"], "selected_match_ids": row["selected_match_ids"],
                "identity_fingerprint": row["identity_fingerprint"], "candidate_count_complete_issue": len(candidates),
                "market_rank_raw": int(row["selector_rank"]), "market_gm_e_sp": row["gm_e_sp"],
                "fundamental_gm_confidence": compact(float(row["fundamental_raw"])),
                "fundamental_no_strength_gm_confidence": compact(float(row["fundamental_no_strength_raw"])),
                "fundamental_no_form_gm_confidence": compact(float(row["fundamental_no_form_raw"])),
                "fundamental_no_rest_gm_confidence": compact(float(row["fundamental_no_rest_raw"])),
                "rank_proxy_gm_confidence": compact(float(row["rank_proxy_raw"])),
                "decision_chain_gm_confidence": compact(float(row["decision_raw"])),
                "fundamental_missing_fraction": compact(float(row["fundamental_missing_fraction"])),
                "mean_history_depth": compact(float(row["mean_history_depth"])), "min_history_depth": compact(float(row["min_history_depth"])),
                "market_percentile": compact(market), "fundamental_percentile": compact(fundamental),
                "fundamental_no_strength_percentile": compact(fundamental_no_strength),
                "fundamental_no_form_percentile": compact(fundamental_no_form),
                "fundamental_no_rest_percentile": compact(fundamental_no_rest),
                "rank_proxy_percentile": compact(rank_proxy),
                "decision_percentile": compact(decision),
                "combined_percentile": compact(0.50 * market + 0.25 * fundamental + 0.25 * decision),
                "combined_no_strength_percentile": compact(0.50 * market + 0.25 * fundamental_no_strength + 0.25 * decision),
                "combined_no_form_percentile": compact(0.50 * market + 0.25 * fundamental_no_form + 0.25 * decision),
                "combined_no_rest_percentile": compact(0.50 * market + 0.25 * fundamental_no_rest + 0.25 * decision),
                "combined_cross_issue_raw": compact(0.50 * market_quality + 0.25 * float(row["fundamental_raw"]) + 0.25 * float(row["decision_raw"])),
                "full_ticket_count": FULL_TICKETS, "full_stake_yuan": FULL_STAKE_YUAN,
                "outcome_boundary": OUTCOME_BOUNDARY,
            })
    return (
        sorted(output, key=lambda row: (str(row["issue_instance"]), int(row["source_selector_rank"]), str(row["portfolio_id"]))),
        sorted(decision_by_match.values(), key=lambda row: (str(row["issue_instance"]), int(row["match_id"]))),
    )


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


def build_ablation_selection(
    census: Sequence[dict[str, str]],
    scores: Sequence[dict[str, object]],
) -> list[dict[str, object]]:
    kall_census = sorted(
        (row for row in census if row["selector_id"] == KALL_SELECTOR),
        key=lambda row: row["issue_instance"],
    )
    by_issue: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in scores:
        by_issue[str(row["issue_instance"])].append(row)
    output: list[dict[str, object]] = []
    for census_row in kall_census:
        issue_instance = census_row["issue_instance"]
        candidates = by_issue.get(issue_instance, [])
        if len(candidates) != int(census_row["candidate_identity_count"]):
            raise RuntimeError(f"ablation candidate census drift: {issue_instance}")
        for ablation_id, score_field, market, fundamental, decision, rank_proxy, definition in ABLATIONS:
            selected = min(
                candidates,
                key=lambda row: (-float(row[score_field]), str(row["portfolio_id"])),
            ) if candidates else None
            output.append({
                "ablation_id": ablation_id,
                "score_field": score_field,
                "market": market,
                "rolling_fundamental": fundamental,
                "decision_chain": decision,
                "rank_timing_proxy": rank_proxy,
                "definition": definition,
                "issue": census_row["issue"],
                "year": census_row["year"],
                "fold": census_row["fold"],
                "issue_instance": issue_instance,
                "candidate_count_complete_issue": len(candidates),
                "policy_status": "SELECTED_PREOUTCOME" if selected else "NO_BET_FROZEN",
                "selected_identity_count": 1 if selected else 0,
                "selected_portfolio_id": selected["portfolio_id"] if selected else "",
                "selected_identity_fingerprint": selected["identity_fingerprint"] if selected else "",
                "selected_match_ids": selected["selected_match_ids"] if selected else "",
                "selected_score": selected[score_field] if selected else "",
                "full_ticket_count": FULL_TICKETS if selected else 0,
                "planned_stake_yuan": FULL_STAKE_YUAN if selected else 0,
                "no_bet_reason": "" if selected else "NO_QUALIFYING_COLD_ANCHOR",
                "tie_break": "score descending, then portfolio_id ascending",
                "outcome_boundary": OUTCOME_BOUNDARY,
            })
    expected = {"SELECTED_PREOUTCOME": 189, "NO_BET_FROZEN": 159}
    for ablation_id, *_ in ABLATIONS:
        actual = Counter(row["policy_status"] for row in output if row["ablation_id"] == ablation_id)
        if actual != expected:
            raise RuntimeError(f"ablation participation drift: {ablation_id} {actual}")
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
    raw_fields = {
        "MARKET_BEST_FULL": "market_gm_e_sp",
        "FUNDAMENTALS_ONLY": "fundamental_gm_confidence",
        "DECISION_CHAIN_ONLY": "decision_chain_gm_confidence",
        "FUNDAMENTALS_PLUS_DECISION": "combined_cross_issue_raw",
    }
    for arm, _field, _ in ARMS:
        selected = [row for row in selection if row["arm"] == arm and row["policy_status"] == "SELECTED_PREOUTCOME"]
        selected_portfolios = [by_key[(str(row["issue_instance"]), str(row["selected_portfolio_id"]))] for row in selected]
        raw_field = raw_fields[arm]
        selected_scores = [float(row[raw_field]) for row in selected_portfolios]
        for quantile in (0.00, 0.25, 0.50, 0.75):
            cutoff = empirical_quantile(selected_scores, quantile)
            eligible = sum(value >= cutoff for value in selected_scores)
            rows.append({
                "threshold_family": "SELECTED_RAW_SCORE_QUANTILE", "arm": arm, "metric": raw_field,
                "operator": ">=", "threshold_label": f"Q{int(quantile * 100):02d}", "threshold_value": compact(cutoff),
                "source_issue_count": len(selected), "eligible_selected_issue_count": eligible,
                "threshold_no_bet_issue_count": 348 - eligible, "planned_stake_yuan": eligible * FULL_STAKE_YUAN,
                "application_rule": "freeze the core-arm K1 identity first; threshold failure becomes NO_BET and never selects a replacement identity",
                "scientific_role": "secondary threshold sensitivity; primary K1 participation remains fixed",
                "missing_rule": "no implicit drop", "outcome_boundary": OUTCOME_BOUNDARY,
            })
    for arm in ("FUNDAMENTALS_ONLY", "FUNDAMENTALS_PLUS_DECISION"):
        selected = [row for row in selection if row["arm"] == arm and row["policy_status"] == "SELECTED_PREOUTCOME"]
        selected_portfolios = [by_key[(str(row["issue_instance"]), str(row["selected_portfolio_id"]))] for row in selected]
        for metric, operator, values in (
            ("fundamental_missing_fraction", "<=", (0.00, 0.25, 0.50, 1.00)),
            ("mean_history_depth", ">=", (0.0, 5.0, 10.0, 20.0)),
        ):
            for value in values:
                eligible = sum(float(row[metric]) <= value if operator == "<=" else float(row[metric]) >= value for row in selected_portfolios)
                rows.append({
                    "threshold_family": "FUNDAMENTAL_DATA_QUALITY", "arm": arm, "metric": metric,
                    "operator": operator, "threshold_label": str(value), "threshold_value": compact(value),
                    "source_issue_count": len(selected_portfolios), "eligible_selected_issue_count": eligible,
                    "threshold_no_bet_issue_count": 348 - eligible, "planned_stake_yuan": eligible * FULL_STAKE_YUAN,
                    "application_rule": "freeze the core-arm K1 identity first; threshold failure becomes NO_BET and never selects a replacement identity",
                    "scientific_role": "secondary missing-data sensitivity only",
                    "missing_rule": "neutral score retained and explicit missingness measured", "outcome_boundary": OUTCOME_BOUNDARY,
                })
    return rows


def build_match_feature_rows(features: dict[int, dict[str, object]]) -> list[dict[str, object]]:
    fields = (
        "elo_diff", "form_diff", "rank_diff", "rest_diff", "history_depth", "fundamental_p3",
        "fundamental_p1", "fundamental_p0", "fundamental_confidence", "fundamental_entropy",
        "fundamental_no_strength_confidence", "fundamental_no_form_confidence", "fundamental_no_rest_confidence",
        "rank_proxy_p3", "rank_proxy_p1", "rank_proxy_p0", "rank_proxy_confidence", "rank_proxy_entropy",
        "fundamental_missing",
    )
    return [{
        "match_id": match_id, "issue": row["issue"], "match_idx": row["match_idx"], "kickoff_ts": row["kickoff_ts"],
        "feature_cutoff_ts": row["feature_cutoff_ts"],
        "year": row["year"], "league": row["league"], "home_team_id": row["home_team_id"], "away_team_id": row["away_team_id"],
        "home_rank": row["home_rank"], "away_rank": row["away_rank"], "handicap_line_norm": row["handicap_line_norm"],
        **{field: compact(float(row[field])) for field in fields},
        "feature_boundary": "rolling history with match kickoff strictly before common issue cutoff; target outcomes are not selected",
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
        decision_chain = load_decision_chain()
        _selector_grid, census, identities, roles = load_frozen_inputs()
        match_ids = {int(role["match_id"]) for role in roles}
        target = read_target_features(db, match_ids)
        features, issue_cutoffs = build_match_features(db, target, roles)
        scores, decision_traces = build_portfolio_scores(identities, roles, features, decision_chain)
        selection = build_selection(census, scores)
        ablation_selection = build_ablation_selection(census, scores)
        issue_overlap, pair_overlap = overlap_rows(selection)
        thresholds = threshold_registry(selection, scores)
        feature_rows = build_match_feature_rows(features)
        role_rows = copy_candidate_roles(roles)
        census_by_issue = {
            row["issue_instance"]: row
            for row in census
            if row["selector_id"] == KALL_SELECTOR
        }
        cutoff_rows = [{
            "issue": census_by_issue[issue_instance]["issue"],
            "year": census_by_issue[issue_instance]["year"],
            "fold": census_by_issue[issue_instance]["fold"],
            "issue_instance": issue_instance,
            "feature_cutoff_ts": cutoff.isoformat(sep=" "),
            "cutoff_rule": "minimum kickoff_ts across immutable K_ALL candidate role union",
            "history_inclusion_rule": "match kickoff_ts strictly before feature_cutoff_ts",
            "outcome_boundary": OUTCOME_BOUNDARY,
        } for issue_instance, cutoff in sorted(issue_cutoffs.items())]

        candidate_fields = list(scores[0])
        selection_fields = list(selection[0])
        write_gzip(stage / "candidate_universe_scores.csv.gz", candidate_fields, scores)
        write_gzip(stage / "candidate_role_vectors.csv.gz", list(role_rows[0]), role_rows)
        write_gzip(stage / "match_feature_scores.csv.gz", list(feature_rows[0]), feature_rows)
        write_gzip(stage / "decision_chain_trace.csv.gz", list(decision_traces[0]), decision_traces)
        write_csv(stage / "selection_freeze.csv", selection_fields, selection)
        write_csv(stage / "ablation_selection_freeze.csv", list(ablation_selection[0]), ablation_selection)
        write_csv(stage / "issue_cutoff_registry.csv", list(cutoff_rows[0]), cutoff_rows)
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

        feature_manifest_rows = [
            {"feature_family": "MARKET_SELECTOR", "feature": "COLD_FIRST_RANK", "source_fields": "#167 selector_rank / MARKET_WF_CAL_MIN / E_SP / GM_E_SP", "availability_rule": "accepted outcome-unexposed #167 Gate A", "timing_grade": "FROZEN_ASOF", "primary_use": "MARKET_BEST_FULL and combined overlay", "missing_rule": "issue remains NO_BET when frozen candidate count is zero"},
            {"feature_family": "TEAM_STRENGTH", "feature": "ROLLING_ELO", "source_fields": "team ids, kickoff, fthg, ftag", "availability_rule": "history match kickoff_ts < common issue feature_cutoff_ts", "timing_grade": "STRICT_PRIOR_HISTORY", "primary_use": "fundamental score and leave-one-family-out ablation", "missing_rule": "neutral 1500 state; explicit missing flag"},
            {"feature_family": "TEAM_FORM", "feature": "ROLLING_LAST10_FORM_GOAL_DIFF", "source_fields": "last 10 strictly-prior points and clipped goal difference", "availability_rule": "history match kickoff_ts < common issue feature_cutoff_ts", "timing_grade": "STRICT_PRIOR_HISTORY", "primary_use": "fundamental score and leave-one-family-out ablation", "missing_rule": "neutral zero form; explicit history depth"},
            {"feature_family": "SCHEDULE_REST", "feature": "CAPPED_REST_DIFF", "source_fields": "common issue cutoff minus last strictly-prior history kickoff", "availability_rule": "history match kickoff_ts < common issue feature_cutoff_ts", "timing_grade": "STRICT_PRIOR_HISTORY", "primary_use": "fundamental score and leave-one-family-out ablation", "missing_rule": "720-hour neutral cap"},
            {"feature_family": "TEAM_RANK", "feature": "TARGET_HOME_AWAY_RANK", "source_fields": "matches.home_rank / matches.away_rank", "availability_rule": "no independent observation timestamp in source", "timing_grade": "HISTORICAL_TIMING_PROXY", "primary_use": "diagnostic rank_proxy fields only; excluded from all four controlling arms", "missing_rule": "zero rank component"},
            {"feature_family": "DECISION_CHAIN", "feature": "ACTIVE_V3_3_3_REDUCED_INPUT_REPLAY", "source_fields": "#167 p_model*, p_market_cal*, q_weight*, E_SP plus frozen handicap", "availability_rule": "q=E_SP×q_weight; predicted_SP=q/p_model; exact byte-bound active_v3.3.3 core", "timing_grade": "FROZEN_ASOF", "primary_use": "decision and combined overlay", "missing_rule": "fail closed on invalid probability/q/SP or decision output"},
            {"feature_family": "LINEUP_AVAILABILITY", "feature": "NOT_AVAILABLE", "source_fields": "none", "availability_rule": "no verifiable as-of field in frozen sources", "timing_grade": "UNAVAILABLE_NOT_USED", "primary_use": "none", "missing_rule": "family excluded rather than imputed"},
            {"feature_family": "TRAVEL_CONTEXT", "feature": "NOT_AVAILABLE", "source_fields": "none", "availability_rule": "no verifiable as-of field in frozen sources", "timing_grade": "UNAVAILABLE_NOT_USED", "primary_use": "none", "missing_rule": "family excluded rather than imputed"},
            {"feature_family": "MOTIVATION_NEWS", "feature": "NOT_AVAILABLE", "source_fields": "none", "availability_rule": "no verifiable as-of field in frozen sources", "timing_grade": "UNAVAILABLE_NOT_USED", "primary_use": "none", "missing_rule": "family excluded rather than imputed"},
        ]
        for row in feature_manifest_rows:
            row["outcome_boundary"] = OUTCOME_BOUNDARY
        write_csv(stage / "feature_manifest.csv", list(feature_manifest_rows[0]), feature_manifest_rows)

        market_ablation = {
            str(row["issue_instance"]): str(row["selected_portfolio_id"])
            for row in ablation_selection
            if row["ablation_id"] == "A0_MARKET_ONLY" and row["policy_status"] == "SELECTED_PREOUTCOME"
        }
        family_removed = {
            "A4_FUND_MINUS_STRENGTH": "TEAM_STRENGTH",
            "A5_FUND_MINUS_FORM": "TEAM_FORM",
            "A6_FUND_MINUS_REST": "SCHEDULE_REST",
            "A7_COMBINED_MINUS_STRENGTH": "TEAM_STRENGTH",
            "A8_COMBINED_MINUS_FORM": "TEAM_FORM",
            "A9_COMBINED_MINUS_REST": "SCHEDULE_REST",
        }
        ablation_rows = []
        for ablation_id, score_field, market, fundamental, decision, rank_proxy, definition in ABLATIONS:
            selected = [
                row for row in ablation_selection
                if row["ablation_id"] == ablation_id and row["policy_status"] == "SELECTED_PREOUTCOME"
            ]
            overlap = sum(
                market_ablation[str(row["issue_instance"])] == str(row["selected_portfolio_id"])
                for row in selected
            )
            ablation_rows.append({
                "ablation_id": ablation_id,
                "score_field": score_field,
                "market": market,
                "rolling_fundamental": fundamental,
                "decision_chain": decision,
                "rank_timing_proxy": rank_proxy,
                "family_removed": family_removed.get(ablation_id, ""),
                "controlling": "1" if ablation_id in {
                    "A0_MARKET_ONLY", "A1_FUNDAMENTALS_FULL", "A2_DECISION_ONLY", "A3_COMBINED_FULL"
                } else "0",
                "definition": definition,
                "selected_issue_count": len(selected),
                "frozen_no_bet_issue_count": 348 - len(selected),
                "same_identity_as_market_count": overlap,
                "different_identity_from_market_count": len(selected) - overlap,
                "selected_identity_set_sha256": canonical_hash(sorted(
                    (row["issue_instance"], row["selected_portfolio_id"]) for row in selected
                )),
                "selection_rule": "within complete issue K1; score descending then portfolio_id ascending",
                "outcome_boundary": OUTCOME_BOUNDARY,
            })
        write_csv(stage / "ablation_registry.csv", list(ablation_rows[0]), ablation_rows)

        segment_rows = [
            {"segment_id": "YEAR", "definition": "target calendar year 2020..2025", "controlling": "0", "use": "Gate B stability"},
            {"segment_id": "FOLD", "definition": "frozen OOS fold from #167", "controlling": "0", "use": "Gate B stability"},
            {"segment_id": "CANDIDATE_COUNT", "definition": "1 versus 2+ complete-issue candidates", "controlling": "0", "use": "selection opportunity sensitivity"},
            {"segment_id": "FUNDAMENTAL_MISSING", "definition": "selected identity missing fraction 0 versus >0", "controlling": "0", "use": "missing-data bias"},
            {"segment_id": "LOYO", "definition": "leave one target year out while preserving every issue intact; no row-level split", "controlling": "0", "use": "Gate B stability and signed lift"},
            {"segment_id": "PRIMARY", "definition": "all 348 frozen issues; 189 selected and 159 no-bet", "controlling": "1", "use": "primary matched comparison"},
        ]
        for row in segment_rows:
            row["outcome_boundary"] = OUTCOME_BOUNDARY
        write_csv(stage / "segment_registry.csv", list(segment_rows[0]), segment_rows)

        source_rows = [
            {"source": SOURCE_167, "role": "accepted candidate/identity/role-vector definition", "manifest_sha256": SOURCE_167_MANIFEST, "content_identity_sha256": SOURCE_167_CONTENT, "parsed": "selector registry/census/identity/role payloads only", "payload_count": len(payload_167)},
            {"source": SOURCE_170_A, "role": "accepted BEST_FULL incumbent identity and participation reproduction", "manifest_sha256": SOURCE_170_A_MANIFEST, "content_identity_sha256": SOURCE_170_A_CONTENT, "parsed": "Gate-A identity and participation only", "payload_count": len(payload_170a)},
            {"source": SOURCE_170_B, "role": "terminal attribution evidence durability binding", "manifest_sha256": SOURCE_170_B_MANIFEST, "content_identity_sha256": SOURCE_170_B_CONTENT, "parsed": "NO; manifest/content/payload hashes only", "payload_count": len(payload_170b)},
            {"source": str(DB_REPOSITORY_PATH), "role": "target identity-safe features and rolling pre-issue-cutoff team history", "manifest_sha256": DB_SHA256, "content_identity_sha256": DB_SHA256, "parsed": "target safe columns; historical scores with kickoff strictly before frozen issue cutoff", "payload_count": 1},
            {"source": str(DECISION_CHAIN_SOURCE_PATH), "role": "documented active_v3.3.3 decision-chain core", "manifest_sha256": DECISION_CHAIN_SOURCE_SHA256, "content_identity_sha256": DECISION_CHAIN_SOURCE_SHA256, "parsed": "structured_decision_for_payload only over frozen reduced inputs", "payload_count": 1},
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
            "database": {"repository_path": str(DB_REPOSITORY_PATH), "resolved_path_not_persisted": True, "sha256": DB_SHA256, "target_query_columns": list(TARGET_FIELDS), "history_query_rule": "match kickoff_ts strictly before frozen common issue cutoff"},
            "decision_chain": {"version": DECISION_CHAIN_VERSION, "repository_path": str(DECISION_CHAIN_SOURCE_PATH), "sha256": DECISION_CHAIN_SOURCE_SHA256, "frozen_package_copy": "decision_chain_runner.py", "input_rule": "MODEL_P_CAL probabilities; q=E_SP×Q_WEIGHT; predicted_SP=q/p; frozen handicap; unavailable historical text/context retained explicitly"},
            "candidate_selector_id": KALL_SELECTOR, "incumbent_selector_id": K1_SELECTOR,
            "issue_cutoff_registry_sha256": canonical_hash(sorted(
                (issue_instance, cutoff.isoformat(sep=" ")) for issue_instance, cutoff in issue_cutoffs.items()
            )),
        }
        (stage / "source_binding.json").write_text(dump_json(source_binding), encoding="utf-8")
        card = {
            "issue": ISSUE, "contract": CONTRACT, "version": VERSION,
            "stage": "REPLACEMENT_GATE_A_OUTCOME_UNEXPOSED_FOUR_ARM_K1_FULL_FREEZE",
            "supersedes": {"pr": 158, "head": "f2e5d427a71d74b7b789a0e594eda1c55569ab73", "reason": "obsolete #132 threshold surface; historical evidence only"},
            "incumbent": {"alias": "BEST_FULL", "selector_id": K1_SELECTOR, "allocation": "FULL_ENUMERATED", "tickets": FULL_TICKETS, "stake_yuan": FULL_STAKE_YUAN, "selected_issue_count": 189, "frozen_no_bet_issue_count": 159, "controlling_baseline_no_tax_roi": -0.0947, "attribution_only_common_full_roi": -0.0909},
            "candidate_universe": {"selector_id": KALL_SELECTOR, "issue_census": 348, "participating_issues": 189, "frozen_no_bet_issues": 159, "identity_count": 424, "candidate_count_range": [0, 7], "fixed_participation": True},
            "arms": [{"arm": arm, "score_field": field, "definition": definition} for arm, field, definition in ARMS],
            "scoring": {"market": "exact #167 K_ALL COLD_FIRST rank", "fundamental": "geometric mean of seven strict pre-issue-cutoff rolling Elo/form/rest confidences; target rank excluded", "rank_proxy_diagnostic": "rank-augmented construction with unstamped target home/away rank; timing proxy only and excluded from controlling arms", "decision": "geometric mean of seven exact active_v3.3.3 decision confidence outputs using frozen reduced inputs", "decision_input_reconstruction": "q=E_SP×q_weight and predicted_SP=q/p_model; exact core hash bound", "combined": "within-issue 0.50 market + 0.25 fundamental + 0.25 decision percentile", "tie_break": "score descending then portfolio_id ascending"},
            "missing_data": "retain identity; neutral default team state and explicit missing fraction; no silent drop",
            "thresholds": "primary K1 has no post-score rejection; secondary pre-registered score-quantile and fundamental data-quality thresholds are diagnostic only",
            "segments": "primary complete-issue denominator; year/fold/candidate-count/missingness are non-controlling diagnostics",
            "denominator": {"issue_rows": len(selection), "issue_census": 348, "candidate_identity_rows": len(scores), "candidate_role_rows": len(role_rows), "unique_match_feature_rows": len(feature_rows), "decision_trace_rows": len(decision_traces), "issue_cutoff_rows": len(cutoff_rows), "ablation_issue_rows": len(ablation_selection), "ablation_count": len(ABLATIONS), "selected_by_arm": dict(selected_counts), "no_bet_by_arm": dict(no_bet_counts), "planned_stake_per_arm_yuan": 189 * FULL_STAKE_YUAN},
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
            "Fundamentals use rolling history strictly before a common issue cutoff; decision scores replay the byte-bound active_v3.3.3 core. "
            "#170 Gate B is cryptographically bound but not parsed. Gate B for #134 is not authorized.\n"
        )
        (stage / "README.md").write_text(readme, encoding="utf-8")
        shutil.copyfile(decision_chain_source(), stage / "decision_chain_runner.py")
        shutil.copyfile(Path(__file__).resolve(), stage / "freeze_runner.py")

        payloads = sorted(path for path in stage.iterdir() if path.is_file())
        content = {
            "contract_version": VERSION,
            "denominator": card["denominator"],
            "controls": {
                "candidate_selector_id": KALL_SELECTOR, "incumbent_selector_id": K1_SELECTOR,
                "source_167_manifest_sha256": SOURCE_167_MANIFEST, "source_170_gate_a_manifest_sha256": SOURCE_170_A_MANIFEST,
                "source_170_gate_b_manifest_sha256": SOURCE_170_B_MANIFEST, "database_sha256": DB_SHA256,
                "decision_chain_source_sha256": DECISION_CHAIN_SOURCE_SHA256,
                "issue_cutoff_registry_sha256": source_binding["issue_cutoff_registry_sha256"],
                "market_selected_identity_sha256": canonical_hash(sorted((row["issue_instance"], row["selected_portfolio_id"]) for row in selection if row["arm"] == "MARKET_BEST_FULL" and row["policy_status"] == "SELECTED_PREOUTCOME")),
                "ablation_selected_identity_sha256": canonical_hash(sorted((row["ablation_id"], row["issue_instance"], row["selected_portfolio_id"]) for row in ablation_selection if row["policy_status"] == "SELECTED_PREOUTCOME")),
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
