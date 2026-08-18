#!/usr/bin/env python3
"""Freeze Issue #180's outcome-unexposed team/matchup Gate A."""

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
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from pathlib import Path
from types import ModuleType

ISSUE = 180
CONTRACT = "BJ-HIST-TEAM-MODEL-N7-001"
VERSION = "bj180-gate-a-v2"
BASE_MAIN_COMMIT = "210a791b0793e99e72358e02c8484458c900a98b"
SOURCE_179 = "bj179_gate_a_preoutcome_v2"
SOURCE_179_MANIFEST = "5839f5c03c94ef903472b64fffa3ad1462ec006717875d0a3903ecdfdc2aa056"
SOURCE_179_CONTENT = "2e8314f00b8774501ecf0ed2cb6ede73a9e7a60c7422dd5dc0d464e1470b740b"
SOURCE_134 = "bj134_gate_a_preoutcome_v3"
SOURCE_134_MANIFEST = "0a7e4d673e7fc5fd4832c91e3b519afe5a2bc3211b99f4c95f57c691921b65fd"
SOURCE_134_CONTENT = "3fe014f3decdbd589cdded52d8a9b2bac0f3cb988c2ae8e15cf79314a02eede1"
SOURCE_DB_SHA256 = "7f62079b18b3c028884da92aa8393f5b198246c9d7c32cd0b401562a055c5d6f"
DB_REPOSITORY_PATH = Path("data/derived/beidan_xlsm/beidan_xlsm.sqlite")
CORE_SOURCE_PATH = Path("scripts/bj180_team_matchup_core.py")
FULL_TICKETS = 3**7
FULL_STAKE_YUAN = 2 * FULL_TICKETS
COMPLETION_EMBARGO_MINUTES = 180
OUTCOME_BOUNDARY = (
    "Gate A outcome-unexposed: target rows expose no score/result/final-SP/payout/tax/ROI; "
    "because the source has no completion timestamp, historical scores are available only when "
    "kickoff <= common issue cutoff minus the fixed 180-minute completion embargo"
)
FORBIDDEN_TARGET_FIELDS = {
    "score",
    "fthg",
    "ftag",
    "result_label",
    "result_code",
    "winning_sp",
    "official_sp_3",
    "official_sp_1",
    "official_sp_0",
    "payout",
    "tax",
    "roi",
    "settlement",
}
FAMILIES = (
    "LATENT_STRENGTH",
    "HOME_AWAY_SPLIT",
    "ROLLING_FORM",
    "REST_CONGESTION",
    "OPPONENT_ADJUSTMENT",
    "TEAM_INITIALIZATION",
    "H2H_PRIOR",
)
CONFIG_NAMES = ("TEAM_PRIMARY", "TEAM_CONSERVATIVE", "TEAM_RESPONSIVE")
VECTOR_SPECS = {
    "team_primary": ("TEAM_PRIMARY", None),
    "team_conservative": ("TEAM_CONSERVATIVE", None),
    "team_responsive": ("TEAM_RESPONSIVE", None),
    "team_minus_latent": ("TEAM_PRIMARY", "LATENT_STRENGTH"),
    "team_minus_home_away": ("TEAM_PRIMARY", "HOME_AWAY_SPLIT"),
    "team_minus_form": ("TEAM_PRIMARY", "ROLLING_FORM"),
    "team_minus_rest": ("TEAM_PRIMARY", "REST_CONGESTION"),
    "team_minus_opponent": ("TEAM_PRIMARY", "OPPONENT_ADJUSTMENT"),
    "team_minus_initialization": ("TEAM_PRIMARY", "TEAM_INITIALIZATION"),
    "team_minus_h2h": ("TEAM_PRIMARY", "H2H_PRIOR"),
}
ARMS = (
    (
        "B0_BEST_FULL",
        "market_gm_e_sp",
        "controlling accepted BEST_FULL identity",
        "BASELINE",
    ),
    (
        "L0_QUICK_LEAGUE",
        "quick_league_gm_e_sp",
        "accepted quick league comparator",
        "BASELINE",
    ),
    (
        "H0_LEAGUE_DIAGNOSTIC",
        "league_diagnostic_gm_e_sp",
        "#179 H_MINUS_RAW_HDA diagnostic only",
        "DIAGNOSTIC",
    ),
    ("T1_DEEP_TEAM", "team_primary_gm_e_sp", "deep team-only primary", "PRIMARY"),
    (
        "TL1_TEAM_LEAGUE",
        "team_league_primary_gm_e_sp",
        "70% league diagnostic plus 30% deep team",
        "PRIMARY",
    ),
    (
        "TL_CFG_CONSERVATIVE",
        "team_league_conservative_gm_e_sp",
        "80% league plus 20% conservative team",
        "SENSITIVITY",
    ),
    (
        "TL_CFG_RESPONSIVE",
        "team_league_responsive_gm_e_sp",
        "60% league plus 40% responsive team",
        "SENSITIVITY",
    ),
    (
        "TL_MINUS_LATENT",
        "team_league_minus_latent_gm_e_sp",
        "primary without latent strength",
        "ABLATION",
    ),
    (
        "TL_MINUS_HOME_AWAY",
        "team_league_minus_home_away_gm_e_sp",
        "primary without home/away splits",
        "ABLATION",
    ),
    (
        "TL_MINUS_FORM",
        "team_league_minus_form_gm_e_sp",
        "primary without rolling form",
        "ABLATION",
    ),
    (
        "TL_MINUS_REST",
        "team_league_minus_rest_gm_e_sp",
        "primary without rest/congestion",
        "ABLATION",
    ),
    (
        "TL_MINUS_OPPONENT",
        "team_league_minus_opponent_gm_e_sp",
        "primary without opponent adjustment",
        "ABLATION",
    ),
    (
        "TL_MINUS_INITIALIZATION",
        "team_league_minus_initialization_gm_e_sp",
        "primary without promoted/relegated/new-team initialization",
        "ABLATION",
    ),
    (
        "TL_MINUS_H2H",
        "team_league_minus_h2h_gm_e_sp",
        "primary without low-weight prior-only H2H",
        "ABLATION",
    ),
)


def repo_root() -> Path:
    for candidate in (
        Path(__file__).resolve().parent,
        *Path(__file__).resolve().parents,
    ):
        if (candidate / ".git").exists() and (candidate / "results").is_dir():
            return candidate
    raise RuntimeError("repository root unavailable")


ROOT = repo_root()
SOURCE_179_DIR = ROOT / "results" / SOURCE_179
SOURCE_134_DIR = ROOT / "results" / SOURCE_134
DEFAULT_OUTPUT = ROOT / "results" / "bj180_gate_a_preoutcome_v2"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode()
    ).hexdigest()


def dump_json(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_gzip(path: Path) -> list[dict[str, str]]:
    with gzip.open(path, "rt", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(
    path: Path, fields: Sequence[str], rows: Iterable[Mapping[str, object]]
) -> None:
    materialized = list(rows)
    if not materialized:
        raise RuntimeError(f"refusing empty CSV: {path.name}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fields, lineterminator="\n", extrasaction="raise"
        )
        writer.writeheader()
        writer.writerows(materialized)


def write_gzip(
    path: Path, fields: Sequence[str], rows: Iterable[Mapping[str, object]]
) -> None:
    materialized = list(rows)
    if not materialized:
        raise RuntimeError(f"refusing empty gzip CSV: {path.name}")
    with (
        path.open("wb") as raw,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped,
    ):
        text = io.TextIOWrapper(zipped, encoding="utf-8", newline="")
        writer = csv.DictWriter(
            text, fieldnames=fields, lineterminator="\n", extrasaction="raise"
        )
        writer.writeheader()
        writer.writerows(materialized)
        text.flush()
        text.detach()


def verify_package(
    directory: Path, manifest_hash: str, content_hash: str
) -> dict[str, str]:
    if sha256_file(directory / "SHA256SUMS.json") != manifest_hash:
        raise RuntimeError(f"source manifest drift: {directory.name}")
    if sha256_file(directory / "CONTENT_IDENTITY.json") != content_hash:
        raise RuntimeError(f"source content drift: {directory.name}")
    manifest = json.loads((directory / "SHA256SUMS.json").read_text(encoding="utf-8"))
    actual = sorted(
        path.name
        for path in directory.iterdir()
        if path.is_file() and path.name != "SHA256SUMS.json"
    )
    if sorted(manifest) != actual:
        raise RuntimeError(f"source manifest coverage drift: {directory.name}")
    for name, expected in manifest.items():
        if sha256_file(directory / name) != expected:
            raise RuntimeError(f"source payload drift: {directory.name}/{name}")
    return manifest


def locate_database() -> Path:
    for base in (ROOT, *ROOT.parents):
        candidate = base / DB_REPOSITORY_PATH
        if candidate.is_file():
            return candidate.resolve()
    raise RuntimeError("canonical source database unavailable")


def ro_connection(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro&immutable=1", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def load_core() -> ModuleType:
    path = Path(__file__).resolve().with_name("bj180_team_matchup_core.py")
    if not path.is_file():
        path = ROOT / CORE_SOURCE_PATH
    spec = importlib.util.spec_from_file_location(
        "bj180_team_matchup_core_frozen", path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("team core loader unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def compact(value: object) -> object:
    return f"{value:.12f}" if isinstance(value, float) else value


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


def load_sources() -> dict[str, object]:
    candidates = read_gzip(SOURCE_179_DIR / "candidate_universe_scores.csv.gz")
    probabilities = read_gzip(SOURCE_179_DIR / "match_probability_freeze.csv.gz")
    selection = read_csv(SOURCE_179_DIR / "selection_freeze.csv")
    roles = read_gzip(SOURCE_134_DIR / "candidate_role_vectors.csv.gz")
    if (
        len(candidates) != 424
        or len(probabilities) != 1558
        or len(selection) != 4872
        or len(roles) != 2968
    ):
        raise RuntimeError("source denominator drift")
    if FORBIDDEN_TARGET_FIELDS.intersection(probabilities[0]):
        raise RuntimeError("#179 target probabilities expose forbidden outcomes")
    candidate_keys = {
        (row["issue_instance"], row["portfolio_id"]) for row in candidates
    }
    roles = [
        row
        for row in roles
        if (row["issue_instance"], row["portfolio_id"]) in candidate_keys
    ]
    if len(roles) != 2968:
        raise RuntimeError("candidate role filtering drift")
    return {
        "candidates": candidates,
        "probabilities": probabilities,
        "selection": selection,
        "roles": roles,
    }


def issue_cutoffs(
    roles: Sequence[Mapping[str, str]], core: ModuleType
) -> tuple[dict[str, object], dict[int, object]]:
    by_issue: dict[str, list[object]] = defaultdict(list)
    match_issues: dict[int, set[str]] = defaultdict(set)
    for row in roles:
        by_issue[row["issue_instance"]].append(core.parse_ts(row["kickoff_ts"]))
        match_issues[int(row["match_id"])].add(row["issue_instance"])
    cutoffs = {issue: min(values) for issue, values in by_issue.items()}
    by_match: dict[int, object] = {}
    for match_id, issues in match_issues.items():
        values = {cutoffs[issue] for issue in issues}
        if len(values) != 1:
            raise RuntimeError(f"inconsistent common cutoff: {match_id}")
        by_match[match_id] = values.pop()
    return cutoffs, by_match


def read_target_rows(db: Path, match_ids: set[int]) -> dict[int, dict[str, object]]:
    output: dict[int, dict[str, object]] = {}
    connection = ro_connection(db)
    try:
        for start in range(0, len(match_ids), 700):
            chunk = sorted(match_ids)[start : start + 700]
            placeholders = ",".join("?" for _ in chunk)
            query = f"""
                SELECT m.match_id, m.issue, m.match_idx, m.kickoff_ts,
                       mf.season_year AS year, m.league, m.home_team_id,
                       m.away_team_id, mf.handicap_line_norm
                  FROM matches m JOIN match_features mf ON mf.match_id=m.match_id
                 WHERE m.match_id IN ({placeholders})
            """
            for row in connection.execute(query, chunk):
                output[int(row["match_id"])] = dict(row)
    finally:
        connection.close()
    if set(output) != match_ids:
        raise RuntimeError(f"target safe join drift: {len(output)} != {len(match_ids)}")
    if FORBIDDEN_TARGET_FIELDS.intersection(output[next(iter(output))]):
        raise RuntimeError("target query exposes forbidden fields")
    return output


def historical_rows(db: Path, before: str) -> Iterator[dict[str, object]]:
    connection = ro_connection(db)
    query = """
        SELECT m.match_id, m.kickoff_ts, m.league, m.home_team_id, m.away_team_id,
               mf.handicap_line_norm, mf.fthg, mf.ftag
          FROM matches m JOIN match_features mf ON mf.match_id=m.match_id
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


def history_available_through(cutoff: dt.datetime) -> dt.datetime:
    """Latest kickoff whose final score may be used at this cutoff."""
    return cutoff - dt.timedelta(minutes=COMPLETION_EMBARGO_MINUTES)


def history_row_is_available(kickoff: dt.datetime, cutoff: dt.datetime) -> bool:
    """The embargo boundary is inclusive; anything later remains unavailable."""
    return kickoff <= history_available_through(cutoff)


def historical_timeline(db: Path, before: str, core: ModuleType) -> list[dt.datetime]:
    """Read only eligible-history kickoff times for the embargo audit."""
    connection = ro_connection(db)
    query = """
        SELECT m.kickoff_ts
          FROM matches m JOIN match_features mf ON mf.match_id=m.match_id
         WHERE m.kickoff_ts IS NOT NULL AND m.kickoff_ts < ?
           AND m.home_team_id IS NOT NULL AND m.away_team_id IS NOT NULL
           AND mf.fthg IS NOT NULL AND mf.ftag IS NOT NULL
         ORDER BY m.kickoff_ts, m.match_id
    """
    try:
        return [
            core.parse_ts(row["kickoff_ts"])
            for row in connection.execute(query, (before,))
        ]
    finally:
        connection.close()


def probability_freeze(
    db: Path,
    targets: Mapping[int, Mapping[str, object]],
    source_probabilities: Sequence[Mapping[str, str]],
    by_match_cutoff: Mapping[int, object],
    core: ModuleType,
) -> tuple[
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
]:
    source_by_match = {int(row["match_id"]): row for row in source_probabilities}
    targets_by_cutoff: dict[object, list[int]] = defaultdict(list)
    for match_id, cutoff in by_match_cutoff.items():
        targets_by_cutoff[cutoff].append(match_id)
    state = core.TeamMatchupState()
    maximum_cutoff = max(targets_by_cutoff)
    history = iter(historical_rows(db, maximum_cutoff.isoformat(sep=" ")))
    timeline = historical_timeline(db, maximum_cutoff.isoformat(sep=" "), core)
    pending = next(history, None)
    output: list[dict[str, object]] = []
    state_rows: list[dict[str, object]] = []
    embargo_rows: list[dict[str, object]] = []
    for cutoff in sorted(targets_by_cutoff):
        availability_cutoff = history_available_through(cutoff)
        while pending is not None and history_row_is_available(
            core.parse_ts(pending["kickoff_ts"]), cutoff
        ):
            state.update(pending)
            pending = next(history, None)
        safe_count = bisect_right(timeline, availability_cutoff)
        old_rule_count = bisect_left(timeline, cutoff)
        excluded_count = old_rule_count - safe_count
        nearest_gap = (
            (cutoff - timeline[old_rule_count - 1]).total_seconds() / 60.0
            if excluded_count
            else None
        )
        embargo_rows.append(
            {
                "feature_cutoff_ts": cutoff.isoformat(sep=" "),
                "score_available_through_ts": availability_cutoff.isoformat(sep=" "),
                "embargo_minutes": COMPLETION_EMBARGO_MINUTES,
                "inclusive_boundary": 1,
                "cumulative_safe_history_rows": safe_count,
                "cumulative_old_kickoff_lt_rows": old_rule_count,
                "excluded_near_cutoff_rows": excluded_count,
                "nearest_excluded_kickoff_gap_minutes": compact(nearest_gap)
                if nearest_gap is not None
                else "",
                "completion_timestamp_source": "UNAVAILABLE_FIXED_EMBARGO",
                "history_rule": "kickoff <= cutoff - 180 minutes",
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
        )
        summary = state.summary()
        if int(summary["training_rows"]) != safe_count:
            raise RuntimeError(
                "completion-embargo history denominator drift: "
                f"state={summary['training_rows']} audit={safe_count} cutoff={cutoff}"
            )
        state_rows.append(
            {
                "feature_cutoff_ts": cutoff.isoformat(sep=" "),
                **summary,
                "state_summary_sha256": canonical_hash(summary),
                "score_available_through_ts": availability_cutoff.isoformat(sep=" "),
                "history_rule": "kickoff <= feature_cutoff_ts - 180 minutes (inclusive)",
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
        )
        for match_id in sorted(targets_by_cutoff[cutoff]):
            target = targets[match_id]
            source = source_by_match[match_id]
            league = tuple(
                float(source[f"deep_minus_raw_hda_p{code}"]) for code in ("3", "1", "0")
            )
            primary, diagnostics, families = state.probabilities(target, cutoff)
            vectors = {"team_primary": primary}
            for name, (config, excluded) in VECTOR_SPECS.items():
                if name == "team_primary":
                    continue
                vectors[name] = state.probabilities(target, cutoff, config, excluded)[0]
            combined = {
                "team_league_primary": core.blend(
                    league, vectors["team_primary"], 0.30
                ),
                "team_league_conservative": core.blend(
                    league, vectors["team_conservative"], 0.20
                ),
                "team_league_responsive": core.blend(
                    league, vectors["team_responsive"], 0.40
                ),
                **{
                    f"team_league_minus_{suffix}": core.blend(
                        league, vectors[f"team_minus_{suffix}"], 0.30
                    )
                    for suffix in (
                        "latent",
                        "home_away",
                        "form",
                        "rest",
                        "opponent",
                        "initialization",
                        "h2h",
                    )
                },
            }
            row: dict[str, object] = {
                **target,
                "feature_cutoff_ts": cutoff.isoformat(sep=" "),
                "history_last_update_ts": summary["last_update_ts"],
                "history_training_rows": summary["training_rows"],
                **diagnostics,
                **{
                    f"market_p{code}": source[f"market_p{code}"]
                    for code in ("3", "1", "0")
                },
                **{
                    f"quick_p{code}": source[f"quick_p{code}"]
                    for code in ("3", "1", "0")
                },
                **{
                    f"league_diagnostic_p{code}": source[f"deep_minus_raw_hda_p{code}"]
                    for code in ("3", "1", "0")
                },
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
            for name, vector in {**vectors, **combined}.items():
                row.update(
                    {
                        f"{name}_p{code}": compact(vector[index])
                        for index, code in enumerate(("3", "1", "0"))
                    }
                )
            for family, vector in families.items():
                row.update(
                    {
                        f"family_{family.lower()}_p{code}": compact(vector[index])
                        for index, code in enumerate(("3", "1", "0"))
                    }
                )
            output.append(row)
    if len(output) != 1558 or {int(row["match_id"]) for row in output} != set(targets):
        raise RuntimeError("probability target denominator drift")
    return (
        sorted(output, key=lambda row: int(row["match_id"])),
        state_rows,
        embargo_rows,
    )


def score_candidates(
    candidates: Sequence[Mapping[str, str]],
    roles: Sequence[Mapping[str, str]],
    probabilities: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    probability_by_match = {str(row["match_id"]): row for row in probabilities}
    roles_by_key: dict[tuple[str, str], list[Mapping[str, str]]] = defaultdict(list)
    for row in roles:
        roles_by_key[(row["issue_instance"], row["portfolio_id"])].append(row)
    vector_names = [
        "team_primary",
        "team_league_primary",
        "team_league_conservative",
        "team_league_responsive",
        "team_league_minus_latent",
        "team_league_minus_home_away",
        "team_league_minus_form",
        "team_league_minus_rest",
        "team_league_minus_opponent",
        "team_league_minus_initialization",
        "team_league_minus_h2h",
    ]
    output = []
    for candidate in candidates:
        key = (candidate["issue_instance"], candidate["portfolio_id"])
        frozen_roles = sorted(
            roles_by_key[key], key=lambda row: int(row["selection_rank"])
        )
        if len(frozen_roles) != 7:
            raise RuntimeError(f"candidate role denominator drift: {key}")
        values = {name: [] for name in vector_names}
        for role in frozen_roles:
            probability = probability_by_match[role["match_id"]]
            sp = predicted_sp(role)
            for name in vector_names:
                vector = [
                    float(probability[f"{name}_p{code}"]) for code in ("3", "1", "0")
                ]
                values[name].append(
                    sum(vector[index] * sp[index] for index in range(3))
                )
        output.append(
            {
                "issue": candidate["issue"],
                "year": candidate["year"],
                "fold": candidate["fold"],
                "issue_instance": candidate["issue_instance"],
                "portfolio_id": candidate["portfolio_id"],
                "source_selector_rank": candidate["source_selector_rank"],
                "candidate_match_id": candidate["candidate_match_id"],
                "selected_match_ids": candidate["selected_match_ids"],
                "identity_fingerprint": candidate["identity_fingerprint"],
                "candidate_count_complete_issue": candidate[
                    "candidate_count_complete_issue"
                ],
                "market_gm_e_sp": candidate["market_gm_e_sp"],
                "quick_league_gm_e_sp": candidate["quick_league_gm_e_sp"],
                "league_diagnostic_gm_e_sp": candidate["deep_minus_raw_hda_gm_e_sp"],
                **{
                    f"{name}_gm_e_sp": compact(geometric(scores))
                    for name, scores in values.items()
                },
                "full_ticket_count": FULL_TICKETS,
                "full_stake_yuan": FULL_STAKE_YUAN,
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
        )
    return sorted(
        output,
        key=lambda row: (
            row["issue_instance"],
            int(row["source_selector_rank"]),
            row["portfolio_id"],
        ),
    )


def select_candidate(
    arm: str, candidates: Sequence[Mapping[str, object]]
) -> Mapping[str, object]:
    if arm == "B0_BEST_FULL":
        return min(
            candidates,
            key=lambda row: (
                int(row["source_selector_rank"]),
                str(row["portfolio_id"]),
            ),
        )
    score_field = next(score for name, score, _, _ in ARMS if name == arm)
    return min(
        candidates, key=lambda row: (-float(row[score_field]), str(row["portfolio_id"]))
    )


def build_selection(
    source_selection: Sequence[Mapping[str, str]],
    scores: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    by_issue: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in scores:
        by_issue[str(row["issue_instance"])].append(row)
    b0 = [row for row in source_selection if row["arm"] == "B0_BEST_FULL"]
    if len(b0) != 348:
        raise RuntimeError("source issue census drift")
    output = []
    for census in sorted(b0, key=lambda row: (row["year"], row["issue"], row["fold"])):
        candidates = by_issue.get(census["issue_instance"], [])
        if len(candidates) != int(census["candidate_identity_count"]):
            raise RuntimeError(f"candidate count drift: {census['issue_instance']}")
        for arm, score_field, _, role in ARMS:
            selected = select_candidate(arm, candidates) if candidates else None
            output.append(
                {
                    "issue": census["issue"],
                    "year": census["year"],
                    "fold": census["fold"],
                    "issue_instance": census["issue_instance"],
                    "arm": arm,
                    "arm_role": role,
                    "policy_status": "SELECTED_PREOUTCOME"
                    if selected
                    else "NO_BET_FROZEN",
                    "candidate_identity_count": len(candidates),
                    "choice_opportunity": int(len(candidates) >= 2),
                    "selected_portfolio_id": selected["portfolio_id"]
                    if selected
                    else "",
                    "selected_identity_fingerprint": selected["identity_fingerprint"]
                    if selected
                    else "",
                    "selected_source_rank": selected["source_selector_rank"]
                    if selected
                    else "",
                    "selected_score": compact(float(selected[score_field]))
                    if selected
                    else "",
                    "ticket_count": FULL_TICKETS if selected else 0,
                    "planned_stake_yuan": FULL_STAKE_YUAN if selected else 0,
                    "allocation": "FULL_ENUMERATED",
                    "outcome_boundary": OUTCOME_BOUNDARY,
                }
            )
    if len(output) != 348 * len(ARMS):
        raise RuntimeError("selection surface drift")
    return output


def source_identity_map(rows: Sequence[Mapping[str, str]], arm: str) -> dict[str, str]:
    return {
        row["issue_instance"]: row["selected_portfolio_id"]
        for row in rows
        if row["arm"] == arm and row["policy_status"] == "SELECTED_PREOUTCOME"
    }


def reproduce_baselines(
    source: Sequence[Mapping[str, str]], selection: Sequence[Mapping[str, object]]
) -> list[dict[str, object]]:
    comparisons = (
        ("B0_BEST_FULL", "B0_BEST_FULL"),
        ("L0_QUICK_LEAGUE", "Q1_QUICK_LEAGUE"),
        ("H0_LEAGUE_DIAGNOSTIC", "H_MINUS_RAW_HDA"),
    )
    output = []
    for target_arm, source_arm in comparisons:
        actual = {
            str(row["issue_instance"]): str(row["selected_portfolio_id"])
            for row in selection
            if row["arm"] == target_arm
            and row["policy_status"] == "SELECTED_PREOUTCOME"
        }
        expected = source_identity_map(source, source_arm)
        if actual != expected or len(actual) != 189:
            raise RuntimeError(f"baseline identity reproduction drift: {target_arm}")
        output.append(
            {
                "target_arm": target_arm,
                "source_arm": source_arm,
                "selected_identity_count": len(actual),
                "identity_set_sha256": canonical_hash(sorted(actual.items())),
                "reproduction_status": "PASS",
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
        )
    return output


def build_overlap(selection: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    selected = {
        (str(row["arm"]), str(row["issue_instance"])): str(row["selected_portfolio_id"])
        for row in selection
        if row["policy_status"] == "SELECTED_PREOUTCOME"
    }
    output = []
    for arm, _, _, role in ARMS:
        rows = [
            row
            for row in selection
            if row["arm"] == arm and row["policy_status"] == "SELECTED_PREOUTCOME"
        ]
        same = sum(
            selected[(arm, str(row["issue_instance"]))]
            == selected[("B0_BEST_FULL", str(row["issue_instance"]))]
            for row in rows
        )
        output.append(
            {
                "arm": arm,
                "arm_role": role,
                "selected_issue_count": len(rows),
                "same_as_b0": same,
                "different_from_b0": len(rows) - same,
                "choice_issue_count": sum(
                    int(row["choice_opportunity"]) for row in rows
                ),
                "selected_identity_set_sha256": canonical_hash(
                    sorted(
                        (row["issue_instance"], row["selected_portfolio_id"])
                        for row in rows
                    )
                ),
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
        )
    return output


def feature_coverage(
    probabilities: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    output = []
    years = sorted({str(row["year"]) for row in probabilities})
    for year in ("ALL", *years):
        rows = (
            list(probabilities)
            if year == "ALL"
            else [row for row in probabilities if str(row["year"]) == year]
        )
        output.append(
            {
                "year": year,
                "match_count": len(rows),
                "new_team_fallback_count": sum(
                    int(row["new_team_fallback"]) for row in rows
                ),
                "min_history_lt5_count": sum(
                    int(row["min_history_n"]) < 5 for row in rows
                ),
                "min_history_lt10_count": sum(
                    int(row["min_history_n"]) < 10 for row in rows
                ),
                "h2h_zero_count": sum(int(row["h2h_prior_n"]) == 0 for row in rows),
                "league_transition_present_count": sum(
                    int(row["home_league_changes"]) + int(row["away_league_changes"])
                    > 0
                    for row in rows
                ),
                "home_congested_7d_count": sum(
                    int(row["home_matches_7d"]) >= 3 for row in rows
                ),
                "away_congested_7d_count": sum(
                    int(row["away_matches_7d"]) >= 3 for row in rows
                ),
                "policy": "RETAIN_MATCH_USE_SHRUNK_PRIOR_AND_EXPLICIT_DEPTH",
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
        )
    return output


def outer_year_registry(
    probabilities: Sequence[Mapping[str, object]],
    state_rows: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    state_by_cutoff = {str(row["feature_cutoff_ts"]): row for row in state_rows}
    output = []
    for year in sorted({int(row["year"]) for row in probabilities}):
        rows = [row for row in probabilities if int(row["year"]) == year]
        cutoffs = sorted({str(row["feature_cutoff_ts"]) for row in rows})
        states = [state_by_cutoff[cutoff] for cutoff in cutoffs]
        output.append(
            {
                "target_year": year,
                "fold": f"OOS_{year}",
                "target_match_count": len(rows),
                "first_cutoff_ts": cutoffs[0],
                "last_cutoff_ts": cutoffs[-1],
                "first_training_rows": states[0]["training_rows"],
                "last_training_rows": states[-1]["training_rows"],
                "first_state_event_sha256": states[0]["history_event_sha256"],
                "last_state_event_sha256": states[-1]["history_event_sha256"],
                "parameter_rule": "FIXED_PREOUTCOME_HYPERPARAMETERS_ALL_FOLDS",
                "state_rule": "EXPANDING_HISTORY_KICKOFF_LE_CUTOFF_MINUS_180_MINUTES",
                "gate_b_evaluation": "YEAR|FOLD|LOYO|EX_LARGEST_YEAR|EX_LARGEST_ISSUE",
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
        )
    return output


def atomic_generate(output: Path, db: Path) -> dict[str, object]:
    output = output.resolve()
    if output.exists():
        raise RuntimeError(f"refusing to overwrite immutable output: {output}")
    stage = output.with_name(output.name + f".stage-{os.getpid()}")
    if stage.exists():
        raise RuntimeError(f"staging path exists: {stage}")
    stage.mkdir(parents=True)
    try:
        if sha256_file(db) != SOURCE_DB_SHA256:
            raise RuntimeError("source database hash drift")
        manifest_179 = verify_package(
            SOURCE_179_DIR, SOURCE_179_MANIFEST, SOURCE_179_CONTENT
        )
        manifest_134 = verify_package(
            SOURCE_134_DIR, SOURCE_134_MANIFEST, SOURCE_134_CONTENT
        )
        core = load_core()
        if (
            tuple(core.FAMILIES) != FAMILIES
            or tuple(core.CONFIGURATIONS) != CONFIG_NAMES
        ):
            raise RuntimeError("core contract drift")
        source = load_sources()
        cutoffs, by_match_cutoff = issue_cutoffs(source["roles"], core)
        targets = read_target_rows(db, set(by_match_cutoff))
        probabilities, state_rows, embargo_rows = probability_freeze(
            db, targets, source["probabilities"], by_match_cutoff, core
        )
        scores = score_candidates(source["candidates"], source["roles"], probabilities)
        selection = build_selection(source["selection"], scores)
        reproduction = reproduce_baselines(source["selection"], selection)
        overlap = build_overlap(selection)
        coverage = feature_coverage(probabilities)
        outer_year = outer_year_registry(probabilities, state_rows)
        excluded_cutoffs = [
            row for row in embargo_rows if int(row["excluded_near_cutoff_rows"]) > 0
        ]
        embargo_summary = {
            "cutoff_count": len(embargo_rows),
            "cutoffs_with_excluded_rows": len(excluded_cutoffs),
            "sum_cutoff_level_excluded_rows": sum(
                int(row["excluded_near_cutoff_rows"]) for row in embargo_rows
            ),
            "minimum_nearest_excluded_kickoff_gap_minutes": min(
                float(row["nearest_excluded_kickoff_gap_minutes"])
                for row in excluded_cutoffs
            )
            if excluded_cutoffs
            else None,
        }
        counts = Counter(row["policy_status"] for row in selection)
        selected_by_arm = Counter(
            row["arm"]
            for row in selection
            if row["policy_status"] == "SELECTED_PREOUTCOME"
        )
        if set(selected_by_arm.values()) != {189} or counts != {
            "NO_BET_FROZEN": 159 * len(ARMS),
            "SELECTED_PREOUTCOME": 189 * len(ARMS),
        }:
            raise RuntimeError(f"selection denominator drift: {counts}")

        write_gzip(
            stage / "match_probability_freeze.csv.gz",
            list(probabilities[0]),
            probabilities,
        )
        write_gzip(stage / "candidate_universe_scores.csv.gz", list(scores[0]), scores)
        write_csv(stage / "selection_freeze.csv", list(selection[0]), selection)
        write_csv(
            stage / "baseline_reproduction.csv", list(reproduction[0]), reproduction
        )
        write_csv(stage / "identity_overlap.csv", list(overlap[0]), overlap)
        write_csv(stage / "team_state_registry.csv", list(state_rows[0]), state_rows)
        write_csv(
            stage / "completion_embargo_audit.csv",
            list(embargo_rows[0]),
            embargo_rows,
        )
        write_csv(stage / "feature_coverage.csv", list(coverage[0]), coverage)
        write_csv(stage / "outer_year_registry.csv", list(outer_year[0]), outer_year)
        cutoff_rows = [
            {
                "issue_instance": issue,
                "feature_cutoff_ts": cutoff.isoformat(sep=" "),
                "rule": "minimum kickoff across frozen issue candidate-role union",
                "score_available_through_ts": history_available_through(
                    cutoff
                ).isoformat(sep=" "),
                "history_rule": "kickoff <= cutoff - 180 minutes (inclusive)",
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
            for issue, cutoff in sorted(cutoffs.items())
        ]
        write_csv(
            stage / "issue_cutoff_registry.csv", list(cutoff_rows[0]), cutoff_rows
        )
        arm_rows = [
            {
                "arm": arm,
                "score_field": score,
                "definition": definition,
                "arm_role": role,
                "candidate_universe": "#179 exact 424 complete-issue identities",
                "selection": "K1 max frozen GM expected-SP; portfolio-id tie break",
                "participating_issues": 189,
                "frozen_no_bet_issues": 159,
                "allocation": "FULL_ENUMERATED",
                "tickets": FULL_TICKETS,
                "stake_yuan": FULL_STAKE_YUAN,
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
            for arm, score, definition, role in ARMS
        ]
        write_csv(stage / "arm_registry.csv", list(arm_rows[0]), arm_rows)
        feature_rows = [
            {
                "family": family,
                "definition": {
                    "LATENT_STRENGTH": "chronological attack/defence EWMA plus Elo",
                    "HOME_AWAY_SPLIT": "role-specific attack/defence EWMA",
                    "ROLLING_FORM": "prior 10-match points only",
                    "REST_CONGESTION": "rest hours and prior-match counts over 7/21 days",
                    "OPPONENT_ADJUSTMENT": "goal residual after opponent attack/defence state",
                    "TEAM_INITIALIZATION": "new-team league prior and 75/25 prior/destination shrink on league transition",
                    "H2H_PRIOR": "prior meetings only, alpha-12 shrink, primary weight 0.03",
                }[family],
                "timing": "KICKOFF_LE_COMMON_ISSUE_CUTOFF_MINUS_180_MINUTES",
                "missingness": "retain match; neutral league/team prior with explicit history depth",
                "controlling": 1,
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
            for family in FAMILIES
        ]
        write_csv(stage / "feature_manifest.csv", list(feature_rows[0]), feature_rows)
        config_rows = []
        for name, config in core.CONFIGURATIONS.items():
            config_rows.append(
                {
                    "configuration": name,
                    **{
                        f"weight_{family.lower()}": config["weights"][family]
                        for family in FAMILIES
                    },
                    "state_half_life_matches": core.STATE_HALF_LIFE_MATCHES,
                    "new_team_prior_matches": core.NEW_TEAM_PRIOR_MATCHES,
                    "controlling": 1,
                    "outcome_boundary": OUTCOME_BOUNDARY,
                }
            )
        write_csv(
            stage / "configuration_registry.csv", list(config_rows[0]), config_rows
        )
        source_binding = {
            "issue": ISSUE,
            "contract": CONTRACT,
            "version": VERSION,
            "base_main_commit": BASE_MAIN_COMMIT,
            "source_179_gate_a": {
                "package": SOURCE_179,
                "manifest": SOURCE_179_MANIFEST,
                "content": SOURCE_179_CONTENT,
                "payload_count": len(manifest_179),
            },
            "source_134_gate_a": {
                "package": SOURCE_134,
                "manifest": SOURCE_134_MANIFEST,
                "content": SOURCE_134_CONTENT,
                "payload_count": len(manifest_134),
                "access": "candidate role vectors only",
            },
            "database": {
                "path": str(DB_REPOSITORY_PATH),
                "sha256": SOURCE_DB_SHA256,
                "target_projection": [
                    "match_id",
                    "issue",
                    "match_idx",
                    "kickoff_ts",
                    "year",
                    "league",
                    "home_team_id",
                    "away_team_id",
                    "handicap_line_norm",
                ],
                "history_projection": [
                    "match_id",
                    "kickoff_ts",
                    "league",
                    "home_team_id",
                    "away_team_id",
                    "handicap_line_norm",
                    "fthg",
                    "ftag",
                ],
                "completion_timestamp_field": None,
                "completion_timestamp_status": "UNAVAILABLE_IN_SOURCE_SCHEMA",
            },
            "completion_embargo": {
                "minutes": COMPLETION_EMBARGO_MINUTES,
                "boundary": "inclusive",
                "rule": "kickoff <= common issue cutoff - 180 minutes",
                "audit_file": "completion_embargo_audit.csv",
                **embargo_summary,
            },
            "core": {
                "path": str(CORE_SOURCE_PATH),
                "sha256": sha256_file(ROOT / CORE_SOURCE_PATH),
            },
            "outcome_boundary": OUTCOME_BOUNDARY,
        }
        (stage / "source_binding.json").write_text(
            dump_json(source_binding), encoding="utf-8"
        )
        card = {
            "issue": ISSUE,
            "contract": CONTRACT,
            "version": VERSION,
            "stage": "GATE_A_OUTCOME_UNEXPOSED_TEAM_MATCHUP_FREEZE",
            "incumbent": {
                "arm": "B0_BEST_FULL",
                "allocation": "FULL_ENUMERATED",
                "tickets": FULL_TICKETS,
                "stake_yuan": FULL_STAKE_YUAN,
                "selected": 189,
                "no_bet": 159,
            },
            "comparators": [
                "B0_BEST_FULL controlling economic",
                "L0_QUICK_LEAGUE accepted quick comparator",
                "H0_LEAGUE_DIAGNOSTIC probability diagnostic only",
            ],
            "candidate_universe": {
                "issues": 348,
                "participating": 189,
                "no_bet": 159,
                "identities": 424,
                "roles": 2968,
                "matches": 1558,
            },
            "arms": [
                {"arm": arm, "score": score, "definition": definition, "role": role}
                for arm, score, definition, role in ARMS
            ],
            "chronology": "single sequential state; source has no completion timestamp, so before each common issue cutoff consume scores only when kickoff <= cutoff - 180 minutes (inclusive); tie by match_id",
            "completion_embargo": {
                "timestamp_source": "UNAVAILABLE_IN_SOURCE_SCHEMA",
                "fallback": "FIXED_180_MINUTE_EMBARGO",
                "minutes": COMPLETION_EMBARGO_MINUTES,
                "boundary": "inclusive",
                "rule": "kickoff <= common issue cutoff - 180 minutes",
                "audit_file": "completion_embargo_audit.csv",
                **embargo_summary,
            },
            "outer_year_evaluation": "target folds OOS_2020..OOS_2025 remain unchanged; hyperparameters fixed across folds; YEAR/FOLD/LOYO and ex-largest are Gate-B requirements",
            "h2h": "prior-only, ordered home/away pair, maximum 12 meetings, alpha 12, primary weight 0.03; explicit minus-H2H ablation",
            "settlement": "not read or produced in Gate A; Gate B requires PI authorization",
            "denominator": {
                "selection_rows": len(selection),
                "selected_rows": counts["SELECTED_PREOUTCOME"],
                "no_bet_rows": counts["NO_BET_FROZEN"],
                "selected_by_arm": dict(selected_by_arm),
                "planned_stake_per_arm_yuan": 189 * FULL_STAKE_YUAN,
            },
            "gate_b_required": "LogLoss/Brier/calibration/coverage then matched FULL-N7 pre-tax ROI lift, LOYO, ex-largest, concentration and risk-adjusted diagnostics; positive claims require strict independent EV",
            "gate_b_status": "NOT_AUTHORIZED_PENDING_PI_GATE_A_REVIEW",
            "promotion_boundary": "B0 remains controlling; H_MINUS_RAW_HDA diagnostic only; no selector threshold/M/allocation/pruning/ticket change",
            "outcome_boundary": OUTCOME_BOUNDARY,
        }
        (stage / "gate_a_card.json").write_text(dump_json(card), encoding="utf-8")
        (stage / "README.md").write_text(
            "# #180 Gate A v2\n\n"
            "Outcome-unexposed chronological deep team/matchup freeze over the exact "
            "#179 candidate denominator. The source database has no authoritative "
            "completion timestamp, so a final score enters state only when its kickoff "
            "is at or before the common issue cutoff minus the fixed 180-minute embargo. "
            "The boundary is inclusive and `completion_embargo_audit.csv` records the "
            "cutoff-level exclusions. B0 remains controlling; Gate B is not authorized.\n",
            encoding="utf-8",
        )
        shutil.copyfile(ROOT / CORE_SOURCE_PATH, stage / "bj180_team_matchup_core.py")
        shutil.copyfile(Path(__file__).resolve(), stage / "freeze_runner.py")
        payloads = sorted(path for path in stage.iterdir() if path.is_file())
        content = {
            "contract_version": VERSION,
            "denominator": card["denominator"],
            "controls": {
                "base_main_commit": BASE_MAIN_COMMIT,
                "database_sha256": SOURCE_DB_SHA256,
                "source_179_manifest": SOURCE_179_MANIFEST,
                "all_arm_identity_sha256": canonical_hash(
                    sorted(
                        (
                            row["arm"],
                            row["issue_instance"],
                            row["selected_portfolio_id"],
                        )
                        for row in selection
                        if row["policy_status"] == "SELECTED_PREOUTCOME"
                    )
                ),
                "team_state_registry_sha256": sha256_file(
                    stage / "team_state_registry.csv"
                ),
            },
            "payloads": {path.name: sha256_file(path) for path in payloads},
        }
        (stage / "CONTENT_IDENTITY.json").write_text(
            dump_json(content), encoding="utf-8"
        )
        payloads = sorted(path for path in stage.iterdir() if path.is_file())
        (stage / "SHA256SUMS.json").write_text(
            dump_json({path.name: sha256_file(path) for path in payloads}),
            encoding="utf-8",
        )
        os.replace(stage, output)
        return {
            "output": str(output),
            "manifest_sha256": sha256_file(output / "SHA256SUMS.json"),
            "content_sha256": sha256_file(output / "CONTENT_IDENTITY.json"),
            "selection_rows": len(selection),
            "selected_rows": counts["SELECTED_PREOUTCOME"],
        }
    except Exception:
        if stage.exists():
            shutil.rmtree(stage)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    db = args.database.resolve() if args.database else locate_database()
    print(json.dumps(atomic_generate(args.output, db), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
