#!/usr/bin/env python3
"""Freeze Issue #179's outcome-unexposed hierarchical league Gate A."""

from __future__ import annotations

import argparse
import csv
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
from pathlib import Path
from types import ModuleType
from typing import Iterable, Iterator, Mapping, Sequence


ISSUE = 179
CONTRACT = "BJ-HIST-LEAGUE-MODEL-N7-001"
VERSION = "bj179-gate-a-v2"
BASE_MAIN_COMMIT = "9ec5cf4856f546861e20fad76d110807576903c7"
SOURCE_GATE_A_MANIFEST = (
    "0a7e4d673e7fc5fd4832c91e3b519afe5a2bc3211b99f4c95f57c691921b65fd"
)
SOURCE_GATE_A_CONTENT = (
    "3fe014f3decdbd589cdded52d8a9b2bac0f3cb988c2ae8e15cf79314a02eede1"
)
SOURCE_DB_SHA256 = "7f62079b18b3c028884da92aa8393f5b198246c9d7c32cd0b401562a055c5d6f"
FULL_TICKETS = 2187
FULL_STAKE_YUAN = 4374
OUTCOME_BOUNDARY = (
    "Gate A outcome-unexposed: target match result/final-SP/payout/tax/ROI/settlement "
    "fields are never read by target probability construction or identity ranking"
)
FORBIDDEN_TARGET_FIELDS = {
    "fthg",
    "ftag",
    "result_code",
    "winning_sp",
    "official_sp_3",
    "official_sp_1",
    "official_sp_0",
    "final_sp",
    "payout",
    "tax",
    "roi",
    "settlement",
}
FAMILIES = (
    "RAW_HDA_SEASON",
    "BJ_HANDICAP_REGIME",
    "EURO_CALIBRATION",
    "ASIAN_CALIBRATION",
    "BEIJING_SP_CALIBRATION",
    "LIQUIDITY_DRIFT",
)
CONFIG_NAMES = (
    "BALANCED_PRIMARY",
    "BALANCED_CONSERVATIVE",
    "BALANCED_RESPONSIVE",
    "PRICING_HEAVY_PRIMARY",
    "REGIME_HEAVY_PRIMARY",
    "PRICING_HEAVY_CONSERVATIVE",
)
ARMS = (
    (
        "B0_BEST_FULL",
        "market_gm_e_sp",
        "accepted BEST_FULL rank-one identity",
        "BASELINE",
    ),
    (
        "Q1_QUICK_LEAGUE",
        "quick_league_gm_e_sp",
        "accepted #134 quick league component",
        "BASELINE",
    ),
    (
        "H1_DEEP_ALL",
        "deep_all_gm_e_sp",
        "six-family BALANCED_PRIMARY hierarchical league model",
        "PRIMARY",
    ),
    (
        "H_CFG_BALANCED_CONSERVATIVE",
        "cfg_balanced_conservative_gm_e_sp",
        "balanced weights with stronger shrinkage and lower residual scale",
        "SENSITIVITY",
    ),
    (
        "H_CFG_BALANCED_RESPONSIVE",
        "cfg_balanced_responsive_gm_e_sp",
        "balanced weights with weaker shrinkage and higher residual scale",
        "SENSITIVITY",
    ),
    (
        "H_CFG_PRICING_HEAVY",
        "cfg_pricing_heavy_primary_gm_e_sp",
        "pricing-heavy weights at primary shrinkage",
        "SENSITIVITY",
    ),
    (
        "H_CFG_REGIME_HEAVY",
        "cfg_regime_heavy_primary_gm_e_sp",
        "raw/BJ regime-heavy weights at primary shrinkage",
        "SENSITIVITY",
    ),
    (
        "H_CFG_PRICING_CONSERVATIVE",
        "cfg_pricing_heavy_conservative_gm_e_sp",
        "pricing-heavy weights with conservative shrinkage",
        "SENSITIVITY",
    ),
    (
        "H_MINUS_RAW_HDA",
        "deep_minus_raw_hda_gm_e_sp",
        "BALANCED_PRIMARY without RAW_HDA_SEASON",
        "ABLATION",
    ),
    (
        "H_MINUS_BJ_REGIME",
        "deep_minus_bj_regime_gm_e_sp",
        "BALANCED_PRIMARY without BJ_HANDICAP_REGIME",
        "ABLATION",
    ),
    (
        "H_MINUS_EURO",
        "deep_minus_euro_gm_e_sp",
        "BALANCED_PRIMARY without EURO_CALIBRATION",
        "ABLATION",
    ),
    (
        "H_MINUS_ASIAN",
        "deep_minus_asian_gm_e_sp",
        "BALANCED_PRIMARY without ASIAN_CALIBRATION",
        "ABLATION",
    ),
    (
        "H_MINUS_BEIJING_SP",
        "deep_minus_beijing_sp_gm_e_sp",
        "BALANCED_PRIMARY without BEIJING_SP_CALIBRATION",
        "ABLATION",
    ),
    (
        "H_MINUS_LIQUIDITY",
        "deep_minus_liquidity_gm_e_sp",
        "BALANCED_PRIMARY without LIQUIDITY_DRIFT",
        "ABLATION",
    ),
)
VECTOR_SPECS = {
    "deep_all": ("BALANCED_PRIMARY", None),
    "cfg_balanced_conservative": ("BALANCED_CONSERVATIVE", None),
    "cfg_balanced_responsive": ("BALANCED_RESPONSIVE", None),
    "cfg_pricing_heavy_primary": ("PRICING_HEAVY_PRIMARY", None),
    "cfg_regime_heavy_primary": ("REGIME_HEAVY_PRIMARY", None),
    "cfg_pricing_heavy_conservative": ("PRICING_HEAVY_CONSERVATIVE", None),
    "deep_minus_raw_hda": ("BALANCED_PRIMARY", "RAW_HDA_SEASON"),
    "deep_minus_bj_regime": ("BALANCED_PRIMARY", "BJ_HANDICAP_REGIME"),
    "deep_minus_euro": ("BALANCED_PRIMARY", "EURO_CALIBRATION"),
    "deep_minus_asian": ("BALANCED_PRIMARY", "ASIAN_CALIBRATION"),
    "deep_minus_beijing_sp": ("BALANCED_PRIMARY", "BEIJING_SP_CALIBRATION"),
    "deep_minus_liquidity": ("BALANCED_PRIMARY", "LIQUIDITY_DRIFT"),
}


def repo_root() -> Path:
    for candidate in (
        Path(__file__).resolve().parent,
        *Path(__file__).resolve().parents,
    ):
        if (candidate / ".git").exists() and (candidate / "results").is_dir():
            return candidate
    raise RuntimeError("repository root unavailable")


ROOT = repo_root()
SOURCE = ROOT / "results" / "bj134_gate_a_preoutcome_v3"
CORE_PATH = ROOT / "scripts" / "bj179_hierarchical_league_core.py"
DEFAULT_OUTPUT = ROOT / "results" / "bj179_gate_a_preoutcome_v2"


def find_source_db() -> Path:
    relative = Path("data/derived/beidan_xlsm/beidan_xlsm.sqlite")
    for base in (ROOT, *ROOT.parents):
        candidate = base / relative
        if candidate.is_file():
            return candidate
    raise RuntimeError(f"source database unavailable: {relative}")


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
    path: Path, fields: Sequence[str], rows: Iterable[dict[str, object]]
) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=fields, lineterminator="\n", extrasaction="raise"
        )
        writer.writeheader()
        writer.writerows(rows)


def write_gzip(
    path: Path, fields: Sequence[str], rows: Iterable[dict[str, object]]
) -> None:
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            text = io.TextIOWrapper(zipped, encoding="utf-8", newline="")
            writer = csv.DictWriter(
                text, fieldnames=fields, lineterminator="\n", extrasaction="raise"
            )
            writer.writeheader()
            writer.writerows(rows)
            text.flush()
            text.detach()


def write_gzip_json(path: Path, value: object) -> None:
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            zipped.write(dump_json(value).encode("utf-8"))


def verify_package(
    directory: Path, manifest_hash: str, content_hash: str
) -> dict[str, str]:
    if sha256_file(directory / "SHA256SUMS.json") != manifest_hash:
        raise RuntimeError(f"source manifest drift: {directory.name}")
    if sha256_file(directory / "CONTENT_IDENTITY.json") != content_hash:
        raise RuntimeError(f"source content identity drift: {directory.name}")
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


def load_core() -> ModuleType:
    spec = importlib.util.spec_from_file_location("bj179_hierarchical_core", CORE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("core loader unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def ro_connection(db: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{db}?mode=ro&immutable=1", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def market_joins() -> str:
    aliases = {
        "ei": ("euro_1x2", "initial"),
        "e10": ("euro_1x2", "10h"),
        "e1": ("euro_1x2", "1h"),
        "ai": ("asian_handicap", "initial"),
        "a10": ("asian_handicap", "10h"),
        "a1": ("asian_handicap", "1h"),
        "oi": ("over_under", "initial"),
        "o10": ("over_under", "10h"),
        "o1": ("over_under", "1h"),
    }
    return "\n".join(
        f"LEFT JOIN market_consensus {alias} ON {alias}.match_id=m.match_id "
        f"AND {alias}.market='{market}' AND {alias}.snapshot='{snapshot}'"
        for alias, (market, snapshot) in aliases.items()
    )


def market_select() -> str:
    pieces = []
    for prefix, alias in (
        ("euro_initial", "ei"),
        ("euro_10h", "e10"),
        ("euro_1h", "e1"),
        ("asian_initial", "ai"),
        ("asian_10h", "a10"),
        ("asian_1h", "a1"),
        ("ou_initial", "oi"),
        ("ou_10h", "o10"),
        ("ou_1h", "o1"),
    ):
        pieces.extend(
            [
                f"{alias}.n_complete AS {prefix}_n",
                f"{alias}.v1_avg AS {prefix}_v1",
                f"{alias}.v2_avg AS {prefix}_v2",
                f"{alias}.v3_avg AS {prefix}_v3",
            ]
        )
        if prefix == "euro_1h":
            pieces.extend(f"{alias}.v{i}_min AS {prefix}_min{i}" for i in (1, 2, 3))
            pieces.extend(f"{alias}.v{i}_max AS {prefix}_max{i}" for i in (1, 2, 3))
    return ",\n".join(pieces)


def historical_rows(db: Path, before: str) -> Iterator[dict[str, object]]:
    connection = ro_connection(db)
    query = f"""
        SELECT m.match_id, m.kickoff_ts, m.league, mf.handicap_line_norm,
               mf.fthg, mf.ftag,
               mf.official_sp_3, mf.official_sp_1, mf.official_sp_0,
               {market_select()}
          FROM matches m JOIN match_features mf ON mf.match_id=m.match_id
          {market_joins()}
         WHERE m.kickoff_ts IS NOT NULL AND m.kickoff_ts < ?
           AND mf.fthg IS NOT NULL AND mf.ftag IS NOT NULL
         ORDER BY m.kickoff_ts, m.match_id
    """
    try:
        for row in connection.execute(query, (before,)):
            yield dict(row)
    finally:
        connection.close()


def fit_outer_year_models(
    db: Path, years: Sequence[int], core: ModuleType
) -> dict[int, object]:
    ordered = sorted(set(years))
    accumulator = core.HierarchicalLeagueModel(max(ordered))
    output = {}
    next_index = 0
    for row in historical_rows(db, f"{max(ordered)}-01-01 00:00:00"):
        row_year = int(str(row["kickoff_ts"])[:4])
        while next_index < len(ordered) and row_year >= ordered[next_index]:
            output[ordered[next_index]] = accumulator.frozen_copy(ordered[next_index])
            next_index += 1
        accumulator.update(row)
    while next_index < len(ordered):
        output[ordered[next_index]] = accumulator.frozen_copy(ordered[next_index])
        next_index += 1
    if any(model.training_rows == 0 for model in output.values()):
        raise RuntimeError("empty outer-year fold")
    return output


def predicted_sp(role: Mapping[str, str]) -> tuple[float, float, float]:
    probabilities = [float(role[f"p_model{code}"]) for code in ("3", "1", "0")]
    expected_sp = float(role["e_sp"])
    q = [expected_sp * float(role[f"q_weight{code}"]) for code in ("3", "1", "0")]
    if abs(sum(q) - expected_sp) > 2e-9:
        raise RuntimeError(f"q reconstruction drift: {role['match_id']}")
    return tuple(q[index] / probabilities[index] for index in range(3))


def geometric(values: Sequence[float]) -> float:
    if not values or any(value <= 0 or not math.isfinite(value) for value in values):
        return 0.0
    return math.exp(sum(math.log(value) for value in values) / len(values))


def compact(value: object) -> object:
    return f"{value:.12f}" if isinstance(value, float) else value


def load_source_inputs() -> dict[str, object]:
    selections = read_csv(SOURCE / "selection_freeze.csv")
    candidates = read_gzip(SOURCE / "candidate_universe_scores.csv.gz")
    roles = read_gzip(SOURCE / "candidate_role_vectors.csv.gz")
    target = read_gzip(SOURCE / "match_feature_ledger.csv.gz")
    if (
        len(selections) != 3132
        or len(candidates) != 424
        or len(roles) != 2968
        or len(target) != 1558
    ):
        raise RuntimeError("#134 source denominator drift")
    if FORBIDDEN_TARGET_FIELDS.intersection(target[0]):
        raise RuntimeError("target feature ledger exposes forbidden outcome fields")
    b0 = [row for row in selections if row["arm"] == "B0_BEST_FULL"]
    quick = [row for row in selections if row["arm"] == "L1_LEAGUE_CORE"]
    if len(b0) != 348 or len(quick) != 348:
        raise RuntimeError("source baseline surface drift")
    return {
        "selections": selections,
        "candidates": candidates,
        "roles": roles,
        "target": target,
        "b0": b0,
        "quick": quick,
    }


def canonical_role_by_match(
    roles: Sequence[dict[str, str]],
) -> dict[str, dict[str, str]]:
    fields = (
        "p_model3",
        "p_model1",
        "p_model0",
        "p_market_cal3",
        "p_market_cal1",
        "p_market_cal0",
        "q_weight3",
        "q_weight1",
        "q_weight0",
        "e_sp",
    )
    output = {}
    for row in roles:
        match_id = row["match_id"]
        if match_id in output and any(
            row[field] != output[match_id][field] for field in fields
        ):
            raise RuntimeError(
                f"role probability vector drift within match: {match_id}"
            )
        output.setdefault(match_id, row)
    if len(output) != 1558:
        raise RuntimeError(f"unique target match drift: {len(output)}")
    return output


def probability_freeze(
    target_rows: Sequence[dict[str, str]],
    roles: Mapping[str, dict[str, str]],
    models: Mapping[int, object],
    core: ModuleType,
) -> list[dict[str, object]]:
    output = []
    for target in sorted(target_rows, key=lambda row: int(row["match_id"])):
        safe_target = {
            key: value
            for key, value in target.items()
            if key not in FORBIDDEN_TARGET_FIELDS
        }
        match_id = safe_target["match_id"]
        role = roles[match_id]
        year = int(safe_target["year"])
        model = models[year]
        # The accepted #134 CSV stores probabilities at 12 decimal places.  Re-normalize
        # that exact serialized vector before downstream log pooling so a 1e-12 text
        # round-trip delta cannot masquerade as a probability-contract failure.
        baseline = core.normalize(
            [float(role[f"p_market_cal{code}"]) for code in ("3", "1", "0")]
        )
        target_bj_sp = predicted_sp(role)
        enriched = {
            **safe_target,
            **{
                f"target_bj_pred_sp_{code}": target_bj_sp[index]
                for index, code in enumerate(("3", "1", "0"))
            },
        }
        families = model.family_vectors(enriched, baseline, "BALANCED_PRIMARY")
        vectors = {
            "market": baseline,
            "quick": core.normalize(
                [float(safe_target[f"league_p{code}"]) for code in ("3", "1", "0")]
            ),
            **{
                name: model.probabilities(enriched, baseline, config, excluded)
                for name, (config, excluded) in VECTOR_SPECS.items()
            },
        }
        if any(abs(sum(vector) - 1.0) > 1e-12 for vector in vectors.values()):
            raise RuntimeError(f"probability normalization drift: {match_id}")
        signatures = core.market_signature(enriched)
        league = str(safe_target.get("league") or "__UNKNOWN__")
        euro_complete = (
            core.no_vig([enriched.get(f"euro_1h_v{index}") for index in (1, 2, 3)])
            is not None
        )
        asian_complete = core.asian_anchor(enriched, baseline) is not None
        beijing_complete = core.beijing_sp_anchor(enriched) is not None
        row = {
            "match_id": match_id,
            "issue": safe_target["issue"],
            "match_idx": safe_target["match_idx"],
            "kickoff_ts": safe_target["kickoff_ts"],
            "year": year,
            "league": league,
            "handicap_line_norm": safe_target["handicap_line_norm"],
            "outer_year_train_rule": f"kickoff year < {year}",
            "unknown_league_fallback": int(league not in model.bj_league_counts),
            "training_raw_league_n": sum(model.raw_league_counts[league].values()),
            "training_bj_league_n": sum(model.bj_league_counts[league].values()),
            "total_bucket": core.total_bucket(safe_target.get("ou_1h_v2")),
            "handicap_bucket": core.handicap_bucket(
                safe_target.get("handicap_line_norm")
            ),
            "asian_line_bucket": core.asian_line_bucket(safe_target.get("asian_1h_v2")),
            "target_euro_source_complete": int(euro_complete),
            "target_asian_source_complete": int(asian_complete),
            "target_beijing_pred_sp_source_complete": int(beijing_complete),
            **{
                f"target_beijing_pred_sp_{code}": compact(target_bj_sp[index])
                for index, code in enumerate(("3", "1", "0"))
            },
            **{f"market_signature_{key}": value for key, value in signatures.items()},
        }
        for name, vector in vectors.items():
            row.update(
                {
                    f"{name}_p{code}": compact(vector[index])
                    for index, code in enumerate(("3", "1", "0"))
                }
            )
        for family, vector in families.items():
            slug = family.lower()
            row.update(
                {
                    f"family_{slug}_p{code}": compact(vector[index])
                    for index, code in enumerate(("3", "1", "0"))
                }
            )
        row["outcome_boundary"] = OUTCOME_BOUNDARY
        output.append(row)
    return output


def score_candidates(
    candidates: Sequence[dict[str, str]],
    roles: Sequence[dict[str, str]],
    probabilities: Sequence[dict[str, object]],
) -> list[dict[str, object]]:
    probability_by_match = {str(row["match_id"]): row for row in probabilities}
    roles_by_key = defaultdict(list)
    for row in roles:
        roles_by_key[(row["issue_instance"], row["portfolio_id"])].append(row)
    output = []
    vector_names = tuple(VECTOR_SPECS)
    for candidate in candidates:
        key = (candidate["issue_instance"], candidate["portfolio_id"])
        frozen_roles = sorted(
            roles_by_key[key], key=lambda row: int(row["selection_rank"])
        )
        if len(frozen_roles) != 7:
            raise RuntimeError(f"candidate role denominator drift: {key}")
        scores = {name: [] for name in vector_names}
        for role in frozen_roles:
            probability = probability_by_match[role["match_id"]]
            sp = predicted_sp(role)
            for name in vector_names:
                vector = [
                    float(probability[f"{name}_p{code}"]) for code in ("3", "1", "0")
                ]
                scores[name].append(
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
                "quick_league_gm_e_sp": candidate["league_gm_e_sp"],
                **{
                    f"{name}_gm_e_sp": compact(geometric(values))
                    for name, values in scores.items()
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
    arm: str, candidates: Sequence[dict[str, object]]
) -> dict[str, object]:
    if arm == "B0_BEST_FULL":
        return min(
            candidates,
            key=lambda row: (
                int(row["source_selector_rank"]),
                str(row["portfolio_id"]),
            ),
        )
    field = next(score for name, score, _, _ in ARMS if name == arm)
    return min(
        candidates, key=lambda row: (-float(row[field]), str(row["portfolio_id"]))
    )


def build_selection(
    source: dict[str, object], scores: Sequence[dict[str, object]]
) -> list[dict[str, object]]:
    by_issue = defaultdict(list)
    for row in scores:
        by_issue[str(row["issue_instance"])].append(row)
    b0_rows = sorted(
        source["b0"], key=lambda row: (row["year"], row["issue"], row["fold"])
    )
    output = []
    for census in b0_rows:
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
    expected = 348 * len(ARMS)
    if len(output) != expected:
        raise RuntimeError(f"selection surface drift: {len(output)} != {expected}")
    return output


def source_identity_map(rows: Sequence[dict[str, str]], arm: str) -> dict[str, str]:
    return {
        row["issue_instance"]: row["selected_portfolio_id"]
        for row in rows
        if row["arm"] == arm and row["policy_status"] == "SELECTED_PREOUTCOME"
    }


def reproduce_baselines(
    source: dict[str, object], selection: Sequence[dict[str, object]]
) -> list[dict[str, object]]:
    comparisons = (
        ("B0_BEST_FULL", "B0_BEST_FULL"),
        ("Q1_QUICK_LEAGUE", "L1_LEAGUE_CORE"),
    )
    output = []
    for target_arm, source_arm in comparisons:
        actual = {
            str(row["issue_instance"]): str(row["selected_portfolio_id"])
            for row in selection
            if row["arm"] == target_arm
            and row["policy_status"] == "SELECTED_PREOUTCOME"
        }
        expected = source_identity_map(source["selections"], source_arm)
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


def build_overlap(selection: Sequence[dict[str, object]]) -> list[dict[str, object]]:
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


def threshold_registry(
    selection: Sequence[dict[str, object]],
) -> list[dict[str, object]]:
    output = []
    for arm, _, _, role in ARMS:
        rows = [
            row
            for row in selection
            if row["arm"] == arm and row["policy_status"] == "SELECTED_PREOUTCOME"
        ]
        values = sorted(float(row["selected_score"]) for row in rows)
        for label, q in (("Q00", 0.0), ("Q25", 0.25), ("Q50", 0.50), ("Q75", 0.75)):
            value = values[int(math.floor(q * (len(values) - 1)))]
            eligible = [row for row in rows if float(row["selected_score"]) >= value]
            output.append(
                {
                    "arm": arm,
                    "arm_role": role,
                    "threshold_label": label,
                    "threshold_quantile": q,
                    "threshold_value": compact(value),
                    "eligible_issue_count": len(eligible),
                    "controlling": 0,
                    "policy": "DESCRIPTIVE_ONLY_NO_PARTICIPATION_OR_SELECTOR_RETUNING",
                    "outcome_boundary": OUTCOME_BOUNDARY,
                }
            )
    return output


def missingness_registry(
    probabilities: Sequence[dict[str, object]], models: Mapping[int, object]
) -> list[dict[str, object]]:
    output = []
    for year_key in ("ALL", *sorted(models)):
        rows = (
            list(probabilities)
            if year_key == "ALL"
            else [row for row in probabilities if int(row["year"]) == year_key]
        )
        signatures = ("breadth", "dispersion", "euro_move", "asian_move", "ou_move")
        output.append(
            {
                "year": year_key,
                "target_match_count": len(rows),
                "unknown_league_fallback_count": sum(
                    int(row["unknown_league_fallback"]) for row in rows
                ),
                "missing_total_line_count": sum(
                    row["total_bucket"] == "T_MISSING" for row in rows
                ),
                "missing_euro_source_count": sum(
                    not int(row["target_euro_source_complete"]) for row in rows
                ),
                "missing_asian_source_count": sum(
                    not int(row["target_asian_source_complete"]) for row in rows
                ),
                "missing_beijing_pred_sp_source_count": sum(
                    not int(row["target_beijing_pred_sp_source_complete"])
                    for row in rows
                ),
                **{
                    f"missing_{name}_count": sum(
                        row[f"market_signature_{name}"] == "MISSING" for row in rows
                    )
                    for name in signatures
                },
                "policy": "RETAIN_MATCH_USE_HIERARCHICAL_GLOBAL_OR_EXPLICIT_MISSING_BUCKET",
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
        )
    return output


def parameter_frontier_registry(core: ModuleType) -> list[dict[str, object]]:
    arm_by_score = {score: (arm, role) for arm, score, _, role in ARMS}
    rows = []
    for vector_name, (config_name, excluded) in VECTOR_SPECS.items():
        config = core.CONFIGURATIONS[config_name]
        score_field = f"{vector_name}_gm_e_sp"
        arm, role = arm_by_score[score_field]
        rows.append(
            {
                "arm": arm,
                "arm_role": role,
                "vector_name": vector_name,
                "configuration": config_name,
                "excluded_family": excluded or "",
                **{
                    f"weight_{family.lower()}": config["weights"][family]
                    for family in FAMILIES
                },
                "shrinkage_multiplier": config["shrinkage_multiplier"],
                "residual_scale_multiplier": config["residual_scale_multiplier"],
                "gate_b_order": "PROBABILITY_FIRST_COMPLETE_FRONTIER_THEN_N7_ECONOMICS",
                "controlling": 1,
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
        )
    return rows


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
        source_manifest = verify_package(
            SOURCE, SOURCE_GATE_A_MANIFEST, SOURCE_GATE_A_CONTENT
        )
        core = load_core()
        if (
            tuple(core.FAMILIES) != FAMILIES
            or tuple(core.CONFIGURATIONS) != CONFIG_NAMES
        ):
            raise RuntimeError("runner/core family or configuration contract drift")
        source = load_source_inputs()
        roles_by_match = canonical_role_by_match(source["roles"])
        years = sorted({int(row["year"]) for row in source["target"]})
        models = fit_outer_year_models(db, years, core)
        probabilities = probability_freeze(
            source["target"], roles_by_match, models, core
        )
        scores = score_candidates(source["candidates"], source["roles"], probabilities)
        selection = build_selection(source, scores)
        reproduction = reproduce_baselines(source, selection)
        overlap = build_overlap(selection)
        thresholds = threshold_registry(selection)
        missingness = missingness_registry(probabilities, models)
        parameter_frontier = parameter_frontier_registry(core)

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
        write_csv(stage / "threshold_registry.csv", list(thresholds[0]), thresholds)
        write_csv(stage / "missingness_registry.csv", list(missingness[0]), missingness)
        write_csv(
            stage / "parameter_frontier.csv",
            list(parameter_frontier[0]),
            parameter_frontier,
        )

        parameter_payload = {
            "contract": CONTRACT,
            "version": VERSION,
            "primary_configuration": core.PRIMARY_CONFIG,
            "configurations": core.CONFIGURATIONS,
            "families": {
                "RAW_HDA_SEASON": "raw score H/D/A global, league and exponentially weighted prior-season evidence",
                "BJ_HANDICAP_REGIME": "separate Beijing-handicap truth by league/season, quarter-line handicap and OU-total buckets",
                "EURO_CALIBRATION": "EURO no-vig residuals by league x BJ handicap and league x EURO mass",
                "ASIAN_CALIBRATION": "Asian 1h home/away HK water plus signed line anchor; residuals by league x Asian line/side",
                "BEIJING_SP_CALIBRATION": "historical official BJDC SP anchor and outcome-safe target predicted-SP anchor; residuals by league x BJ handicap/mass",
                "LIQUIDITY_DRIFT": "breadth, dispersion, EURO/Asian/OU movement plus prior-season league residual; alpha 180/100; scale 0.35",
            },
            "frontier": "six pre-frozen configurations span weights, shrinkage and residual scales; primary has six leave-one-family-out ablations",
            "ablation": "remove exactly one of six families from BALANCED_PRIMARY and renormalize remaining weights",
            "unknown_league": "raw/BJ global priors and global regime cells; league calibration cells contribute zero residual",
            "folds": {str(year): models[year].to_payload() for year in years},
            "outcome_boundary": OUTCOME_BOUNDARY,
        }
        write_gzip_json(
            stage / "outer_year_parameter_freeze.json.gz", parameter_payload
        )
        training_rows = [
            {
                **models[year].summary(),
                "parameter_payload_sha256": canonical_hash(models[year].to_payload()),
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
            for year in years
        ]
        write_csv(
            stage / "outer_year_training_registry.csv",
            list(training_rows[0]),
            training_rows,
        )

        arm_rows = [
            {
                "arm": arm,
                "score_field": field,
                "definition": definition,
                "arm_role": role,
                "candidate_universe": "#134 exact 424 complete-issue identities",
                "selection": "K1 max frozen GM expected-SP; portfolio-id tie break",
                "participating_issues": 189,
                "frozen_no_bet_issues": 159,
                "allocation": "FULL_ENUMERATED",
                "tickets": FULL_TICKETS,
                "stake_yuan": FULL_STAKE_YUAN,
                "outcome_boundary": OUTCOME_BOUNDARY,
            }
            for arm, field, definition, role in ARMS
        ]
        write_csv(stage / "arm_registry.csv", list(arm_rows[0]), arm_rows)
        feature_rows = [
            {
                "family": "RAW_HDA_SEASON",
                "features": "raw score H/D/A global, league and recency-weighted season counts",
                "timing": "OUTER_YEAR_TRAIN_LT_TARGET_YEAR",
                "missingness": "global hierarchical fallback",
                "controlling": 1,
            },
            {
                "family": "BJ_HANDICAP_REGIME",
                "features": "separate Beijing-handicap outcome by league/season, signed BJ line and OU total",
                "timing": "OUTER_YEAR_TRAIN_LT_TARGET_YEAR + TARGET_PREKICKOFF_LINE",
                "missingness": "explicit T_MISSING/global cells",
                "controlling": 1,
            },
            {
                "family": "EURO_CALIBRATION",
                "features": "EURO 1h no-vig residual by league/BJ-handicap/EURO-mass",
                "timing": "OUTER_YEAR_TRAIN_LT_TARGET_YEAR + TARGET_PREKICKOFF_MARKET",
                "missingness": "market baseline retained; missing residual zero",
                "controlling": 1,
            },
            {
                "family": "ASIAN_CALIBRATION",
                "features": "Asian 1h home/away HK water and signed line anchor; league/line/side residual",
                "timing": "OUTER_YEAR_TRAIN_LT_TARGET_YEAR + TARGET_PREKICKOFF_ASIAN_1H",
                "missingness": "EURO target baseline fallback; explicit A/AS missing buckets",
                "controlling": 1,
            },
            {
                "family": "BEIJING_SP_CALIBRATION",
                "features": "historical official BJDC SP; target outcome-safe predicted-SP reconstructed from #134 roles",
                "timing": "HISTORICAL_OUTER_YEAR_OFFICIAL_SP + TARGET_PREOUTCOME_PREDICTED_SP",
                "missingness": "EURO target baseline fallback; coverage reported by fold",
                "controlling": 1,
            },
            {
                "family": "LIQUIDITY_DRIFT",
                "features": "bookmaker breadth, dispersion, EURO/Asian/OU movement, prior-season drift",
                "timing": "OUTER_YEAR_TRAIN_LT_TARGET_YEAR + TARGET_PREKICKOFF_SNAPSHOTS",
                "missingness": "explicit MISSING bucket",
                "controlling": 1,
            },
            {
                "family": "TEAM_NEWS_CONTEXT",
                "features": "none",
                "timing": "OUT_OF_SCOPE",
                "missingness": "deferred #180/#181/#182",
                "controlling": 0,
            },
        ]
        for row in feature_rows:
            row["outcome_boundary"] = OUTCOME_BOUNDARY
        write_csv(stage / "feature_manifest.csv", list(feature_rows[0]), feature_rows)

        source_binding = {
            "contract": CONTRACT,
            "version": VERSION,
            "base_main_commit": BASE_MAIN_COMMIT,
            "source_134_gate_a": {
                "package": SOURCE.name,
                "manifest": SOURCE_GATE_A_MANIFEST,
                "content": SOURCE_GATE_A_CONTENT,
                "payload_count": len(source_manifest),
            },
            "database": {
                "repository_path": "data/derived/beidan_xlsm/beidan_xlsm.sqlite",
                "sha256": SOURCE_DB_SHA256,
                "access": "training rows only where kickoff year < target fold, including raw score, BJ line, official historical BJDC SP and market snapshots; target projection and predicted SP consumed from #134 outcome-unexposed roles",
            },
            "core": {
                "path": "scripts/bj179_hierarchical_league_core.py",
                "sha256": sha256_file(CORE_PATH),
            },
            "outcome_boundary": OUTCOME_BOUNDARY,
        }
        (stage / "source_binding.json").write_text(
            dump_json(source_binding), encoding="utf-8"
        )
        source_census = [
            {
                "source": SOURCE.name,
                "role": "exact candidate/role/target-safe probability baseline",
                "manifest": SOURCE_GATE_A_MANIFEST,
                "content": SOURCE_GATE_A_CONTENT,
                "access": "manifest-covered Gate-A payloads",
                "outcome_boundary": OUTCOME_BOUNDARY,
            },
            {
                "source": "data/derived/beidan_xlsm/beidan_xlsm.sqlite",
                "role": "outer-year raw/BJ outcomes plus EURO/Asian/official-BJ-SP training features",
                "manifest": SOURCE_DB_SHA256,
                "content": SOURCE_DB_SHA256,
                "access": "training kickoff year < target only",
                "outcome_boundary": OUTCOME_BOUNDARY,
            },
            {
                "source": "scripts/bj179_hierarchical_league_core.py",
                "role": "frozen hierarchical implementation",
                "manifest": sha256_file(CORE_PATH),
                "content": sha256_file(CORE_PATH),
                "access": "package copy",
                "outcome_boundary": OUTCOME_BOUNDARY,
            },
        ]
        write_csv(stage / "source_census.csv", list(source_census[0]), source_census)

        counts = Counter(row["policy_status"] for row in selection)
        selected_by_arm = Counter(
            row["arm"]
            for row in selection
            if row["policy_status"] == "SELECTED_PREOUTCOME"
        )
        card = {
            "issue": ISSUE,
            "contract": CONTRACT,
            "version": VERSION,
            "stage": "GATE_A_OUTCOME_UNEXPOSED_HIERARCHICAL_LEAGUE_FREEZE",
            "candidate_universe": {
                "identities": 424,
                "roles": 2968,
                "matches": 1558,
                "issue_census": 348,
                "participating": 189,
                "no_bet": 159,
                "choice": 113,
                "invariant": 76,
            },
            "arms": [
                {"arm": arm, "score": field, "definition": definition, "role": role}
                for arm, field, definition, role in ARMS
            ],
            "baseline_reproduction": reproduction,
            "outer_year": "training kickoff year strictly less than target year; no same-year target outcome/history enters probability fit",
            "parameter_frontier": {
                "configuration_count": len(CONFIG_NAMES),
                "primary_ablation_count": len(FAMILIES),
                "rows": len(parameter_frontier),
                "policy": "all frozen configurations report probability metrics before any N7 economics",
            },
            "probability_first_gate_b": [
                "complete weight/shrinkage/ablation frontier",
                "multiclass log loss",
                "multiclass Brier",
                "calibration by probability bin",
                "support/unknown league",
            ],
            "economics_second_gate_b": [
                "matched FULL N7 pre-tax ROI/lift",
                "tax sensitivity",
                "LOYO",
                "ex-largest",
                "risk diagnostics",
            ],
            "denominator": {
                "selection_rows": len(selection),
                "selected_rows": counts["SELECTED_PREOUTCOME"],
                "no_bet_rows": counts["NO_BET_FROZEN"],
                "selected_by_arm": dict(selected_by_arm),
                "planned_stake_per_arm_yuan": 189 * FULL_STAKE_YUAN,
            },
            "thresholds": "descriptive raw cross-issue Q00/Q25/Q50/Q75 only; no participation/filter/selector retuning",
            "gate_b_status": "NOT_AUTHORIZED_PENDING_PI_GATE_A_REVIEW",
            "promotion_boundary": "paper research; positive claim requires strict independent EV; negative deep model cannot demote inherited B0",
            "outcome_boundary": OUTCOME_BOUNDARY,
        }
        (stage / "gate_a_card.json").write_text(dump_json(card), encoding="utf-8")
        (stage / "README.md").write_text(
            "# #179 Gate A v2\n\nOutcome-unexposed six-family hierarchical league/season probability, parameter-frontier and FULL-N7 identity freeze. Gate B is not authorized.\n",
            encoding="utf-8",
        )
        shutil.copyfile(CORE_PATH, stage / "bj179_hierarchical_league_core.py")
        shutil.copyfile(Path(__file__).resolve(), stage / "freeze_runner.py")
        payloads = sorted(path for path in stage.iterdir() if path.is_file())
        content = {
            "contract_version": VERSION,
            "denominator": card["denominator"],
            "controls": {
                "base_main_commit": BASE_MAIN_COMMIT,
                "source_134_manifest": SOURCE_GATE_A_MANIFEST,
                "database_sha256": SOURCE_DB_SHA256,
                "primary_configuration": core.PRIMARY_CONFIG,
                "configurations": core.CONFIGURATIONS,
                "baseline_identity_sha256": reproduction[0]["identity_set_sha256"],
                "quick_identity_sha256": reproduction[1]["identity_set_sha256"],
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
                "outer_year_parameter_sha256": canonical_hash(parameter_payload),
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
            "content_identity_sha256": sha256_file(output / "CONTENT_IDENTITY.json"),
            "denominator": card["denominator"],
        }
    except BaseException:
        if stage.exists():
            shutil.rmtree(stage)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--db", type=Path, default=find_source_db())
    args = parser.parse_args()
    print(dump_json(atomic_generate(args.output, args.db.resolve())), end="")


if __name__ == "__main__":
    main()
