#!/usr/bin/env python3
"""Freeze #134 Plan-v3's outcome-unexposed quick FULL-N7 selector core."""
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
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from pathlib import Path
from types import ModuleType


CONTRACT = "BJ-HIST-FUNDAMENTAL-OVERLAY-N7-001"
VERSION = "bj134-gate-a-v3"
ISSUE = 134
UNIT_STAKE_YUAN = 2
FULL_TICKETS = 3 ** 7
FULL_STAKE_YUAN = UNIT_STAKE_YUAN * FULL_TICKETS
DB_REPOSITORY_PATH = Path("data/derived/beidan_xlsm/beidan_xlsm.sqlite")
DB_SHA256 = "7f62079b18b3c028884da92aa8393f5b198246c9d7c32cd0b401562a055c5d6f"
BASE_MAIN_COMMIT = "d300d0bdb93efada661bfa039788e6536ff89257"

SOURCE_167 = "bj167_gate_a_strategy_atlas_v3r1"
SOURCE_167_MANIFEST = "5a82422755723453638d25c90f91213da046a9e7bed87a851b2e5700faa9c724"
SOURCE_167_CONTENT = "0806185a7a68b99fd2a6a465308d11e2886995f992bfa722adb287a4e6a4d147"
SOURCE_170_A = "bj170_gate_a_preoutcome_v2"
SOURCE_170_A_MANIFEST = "bb60ac5638d29674ad8c1c05f1ffe3ab9cdf12acb70ebdae6cea679743136d87"
SOURCE_170_A_CONTENT = "adc4d0f96628c784149da998a20e8830cde26db4001fe457eaf9ca4b7bb74223"
SOURCE_170_B = "bj170_gate_b_selector_allocator_stack_v1"
SOURCE_170_B_MANIFEST = "08e83353ad483e5d75911116a413186f007385f5dd37b8c4b757ac903221e512"
SOURCE_170_B_CONTENT = "75325aa0f60e277ad3fbf9d90116450833106bc3863b412ea3efcad9948a47b2"
SOURCE_175_PATH = Path("docs/research-notes/Issue-167-N7-Strategy-Atlas-Decision-Guide.md")
SOURCE_175_SHA256 = "ec8161fc430c6ea4133f1da7c805772bbd8c8d22cffe8d450380e1c044b34681"
SOURCE_175_MERGE = "56331b4"
SOURCE_176 = "bj176_issue_equity_risk_v1"
SOURCE_176_MANIFEST = "39316952296c2349f5da2f963d43c0baf0d812fba4eea967536a8b80bd57d5ee"
SOURCE_176_CONTENT = "94188354baf01c68cb0ec0791248d3f8f03e31d4a7011db7b6b68e9797720f5c"
SOURCE_176_MERGE = BASE_MAIN_COMMIT

CORE_SOURCE_PATH = Path("scripts/bj134_quick_core.py")
CORE_SOURCE_SHA256 = "0836a11fe411ee080069400111170124b81ba8461114bcf9a87884837f12ef9a"
K1_SELECTOR = "S2_ESP290_GM300_MARKET_WF_CAL_MIN_LOWP20_COLD_FIRST_K1"
KALL_SELECTOR = "S2_ESP290_GM300_MARKET_WF_CAL_MIN_LOWP20_COLD_FIRST_K_ALL"
OUTCOME_BOUNDARY = (
    "Gate A outcome-unexposed: candidate target result/final-SP/payout/tax/ROI/settlement "
    "fields are not read by target projection or identity ranking"
)

ARMS = (
    ("B0_BEST_FULL", "market_gm_e_sp", "exact accepted COLD_FIRST rank-one identity", "PRIMARY"),
    ("L1_LEAGUE_CORE", "league_gm_e_sp", "outer-year shrunk league/regime probability", "PRIMARY"),
    ("T1_TEAM_CORE", "team_gm_e_sp", "strict rolling team Poisson handicap probability", "PRIMARY"),
    ("M1_MARKET_DYNAMICS", "market_dynamics_gm_e_sp", "initial-to-10h-to-1h market residual probability", "PRIMARY"),
    ("F1_CORE_ALL", "combined_gm_e_sp", "fixed L/T/M log pool 0.30/0.30/0.40", "PRIMARY"),
    ("D1_DECISION_CHAIN_CORE", "decision_lexicographic", "fixed risk-first FULL-N7 decision chain", "PRIMARY"),
    ("F_MINUS_L", "combined_minus_league_gm_e_sp", "combined core leaving out league", "LOFO"),
    ("F_MINUS_T", "combined_minus_team_gm_e_sp", "combined core leaving out team", "LOFO"),
    ("F_MINUS_M", "combined_minus_market_gm_e_sp", "combined core leaving out market dynamics", "LOFO"),
)
PROBABILITY_ARMS = {
    "L1_LEAGUE_CORE": "league",
    "T1_TEAM_CORE": "team",
    "M1_MARKET_DYNAMICS": "market_dynamics",
    "F1_CORE_ALL": "combined",
    "F_MINUS_L": "combined_minus_league",
    "F_MINUS_T": "combined_minus_team",
    "F_MINUS_M": "combined_minus_market",
}
TARGET_QUERY_COLUMNS = (
    "match_id", "issue", "match_idx", "kickoff_ts", "year", "league",
    "home_team_id", "away_team_id", "home_rank", "away_rank", "handicap_line_norm",
    "euro_initial_n", "euro_initial_v1", "euro_initial_v2", "euro_initial_v3",
    "euro_10h_n", "euro_10h_v1", "euro_10h_v2", "euro_10h_v3",
    "euro_1h_n", "euro_1h_v1", "euro_1h_v2", "euro_1h_v3",
    "euro_1h_min1", "euro_1h_min2", "euro_1h_min3",
    "euro_1h_max1", "euro_1h_max2", "euro_1h_max3",
    "asian_initial_n", "asian_initial_v1", "asian_initial_v2", "asian_initial_v3",
    "asian_10h_n", "asian_10h_v1", "asian_10h_v2", "asian_10h_v3",
    "asian_1h_n", "asian_1h_v1", "asian_1h_v2", "asian_1h_v3",
    "ou_initial_n", "ou_initial_v1", "ou_initial_v2", "ou_initial_v3",
    "ou_10h_n", "ou_10h_v1", "ou_10h_v2", "ou_10h_v3",
    "ou_1h_n", "ou_1h_v1", "ou_1h_v2", "ou_1h_v3",
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
RISK_176 = ROOT / "results" / SOURCE_176
DEFAULT_OUTPUT = ROOT / "results" / "bj134_gate_a_preoutcome_v3"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


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
    with path.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
        text = io.TextIOWrapper(zipped, encoding="utf-8", newline="")
        writer = csv.DictWriter(text, fieldnames=fields, extrasaction="raise", lineterminator="\n")
        writer.writeheader()
        writer.writerows(materialized)
        text.flush()
        text.detach()
    return len(materialized)


def write_gzip_json(path: Path, value: object) -> None:
    encoded = dump_json(value).encode()
    with path.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
        zipped.write(encoded)


def verify_package(directory: Path, expected_manifest: str, expected_content: str) -> dict[str, str]:
    if sha256_file(directory / "SHA256SUMS.json") != expected_manifest:
        raise RuntimeError(f"manifest drift: {directory.name}")
    if sha256_file(directory / "CONTENT_IDENTITY.json") != expected_content:
        raise RuntimeError(f"content identity drift: {directory.name}")
    declared = json.loads((directory / "SHA256SUMS.json").read_text(encoding="utf-8"))
    actual = sorted(path.name for path in directory.iterdir() if path.is_file() and path.name != "SHA256SUMS.json")
    if sorted(declared) != actual:
        raise RuntimeError(f"manifest coverage drift: {directory.name}")
    for name, expected in declared.items():
        if sha256_file(directory / name) != expected:
            raise RuntimeError(f"payload drift: {directory.name}/{name}")
    return declared


def locate_database(root: Path = ROOT) -> Path:
    for candidate in [root / DB_REPOSITORY_PATH, *(parent / DB_REPOSITORY_PATH for parent in root.parents)]:
        if candidate.exists():
            return candidate.resolve()
    raise RuntimeError("canonical source database unavailable")


def ro_connection(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro&immutable=1", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def build_source_schema(
    db: Path,
    census: Sequence[Mapping[str, object]],
    identities: Sequence[Mapping[str, object]],
    roles: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    connection = ro_connection(db)
    try:
        tables = {}
        for table in ("matches", "match_features", "market_consensus"):
            tables[table] = [
                {
                    "cid": row["cid"],
                    "name": row["name"],
                    "type": row["type"],
                    "notnull": row["notnull"],
                    "default": row["dflt_value"],
                    "pk": row["pk"],
                }
                for row in connection.execute(f"PRAGMA table_info({table})")
            ]
    finally:
        connection.close()
    return {
        "database_sha256": DB_SHA256,
        "database_tables": tables,
        "upstream_csv_fields": {
            "selector_issue_census.csv": list(census[0]),
            "selection_identities.csv.gz": list(identities[0]),
            "candidate_role_vectors.csv.gz": list(roles[0]),
        },
        "target_projection": {
            "columns": list(TARGET_QUERY_COLUMNS),
            "forbidden_families": [
                "target result/score", "final or winning SP", "payout", "tax", "ROI", "settlement"
            ],
        },
        "market_snapshot_semantics": {
            "source": "market_consensus",
            "included": ["initial", "10h", "1h"],
            "excluded": ["final"],
            "vector_rule": "n>0 and v1/v2/v3 present",
            "euro_probability_rule": "no-vig inverse odds",
            "asian_ou_rule": "published consensus line v2; v1/v3 retained for coverage audit",
        },
        "training_projection": {
            "outcomes": "permitted only for kickoff/calendar periods strictly before the target cutoff/fold",
            "outer_year": "calendar year < target year",
            "team_state": "kickoff < common issue cutoff",
        },
        "outcome_boundary": OUTCOME_BOUNDARY,
    }


def core_source() -> Path:
    bundled = Path(__file__).resolve().with_name("bj134_quick_core.py")
    return bundled if bundled.is_file() else ROOT / CORE_SOURCE_PATH


def load_core() -> ModuleType:
    path = core_source()
    actual = sha256_file(path)
    if CORE_SOURCE_SHA256 != "TO_BE_FILLED" and actual != CORE_SOURCE_SHA256:
        raise RuntimeError(f"quick-core source drift: {actual} != {CORE_SOURCE_SHA256}")
    spec = importlib.util.spec_from_file_location("bj134_quick_core_frozen", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load quick core")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


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
    selector_grid = [
        row for row in read_csv(GATE_A_167 / "selector_grid.csv")
        if row["selector_id"] in {K1_SELECTOR, KALL_SELECTOR}
    ]
    if {row["selector_id"] for row in selector_grid} != {K1_SELECTOR, KALL_SELECTOR}:
        raise RuntimeError("selector registry incomplete")
    census = [
        row for row in read_csv(GATE_A_167 / "selector_census.csv")
        if row["selector_id"] in {K1_SELECTOR, KALL_SELECTOR}
    ]
    if Counter(row["selector_id"] for row in census) != {K1_SELECTOR: 348, KALL_SELECTOR: 348}:
        raise RuntimeError("selector census drift")
    identities: list[dict[str, str]] = []
    for path in relevant_shards("selector_identities"):
        with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
            identities.extend(
                row for row in csv.DictReader(handle)
                if row["selector_id"] in {K1_SELECTOR, KALL_SELECTOR}
            )
    k1 = [row for row in identities if row["selector_id"] == K1_SELECTOR]
    kall = [row for row in identities if row["selector_id"] == KALL_SELECTOR]
    if len(k1) != 189 or len(kall) != 424:
        raise RuntimeError(f"identity denominator drift: K1={len(k1)} KALL={len(kall)}")
    k1_keys = {(row["issue_instance"], row["portfolio_id"]) for row in k1}
    rank1_keys = {
        (row["issue_instance"], row["portfolio_id"])
        for row in kall if row["selector_rank"] == "1"
    }
    if k1_keys != rank1_keys:
        raise RuntimeError("K1 does not reproduce K_ALL rank 1")
    candidate_keys = {(row["issue_instance"], row["portfolio_id"]) for row in kall}
    roles: list[dict[str, str]] = []
    for path in relevant_shards("selector_role_vectors"):
        with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
            roles.extend(
                row for row in csv.DictReader(handle)
                if row["selector_id"] == KALL_SELECTOR
                and (row["issue_instance"], row["portfolio_id"]) in candidate_keys
            )
    if len(roles) != len(kall) * 7:
        raise RuntimeError(f"role denominator drift: {len(roles)}")
    with gzip.open(GATE_A_170 / "identity_freeze.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        best170 = [row for row in csv.DictReader(handle) if row["selector_alias"] == "BEST_FULL"]
    participation = [
        row for row in read_csv(GATE_A_170 / "selector_issue_participation.csv")
        if row["selector_alias"] == "BEST_FULL"
    ]
    if len(best170) != 189 or len(participation) != 348:
        raise RuntimeError("#170 BEST_FULL denominator drift")
    if {(row["issue_instance"], row["portfolio_id"]) for row in best170} != k1_keys:
        raise RuntimeError("#170 BEST_FULL identity drift")
    if Counter(row["frozen_policy_status"] for row in participation) != {
        "SELECTED_PREOUTCOME": 189, "NO_BET_FROZEN": 159
    }:
        raise RuntimeError("#170 BEST_FULL participation drift")
    return (
        selector_grid,
        census,
        sorted(kall, key=lambda row: (row["issue_instance"], int(row["selector_rank"]), row["portfolio_id"])),
        sorted(roles, key=lambda row: (row["issue_instance"], row["portfolio_id"], int(row["selection_rank"]))),
    )


def _market_joins() -> str:
    joins = []
    aliases = {
        "ei": ("euro_1x2", "initial"), "e10": ("euro_1x2", "10h"), "e1": ("euro_1x2", "1h"),
        "ai": ("asian_handicap", "initial"), "a10": ("asian_handicap", "10h"), "a1": ("asian_handicap", "1h"),
        "oi": ("over_under", "initial"), "o10": ("over_under", "10h"), "o1": ("over_under", "1h"),
    }
    for alias, (market, snapshot) in aliases.items():
        joins.append(
            f"LEFT JOIN market_consensus {alias} ON {alias}.match_id=m.match_id "
            f"AND {alias}.market='{market}' AND {alias}.snapshot='{snapshot}'"
        )
    return "\n".join(joins)


def _market_select() -> str:
    pieces = []
    for prefix, alias in (
        ("euro_initial", "ei"), ("euro_10h", "e10"), ("euro_1h", "e1"),
        ("asian_initial", "ai"), ("asian_10h", "a10"), ("asian_1h", "a1"),
        ("ou_initial", "oi"), ("ou_10h", "o10"), ("ou_1h", "o1"),
    ):
        pieces.extend([
            f"{alias}.n_complete AS {prefix}_n",
            f"{alias}.v1_avg AS {prefix}_v1",
            f"{alias}.v2_avg AS {prefix}_v2",
            f"{alias}.v3_avg AS {prefix}_v3",
        ])
        if prefix == "euro_1h":
            pieces.extend([
                f"{alias}.v{position}_min AS {prefix}_min{position}" for position in (1, 2, 3)
            ])
            pieces.extend([
                f"{alias}.v{position}_max AS {prefix}_max{position}" for position in (1, 2, 3)
            ])
    return ",\n".join(pieces)


def read_target_features(db: Path, match_ids: set[int]) -> dict[int, dict[str, object]]:
    connection = ro_connection(db)
    output: dict[int, dict[str, object]] = {}
    for start in range(0, len(match_ids), 700):
        chunk = sorted(match_ids)[start:start + 700]
        placeholders = ",".join("?" for _ in chunk)
        query = f"""
            SELECT m.match_id, m.issue, m.match_idx, m.kickoff_ts, mf.season_year AS year,
                   m.league, m.home_team_id, m.away_team_id, m.home_rank, m.away_rank,
                   mf.handicap_line_norm, {_market_select()}
              FROM matches m JOIN match_features mf ON mf.match_id=m.match_id
              {_market_joins()}
             WHERE m.match_id IN ({placeholders})
        """
        for row in connection.execute(query, chunk):
            payload = dict(row)
            output[int(payload["match_id"])] = payload
    connection.close()
    if set(output) != match_ids:
        raise RuntimeError(f"target safe-feature join drift: {len(output)} != {len(match_ids)}")
    return output


def target_projection(row: Mapping[str, object]) -> dict[str, object]:
    """Canonical target-safe projection used by mutation regression tests."""
    return {field: row.get(field) for field in TARGET_QUERY_COLUMNS}


def build_snapshot_coverage(
    target: Mapping[int, Mapping[str, object]],
) -> list[dict[str, object]]:
    """Freeze complete-vector coverage without changing the retained cohort."""
    rows: list[dict[str, object]] = []
    for market in ("euro", "asian", "ou"):
        for snapshot in ("initial", "10h", "1h"):
            prefix = f"{market}_{snapshot}"
            missing = sorted(
                match_id
                for match_id, row in target.items()
                if int(float(row.get(f"{prefix}_n") or 0)) <= 0
                or any(row.get(f"{prefix}_v{position}") is None for position in (1, 2, 3))
            )
            rows.append({
                "market": market.upper(),
                "snapshot": snapshot.upper(),
                "required_fields": f"{prefix}_n>0|{prefix}_v1|{prefix}_v2|{prefix}_v3",
                "candidate_match_count": len(target),
                "complete_vector_count": len(target) - len(missing),
                "missing_vector_count": len(missing),
                "missing_match_ids_sha256": canonical_hash(missing),
                "selection_policy": "RETAIN_IDENTITY_USE_EXPLICIT_MISSING_BUCKET",
                "controlling_value": "NO_VIG_VECTOR" if market == "euro" else "PUBLISHED_LINE_V2",
                "outcome_boundary": OUTCOME_BOUNDARY,
            })
    return rows


def historical_rows(db: Path, before: str, with_markets: bool) -> Iterator[dict[str, object]]:
    connection = ro_connection(db)
    market_select = f", {_market_select()}" if with_markets else ""
    market_joins = _market_joins() if with_markets else ""
    query = f"""
        SELECT m.match_id, m.kickoff_ts, mf.season_year AS year, m.league,
               m.home_team_id, m.away_team_id, mf.handicap_line_norm, mf.fthg, mf.ftag
               {market_select}
          FROM matches m JOIN match_features mf ON mf.match_id=m.match_id
          {market_joins}
         WHERE m.kickoff_ts IS NOT NULL AND m.kickoff_ts < ?
           AND m.home_team_id IS NOT NULL AND m.away_team_id IS NOT NULL
           AND mf.fthg IS NOT NULL AND mf.ftag IS NOT NULL
         ORDER BY m.kickoff_ts, m.match_id
    """
    try:
        for row in connection.execute(query, (before,)):
            yield dict(row)
    finally:
        connection.close()


def fit_outer_year_models(db: Path, target_years: Sequence[int], core: ModuleType) -> dict[int, object]:
    accumulator = core.TrainingAccumulator()
    output: dict[int, object] = {}
    years = sorted(set(target_years))
    next_index = 0
    for row in historical_rows(db, f"{max(years)}-01-01 00:00:00", with_markets=True):
        row_year = int(str(row["kickoff_ts"])[:4])
        while next_index < len(years) and row_year >= years[next_index]:
            output[years[next_index]] = accumulator.frozen_copy()
            next_index += 1
        accumulator.update(row)
    while next_index < len(years):
        output[years[next_index]] = accumulator.frozen_copy()
        next_index += 1
    if any(model.training_rows == 0 for model in output.values()):
        raise RuntimeError("empty outer-year training fold")
    return output


def frozen_issue_cutoffs(roles: Sequence[dict[str, str]], core: ModuleType) -> tuple[dict[str, dt.datetime], dict[int, dt.datetime]]:
    by_issue: dict[str, list[dt.datetime]] = defaultdict(list)
    match_issues: dict[int, set[str]] = defaultdict(set)
    for role in roles:
        timestamp = core.parse_ts(role["kickoff_ts"])
        if timestamp is None:
            raise RuntimeError(f"missing frozen kickoff: {role['match_id']}")
        by_issue[role["issue_instance"]].append(timestamp)
        match_issues[int(role["match_id"])].add(role["issue_instance"])
    issue_cutoffs = {issue: min(values) for issue, values in by_issue.items()}
    match_cutoffs: dict[int, dt.datetime] = {}
    for match_id, issue_instances in match_issues.items():
        values = {issue_cutoffs[issue] for issue in issue_instances}
        if len(values) != 1:
            raise RuntimeError(f"match mapped to inconsistent issue cutoffs: {match_id}")
        match_cutoffs[match_id] = values.pop()
    return issue_cutoffs, match_cutoffs


def build_match_features(
    db: Path,
    target: dict[int, dict[str, object]],
    roles: Sequence[dict[str, str]],
    models: Mapping[int, object],
    core: ModuleType,
) -> tuple[dict[int, dict[str, object]], dict[str, dt.datetime]]:
    issue_cutoffs, match_cutoffs = frozen_issue_cutoffs(roles, core)
    target_by_cutoff: dict[dt.datetime, list[int]] = defaultdict(list)
    for match_id, cutoff in match_cutoffs.items():
        target_by_cutoff[cutoff].append(match_id)
    history = historical_rows(db, max(issue_cutoffs.values()).isoformat(sep=" "), with_markets=False)
    history_iter = iter(history)
    pending = next(history_iter, None)
    state = core.TeamState()
    output: dict[int, dict[str, object]] = {}
    for cutoff in sorted(target_by_cutoff):
        while pending is not None:
            timestamp = core.parse_ts(pending["kickoff_ts"])
            if timestamp is None:
                raise RuntimeError(f"invalid history kickoff: {pending['match_id']}")
            if timestamp >= cutoff:
                break
            state.update(pending)
            pending = next(history_iter, None)
        for match_id in sorted(target_by_cutoff[cutoff]):
            safe = target_projection(target[match_id])
            year = int(safe["year"])
            model = models[year]
            league = str(safe.get("league") or "__MISSING__")
            home_goals, away_goals = model.goal_prior(league)
            team = state.snapshot(safe, cutoff, home_goals, away_goals)
            league_p = model.league_probabilities(safe)
            market_p = model.market_probabilities(safe)
            team_p = tuple(float(team[f"team_p{code}"]) for code in core.CODES)
            combined = core.blend_probabilities(((league_p, 0.30), (team_p, 0.30), (market_p, 0.40)))
            minus_l = core.blend_probabilities(((team_p, 3 / 7), (market_p, 4 / 7)))
            minus_t = core.blend_probabilities(((league_p, 3 / 7), (market_p, 4 / 7)))
            minus_m = core.blend_probabilities(((league_p, 0.50), (team_p, 0.50)))
            signature = core.market_signature(safe)
            league_train_n = sum(model.league_counts[league].values())
            market_missing = int(any(value == "MISSING" for value in signature.values()))
            output[match_id] = {
                **safe,
                "feature_cutoff_ts": cutoff.isoformat(sep=" "),
                "outer_year_train_rule": f"year < {year}",
                "league_train_n": league_train_n,
                **team,
                **{f"league_p{code}": league_p[index] for index, code in enumerate(core.CODES)},
                **{f"market_dynamics_p{code}": market_p[index] for index, code in enumerate(core.CODES)},
                **{f"combined_p{code}": combined[index] for index, code in enumerate(core.CODES)},
                **{f"combined_minus_league_p{code}": minus_l[index] for index, code in enumerate(core.CODES)},
                **{f"combined_minus_team_p{code}": minus_t[index] for index, code in enumerate(core.CODES)},
                **{f"combined_minus_market_p{code}": minus_m[index] for index, code in enumerate(core.CODES)},
                **{f"market_signature_{key}": value for key, value in signature.items()},
                "market_missing": market_missing,
                "timing_risk": int(team["team_missing"] or market_missing or league_train_n < 30),
                "target_rank_timing_grade": "HISTORICAL_TIMING_PROXY_NOT_USED",
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
    if set(output) != set(target):
        raise RuntimeError("target feature output drift")
    return output, issue_cutoffs


def geometric(values: Sequence[float]) -> float:
    if not values or any(value <= 0 or not math.isfinite(value) for value in values):
        return 0.0
    return math.exp(sum(math.log(value) for value in values) / len(values))


def predicted_sp(role: Mapping[str, str]) -> tuple[float, float, float]:
    probabilities = [float(role[f"p_model{code}"]) for code in ("3", "1", "0")]
    expected_sp = float(role["e_sp"])
    q = [expected_sp * float(role[f"q_weight{code}"]) for code in ("3", "1", "0")]
    if abs(sum(q) - expected_sp) > 2e-9:
        raise RuntimeError(f"q reconstruction drift: {role['match_id']}")
    return tuple(q[index] / probabilities[index] for index in range(3))


def argmax_code(values: Sequence[float]) -> str:
    index = max(range(3), key=lambda item: (values[item], -item))
    return ("3", "1", "0")[index]


def compact(value: object) -> object:
    return f"{value:.12f}" if isinstance(value, float) else value


def build_portfolio_scores(
    identities: Sequence[dict[str, str]],
    roles: Sequence[dict[str, str]],
    features: Mapping[int, Mapping[str, object]],
) -> list[dict[str, object]]:
    candidate_count_by_issue = Counter(identity["issue_instance"] for identity in identities)
    roles_by_key: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for role in roles:
        roles_by_key[(role["issue_instance"], role["portfolio_id"])].append(role)
    output = []
    for identity in identities:
        key = (identity["issue_instance"], identity["portfolio_id"])
        frozen_roles = sorted(roles_by_key[key], key=lambda row: int(row["selection_rank"]))
        if len(frozen_roles) != 7 or [row["match_id"] for row in frozen_roles] != identity["selected_match_ids"].split("|"):
            raise RuntimeError(f"identity/role drift: {key}")
        arm_leg_scores: dict[str, list[float]] = {value: [] for value in PROBABILITY_ARMS.values()}
        timing_risk = handicap_conflict = probability_conflict = 0
        for role in frozen_roles:
            feature = features[int(role["match_id"])]
            sp = predicted_sp(role)
            vectors = {
                name: [float(feature[f"{name}_p{code}"]) for code in ("3", "1", "0")]
                for name in PROBABILITY_ARMS.values()
            }
            for name, vector in vectors.items():
                arm_leg_scores[name].append(sum(vector[index] * sp[index] for index in range(3)))
            timing_risk += int(feature["timing_risk"])
            league_top, team_top = argmax_code(vectors["league"]), argmax_code(vectors["team"])
            if abs(float(feature["handicap_line_norm"] or 0.0)) >= 1.0 and league_top != team_top:
                handicap_conflict += 1
            model_vector = [float(role[f"p_model{code}"]) for code in ("3", "1", "0")]
            q_vector = [float(role[f"q_weight{code}"]) for code in ("3", "1", "0")]
            if argmax_code(model_vector) != argmax_code(vectors["market_dynamics"]):
                probability_conflict += 1
            if argmax_code(q_vector) != argmax_code(vectors["combined"]):
                probability_conflict += 1
        raw = {f"{name}_gm_e_sp": geometric(values) for name, values in arm_leg_scores.items()}
        output.append({
            "issue": identity["issue"], "year": identity["year"], "fold": identity["fold"],
            "issue_instance": identity["issue_instance"], "portfolio_id": identity["portfolio_id"],
            "source_selector_rank": int(identity["selector_rank"]),
            "candidate_match_id": identity["candidate_match_id"],
            "selected_match_ids": identity["selected_match_ids"],
            "identity_fingerprint": identity["identity_fingerprint"],
            "candidate_count_complete_issue": candidate_count_by_issue[identity["issue_instance"]],
            "market_gm_e_sp": float(identity["gm_e_sp"]),
            **raw,
            "decision_missing_timing_legs": timing_risk,
            "decision_handicap_contradiction_legs": handicap_conflict,
            "decision_probability_q_conflict_count": probability_conflict,
            "decision_f1_gm_e_sp": raw["combined_gm_e_sp"],
            "full_ticket_count": FULL_TICKETS,
            "full_stake_yuan": FULL_STAKE_YUAN,
            "outcome_boundary": OUTCOME_BOUNDARY,
        })
    return sorted(output, key=lambda row: (row["issue_instance"], row["source_selector_rank"], row["portfolio_id"]))


def select_candidate(arm: str, candidates: Sequence[dict[str, object]]) -> dict[str, object]:
    if arm == "B0_BEST_FULL":
        return min(candidates, key=lambda row: (int(row["source_selector_rank"]), str(row["portfolio_id"])))
    if arm == "D1_DECISION_CHAIN_CORE":
        return min(candidates, key=lambda row: (
            int(row["decision_missing_timing_legs"]),
            int(row["decision_handicap_contradiction_legs"]),
            int(row["decision_probability_q_conflict_count"]),
            -float(row["decision_f1_gm_e_sp"]),
            str(row["portfolio_id"]),
        ))
    field = next(score for name, score, _, _ in ARMS if name == arm)
    return min(candidates, key=lambda row: (-float(row[field]), str(row["portfolio_id"])))


def build_selection(census: Sequence[dict[str, str]], scores: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    by_issue: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in scores:
        by_issue[str(row["issue_instance"])].append(row)
    census_rows = sorted(
        (row for row in census if row["selector_id"] == KALL_SELECTOR),
        key=lambda row: (row["year"], row["issue"], row["fold"]),
    )
    output = []
    for row in census_rows:
        candidates = by_issue.get(row["issue_instance"], [])
        declared = int(row["candidate_identity_count"])
        if declared != len(candidates):
            raise RuntimeError(f"candidate count drift: {row['issue_instance']}")
        for arm, score_field, _, role in ARMS:
            selected = select_candidate(arm, candidates) if candidates else None
            score = ""
            decision_tuple = ""
            if selected:
                if arm == "D1_DECISION_CHAIN_CORE":
                    decision_tuple = "|".join(str(selected[field]) for field in (
                        "decision_missing_timing_legs", "decision_handicap_contradiction_legs",
                        "decision_probability_q_conflict_count", "decision_f1_gm_e_sp",
                    ))
                    score = selected["decision_f1_gm_e_sp"]
                else:
                    score = selected[score_field]
            output.append({
                "issue": row["issue"], "year": row["year"], "fold": row["fold"],
                "issue_instance": row["issue_instance"], "arm": arm, "arm_role": role,
                "policy_status": "SELECTED_PREOUTCOME" if selected else "NO_BET_FROZEN",
                "candidate_identity_count": declared,
                "choice_opportunity": int(declared >= 2),
                "selected_portfolio_id": selected["portfolio_id"] if selected else "",
                "selected_identity_fingerprint": selected["identity_fingerprint"] if selected else "",
                "selected_source_rank": selected["source_selector_rank"] if selected else "",
                "selected_score": compact(score),
                "decision_lexicographic_tuple": decision_tuple,
                "ticket_count": FULL_TICKETS if selected else 0,
                "planned_stake_yuan": FULL_STAKE_YUAN if selected else 0,
                "allocation": "FULL_ENUMERATED",
                "outcome_boundary": OUTCOME_BOUNDARY,
            })
    return output


def empirical_quantile(values: Sequence[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[int(math.floor(q * (len(ordered) - 1)))]


def build_threshold_registry(selection: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    output = []
    for arm, _, _, role in ARMS:
        selected = [row for row in selection if row["arm"] == arm and row["policy_status"] == "SELECTED_PREOUTCOME"]
        values = [float(row["selected_score"]) for row in selected]
        for label, q in (("Q00", 0.0), ("Q25", 0.25), ("Q50", 0.50), ("Q75", 0.75)):
            threshold = empirical_quantile(values, q)
            eligible = [row for row in selected if float(row["selected_score"]) >= threshold]
            output.append({
                "arm": arm, "arm_role": role, "threshold_family": "SELECTED_RAW_CROSS_ISSUE",
                "threshold_label": label, "threshold_quantile": q,
                "threshold_value": compact(threshold), "eligible_selected_issue_count": len(eligible),
                "eligible_choice_issue_count": sum(int(row["choice_opportunity"]) for row in eligible),
                "eligible_identity_set_sha256": canonical_hash(sorted(
                    (row["issue_instance"], row["selected_portfolio_id"]) for row in eligible
                )),
                "controlling": 0, "outcome_boundary": OUTCOME_BOUNDARY,
            })
    return output


def build_overlap(selection: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    selected = {
        (str(row["arm"]), str(row["issue_instance"])): str(row["selected_portfolio_id"])
        for row in selection if row["policy_status"] == "SELECTED_PREOUTCOME"
    }
    output = []
    for arm, _, _, role in ARMS:
        rows = [row for row in selection if row["arm"] == arm and row["policy_status"] == "SELECTED_PREOUTCOME"]
        same = sum(selected[(arm, str(row["issue_instance"]))] == selected[("B0_BEST_FULL", str(row["issue_instance"]))] for row in rows)
        choice_rows = [row for row in rows if row["choice_opportunity"]]
        choice_same = sum(selected[(arm, str(row["issue_instance"]))] == selected[("B0_BEST_FULL", str(row["issue_instance"]))] for row in choice_rows)
        output.append({
            "arm": arm, "arm_role": role, "selected_issue_count": len(rows),
            "same_as_incumbent_all": same, "different_from_incumbent_all": len(rows) - same,
            "choice_issue_count": len(choice_rows), "same_as_incumbent_choice": choice_same,
            "different_from_incumbent_choice": len(choice_rows) - choice_same,
            "selected_identity_set_sha256": canonical_hash(sorted(
                (row["issue_instance"], row["selected_portfolio_id"]) for row in rows
            )),
            "outcome_boundary": OUTCOME_BOUNDARY,
        })
    return output


def feature_rows(features: Mapping[int, Mapping[str, object]]) -> list[dict[str, object]]:
    excluded = {"home_rank", "away_rank"}
    return [
        {key: compact(value) for key, value in row.items() if key not in excluded}
        for _, row in sorted(features.items())
    ]


def atomic_generate(output: Path, db: Path) -> dict[str, object]:
    if output.exists():
        raise RuntimeError(f"refusing to overwrite immutable output: {output}")
    stage = output.with_name(output.name + f".stage-{os.getpid()}")
    if stage.exists():
        raise RuntimeError(f"staging path exists: {stage}")
    stage.mkdir(parents=True)
    try:
        if sha256_file(db) != DB_SHA256:
            raise RuntimeError("database hash drift")
        if sha256_file(ROOT / SOURCE_175_PATH) != SOURCE_175_SHA256:
            raise RuntimeError("#175 guide hash drift")
        payload_167 = verify_package(GATE_A_167, SOURCE_167_MANIFEST, SOURCE_167_CONTENT)
        payload_170a = verify_package(GATE_A_170, SOURCE_170_A_MANIFEST, SOURCE_170_A_CONTENT)
        payload_170b = verify_package(GATE_B_170, SOURCE_170_B_MANIFEST, SOURCE_170_B_CONTENT)
        payload_176 = verify_package(RISK_176, SOURCE_176_MANIFEST, SOURCE_176_CONTENT)
        core = load_core()
        _selector_grid, census, identities, roles = load_frozen_inputs()
        match_ids = {int(row["match_id"]) for row in roles}
        target = read_target_features(db, match_ids)
        snapshot_coverage = build_snapshot_coverage(target)
        source_schema = build_source_schema(db, census, identities, roles)
        years = sorted({int(row["year"]) for row in identities})
        models = fit_outer_year_models(db, years, core)
        features, issue_cutoffs = build_match_features(db, target, roles, models, core)
        scores = build_portfolio_scores(identities, roles, features)
        selection = build_selection(census, scores)
        overlaps = build_overlap(selection)
        thresholds = build_threshold_registry(selection)
        kall_census = [row for row in census if row["selector_id"] == KALL_SELECTOR]
        candidate_counts = Counter(int(row["candidate_identity_count"]) for row in kall_census)
        if sum(value for key, value in candidate_counts.items() if key >= 2) != 113 or candidate_counts[1] != 76 or candidate_counts[0] != 159:
            raise RuntimeError(f"choice-opportunity denominator drift: {candidate_counts}")
        incumbent = [
            row for row in selection
            if row["arm"] == "B0_BEST_FULL" and row["policy_status"] == "SELECTED_PREOUTCOME"
        ]
        rank1 = {
            (row["issue_instance"], row["portfolio_id"])
            for row in identities if row["selector_rank"] == "1"
        }
        if {(row["issue_instance"], row["selected_portfolio_id"]) for row in incumbent} != rank1:
            raise RuntimeError("BEST_FULL reproduction drift")

        write_gzip(stage / "candidate_universe_scores.csv.gz", list(scores[0]), scores)
        write_gzip(stage / "candidate_role_vectors.csv.gz", list(roles[0]), roles)
        match_rows = feature_rows(features)
        write_gzip(stage / "match_feature_ledger.csv.gz", list(match_rows[0]), match_rows)
        write_csv(stage / "selection_freeze.csv", list(selection[0]), selection)
        write_csv(stage / "identity_overlap.csv", list(overlaps[0]), overlaps)
        write_csv(stage / "threshold_registry.csv", list(thresholds[0]), thresholds)
        write_csv(stage / "snapshot_coverage.csv", list(snapshot_coverage[0]), snapshot_coverage)
        (stage / "source_schema.json").write_text(dump_json(source_schema), encoding="utf-8")
        cutoff_rows = [{
            "issue_instance": issue, "feature_cutoff_ts": cutoff.isoformat(sep=" "),
            "rule": "minimum kickoff across immutable issue K_ALL candidate-role union",
            "history_rule": "strict kickoff < feature_cutoff_ts", "outcome_boundary": OUTCOME_BOUNDARY,
        } for issue, cutoff in sorted(issue_cutoffs.items())]
        write_csv(stage / "issue_cutoff_registry.csv", list(cutoff_rows[0]), cutoff_rows)
        parameter_payload = {
            "contract": CONTRACT, "version": VERSION,
            "recipe": {
                "league": "global, league handicap-result, prior-season league handicap-result, league raw HDA, prior-season league raw HDA, handicap bucket and EURO-top-mass x OU-total bucket empirical blend; fixed Dirichlet alpha 3/90/45/90/45/90/90; 0.25 shrunken calibration residual",
                "team": "rolling Elo plus 12-match role goal rates; eight-match league-goal shrinkage; Poisson grid 0..12; strict earlier kickoff",
                "market_dynamics": "EURO 1h no-vig plus 0.50 mean prior-year residual across EURO/Asian/OU movement, breadth, dispersion and handicap buckets; alpha 120",
                "combined": "logarithmic pool L/T/M=0.30/0.30/0.40",
                "lofo": {"F_MINUS_L": "T/M=3/7,4/7", "F_MINUS_T": "L/M=3/7,4/7", "F_MINUS_M": "L/T=0.5,0.5"},
            },
            "folds": {str(year): models[year].to_payload(year) for year in years},
            "outcome_boundary": "Each target year uses only calendar years strictly before it; same-year earlier results update team state only after their kickoff.",
        }
        write_gzip_json(stage / "outer_year_model_freeze.json.gz", parameter_payload)
        training_rows = [{
            **models[year].summary(year),
            "parameter_payload_sha256": canonical_hash(models[year].to_payload(year)),
            "outcome_boundary": OUTCOME_BOUNDARY,
        } for year in years]
        write_csv(stage / "outer_year_training_registry.csv", list(training_rows[0]), training_rows)

        arm_rows = [{
            "arm": arm, "score_field": score, "definition": definition, "arm_role": role,
            "candidate_selector_id": KALL_SELECTOR, "incumbent_selector_id": K1_SELECTOR,
            "selection_scope": "complete issue K1", "allocation": "FULL_ENUMERATED",
            "tickets": FULL_TICKETS, "stake_yuan": FULL_STAKE_YUAN,
            "participating_issues": 189, "frozen_no_bet_issues": 159,
            "choice_opportunity_issues": 113, "invariant_issues": 76,
            "outcome_boundary": OUTCOME_BOUNDARY,
        } for arm, score, definition, role in ARMS]
        write_csv(stage / "arm_registry.csv", list(arm_rows[0]), arm_rows)
        feature_manifest = [
            {"family": "LEAGUE_CORE", "features": "prior-year league/season 3/1/0, goals, handicap and odds regimes, calibration residual", "timing": "OUTER_YEAR_TRAIN_LT_TARGET_YEAR", "coverage": "retained with global shrinkage", "controlling": 1},
            {"family": "TEAM_CORE", "features": "rolling Elo, role goals for/against, form, rest, history depth, Poisson handicap probability", "timing": "STRICT_KICKOFF_LT_ISSUE_CUTOFF", "coverage": "neutral league prior when unseen; explicit depth/missing", "controlling": 1},
            {"family": "MARKET_DYNAMICS", "features": "EURO no-vig initial/10h/1h, Asian and OU line movement, breadth, dispersion, frozen-market disagreement", "timing": "PRE_KICKOFF_SNAPSHOT_SEMANTICS", "coverage": "identity retained; explicit MISSING movement bucket", "controlling": 1},
            {"family": "TARGET_RANK", "features": "home_rank/away_rank", "timing": "HISTORICAL_TIMING_PROXY", "coverage": "emitted nowhere in scores", "controlling": 0},
            {"family": "NEWS_LINEUP_INJURY_MOTIVATION", "features": "none", "timing": "UNAVAILABLE_NOT_USED", "coverage": "deferred to #181/#182", "controlling": 0},
            {"family": "V4_2_EXECUTION_COMPRESSION", "features": "none", "timing": "NON_CONTROLLING_FOR_FULL_ENUMERATED", "coverage": "not used", "controlling": 0},
        ]
        for row in feature_manifest:
            row["outcome_boundary"] = OUTCOME_BOUNDARY
        write_csv(stage / "feature_manifest.csv", list(feature_manifest[0]), feature_manifest)
        segments = [
            {"segment": "ALL_189", "definition": "all matched participating issues", "issue_count": 189, "controlling": 1},
            {"segment": "CHOICE_113", "definition": "issues with 2-7 frozen candidates", "issue_count": 113, "controlling": 1},
            {"segment": "INVARIANT_76", "definition": "issues with one frozen candidate", "issue_count": 76, "controlling": 0},
            {"segment": "LOYO", "definition": "leave one target year out; preserve complete issues", "issue_count": 189, "controlling": 0},
        ]
        for row in segments:
            row["outcome_boundary"] = OUTCOME_BOUNDARY
        write_csv(stage / "segment_registry.csv", list(segments[0]), segments)

        source_rows = [
            {"source": SOURCE_167, "role": "candidate/identity/role-vector definition", "manifest": SOURCE_167_MANIFEST, "content": SOURCE_167_CONTENT, "access": "Gate-A selection payloads", "payload_count": len(payload_167)},
            {"source": SOURCE_170_A, "role": "BEST_FULL identity reproduction", "manifest": SOURCE_170_A_MANIFEST, "content": SOURCE_170_A_CONTENT, "access": "Gate-A identity/participation", "payload_count": len(payload_170a)},
            {"source": SOURCE_170_B, "role": "terminal attribution durability", "manifest": SOURCE_170_B_MANIFEST, "content": SOURCE_170_B_CONTENT, "access": "hash verification only; no semantic read", "payload_count": len(payload_170b)},
            {"source": str(SOURCE_175_PATH), "role": "analysis-first terminology/decision interpretation", "manifest": SOURCE_175_SHA256, "content": SOURCE_175_SHA256, "access": "hash verification only; no selection score", "payload_count": 1},
            {"source": SOURCE_176, "role": "analysis-first equity/risk interpretation", "manifest": SOURCE_176_MANIFEST, "content": SOURCE_176_CONTENT, "access": "hash verification only; no risk metric parsed into selection", "payload_count": len(payload_176)},
            {"source": str(DB_REPOSITORY_PATH), "role": "prior outcomes plus target-safe football/market features", "manifest": DB_SHA256, "content": DB_SHA256, "access": "target safe projection; training year < target; same-year team history strictly earlier kickoff", "payload_count": 1},
            {"source": str(CORE_SOURCE_PATH), "role": "frozen quick-core probability implementation", "manifest": sha256_file(core_source()), "content": sha256_file(core_source()), "access": "manifest-covered package copy", "payload_count": 1},
        ]
        for row in source_rows:
            row["outcome_boundary"] = OUTCOME_BOUNDARY
        write_csv(stage / "source_census.csv", list(source_rows[0]), source_rows)
        source_binding = {
            "contract": CONTRACT, "version": VERSION, "base_main_commit": BASE_MAIN_COMMIT,
            "source_167_gate_a": {"package": SOURCE_167, "manifest": SOURCE_167_MANIFEST, "content": SOURCE_167_CONTENT},
            "source_170_gate_a": {"package": SOURCE_170_A, "manifest": SOURCE_170_A_MANIFEST, "content": SOURCE_170_A_CONTENT},
            "source_170_gate_b": {"package": SOURCE_170_B, "manifest": SOURCE_170_B_MANIFEST, "content": SOURCE_170_B_CONTENT, "access": "hash verification only"},
            "source_175": {"path": str(SOURCE_175_PATH), "sha256": SOURCE_175_SHA256, "merge": SOURCE_175_MERGE, "access": "interpretation only"},
            "source_176": {"package": SOURCE_176, "manifest": SOURCE_176_MANIFEST, "content": SOURCE_176_CONTENT, "merge": SOURCE_176_MERGE, "access": "durability verification and Gate-B interpretation only; not selection"},
            "database": {"path": str(DB_REPOSITORY_PATH), "sha256": DB_SHA256, "target_columns": list(TARGET_QUERY_COLUMNS)},
            "quick_core": {"path": str(CORE_SOURCE_PATH), "sha256": sha256_file(core_source()), "package_copy": "bj134_quick_core.py"},
            "outcome_boundary": OUTCOME_BOUNDARY,
        }
        (stage / "source_binding.json").write_text(dump_json(source_binding), encoding="utf-8")
        counts = Counter(row["policy_status"] for row in selection)
        selected_by_arm = Counter(row["arm"] for row in selection if row["policy_status"] == "SELECTED_PREOUTCOME")
        card = {
            "issue": ISSUE, "contract": CONTRACT, "version": VERSION,
            "stage": "GATE_A_OUTCOME_UNEXPOSED_QUICK_BACKTESTABLE_CORE",
            "pi_plan": "Issue #134 comment 5175086784",
            "incumbent": {"alias": "BEST_FULL", "selector_id": K1_SELECTOR, "allocation": "FULL_ENUMERATED", "tickets": FULL_TICKETS, "stake_yuan": FULL_STAKE_YUAN, "selected": 189, "no_bet": 159, "baseline_no_tax_roi": -0.0947},
            "candidate_universe": {"selector_id": KALL_SELECTOR, "issue_census": 348, "participating": 189, "no_bet": 159, "identities": 424, "choice_opportunities": 113, "invariant": 76},
            "arms": [{"arm": arm, "score": score, "definition": definition, "role": role} for arm, score, definition, role in ARMS],
            "decision_chain": {"lexicographic": ["min missing/timing-risk legs", "min handicap-fit contradictions", "min model-market/q conflict count", "max F1 GM E_SP", "portfolio_id"], "full_constraint": "rerank identity only; never alter codes/tickets/allocation", "v4_2": "execution compression excluded"},
            "outer_year": "all fold model parameters use training calendar year < target year; same-year football state advances only after earlier kickoff",
            "thresholds": "non-controlling raw cross-issue Q00/Q25/Q50/Q75; no within-issue percentile threshold",
            "snapshot_coverage": snapshot_coverage,
            "denominator": {"issue_census": 348, "candidate_identity_rows": len(scores), "candidate_role_rows": len(roles), "unique_match_rows": len(features), "arm_count": len(ARMS), "selection_rows": len(selection), "selected_rows": counts["SELECTED_PREOUTCOME"], "no_bet_rows": counts["NO_BET_FROZEN"], "selected_by_arm": dict(selected_by_arm), "choice_opportunity_issues": 113, "invariant_issues": 76, "planned_stake_per_arm_yuan": 189 * FULL_STAKE_YUAN},
            "analysis_first": {"guide_175_bound": True, "risk_176_bound": True, "selection_influence": "none"},
            "gate_b_status": "NOT_AUTHORIZED_PENDING_PI_GATE_A_REVIEW",
            "promotion_boundary": "paper research only; positive lift requires strict independent EV; negative overlay cannot demote incumbent",
            "outcome_boundary": OUTCOME_BOUNDARY,
        }
        (stage / "gate_a_card.json").write_text(dump_json(card), encoding="utf-8")
        (stage / "README.md").write_text(
            "# #134 Gate A v3\n\nOutcome-unexposed quick backtestable league/team/market-dynamics FULL-N7 selector core. "
            "It preserves the exact BEST_FULL denominator and allocation, freezes six primary plus three LOFO identity views, "
            "and binds #175/#176 only as interpretation prerequisites. Gate B is not authorized.\n",
            encoding="utf-8",
        )
        shutil.copyfile(core_source(), stage / "bj134_quick_core.py")
        shutil.copyfile(Path(__file__).resolve(), stage / "freeze_runner.py")
        payloads = sorted(path for path in stage.iterdir() if path.is_file())
        content = {
            "contract_version": VERSION,
            "denominator": card["denominator"],
            "controls": {
                "base_main_commit": BASE_MAIN_COMMIT, "database_sha256": DB_SHA256,
                "candidate_selector": KALL_SELECTOR, "incumbent_selector": K1_SELECTOR,
                "incumbent_identity_sha256": canonical_hash(sorted(
                    (row["issue_instance"], row["selected_portfolio_id"]) for row in incumbent
                )),
                "all_arm_identity_sha256": canonical_hash(sorted(
                    (row["arm"], row["issue_instance"], row["selected_portfolio_id"])
                    for row in selection if row["policy_status"] == "SELECTED_PREOUTCOME"
                )),
                "outer_year_parameter_sha256": canonical_hash(parameter_payload),
                "source_175_sha256": SOURCE_175_SHA256, "source_176_manifest": SOURCE_176_MANIFEST,
            },
            "payloads": {path.name: sha256_file(path) for path in payloads},
        }
        (stage / "CONTENT_IDENTITY.json").write_text(dump_json(content), encoding="utf-8")
        payloads = sorted(path for path in stage.iterdir() if path.is_file())
        (stage / "SHA256SUMS.json").write_text(
            dump_json({path.name: sha256_file(path) for path in payloads}), encoding="utf-8"
        )
        os.replace(stage, output)
        return {
            "output": str(output), "manifest_sha256": sha256_file(output / "SHA256SUMS.json"),
            "content_identity_sha256": sha256_file(output / "CONTENT_IDENTITY.json"),
            "denominator": card["denominator"],
        }
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
