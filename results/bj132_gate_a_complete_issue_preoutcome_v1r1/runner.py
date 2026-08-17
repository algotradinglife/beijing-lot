#!/usr/bin/env python3
"""Freeze #132's primary, complete-issue p-min/q-min deletion comparison.

This replaces the legacy #127-segment-compatible comparator.  It reads only
accepted outcome-unexposed probability and predicted-SP bundles, aggregates
every eligible match in an issue instance, and freezes matched FULL, p-min
delete, and q-min delete arms.  It deliberately cannot settle an outcome.
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
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

CODES = ("3", "1", "0")
CONTRACT = "BJ-HIST-DELETE-SCORE-N7-001"
VERSION = "bj132-complete-issue-gatea-v1"
CONTENT_VERSION = "bj132-complete-issue-content-v1"
BJ101_MANIFEST = "86e37682a95fad2a2a67187f1ee528f665d371583c621dc9d14af58f74302447"
BJ90_MANIFEST = "4a1107ca64d169bf0171a394d1e450a14ee5386005fce34f6ca7ebb70bd720b2"
FULL_K, DELETE_K, UNIT_STAKE, N = 3 ** 7, 2 * 3 ** 6, 2, 7
# This is a deterministic search cap, not a budget or eligibility gate.  Every
# eligible match competes for these globally lowest-p candidates within its
# complete issue instance before the cap is applied.
MAX_CANDIDATES_PER_ISSUE_VARIANT = 32
REGIMES = ((2.80, 2.90), (2.90, 3.00), (3.00, 3.05))
LOW_P = (0.20, 0.25, 0.30)
VARIANTS = {
    f"ESP{int(e * 100):03d}_GM{int(g * 100):03d}_LOWP{int(p * 100):02d}":
    {"e_sp_min": e, "gm_e_sp_min": g, "p_min_max": p}
    for e, g in REGIMES for p in LOW_P
}

MEMBERSHIP_FIELDS = (
    "issue", "fold", "year", "pool_id", "segment_index", "pool_disposition",
    "match_id", "match_idx", "kickoff_ts", "p3", "p1", "p0", "deleted_code",
    "p_min", "p_min_rank", "p_min_bucket", "eligible_t05", "eligible_t10",
    "eligible_t15", "eligible_t20",
)
SP_FIELDS = (
    "match_id", "issue", "match_idx", "year", "fold", "deployed_method",
    "deployed_sp_3", "deployed_sp_1", "deployed_sp_0", "m2_conservative_sp_3",
    "m2_conservative_sp_1", "m2_conservative_sp_0",
)
ISSUE_CENSUS_FIELDS = (
    "issue", "fold", "year", "issue_instance", "eligible_match_count",
    "first_kickoff_ts", "last_kickoff_ts", "source_segment_count",
    "issue_disposition", "fold_integrity", "selection_scope",
)
SCATTER_FIELDS = ISSUE_CENSUS_FIELDS[:4] + (
    "match_id", "match_idx", "kickoff_ts", "p3", "p1", "p0", "p_min", "p_max",
    "argmin_code", "e_sp", "predicted_sp3", "predicted_sp1", "predicted_sp0",
    "q3", "q1", "q0", "q_min", "q_min_code",
)
FRONTIER_FIELDS = ISSUE_CENSUS_FIELDS + (
    "variant_id", "arm", "portfolio_id", "candidate_match_id", "candidate_p_min",
    "candidate_rank_in_complete_issue", "candidate_count_complete_issue",
    "candidate_search_count", "candidate_cap_applied", "selected_match_ids", "selected_n",
    "gm_e_sp", "p_min_deleted_match_id", "p_min_deleted_code", "p_min_deleted_probability",
    "p_min_predicted_sp", "p_min_q", "q_min_deleted_match_id", "q_min_deleted_code",
    "q_min_deleted_probability", "q_min_predicted_sp", "q_min_q", "rankers_disagree",
    "formula_k", "stake_yuan", "matched_full_k", "matched_full_stake_yuan",
    "stake_reduction_fraction", "participation_policy", "tax_bucket_key", "disposition",
    "reason", "descriptor_sha256",
)
ROLE_FIELDS = (
    "variant_id", "portfolio_id", "issue", "fold", "year", "issue_instance",
    "match_id", "match_idx", "selection_rank", "e_sp", "p_min", "p3", "p1", "p0",
    "predicted_sp3", "predicted_sp1", "predicted_sp0", "q3", "q1", "q0",
    "is_candidate", "p_min_deleted_match_id", "p_min_deleted_code",
    "q_min_deleted_match_id", "q_min_deleted_code",
)
DISAGREEMENT_FIELDS = (
    "variant_id", "portfolio_id", "issue", "fold", "year", "issue_instance",
    "candidate_match_id", "candidate_rank_in_complete_issue", "p_min_deleted_match_id",
    "p_min_deleted_match_idx", "p_min_deleted_code", "p_min_probability", "p_min_predicted_sp",
    "p_min_q", "q_min_deleted_match_id", "q_min_deleted_match_idx", "q_min_deleted_code",
    "q_min_probability", "q_min_predicted_sp", "q_min_q",
)
SUMMARY_FIELDS = (
    "variant_id", "issue_instances", "explicit_no_bet_rows", "available_issue_instances",
    "complete_issue_candidates", "search_candidates", "cap_applied_issue_instances",
    "portfolio_identities", "matched_full_rows", "p_min_delete_rows", "q_min_delete_rows",
    "ranker_disagreements", "full_stake_yuan", "p_min_stake_yuan", "q_min_stake_yuan",
)
ISSUE_ACCOUNTING_FIELDS = (
    "variant_id", "arm", "issue", "fold", "year", "issue_instance", "portfolio_count",
    "unique_selected_matches", "portfolio_stake_yuan", "total_stake_yuan",
    "formula_tickets", "tax_bucket_key", "overlap_semantics", "loyo_unit",
)
SOURCE_FIELDS = ("source", "role", "manifest_sha256", "payload", "payload_sha256", "rows", "join_status")


def root(anchor: Path) -> Path:
    for candidate in (anchor.resolve().parent, *anchor.resolve().parents):
        if (candidate / ".git").exists():
            return candidate
    raise RuntimeError("repository root unavailable")


ROOT = root(Path(__file__))
BJ101 = ROOT / "results" / "bj101_gate_a_preoutcome_v1r1"
BJ90 = ROOT / "results" / "bj90_downstream_safe_projection_v1r1"
OUTPUT = ROOT / "results" / "bj132_gate_a_complete_issue_preoutcome_v1r1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def identity(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def fmt(value: float) -> str:
    if not math.isfinite(value):
        raise RuntimeError("non-finite value")
    return format(value, ".12f")


def exact_bundle(path: Path, expected_manifest: str) -> dict[str, str]:
    manifest_path = path / "SHA256SUMS.json"
    if sha256(manifest_path) != expected_manifest:
        raise RuntimeError(f"unaccepted input manifest: {path}")
    declared = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = {item.name: sha256(item) for item in path.iterdir()
              if item.is_file() and item.name != manifest_path.name}
    if not isinstance(declared, dict) or actual != declared:
        raise RuntimeError(f"manifest coverage drift: {path}")
    return declared


def schema(reader: csv.DictReader, expected: tuple[str, ...], label: str) -> None:
    if tuple(reader.fieldnames or ()) != expected:
        raise RuntimeError(f"{label} schema drift")


def geometric(values: list[float]) -> float:
    if len(values) != N or any(not math.isfinite(value) or value <= 0 for value in values):
        raise RuntimeError("invalid seven-leg geometric mean")
    return math.exp(sum(math.log(value) for value in values) / N)


def gzip_writer(path: Path, fields: tuple[str, ...]):
    raw = path.open("wb")
    zipped = gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0)
    text = io.TextIOWrapper(zipped, encoding="utf-8", newline="")
    writer = csv.DictWriter(text, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    return raw, zipped, text, writer


def close_gzip(handles) -> None:
    raw, zipped, text, _ = handles
    text.flush(); text.detach(); zipped.close(); raw.close()


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader(); writer.writerows(rows)


def issue_key(row: dict[str, str]) -> tuple[str, str, str]:
    return row["issue"], row["fold"], row["year"]


def complete_instance(row: dict[str, object]) -> str:
    return f"{row['issue']}@{row['fold']}"


def load_sources() -> tuple[dict[str, str], dict[tuple[str, str, str], list[dict[str, object]]]]:
    m101, m90 = exact_bundle(BJ101, BJ101_MANIFEST), exact_bundle(BJ90, BJ90_MANIFEST)
    with (BJ101 / "issue_pool_membership.csv").open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle); schema(reader, MEMBERSHIP_FIELDS, "#101 membership")
        members = list(reader)
    if len(members) != 47819 or len({row["match_id"] for row in members}) != len(members):
        raise RuntimeError("#101 full-match denominator drift")
    predictions: dict[tuple[str, str, str, str, str], dict[str, str]] = {}
    with gzip.open(BJ90 / "oos_prediction_vectors.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle); schema(reader, SP_FIELDS, "#90 predicted SP")
        for row in reader:
            key = (row["match_id"], row["issue"], row["match_idx"], row["year"], row["fold"])
            if key in predictions:
                raise RuntimeError("duplicate #90 prediction identity")
            predictions[key] = row
    by_issue: dict[tuple[str, str, str], list[dict[str, object]]] = defaultdict(list)
    for member in members:
        key = (member["match_id"], member["issue"], member["match_idx"], member["year"], member["fold"])
        predicted = predictions.get(key)
        if predicted is None:
            raise RuntimeError(f"missing #90 prediction for match {member['match_id']}")
        p = {code: float(member[f"p{code}"]) for code in CODES}
        sp = {code: float(predicted[f"deployed_sp_{code}"]) for code in CODES}
        if any(value <= 0 or not math.isfinite(value) for value in (*p.values(), *sp.values())) or abs(sum(p.values()) - 1) > 1e-6:
            raise RuntimeError(f"invalid pre-outcome vector for match {member['match_id']}")
        p_code = min(CODES, key=lambda code: (p[code], CODES.index(code)))
        q = {code: p[code] * sp[code] for code in CODES}
        q_code = min(CODES, key=lambda code: (q[code], int(member["match_idx"]), CODES.index(code)))
        feature = {**member, "p": p, "sp": sp, "q": q, "p_min": p[p_code], "p_max": max(p.values()),
                   "argmin_code": p_code, "e_sp": sum(q.values()), "q_min": q[q_code], "q_min_code": q_code}
        by_issue[issue_key(member)].append(feature)
    for key, rows in by_issue.items():
        folds = {str(row["fold"]) for row in rows}; years = {str(row["year"]) for row in rows}
        if folds != {key[1]} or years != {key[2]}:
            raise RuntimeError("issue instance crosses fold or year")
        rows.sort(key=lambda row: (str(row["kickoff_ts"]), int(str(row["match_idx"])), int(str(row["match_id"]))))
    provenance = {
        "bj101_manifest_sha256": BJ101_MANIFEST,
        "bj101_membership_sha256": m101["issue_pool_membership.csv"],
        "bj90_manifest_sha256": BJ90_MANIFEST,
        "bj90_prediction_sha256": m90["oos_prediction_vectors.csv.gz"],
    }
    return provenance, by_issue


def rank_candidates(rows: list[dict[str, object]], p_limit: float) -> tuple[list[dict[str, object]], int, bool]:
    candidates = [row for row in rows if float(row["p_min"]) <= p_limit]
    candidates.sort(key=lambda row: (float(row["p_min"]), int(str(row["match_idx"])), int(str(row["match_id"]))))
    return candidates[:MAX_CANDIDATES_PER_ISSUE_VARIANT], len(candidates), len(candidates) > MAX_CANDIDATES_PER_ISSUE_VARIANT


def assemble(candidate: dict[str, object], all_rows: list[dict[str, object]], e_sp_min: float, gm_min: float) -> tuple[list[dict[str, object]], float] | None:
    companions = sorted((row for row in all_rows if row["match_id"] != candidate["match_id"] and float(row["e_sp"]) >= e_sp_min),
                        key=lambda row: (-float(row["e_sp"]), float(row["p_min"]), int(str(row["match_idx"])), int(str(row["match_id"]))))[:6]
    selected = [candidate, *companions]
    if len(selected) != N:
        return None
    selected.sort(key=lambda row: (-float(row["e_sp"]), float(row["p_min"]), int(str(row["match_idx"])), int(str(row["match_id"]))))
    gm = geometric([float(row["e_sp"]) for row in selected])
    return (selected, gm) if gm >= gm_min else None


def minimum(selected: list[dict[str, object]], score: str) -> tuple[dict[str, object], str, float, float, float]:
    values: list[tuple[float, int, int, dict[str, object], str]] = []
    for row in selected:
        for index, code in enumerate(CODES):
            values.append((float(row[score][code]), int(str(row["match_idx"])), index, row, code))
    _, _, _, match, code = min(values)
    return match, code, float(match["p"][code]), float(match["sp"][code]), float(match["q"][code])


def role_row(row: dict[str, object], variant: str, portfolio_id: str, rank: int, candidate_id: str,
             p_delete: tuple[dict[str, object], str, float, float, float], q_delete: tuple[dict[str, object], str, float, float, float]) -> dict[str, object]:
    p, sp, q = row["p"], row["sp"], row["q"]
    return {"variant_id": variant, "portfolio_id": portfolio_id, "issue": row["issue"], "fold": row["fold"], "year": row["year"], "issue_instance": complete_instance(row), "match_id": row["match_id"], "match_idx": row["match_idx"], "selection_rank": rank, "e_sp": fmt(float(row["e_sp"])), "p_min": fmt(float(row["p_min"])), "p3": fmt(float(p["3"])), "p1": fmt(float(p["1"])), "p0": fmt(float(p["0"])), "predicted_sp3": fmt(float(sp["3"])), "predicted_sp1": fmt(float(sp["1"])), "predicted_sp0": fmt(float(sp["0"])), "q3": fmt(float(q["3"])), "q1": fmt(float(q["1"])), "q0": fmt(float(q["0"])), "is_candidate": int(row["match_id"] == candidate_id), "p_min_deleted_match_id": p_delete[0]["match_id"], "p_min_deleted_code": p_delete[1], "q_min_deleted_match_id": q_delete[0]["match_id"], "q_min_deleted_code": q_delete[1]}


def freeze(output: Path, bj101: Path = BJ101, bj90: Path = BJ90) -> dict[str, object]:
    global BJ101, BJ90
    if output.exists():
        raise RuntimeError(f"refusing immutable overwrite: {output}")
    original101, original90 = BJ101, BJ90
    BJ101, BJ90 = bj101, bj90
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".bj132_issue_gatea_", dir=output.parent))
    try:
        provenance, by_issue = load_sources()
        frontier_h = gzip_writer(stage / "matched_delete_score_frontier.csv.gz", FRONTIER_FIELDS)
        role_h = gzip_writer(stage / "portfolio_role_assignments.csv.gz", ROLE_FIELDS)
        disagreement_h = gzip_writer(stage / "ranker_disagreements.csv.gz", DISAGREEMENT_FIELDS)
        fw, rw, dw = frontier_h[-1], role_h[-1], disagreement_h[-1]
        census: list[dict[str, object]] = []
        scatter: list[dict[str, object]] = []
        summary: dict[str, Counter[str]] = defaultdict(Counter)
        accounting: dict[tuple[str, str, str], dict[str, object]] = {}
        frontier_count = role_count = disagreement_count = portfolio_count = 0
        for issue_tuple, rows in sorted(by_issue.items(), key=lambda item: (int(item[0][2]), int(item[0][0]))):
            issue, fold, year = issue_tuple
            instance = f"{issue}@{fold}"
            segments = {str(row["pool_id"]) for row in rows}
            disposition = "AVAILABLE_COMPLETE_ISSUE" if len(rows) >= N else "NO_BET_INSUFFICIENT_COMPLETE_ISSUE_MATCHES"
            base = {"issue": issue, "fold": fold, "year": year, "issue_instance": instance, "eligible_match_count": len(rows), "first_kickoff_ts": rows[0]["kickoff_ts"], "last_kickoff_ts": rows[-1]["kickoff_ts"], "source_segment_count": len(segments), "issue_disposition": disposition, "fold_integrity": "INTACT", "selection_scope": "COMPLETE_ISSUE"}
            census.append(base)
            for row in rows:
                p, sp, q = row["p"], row["sp"], row["q"]
                scatter.append({**{key: base[key] for key in ISSUE_CENSUS_FIELDS[:4]}, "match_id": row["match_id"], "match_idx": row["match_idx"], "kickoff_ts": row["kickoff_ts"], "p3": fmt(float(p["3"])), "p1": fmt(float(p["1"])), "p0": fmt(float(p["0"])), "p_min": fmt(float(row["p_min"])), "p_max": fmt(float(row["p_max"])), "argmin_code": row["argmin_code"], "e_sp": fmt(float(row["e_sp"])), "predicted_sp3": fmt(float(sp["3"])), "predicted_sp1": fmt(float(sp["1"])), "predicted_sp0": fmt(float(sp["0"])), "q3": fmt(float(q["3"])), "q1": fmt(float(q["1"])), "q0": fmt(float(q["0"])), "q_min": fmt(float(row["q_min"])), "q_min_code": row["q_min_code"]})
            for variant, rule in VARIANTS.items():
                counter = summary[variant]; counter["issue_instances"] += 1
                search, complete_count, capped = rank_candidates(rows, float(rule["p_min_max"])) if len(rows) >= N else ([], 0, False)
                counter["complete_issue_candidates"] += complete_count; counter["search_candidates"] += len(search); counter["cap_applied_issue_instances"] += int(capped)
                if len(rows) < N:
                    reason = "INSUFFICIENT_COMPLETE_ISSUE_MATCHES"
                elif not complete_count:
                    reason = "NO_COMPLETE_ISSUE_CANDIDATE"
                else:
                    reason = "PORTFOLIOS_AVAILABLE"
                fw.writerow({**base, "variant_id": variant, "arm": "NO_BET_CONTROL", "portfolio_id": "", "candidate_match_id": "", "candidate_p_min": "", "candidate_rank_in_complete_issue": "", "candidate_count_complete_issue": complete_count, "candidate_search_count": len(search), "candidate_cap_applied": str(capped).upper(), "selected_match_ids": "", "selected_n": 0, "gm_e_sp": "", "p_min_deleted_match_id": "", "p_min_deleted_code": "", "p_min_deleted_probability": "", "p_min_predicted_sp": "", "p_min_q": "", "q_min_deleted_match_id": "", "q_min_deleted_code": "", "q_min_deleted_probability": "", "q_min_predicted_sp": "", "q_min_q": "", "rankers_disagree": "", "formula_k": 0, "stake_yuan": 0, "matched_full_k": FULL_K, "matched_full_stake_yuan": FULL_K * UNIT_STAKE, "stake_reduction_fraction": fmt(1 / 3), "participation_policy": "ALL_FROZEN_PORTFOLIOS_RETAINED", "tax_bucket_key": f"{instance}|{variant}|NO_BET_CONTROL", "disposition": "NO_BET", "reason": reason, "descriptor_sha256": identity({"contract": CONTRACT, "variant": variant, "issue_instance": instance, "arm": "NO_BET_CONTROL", "reason": reason})})
                frontier_count += 1; counter["explicit_no_bet_rows"] += 1
                if not search:
                    continue
                unique: dict[str, tuple[dict[str, object], list[dict[str, object]], float, int]] = {}
                for candidate_rank, candidate in enumerate(search, 1):
                    built = assemble(candidate, rows, float(rule["e_sp_min"]), float(rule["gm_e_sp_min"]))
                    if built is None:
                        continue
                    selected, gm = built
                    signature = identity({"variant": variant, "issue_instance": instance, "candidate": candidate["match_id"], "selected": [row["match_id"] for row in selected]})
                    unique[signature] = candidate, selected, gm, candidate_rank
                if unique: counter["available_issue_instances"] += 1
                for portfolio_id, (candidate, selected, gm, candidate_rank) in sorted(unique.items()):
                    p_delete = minimum(selected, "p")
                    q_delete = minimum(selected, "q")
                    disagree = int((p_delete[0]["match_id"], p_delete[1]) != (q_delete[0]["match_id"], q_delete[1]))
                    selected_ids = ";".join(str(row["match_id"]) for row in selected)
                    shared = {**base, "variant_id": variant, "portfolio_id": portfolio_id, "candidate_match_id": candidate["match_id"], "candidate_p_min": fmt(float(candidate["p_min"])), "candidate_rank_in_complete_issue": candidate_rank, "candidate_count_complete_issue": complete_count, "candidate_search_count": len(search), "candidate_cap_applied": str(capped).upper(), "selected_match_ids": selected_ids, "selected_n": N, "gm_e_sp": fmt(gm), "p_min_deleted_match_id": p_delete[0]["match_id"], "p_min_deleted_code": p_delete[1], "p_min_deleted_probability": fmt(p_delete[2]), "p_min_predicted_sp": fmt(p_delete[3]), "p_min_q": fmt(p_delete[4]), "q_min_deleted_match_id": q_delete[0]["match_id"], "q_min_deleted_code": q_delete[1], "q_min_deleted_probability": fmt(q_delete[2]), "q_min_predicted_sp": fmt(q_delete[3]), "q_min_q": fmt(q_delete[4]), "rankers_disagree": disagree, "matched_full_k": FULL_K, "matched_full_stake_yuan": FULL_K * UNIT_STAKE, "stake_reduction_fraction": fmt(1 / 3), "participation_policy": "ALL_FROZEN_PORTFOLIOS_RETAINED", "disposition": "AVAILABLE", "reason": "MATCHED_COMPLETE_ISSUE_PAIR"}
                    for arm, k in (("MATCHED_FULL_N7", FULL_K), ("P_MIN_DELETE_N7", DELETE_K), ("Q_MIN_DELETE_N7", DELETE_K)):
                        tax_key = f"{instance}|{variant}|{arm}"
                        fw.writerow({**shared, "arm": arm, "formula_k": k, "stake_yuan": k * UNIT_STAKE, "tax_bucket_key": tax_key, "descriptor_sha256": identity({"contract": CONTRACT, "variant": variant, "issue_instance": instance, "portfolio": portfolio_id, "arm": arm, "matches": selected_ids, "p_delete": (p_delete[0]["match_id"], p_delete[1]), "q_delete": (q_delete[0]["match_id"], q_delete[1])})})
                        counter[{"MATCHED_FULL_N7": "matched_full_rows", "P_MIN_DELETE_N7": "p_min_delete_rows", "Q_MIN_DELETE_N7": "q_min_delete_rows"}[arm]] += 1
                        counter[{"MATCHED_FULL_N7": "full_stake_yuan", "P_MIN_DELETE_N7": "p_min_stake_yuan", "Q_MIN_DELETE_N7": "q_min_stake_yuan"}[arm]] += k * UNIT_STAKE
                        entry = accounting.setdefault((variant, arm, instance), {"variant_id": variant, "arm": arm, "issue": issue, "fold": fold, "year": year, "issue_instance": instance, "portfolio_count": 0, "matches": set(), "portfolio_stake_yuan": k * UNIT_STAKE, "total_stake_yuan": 0, "formula_tickets": k, "tax_bucket_key": tax_key, "overlap_semantics": "all retained portfolios share one complete-issue policy bucket; no overlap rejection", "loyo_unit": "entire issue instance held intact within its year/fold"})
                        entry["portfolio_count"] += 1; entry["total_stake_yuan"] += k * UNIT_STAKE; entry["matches"].update(str(row["match_id"]) for row in selected)
                        frontier_count += 1
                    for rank, row in enumerate(selected, 1):
                        rw.writerow(role_row(row, variant, portfolio_id, rank, str(candidate["match_id"]), p_delete, q_delete)); role_count += 1
                    if disagree:
                        dw.writerow({"variant_id": variant, "portfolio_id": portfolio_id, "issue": issue, "fold": fold, "year": year, "issue_instance": instance, "candidate_match_id": candidate["match_id"], "candidate_rank_in_complete_issue": candidate_rank, "p_min_deleted_match_id": p_delete[0]["match_id"], "p_min_deleted_match_idx": p_delete[0]["match_idx"], "p_min_deleted_code": p_delete[1], "p_min_probability": fmt(p_delete[2]), "p_min_predicted_sp": fmt(p_delete[3]), "p_min_q": fmt(p_delete[4]), "q_min_deleted_match_id": q_delete[0]["match_id"], "q_min_deleted_match_idx": q_delete[0]["match_idx"], "q_min_deleted_code": q_delete[1], "q_min_probability": fmt(q_delete[2]), "q_min_predicted_sp": fmt(q_delete[3]), "q_min_q": fmt(q_delete[4])})
                        counter["ranker_disagreements"] += 1; disagreement_count += 1
                    portfolio_count += 1; counter["portfolio_identities"] += 1
        for handles in (frontier_h, role_h, disagreement_h): close_gzip(handles)
        write_csv(stage / "issue_census.csv", ISSUE_CENSUS_FIELDS, census)
        write_csv(stage / "candidate_scatter.csv", SCATTER_FIELDS, sorted(scatter, key=lambda row: (int(str(row["year"])), int(str(row["issue"])), int(str(row["match_idx"])), int(str(row["match_id"])))))
        write_csv(stage / "threshold_census.csv", SUMMARY_FIELDS, [{"variant_id": variant, **{field: summary[variant][field] for field in SUMMARY_FIELDS if field != "variant_id"}} for variant in sorted(VARIANTS)])
        accounting_rows = []
        for entry in accounting.values():
            matches = entry.pop("matches")
            accounting_rows.append({**entry, "unique_selected_matches": len(matches)})
        write_csv(stage / "issue_accounting.csv", ISSUE_ACCOUNTING_FIELDS, sorted(accounting_rows, key=lambda row: (row["variant_id"], row["arm"], int(str(row["year"])), int(str(row["issue"])))))
        write_csv(stage / "source_census.csv", SOURCE_FIELDS, [
            {"source": "bj101_gate_a_preoutcome_v1r1", "role": "complete eligible issue membership and calibrated probability", "manifest_sha256": BJ101_MANIFEST, "payload": "issue_pool_membership.csv", "payload_sha256": provenance["bj101_membership_sha256"], "rows": 47819, "join_status": "all rows uniquely joined; segment columns are diagnostics only"},
            {"source": "bj90_downstream_safe_projection_v1r1", "role": "as-of predicted SP vector", "manifest_sha256": BJ90_MANIFEST, "payload": "oos_prediction_vectors.csv.gz", "payload_sha256": provenance["bj90_prediction_sha256"], "rows": 100589, "join_status": "47819 of 47819 #101 members joined on full identity"},
        ])
        card = {"issue": 132, "contract": CONTRACT, "generator_version": VERSION, "stage": "GATE_A_OUTCOME_UNEXPOSED_COMPLETE_ISSUE_MATCHED_FREEZE", "provenance": provenance, "denominator": {"eligible_matches": 47819, "issue_instances": len(by_issue), "frontier_rows": frontier_count, "portfolio_identities": portfolio_count, "role_rows": role_count, "ranker_disagreements": disagreement_count}, "variants": VARIANTS, "complete_issue_contract": {"primary_unit": "(issue, fold) issue instance; no issue is segmented for selection or construction", "candidate_competition": "all complete-issue matches with p_min <= variant maximum sort by p_min, match_idx, match_id; deterministic top 32 are searched", "n7_construction": "candidate plus six highest E_SP eligible companions from the whole same issue instance; candidates and companions compete across the full issue", "large_issue_cap": MAX_CANDIDATES_PER_ISSUE_VARIANT, "insufficient_issue_rule": "<7 matches is an explicit NO_BET row", "segment_metadata": "source pool_id/segment_index is never read as a selection, availability, or construction constraint"}, "arms": {"MATCHED_FULL_N7": {"tickets": FULL_K, "stake_yuan": FULL_K * UNIT_STAKE}, "P_MIN_DELETE_N7": {"tickets": DELETE_K, "stake_yuan": DELETE_K * UNIT_STAKE}, "Q_MIN_DELETE_N7": {"tickets": DELETE_K, "stake_yuan": DELETE_K * UNIT_STAKE}}, "role_encoding": "one seven-row role assignment per portfolio; the frontier's p/q deletion identities deterministically derive all three arms' allowed-code sets without arm-by-arm role duplication", "deletion_rule": "Within each matched seven-match portfolio, p_min selects argmin calibrated p and q_min selects argmin q=p*predicted_SP, with match_idx then code-order (3,1,0) tie breaks. The match set is identical across three arms.", "accounting": {"budget": "stake and K are reported outputs, never a rejection gate", "participation": "all frozen portfolios are retained; no overlap rejection", "tax": "Gate B will aggregate gross by issue_instance, variant, arm and apply the existing actual-tax rule without cross-issue aggregation", "folds_and_loyo": "every output retains fold/year; any LOYO report holds each complete issue instance intact"}, "outcome_boundary": "No result, score, final SP, payout, tax realization, ROI, or settlement source is read or emitted. Gate B is NOT_RUN and NOT_AUTHORIZED pending PI acceptance of this exact replacement Gate A.", "legacy_boundary": "results/bj132_gate_a_preoutcome_v1 and its settlement are immutable segment-compatible legacy comparators only; they are non-controlling sensitivity evidence.", "scope": "historical paper-only research; no purchase, production, or promotion."}
        (stage / "gate_a_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        shutil.copyfile(__file__, stage / "runner.py")
        (stage / "README.md").write_text("# #132 replacement Gate A\n\nComplete-issue, outcome-unexposed matched FULL / p-min delete / q-min delete freeze. Run `python3 runner.py --output <new-dir>`; Gate B remains unauthorized.\n", encoding="utf-8")
        gzip_names = ("matched_delete_score_frontier.csv.gz", "portfolio_role_assignments.csv.gz", "ranker_disagreements.csv.gz")
        def decompressed(path: Path) -> tuple[str, int]:
            digest, size = hashlib.sha256(), 0
            with gzip.open(path, "rb") as handle:
                for block in iter(lambda: handle.read(1 << 20), b""):
                    digest.update(block); size += len(block)
            return digest.hexdigest(), size
        content = {"contract_version": CONTENT_VERSION, "gzip_payloads": {name: {"canonical_decompressed_sha256": decompressed(stage / name)[0], "canonical_decompressed_bytes": decompressed(stage / name)[1]} for name in gzip_names}, "non_compressed_controls": {item.name: sha256(item) for item in sorted(stage.iterdir()) if item.is_file() and item.name not in gzip_names}}
        (stage / "CONTENT_IDENTITY.json").write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest = {item.name: sha256(item) for item in sorted(stage.iterdir()) if item.is_file()}
        (stage / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(stage, output)
        return {"manifest_sha256": sha256(output / "SHA256SUMS.json"), "issue_instances": len(by_issue), "frontier_rows": frontier_count, "portfolio_identities": portfolio_count, "role_rows": role_count, "ranker_disagreements": disagreement_count}
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    finally:
        BJ101, BJ90 = original101, original90


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--bj101", type=Path, default=BJ101)
    parser.add_argument("--bj90", type=Path, default=BJ90)
    args = parser.parse_args()
    print(json.dumps(freeze(args.output.resolve(), args.bj101.resolve(), args.bj90.resolve()), sort_keys=True))


if __name__ == "__main__":
    main()
