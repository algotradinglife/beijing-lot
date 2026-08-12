#!/usr/bin/env python3
"""Freeze #137's outcome-unexposed complete-issue sampling surface.

The runner reads the accepted #132 selector/SP input and the 10-hour EURO
consensus.  Historical outcomes are permitted only to build a strictly
prior-year, aggregate market calibration map; no test-row outcome, final SP,
settlement, payout, ROI, or tax result is read or emitted.  The result is a
portable Gate-A package.  It deliberately cannot settle a ticket.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import math
import os
import shutil
import sqlite3
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable


CODES = ("3", "1", "0")
N = 7
FULL_K = 3 ** N
PRUNED_K = 2 * 3 ** (N - 1)
UNIT_STAKE = 2
CONTRACT = "BJ-HIST-PROB-SAMPLING-N7-001"
VERSION = "bj137-gate-a-v2"
CONTENT_VERSION = "bj137-gate-a-content-v2"
BJ132_MANIFEST = "6583503ee80fd2b40bb1c000917ff094afa0551b6a3f0af4b8d175a6432872f9"
MAX_IDENTITIES_PER_ISSUE_GATE = 32
M_GRID = (1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 1458, 2187)
PRIMARY_SEED = 137001
SENSITIVITY_SEEDS = (137001, 137002, 137003)
MARKET_START_YEAR = 2018
MIN_STRATUM_OBSERVATIONS = 100
SHRINKAGE_PSEUDOCOUNT = 50.0
BLEND_ALPHAS = (0.25, 0.50, 0.75)


def repository_root() -> Path:
    for candidate in (Path(__file__).resolve().parent, *Path(__file__).resolve().parents):
        if (candidate / ".git").exists() and (candidate / "scripts").is_dir():
            return candidate
    raise RuntimeError("repository root unavailable")


ROOT = repository_root()
SOURCE_132 = ROOT / "results" / "bj132_gate_a_complete_issue_preoutcome_v1r1"
SOURCE_DB = ROOT.parent.parent / "data" / "derived" / "beidan_xlsm" / "beidan_xlsm.sqlite"
OUTPUT = ROOT / "results" / "bj137_gate_a_preoutcome_v2"

GATES = ({"gate_id": "NO_GATE", "e_sp_min": 0.0, "gm_e_sp_min": 0.0},) + tuple(
    {
        "gate_id": f"ESP{int(e_sp * 100):03d}_GM{int(gm * 100):03d}",
        "e_sp_min": e_sp,
        "gm_e_sp_min": gm,
    }
    for e_sp in (2.80, 2.90, 3.00)
    for gm in (2.90, 3.00, 3.05)
)
TOP_K = (1, 2, 4, 8, "ALL")

SCATTER_FIELDS = (
    "issue", "fold", "year", "issue_instance", "match_id", "match_idx", "kickoff_ts",
    "p3", "p1", "p0", "p_min", "p_max", "argmin_code", "e_sp",
    "predicted_sp3", "predicted_sp1", "predicted_sp0", "q3", "q1", "q0",
    "q_min", "q_min_code",
)
ISSUE_CENSUS_FIELDS = (
    "issue", "fold", "year", "issue_instance", "eligible_match_count", "first_kickoff_ts",
    "last_kickoff_ts", "source_segment_count", "issue_disposition", "fold_integrity",
    "selection_scope",
)
MATCH_VECTOR_FIELDS = SCATTER_FIELDS + (
    "handicap_bucket", "market_raw3", "market_raw1", "market_raw0",
    "market_cal3", "market_cal1", "market_cal0",
    "blend_a25_3", "blend_a25_1", "blend_a25_0",
    "blend_a50_3", "blend_a50_1", "blend_a50_0",
    "blend_a75_3", "blend_a75_1", "blend_a75_0",
    "q_weight3", "q_weight1", "q_weight0", "model_market_l1_distance",
)
GATE_CENSUS_FIELDS = ISSUE_CENSUS_FIELDS + (
    "gate_id", "e_sp_min", "gm_e_sp_min", "gate_eligible_match_count",
    "candidate_count_complete_issue", "candidate_search_count", "candidate_cap_applied",
    "portfolio_identity_count", "full_ticket_count", "full_stake_yuan", "disposition", "reason",
)
IDENTITY_FIELDS = ISSUE_CENSUS_FIELDS + (
    "gate_id", "e_sp_min", "gm_e_sp_min", "portfolio_id", "candidate_match_id",
    "candidate_rank_in_complete_issue", "candidate_count_complete_issue", "candidate_search_count",
    "candidate_cap_applied", "selected_match_ids", "selected_n", "gm_e_sp", "full_k",
    "full_stake_yuan", "p_min_delete_match_id", "p_min_delete_code", "q_min_delete_match_id",
    "q_min_delete_code", "descriptor_sha256", "participation_rank", "selection_scope", "segment_boundary",
)
ROLE_FIELDS = (
    "gate_id", "portfolio_id", "issue", "fold", "year", "issue_instance", "match_id",
    "match_idx", "kickoff_ts", "selection_rank", "is_candidate", "e_sp", "p_min",
    "predicted_sp3", "predicted_sp1", "predicted_sp0", "p_model3", "p_model1", "p_model0",
    "p_market_raw3", "p_market_raw1", "p_market_raw0", "p_market_cal3", "p_market_cal1",
    "p_market_cal0", "p_blend_a25_3", "p_blend_a25_1", "p_blend_a25_0", "p_blend_a50_3",
    "p_blend_a50_1", "p_blend_a50_0", "p_blend_a75_3", "p_blend_a75_1", "p_blend_a75_0",
    "q_weight3", "q_weight1", "q_weight0", "p_min_delete_match_id", "p_min_delete_code",
    "q_min_delete_match_id", "q_min_delete_code",
)
SAMPLER_PLAN_FIELDS = (
    "gate_id", "top_k_id", "requested_n7_count", "sampler_id", "probability_vector", "mechanism",
    "duplicate_policy", "M", "M_scope", "seed", "seed_role", "ticket_space_k", "stake_per_draw_yuan",
    "issue_total_draw_formula", "issue_total_stake_formula", "expected_unique_formula",
    "realized_unique_rule", "outcome_boundary", "primary_or_sensitivity",
)
PARTICIPATION_FIELDS = ISSUE_CENSUS_FIELDS + (
    "gate_id", "top_k_id", "requested_n7_count", "available_identity_count", "selected_identity_count",
    "selected_portfolio_ids", "full_ticket_count", "full_stake_yuan", "sample_M_scope",
    "issue_total_draw_formula", "issue_total_stake_formula", "disposition", "reason",
)
CALIBRATION_MAP_FIELDS = (
    "fold", "test_year", "train_years", "outcome_code", "handicap_bucket", "probability_bin",
    "cell_n", "cell_hits", "code_bin_n", "code_bin_hits", "code_n", "code_hits",
    "minimum_stratum_observations", "shrinkage_pseudocount", "fallback_order", "formula",
)
CALIBRATION_CENSUS_FIELDS = (
    "fold", "test_year", "train_years", "training_match_rows", "training_outcome_rows",
    "mapping_target_boundary", "test_outcomes_read", "market_rows_in_test_fold",
)
SOURCE_FIELDS = ("source", "role", "identity", "sha256", "rows", "join_status")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def compact_hash(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def fmt(value: float) -> str:
    if not math.isfinite(value):
        raise RuntimeError("non-finite numeric output")
    return format(value, ".12f")


def exact_bundle(path: Path, expected_manifest: str) -> dict[str, str]:
    manifest_path = path / "SHA256SUMS.json"
    if not manifest_path.is_file() or sha256(manifest_path) != expected_manifest:
        raise RuntimeError(f"unaccepted input manifest: {path}")
    declared = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = {
        item.name: sha256(item)
        for item in path.iterdir()
        if item.is_file() and item.name != manifest_path.name
    }
    if not isinstance(declared, dict) or actual != declared:
        raise RuntimeError(f"manifest coverage drift: {path}")
    return declared


def require_schema(reader: csv.DictReader, expected: tuple[str, ...], label: str) -> None:
    if tuple(reader.fieldnames or ()) != expected:
        raise RuntimeError(f"{label} schema drift")


def normalize(values: Iterable[float]) -> dict[str, float]:
    materialized = list(values)
    if len(materialized) != len(CODES) or any(value <= 0 or not math.isfinite(value) for value in materialized):
        raise RuntimeError("invalid probability vector")
    total = sum(materialized)
    return {code: value / total for code, value in zip(CODES, materialized)}


def devig(odds: Iterable[float]) -> dict[str, float]:
    values = list(odds)
    if len(values) != len(CODES) or any(value <= 0 or not math.isfinite(value) for value in values):
        raise RuntimeError("invalid market odds")
    return normalize(1.0 / value for value in values)


def probability_bin(value: float) -> int:
    if value < 0 or value > 1 or not math.isfinite(value):
        raise RuntimeError("market probability outside [0, 1]")
    return min(9, int(value * 10.0))


def handicap_bucket(value: object) -> str:
    if value is None:
        return "UNKNOWN"
    number = float(value)
    if number < 0:
        return "NEGATIVE"
    if number > 0:
        return "POSITIVE"
    return "ZERO"


def geometric(values: Iterable[float]) -> float:
    materialized = list(values)
    if len(materialized) != N or any(value <= 0 or not math.isfinite(value) for value in materialized):
        raise RuntimeError("invalid seven-leg expected-SP geometric mean")
    return math.exp(sum(math.log(value) for value in materialized) / N)


def stable_uniform(*parts: object) -> float:
    token = "|".join(str(part) for part in parts).encode("utf-8")
    value = int.from_bytes(hashlib.sha256(token).digest()[:8], "big")
    return (value + 0.5) / (2 ** 64)


def ticket_weights(leg_vectors: list[dict[str, float]]) -> list[tuple[tuple[str, ...], float]]:
    if len(leg_vectors) != N:
        raise RuntimeError("ticket product needs exactly seven legs")
    out: list[tuple[tuple[str, ...], float]] = [((), 1.0)]
    for vector in leg_vectors:
        if set(vector) != set(CODES) or abs(sum(vector.values()) - 1.0) > 1e-9:
            raise RuntimeError("ticket vector is not normalized")
        out = [(prior + (code,), mass * vector[code]) for prior, mass in out for code in CODES]
    if len(out) != FULL_K or abs(sum(mass for _, mass in out) - 1.0) > 1e-9:
        raise RuntimeError("ticket-space probability invariant failed")
    return out


def expected_unique_coverage(weights: Iterable[float], draws: int) -> float:
    if draws < 0:
        raise RuntimeError("negative sample count")
    return sum(1.0 - (1.0 - weight) ** draws for weight in weights)


def weighted_with_replacement(weights: list[tuple[tuple[str, ...], float]], draws: int, seed: int, key: str) -> list[tuple[str, ...]]:
    if not 0 <= draws <= FULL_K:
        raise RuntimeError("draw count outside frozen N7 space")
    cumulative: list[tuple[tuple[str, ...], float]] = []
    running = 0.0
    for ticket, weight in weights:
        running += weight
        cumulative.append((ticket, running))
    selected: list[tuple[str, ...]] = []
    for draw in range(draws):
        target = stable_uniform("bj137", "WR", seed, key, draw)
        for ticket, bound in cumulative:
            if target <= bound:
                selected.append(ticket)
                break
        else:
            selected.append(cumulative[-1][0])
    return selected


def weighted_without_replacement(weights: list[tuple[tuple[str, ...], float]], draws: int, seed: int, key: str) -> list[tuple[str, ...]]:
    if not 0 <= draws <= len(weights):
        raise RuntimeError("distinct draw count outside frozen N7 space")
    keyed = []
    for ordinal, (ticket, weight) in enumerate(weights):
        uniform = max(stable_uniform("bj137", "WOR", seed, key, ordinal), 1e-18)
        keyed.append((-math.log(uniform) / weight, ticket))
    return [ticket for _, ticket in sorted(keyed)[:draws]]


def top_mass(weights: list[tuple[tuple[str, ...], float]], count: int) -> list[tuple[str, ...]]:
    if not 0 <= count <= len(weights):
        raise RuntimeError("top-mass count outside frozen N7 space")
    return [ticket for ticket, _ in sorted(weights, key=lambda item: (-item[1], item[0]))[:count]]


def gzip_writer(path: Path, fields: tuple[str, ...]):
    raw = path.open("wb")
    zipped = gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0)
    text = io.TextIOWrapper(zipped, encoding="utf-8", newline="")
    writer = csv.DictWriter(text, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    return raw, zipped, text, writer


def close_gzip(handles) -> None:
    raw, zipped, text, _ = handles
    text.flush()
    text.detach()
    zipped.close()
    raw.close()


def write_csv(path: Path, fields: tuple[str, ...], rows: Iterable[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def load_selector_source(source: Path) -> tuple[dict[str, str], list[dict[str, object]], list[dict[str, str]]]:
    manifest = exact_bundle(source, BJ132_MANIFEST)
    card = json.loads((source / "gate_a_card.json").read_text(encoding="utf-8"))
    if card.get("stage") != "GATE_A_OUTCOME_UNEXPOSED_COMPLETE_ISSUE_MATCHED_FREEZE":
        raise RuntimeError("#132 source is not accepted outcome-unexposed complete-issue input")
    with (source / "candidate_scatter.csv").open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        require_schema(reader, SCATTER_FIELDS, "#132 candidate scatter")
        raw = list(reader)
    if len(raw) != 47819 or len({row["match_id"] for row in raw}) != len(raw):
        raise RuntimeError("#132 candidate-scatter denominator drift")
    with (source / "issue_census.csv").open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        require_schema(reader, ISSUE_CENSUS_FIELDS, "#132 issue census")
        census = list(reader)
    if len(census) != 348 or {row["selection_scope"] for row in census} != {"COMPLETE_ISSUE"}:
        raise RuntimeError("#132 complete-issue census drift")
    rows: list[dict[str, object]] = []
    for row in raw:
        probability = {code: float(row[f"p{code}"]) for code in CODES}
        sp = {code: float(row[f"predicted_sp{code}"]) for code in CODES}
        q = {code: float(row[f"q{code}"]) for code in CODES}
        if abs(sum(probability.values()) - 1.0) > 1e-8 or any(value <= 0 for value in (*probability.values(), *sp.values())):
            raise RuntimeError(f"invalid frozen probability input for {row['match_id']}")
        if any(abs(q[code] - probability[code] * sp[code]) > 2e-8 for code in CODES):
            raise RuntimeError(f"frozen q invariant failed for {row['match_id']}")
        rows.append({**row, "p_model": probability, "sp": sp, "q": q})
    return manifest, rows, census


def add_count(target: dict[object, list[int]], key: object, hit: int) -> None:
    pair = target.setdefault(key, [0, 0])
    pair[0] += 1
    pair[1] += hit


def load_market_and_training(source_db: Path, match_ids: list[str], evaluation_years: tuple[int, ...]):
    if not source_db.is_file():
        raise RuntimeError(f"missing source database: {source_db}")
    db_hash = sha256(source_db)
    conn = sqlite3.connect(f"file:{source_db}?mode=ro", uri=True)
    try:
        conn.execute("PRAGMA temp_store=MEMORY")
        conn.execute("PRAGMA cache_size=-65536")
        conn.execute("CREATE TEMP TABLE frozen_ids(match_id INTEGER PRIMARY KEY)")
        conn.executemany("INSERT INTO frozen_ids(match_id) VALUES (?)", ((int(value),) for value in match_ids))
        market: dict[str, dict[str, object]] = {}
        query = """
            SELECT m.match_id, m.issue, m.match_idx, m.kickoff_ts, m.handicap_line_norm,
                   c.v1_avg, c.v2_avg, c.v3_avg
            FROM frozen_ids AS f
            JOIN matches AS m ON m.match_id=f.match_id
            JOIN market_consensus AS c
              ON c.match_id=m.match_id AND c.market='euro_1x2' AND c.snapshot='10h'
            WHERE c.v1_avg>0 AND c.v2_avg>0 AND c.v3_avg>0
        """
        for match_id, issue, match_idx, kickoff_ts, line, o3, o1, o0 in conn.execute(query):
            market[str(match_id)] = {
                "issue": str(issue), "match_idx": str(match_idx), "kickoff_ts": str(kickoff_ts),
                "handicap_bucket": handicap_bucket(line),
                "p_market_raw": devig((float(o3), float(o1), float(o0))),
            }
        if len(market) != len(match_ids):
            raise RuntimeError(f"10h EURO coverage failed: {len(market)} of {len(match_ids)}")

        per_year: dict[int, dict[str, dict[object, list[int]]]] = defaultdict(lambda: defaultdict(dict))
        train_query = """
            SELECT CAST(substr(m.kickoff_ts, 1, 4) AS INTEGER) AS calendar_year,
                   m.handicap_line_norm, o.outcome_code, o.hit, c.v1_avg, c.v2_avg, c.v3_avg
            FROM matches AS m
            JOIN market_consensus AS c
              ON c.match_id=m.match_id AND c.market='euro_1x2' AND c.snapshot='10h'
            JOIN outcome_features AS o ON o.match_id=m.match_id
            WHERE CAST(substr(m.kickoff_ts, 1, 4) AS INTEGER)>=?
              AND CAST(substr(m.kickoff_ts, 1, 4) AS INTEGER)<?
              AND o.outcome_code IN ('3','1','0')
              AND o.hit IN (0,1)
              AND o.has_trusted_settlement=1
              AND c.v1_avg>0 AND c.v2_avg>0 AND c.v3_avg>0
        """
        for year, line, code, hit, o3, o1, o0 in conn.execute(train_query, (MARKET_START_YEAR, max(evaluation_years))):
            raw = devig((float(o3), float(o1), float(o0)))
            bucket = handicap_bucket(line)
            bin_index = probability_bin(raw[str(code)])
            stores = per_year[int(year)]
            add_count(stores["cell"], (str(code), bucket, bin_index), int(hit))
            add_count(stores["code_bin"], (str(code), bin_index), int(hit))
            add_count(stores["code"], str(code), int(hit))
            add_count(stores["all"], "all", int(hit))
    finally:
        conn.close()
    return db_hash, market, per_year


def aggregate_counts(per_year: dict[int, dict[str, dict[object, list[int]]]], test_year: int):
    merged: dict[str, dict[object, list[int]]] = defaultdict(dict)
    for year in range(MARKET_START_YEAR, test_year):
        for level, entries in per_year.get(year, {}).items():
            for key, pair in entries.items():
                target = merged[level].setdefault(key, [0, 0])
                target[0] += pair[0]
                target[1] += pair[1]
    return merged


def mapped_market_probability(raw: dict[str, float], bucket: str, counts: dict[str, dict[object, list[int]]]):
    out: dict[str, float] = {}
    diagnostics: dict[str, tuple[int, int, int, int, int, int]] = {}
    for code in CODES:
        bin_index = probability_bin(raw[code])
        cell = counts["cell"].get((code, bucket, bin_index), [0, 0])
        code_bin = counts["code_bin"].get((code, bin_index), [0, 0])
        code_total = counts["code"].get(code, [0, 0])
        if code_total[0] == 0:
            raise RuntimeError("market calibration has no strictly prior outcome support")
        base_rate = code_total[1] / code_total[0]
        if cell[0] >= MIN_STRATUM_OBSERVATIONS:
            selected = cell
        elif code_bin[0] >= MIN_STRATUM_OBSERVATIONS:
            selected = code_bin
        else:
            selected = code_total
        out[code] = (selected[1] + SHRINKAGE_PSEUDOCOUNT * base_rate) / (selected[0] + SHRINKAGE_PSEUDOCOUNT)
        diagnostics[code] = (*cell, *code_bin, *code_total)
    return normalize(out[code] for code in CODES), diagnostics


def enrich_vectors(rows: list[dict[str, object]], market: dict[str, dict[str, object]], per_year):
    by_year: dict[int, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        payload = market.get(str(row["match_id"]))
        if payload is None:
            raise RuntimeError(f"missing market input for {row['match_id']}")
        for field in ("issue", "match_idx", "kickoff_ts"):
            if str(row[field]) != str(payload[field]):
                raise RuntimeError(f"market identity mismatch for {row['match_id']}")
        row["handicap_bucket"] = payload["handicap_bucket"]
        row["p_market_raw"] = payload["p_market_raw"]
        by_year[int(str(row["year"]))].append(row)

    map_rows: list[dict[str, object]] = []
    census: list[dict[str, object]] = []
    for test_year, group in sorted(by_year.items()):
        counts = aggregate_counts(per_year, test_year)
        train_outcome_rows = sum(pair[0] for pair in counts["code"].values())
        train_match_rows = train_outcome_rows // len(CODES)
        if train_match_rows == 0:
            raise RuntimeError(f"no historical market calibration source for {test_year}")
        fold = f"OOS_{test_year}"
        census.append({
            "fold": fold, "test_year": test_year, "train_years": f"{MARKET_START_YEAR}-{test_year - 1}",
            "training_match_rows": train_match_rows, "training_outcome_rows": train_outcome_rows,
            "mapping_target_boundary": "strictly calendar-year prior rows only; aggregate hit counts only",
            "test_outcomes_read": "0", "market_rows_in_test_fold": len(group),
        })
        for bucket in ("NEGATIVE", "ZERO", "POSITIVE", "UNKNOWN"):
            for bin_index in range(10):
                for code in CODES:
                    cell = counts["cell"].get((code, bucket, bin_index), [0, 0])
                    code_bin = counts["code_bin"].get((code, bin_index), [0, 0])
                    code_total = counts["code"].get(code, [0, 0])
                    map_rows.append({
                        "fold": fold, "test_year": test_year, "train_years": f"{MARKET_START_YEAR}-{test_year - 1}",
                        "outcome_code": code, "handicap_bucket": bucket, "probability_bin": bin_index,
                        "cell_n": cell[0], "cell_hits": cell[1], "code_bin_n": code_bin[0],
                        "code_bin_hits": code_bin[1], "code_n": code_total[0], "code_hits": code_total[1],
                        "minimum_stratum_observations": MIN_STRATUM_OBSERVATIONS,
                        "shrinkage_pseudocount": fmt(SHRINKAGE_PSEUDOCOUNT),
                        "fallback_order": "code×handicap_bucket×probability_bin;code×probability_bin;code",
                        "formula": "normalize((hits + 50*(code_hits/code_n))/(n+50)) independently over 3/1/0",
                    })
        for row in group:
            p_market_cal, _ = mapped_market_probability(row["p_market_raw"], str(row["handicap_bucket"]), counts)
            row["p_market_cal"] = p_market_cal
            for alpha in BLEND_ALPHAS:
                row[f"blend_{alpha:.2f}"] = normalize(
                    alpha * row["p_model"][code] + (1.0 - alpha) * p_market_cal[code]
                    for code in CODES
                )
            row["q_weight"] = normalize(row["p_model"][code] * row["sp"][code] for code in CODES)
    return map_rows, census


def issue_key(row: dict[str, object]) -> tuple[str, str, str]:
    return str(row["issue"]), str(row["fold"]), str(row["year"])


def sort_key(row: dict[str, object]):
    return (-float(row["e_sp"]), float(row["p_min"]), int(str(row["match_idx"])), int(str(row["match_id"])))


def delete_code(selected: list[dict[str, object]], field: str) -> tuple[str, str]:
    candidates = []
    for row in selected:
        values = row[field]
        for index, code in enumerate(CODES):
            candidates.append((values[code], int(str(row["match_idx"])), index, str(row["match_id"]), code))
    _, _, _, match_id, code = min(candidates)
    return match_id, code


def top_k_id(value: int | str) -> str:
    return "K_ALL" if value == "ALL" else f"K{int(value)}"


def build_identities(by_issue: dict[tuple[str, str, str], list[dict[str, object]]], issue_census: dict[tuple[str, str, str], dict[str, str]], stage: Path):
    identity_handles = gzip_writer(stage / "n7_identities.csv.gz", IDENTITY_FIELDS)
    role_handles = gzip_writer(stage / "n7_role_vectors.csv.gz", ROLE_FIELDS)
    iw, rw = identity_handles[-1], role_handles[-1]
    census_rows: list[dict[str, object]] = []
    participation_rows: list[dict[str, object]] = []
    identities = roles = 0
    try:
        for gate in GATES:
            for key, source_rows in sorted(by_issue.items(), key=lambda item: (int(item[0][2]), int(item[0][0]))):
                issue, fold, year = key
                base = issue_census[key]
                eligible = [row for row in source_rows if float(row["e_sp"]) >= float(gate["e_sp_min"])]
                candidates = sorted(eligible, key=sort_key)
                search = candidates[:MAX_IDENTITIES_PER_ISSUE_GATE]
                cap_applied = len(candidates) > MAX_IDENTITIES_PER_ISSUE_GATE
                unique: dict[tuple[str, ...], tuple[dict[str, object], list[dict[str, object]], float, int]] = {}
                for candidate_rank, candidate in enumerate(search, 1):
                    companions = [row for row in candidates if row["match_id"] != candidate["match_id"]][:6]
                    selected = [candidate, *companions]
                    if len(selected) != N:
                        continue
                    selected = sorted(selected, key=sort_key)
                    gm = geometric(float(row["e_sp"]) for row in selected)
                    if gm < float(gate["gm_e_sp_min"]):
                        continue
                    match_ids = tuple(str(row["match_id"]) for row in selected)
                    prior = unique.get(match_ids)
                    if prior is None or candidate_rank < prior[3]:
                        unique[match_ids] = (candidate, selected, gm, candidate_rank)
                if not eligible:
                    reason = "NO_MATCH_PASSES_E_SP_GATE"
                elif len(eligible) < N:
                    reason = "INSUFFICIENT_GATED_COMPLETE_ISSUE_MATCHES"
                elif not unique:
                    reason = "NO_N7_IDENTITY_PASSES_GM_E_SP_GATE"
                else:
                    reason = "PORTFOLIOS_AVAILABLE"
                disposition = "AVAILABLE" if unique else "NO_BET"
                census_rows.append({
                    **base, "gate_id": gate["gate_id"], "e_sp_min": fmt(float(gate["e_sp_min"])),
                    "gm_e_sp_min": fmt(float(gate["gm_e_sp_min"])), "gate_eligible_match_count": len(eligible),
                    "candidate_count_complete_issue": len(candidates), "candidate_search_count": len(search),
                    "candidate_cap_applied": str(cap_applied).upper(), "portfolio_identity_count": len(unique),
                    "full_ticket_count": len(unique) * FULL_K, "full_stake_yuan": len(unique) * FULL_K * UNIT_STAKE,
                    "disposition": disposition, "reason": reason,
                })
                ranked = sorted(
                    unique.values(),
                    key=lambda entry: (
                        entry[3],
                        tuple(str(row["match_id"]) for row in entry[1]),
                    ),
                )
                frozen_portfolio_ids: list[str] = []
                for ordinal, entry in enumerate(ranked, 1):
                    candidate, selected, gm, candidate_rank = entry
                    portfolio_id = compact_hash({
                        "contract": CONTRACT, "gate": gate["gate_id"], "issue_instance": base["issue_instance"],
                        "match_ids": [str(row["match_id"]) for row in selected],
                    })
                    p_min_match, p_min_code = delete_code(selected, "p_model")
                    q_match, q_code = delete_code(selected, "q_weight")
                    descriptor = compact_hash({
                        "contract": CONTRACT, "generator_version": VERSION, "gate": gate,
                        "issue_instance": base["issue_instance"], "candidate_match_id": candidate["match_id"],
                        "ordered_match_ids": [str(row["match_id"]) for row in selected],
                        "vectors": [{
                            "model": row["p_model"], "market_cal": row["p_market_cal"],
                            "q_weight": row["q_weight"], "sp": row["sp"],
                        } for row in selected],
                    })
                    iw.writerow({
                        **base, "gate_id": gate["gate_id"], "e_sp_min": fmt(float(gate["e_sp_min"])),
                        "gm_e_sp_min": fmt(float(gate["gm_e_sp_min"])), "portfolio_id": portfolio_id,
                        "candidate_match_id": candidate["match_id"], "candidate_rank_in_complete_issue": candidate_rank,
                        "candidate_count_complete_issue": len(candidates), "candidate_search_count": len(search),
                        "candidate_cap_applied": str(cap_applied).upper(),
                        "selected_match_ids": "|".join(str(row["match_id"]) for row in selected), "selected_n": N,
                        "gm_e_sp": fmt(gm), "full_k": FULL_K, "full_stake_yuan": FULL_K * UNIT_STAKE,
                        "p_min_delete_match_id": p_min_match, "p_min_delete_code": p_min_code,
                        "q_min_delete_match_id": q_match, "q_min_delete_code": q_code,
                        "descriptor_sha256": descriptor, "participation_rank": ordinal,
                        "selection_scope": "COMPLETE_ISSUE",
                        "segment_boundary": "NONE; source segments are diagnostic-only",
                    })
                    frozen_portfolio_ids.append(portfolio_id)
                    for rank, row in enumerate(selected, 1):
                        rw.writerow({
                            "gate_id": gate["gate_id"], "portfolio_id": portfolio_id, "issue": row["issue"],
                            "fold": row["fold"], "year": row["year"], "issue_instance": row["issue_instance"],
                            "match_id": row["match_id"], "match_idx": row["match_idx"], "kickoff_ts": row["kickoff_ts"],
                            "selection_rank": rank, "is_candidate": int(row["match_id"] == candidate["match_id"]),
                            "e_sp": fmt(float(row["e_sp"])), "p_min": fmt(float(row["p_min"])),
                            **{f"predicted_sp{code}": fmt(row["sp"][code]) for code in CODES},
                            **{f"p_model{code}": fmt(row["p_model"][code]) for code in CODES},
                            **{f"p_market_raw{code}": fmt(row["p_market_raw"][code]) for code in CODES},
                            **{f"p_market_cal{code}": fmt(row["p_market_cal"][code]) for code in CODES},
                            **{f"p_blend_a25_{code}": fmt(row["blend_0.25"][code]) for code in CODES},
                            **{f"p_blend_a50_{code}": fmt(row["blend_0.50"][code]) for code in CODES},
                            **{f"p_blend_a75_{code}": fmt(row["blend_0.75"][code]) for code in CODES},
                            **{f"q_weight{code}": fmt(row["q_weight"][code]) for code in CODES},
                            "p_min_delete_match_id": p_min_match, "p_min_delete_code": p_min_code,
                            "q_min_delete_match_id": q_match, "q_min_delete_code": q_code,
                        })
                        roles += 1
                    identities += 1
                for requested in TOP_K:
                    if requested == "ALL":
                        selected_ids = frozen_portfolio_ids
                        top_reason = reason
                    elif len(frozen_portfolio_ids) >= int(requested):
                        selected_ids = frozen_portfolio_ids[:int(requested)]
                        top_reason = "PORTFOLIOS_AVAILABLE"
                    else:
                        selected_ids = []
                        top_reason = "INSUFFICIENT_N7_IDENTITIES_FOR_REQUESTED_K"
                    participation_rows.append({
                        **base, "gate_id": gate["gate_id"], "top_k_id": top_k_id(requested),
                        "requested_n7_count": requested, "available_identity_count": len(frozen_portfolio_ids),
                        "selected_identity_count": len(selected_ids),
                        "selected_portfolio_ids": "|".join(selected_ids),
                        "full_ticket_count": len(selected_ids) * FULL_K,
                        "full_stake_yuan": len(selected_ids) * FULL_K * UNIT_STAKE,
                        "sample_M_scope": "PER_N7_IDENTITY; issue total is selected_identity_count × M",
                        "issue_total_draw_formula": "selected_identity_count × M",
                        "issue_total_stake_formula": "selected_identity_count × M × ¥2",
                        "disposition": "AVAILABLE" if selected_ids else "NO_BET",
                        "reason": top_reason,
                    })
    finally:
        close_gzip(identity_handles)
        close_gzip(role_handles)
    return census_rows, participation_rows, identities, roles


def sampler_plan_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    base = {
        "ticket_space_k": FULL_K, "stake_per_draw_yuan": UNIT_STAKE,
        "expected_unique_formula": "sum_t[1-(1-w(t))^M] for independent draws; distinct mechanisms equal M/FULL_K",
        "outcome_boundary": "pre-outcome sampler only; Gate B must report realized unique ticket count and all settlement metrics",
    }
    def append(gate_id: str, requested_k: int | str, sampler_id: str, vector: str, mechanism: str, duplicate: str, m: int, seed: object, role: str, primary: str):
        rows.append({
            "gate_id": gate_id, "top_k_id": top_k_id(requested_k), "requested_n7_count": requested_k,
            "sampler_id": sampler_id, "probability_vector": vector, "mechanism": mechanism,
            "duplicate_policy": duplicate, "M": m, "M_scope": "PER_N7_IDENTITY", "seed": seed,
            "seed_role": role, "issue_total_draw_formula": "selected_identity_count × M",
            "issue_total_stake_formula": "selected_identity_count × M × ¥2", **base,
            "realized_unique_rule": "count distinct ticket identities; duplicate draws retain separate ¥2 stakes" if duplicate == "DUPLICATE_STAKES" else "all selected tickets are distinct",
            "primary_or_sensitivity": primary,
        })
    for gate in GATES:
        gate_id = str(gate["gate_id"])
        for requested_k in TOP_K:
            append(gate_id, requested_k, "FULL_N7_CONTROL", "UNIFORM_FULL", "ENUMERATE_FULL", "NOT_APPLICABLE", FULL_K, "NA", "CONTROL", "CONTROL")
            for m in M_GRID:
                append(gate_id, requested_k, "TOP_MODEL_P_CAL_DISTINCT", "MODEL_P_CAL", "DETERMINISTIC_TOP_MASS", "DEDUPLICATED", m, "NA", "DETERMINISTIC", "MATCHED_CONTROL")
                for seed in SENSITIVITY_SEEDS:
                    role = "PRIMARY" if seed == PRIMARY_SEED else "SENSITIVITY"
                    append(gate_id, requested_k, "MODEL_P_CAL_WR_DUPLICATE_STAKES", "MODEL_P_CAL", "INDEPENDENT_WITH_REPLACEMENT", "DUPLICATE_STAKES", m, seed, role, "PRIMARY" if role == "PRIMARY" else "SENSITIVITY")
                    append(gate_id, requested_k, "MODEL_P_CAL_WOR_DISTINCT", "MODEL_P_CAL", "WEIGHTED_WITHOUT_REPLACEMENT", "DEDUPLICATED", m, seed, role, "PRIMARY" if role == "PRIMARY" else "SENSITIVITY")
                    append(gate_id, requested_k, "MARKET_WF_CAL_WOR_DISTINCT", "MARKET_WF_CAL", "WEIGHTED_WITHOUT_REPLACEMENT", "DEDUPLICATED", m, seed, role, "COMPARATOR")
                    for alpha in BLEND_ALPHAS:
                        append(gate_id, requested_k, f"BLEND_A{int(alpha * 100):02d}_WOR_DISTINCT", f"BLEND_A{int(alpha * 100):02d}", "WEIGHTED_WITHOUT_REPLACEMENT", "DEDUPLICATED", m, seed, role, "COMPARATOR")
                    append(gate_id, requested_k, "Q_INFORMED_WOR_DISTINCT", "Q_WEIGHT", "WEIGHTED_WITHOUT_REPLACEMENT", "DEDUPLICATED", m, seed, role, "SECONDARY")
            append(gate_id, requested_k, "P_MIN_GLOBAL_DELETE_CONTROL", "MODEL_P_CAL", "ONE_GLOBAL_CODE_DELETE", "DEDUPLICATED", PRUNED_K, "NA", "CONTROL", "HARD_PRUNE_CONTROL")
            append(gate_id, requested_k, "Q_MIN_GLOBAL_DELETE_CONTROL", "Q_WEIGHT", "ONE_GLOBAL_CODE_DELETE", "DEDUPLICATED", PRUNED_K, "NA", "CONTROL", "HARD_PRUNE_CONTROL")
    return rows


def match_vector_row(row: dict[str, object]) -> dict[str, object]:
    return {
        **{field: row[field] for field in SCATTER_FIELDS}, "handicap_bucket": row["handicap_bucket"],
        **{f"market_raw{code}": fmt(row["p_market_raw"][code]) for code in CODES},
        **{f"market_cal{code}": fmt(row["p_market_cal"][code]) for code in CODES},
        **{f"blend_a25_{code}": fmt(row["blend_0.25"][code]) for code in CODES},
        **{f"blend_a50_{code}": fmt(row["blend_0.50"][code]) for code in CODES},
        **{f"blend_a75_{code}": fmt(row["blend_0.75"][code]) for code in CODES},
        **{f"q_weight{code}": fmt(row["q_weight"][code]) for code in CODES},
        "model_market_l1_distance": fmt(sum(abs(row["p_model"][code] - row["p_market_raw"][code]) for code in CODES)),
    }


def decompressed_digest(path: Path) -> tuple[str, int]:
    digest, size = hashlib.sha256(), 0
    with gzip.open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
            size += len(block)
    return digest.hexdigest(), size


def freeze(output: Path, source_132: Path = SOURCE_132, source_db: Path = SOURCE_DB) -> dict[str, object]:
    if output.exists():
        raise RuntimeError(f"refusing immutable overwrite: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".bj137_gate_a_", dir=output.parent))
    try:
        input_manifest, rows, issue_census_rows = load_selector_source(source_132)
        db_hash, market, training = load_market_and_training(source_db, [str(row["match_id"]) for row in rows], tuple(sorted({int(str(row["year"])) for row in rows})))
        calibration_map, calibration_census = enrich_vectors(rows, market, training)
        by_issue: dict[tuple[str, str, str], list[dict[str, object]]] = defaultdict(list)
        for row in rows:
            by_issue[issue_key(row)].append(row)
        census_by_issue = {(row["issue"], row["fold"], row["year"]): row for row in issue_census_rows}
        if set(by_issue) != set(census_by_issue):
            raise RuntimeError("complete-issue census identity mismatch")
        for key, group in by_issue.items():
            group.sort(key=lambda row: (str(row["kickoff_ts"]), int(str(row["match_idx"])), int(str(row["match_id"]))))
            if len(group) != int(census_by_issue[key]["eligible_match_count"]):
                raise RuntimeError(f"complete-issue match count drift: {key}")
        gate_census, participation, identities, roles = build_identities(by_issue, census_by_issue, stage)
        write_csv(stage / "match_vectors.csv", MATCH_VECTOR_FIELDS, [match_vector_row(row) for row in sorted(rows, key=lambda item: (int(str(item["year"])), int(str(item["issue"])), int(str(item["match_idx"])), int(str(item["match_id"]))))])
        write_csv(stage / "issue_census.csv", ISSUE_CENSUS_FIELDS, issue_census_rows)
        write_csv(stage / "gate_issue_census.csv", GATE_CENSUS_FIELDS, gate_census)
        write_csv(stage / "issue_participation_grid.csv", PARTICIPATION_FIELDS, participation)
        write_csv(stage / "sampler_plan.csv", SAMPLER_PLAN_FIELDS, sampler_plan_rows())
        write_csv(stage / "market_calibration_map.csv", CALIBRATION_MAP_FIELDS, calibration_map)
        write_csv(stage / "market_calibration_census.csv", CALIBRATION_CENSUS_FIELDS, calibration_census)
        write_csv(stage / "source_census.csv", SOURCE_FIELDS, [
            {"source": "bj132_gate_a_complete_issue_preoutcome_v1r1", "role": "accepted complete-issue selector, model p and predicted SP", "identity": "SHA256SUMS.json", "sha256": BJ132_MANIFEST, "rows": 47819, "join_status": "all 47,819 unique frozen match ids read; source segments remain diagnostic-only"},
            {"source": "beidan_xlsm.sqlite", "role": "10h EURO consensus and strictly-prior aggregate market calibration targets", "identity": str(source_db), "sha256": db_hash, "rows": 47819, "join_status": "47,819 of 47,819 exact match-id rows join to euro_1x2@10h; test outcomes are not read"},
        ])
        card = {
            "issue": 137,
            "contract": CONTRACT,
            "generator_version": VERSION,
            "stage": "GATE_A_OUTCOME_UNEXPOSED_COMPLETE_ISSUE_SAMPLING_FREEZE",
            "source": {
                "bj132_manifest_sha256": BJ132_MANIFEST,
                "bj132_candidate_scatter_sha256": input_manifest["candidate_scatter.csv"],
                "database_sha256": db_hash,
                "database_path": str(source_db),
            },
            "denominator": {"eligible_matches": len(rows), "issue_instances": len(by_issue), "gates": len(GATES), "top_k_arms": len(TOP_K), "portfolio_identities": identities, "role_rows": roles, "issue_participation_rows": len(participation)},
            "complete_issue_contract": {
                "primary_unit": "(issue, fold) complete lottery issue; no selection or performance partition follows source segments",
                "gate_application": "match-level E_SP floor is applied over every eligible match in the complete issue before seven-leg construction; identity GM_E_SP is then checked",
                "candidate_competition": "all gate-passing complete-issue matches rank by E_SP descending, p_min ascending, match_idx, match_id; deterministic top 32 candidates are searched",
                "large_issue_cap": MAX_IDENTITIES_PER_ISSUE_GATE,
                "n7_construction": "each candidate plus the six highest E_SP gate-passing companions from the same undivided issue; duplicate identities collapse deterministically",
                "no_bet": "each gate×issue with no valid identity is retained explicitly as NO_BET",
                "selection_axis": "each gate ranks deduplicated N7 identities by candidate rank and identity key, then freezes K=1,2,4,8 and ALL participation rows; a fixed K has explicit NO_BET if insufficient identities rather than borrowing from a segment",
            },
            "gates": GATES,
            "sampler_contract": {
                "ticket_space": FULL_K,
                "M_grid": M_GRID,
                "M_scope": "M is a per-selected-N7 ticket count. For every issue×gate×K arm, issue total draws=selected_identity_count×M and issue total stake=selected_identity_count×M×¥2; the participation grid freezes selected identity lists and FULL baselines before outcome access.",
                "top_K_grid": TOP_K,
                "seeds": {"primary": PRIMARY_SEED, "bounded_sensitivity": SENSITIVITY_SEEDS},
                "model_p_cal": "accepted #132 calibrated model probability p3/p1/p0",
                "market_p_cal": "10h EURO reciprocal-odds overround-normalized, mapped with strictly-prior calendar-year hit-rate bins and outcome-code×handicap×probability strata where n>=100",
                "blend": {str(alpha): f"{alpha}*model_p_cal + {1-alpha}*market_p_cal; renormalized" for alpha in BLEND_ALPHAS},
                "q_secondary": "normalize(model_p_cal * predicted_SP) per match; optional #132-derived secondary only",
                "with_replacement": "independent deterministic hash draws; repeated tickets retain distinct ¥2 stakes; Gate B reports draw count and distinct-ticket count separately",
                "without_replacement": "deterministic exponential-key probability-proportional distinct sampling",
                "expected_unique": "for each identity and M under replacement, sum_t(1-(1-w(t))^M); Gate B must compare this analytic result to realized distinct count",
                "controls": ["FULL_N7_CONTROL", "TOP_MODEL_P_CAL_DISTINCT", "P_MIN_GLOBAL_DELETE_CONTROL", "Q_MIN_GLOBAL_DELETE_CONTROL"],
            },
            "market_calibration": {
                "warmup_year": MARKET_START_YEAR,
                "chronology": "for test year y, only outcomes with calendar year y'<y contribute; test-row outcome access is zero",
                "strata": ["outcome code", "handicap sign bucket", "10h market-probability decile"],
                "fallback": "code×handicap×bin, then code×bin, then code global; each receives fixed 50-observation shrinkage to code global hit rate before three-way renormalization",
                "settlement_boundary": "only aggregate historical hit counts are emitted; no match-level result_code, final SP, payout, ROI, or tax source is read into the package",
            },
            "gate_b_requirements": {
                "authorization": "NOT_RUN_AND_NOT_AUTHORIZED_PENDING_PI_ACCEPTANCE",
                "settlement_unit": "complete issue; aggregate duplicate stakes, overlap, gross return and actual tax at issue level",
                "metrics": ["taxfree and actual-tax ROI", "selector lift versus the same-gate K_ALL FULL baseline", "sampler-minus-the-exact-same-selected-FULL baseline and sampler-minus-hard-control deltas", "gate×K×M interaction surface without hiding either main effect", "stake/draw/unique/gross retention with issue-total reconciliation", "expected versus realized unique coverage", "hit/coverage, payout concentration, drawdown, miss streak, largest-event sensitivity", "issue/year/fold/LOYO and full ROI-versus-M curves"],
                "sweet_spot": "fixed before outcomes: relevant matched delta must persist across all three seeds and chronological fold/LOYO views; a single seed-local maximum cannot nominate policy; taxfree and taxpaid conclusions are separate. Selection-only improvement is reported even if sampler lift is absent.",
            },
            "outcome_boundary": "No test outcome, score, final SP, winning SP, settlement, payout, ROI, tax realization, or post-kickoff market is read or emitted. Historical aggregate targets are used only for the expressly-required strictly-prior market calibration transform.",
            "scope": "historical paper research only; no purchase, production, or promotion authority.",
        }
        (stage / "gate_a_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        shutil.copyfile(__file__, stage / "freeze_runner.py")
        (stage / "README.md").write_text(
            "# #137 Gate A: complete-issue probability sampling freeze\n\n"
            "This immutable package freezes complete-issue K=1/2/4/8/ALL participation, pre-outcome selector, market-calibration, identity, and sampler inputs. "
            "Gate B is not authorized. Replay with `python3 freeze_runner.py --output <new-dir>`; temporary staging is created beside the output, never in `/tmp`.\n",
            encoding="utf-8",
        )
        gzip_names = ("n7_identities.csv.gz", "n7_role_vectors.csv.gz")
        content = {
            "contract_version": CONTENT_VERSION,
            "gzip_payloads": {
                name: {"canonical_decompressed_sha256": decompressed_digest(stage / name)[0], "canonical_decompressed_bytes": decompressed_digest(stage / name)[1]}
                for name in gzip_names
            },
            "non_compressed_controls": {item.name: sha256(item) for item in sorted(stage.iterdir()) if item.is_file() and item.name not in gzip_names},
        }
        (stage / "CONTENT_IDENTITY.json").write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest = {item.name: sha256(item) for item in sorted(stage.iterdir()) if item.is_file()}
        (stage / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(stage, output)
        return {"output": str(output), "manifest_sha256": sha256(output / "SHA256SUMS.json"), "eligible_matches": len(rows), "issue_instances": len(by_issue), "gates": len(GATES), "portfolio_identities": identities, "role_rows": roles}
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--source-132", type=Path, default=SOURCE_132)
    parser.add_argument("--source-db", type=Path, default=SOURCE_DB)
    args = parser.parse_args()
    print(json.dumps(freeze(args.output.resolve(), args.source_132.resolve(), args.source_db.resolve()), sort_keys=True))


if __name__ == "__main__":
    main()
