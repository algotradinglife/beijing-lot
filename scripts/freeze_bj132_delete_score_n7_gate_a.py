#!/usr/bin/env python3
"""Freeze #132's outcome-unexposed p-min versus q-min N7 comparison."""
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
VERSION = "bj132-gatea-v1"
CONTENT_VERSION = "bj132-portable-content-v1"
BJ127_MANIFEST = "a8eeb50204bb9a2d69578538e28943a432bea11083661a63b950a5ab5a2481da"
FULL_K, DELETE_K, UNIT_STAKE = 3 ** 7, 2 * 3 ** 6, 2

FRONTIER_FIELDS = (
    "issue", "fold", "year", "pool_id", "segment_index", "first_kickoff_ts", "last_kickoff_ts", "variant_id",
    "arm", "portfolio_id", "selected_match_ids", "selected_n", "gm_e_sp", "disposition", "reason",
    "p_min_deleted_match_id", "p_min_deleted_code", "p_min_deleted_probability", "p_min_predicted_sp", "p_min_q",
    "q_min_deleted_match_id", "q_min_deleted_code", "q_min_deleted_probability", "q_min_predicted_sp", "q_min_q",
    "rankers_disagree", "formula_k", "stake_yuan", "matched_full_k", "matched_full_stake_yuan", "stake_reduction_fraction",
    "descriptor_sha256",
)
ROLE_FIELDS = (
    "variant_id", "portfolio_id", "arm", "issue", "fold", "year", "pool_id", "match_id", "match_idx", "selection_rank",
    "e_sp", "p_min", "p3", "p1", "p0", "predicted_sp3", "predicted_sp1", "predicted_sp0", "q3", "q1", "q0",
    "p_min_deleted_match_id", "p_min_deleted_code", "q_min_deleted_match_id", "q_min_deleted_code", "allowed_codes",
)
DISAGREEMENT_FIELDS = (
    "variant_id", "portfolio_id", "issue", "fold", "year", "pool_id", "first_kickoff_ts", "selector_stratum",
    "p_min_deleted_match_id", "p_min_deleted_match_idx", "p_min_deleted_code", "p_min_probability", "p_min_predicted_sp", "p_min_q",
    "q_min_deleted_match_id", "q_min_deleted_match_idx", "q_min_deleted_code", "q_min_probability", "q_min_predicted_sp", "q_min_q",
)
SUMMARY_FIELDS = (
    "variant_id", "source_no_bet_rows", "source_portfolios", "matched_full_rows", "p_min_delete_rows", "q_min_delete_rows",
    "ranker_disagreements", "full_stake_yuan", "p_min_stake_yuan", "q_min_stake_yuan", "stake_reduction_fraction",
)


def repository_root(path: Path) -> Path:
    for candidate in (path.resolve().parent, *path.resolve().parents):
        if (candidate / ".git").exists():
            return candidate
    raise RuntimeError("repository root unavailable")


ROOT = repository_root(Path(__file__))
SOURCE = ROOT / "results" / "bj127_gate_a_preoutcome_v2"
OUTPUT = ROOT / "results" / "bj132_gate_a_preoutcome_v1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_id(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def fmt(value: float) -> str:
    if not math.isfinite(value):
        raise RuntimeError("non-finite value")
    return format(value, ".12f")


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


def exact_source() -> dict[str, str]:
    manifest_path = SOURCE / "SHA256SUMS.json"
    if sha256(manifest_path) != BJ127_MANIFEST:
        raise RuntimeError("#127 Gate-A manifest is not the accepted input")
    declared = json.loads(manifest_path.read_text(encoding="utf-8"))
    actual = {path.name: sha256(path) for path in SOURCE.iterdir()
              if path.is_file() and path.name != "SHA256SUMS.json"}
    if declared != actual:
        raise RuntimeError("#127 Gate-A manifest coverage drift")
    return declared


def minimum(rows: list[dict[str, str]], score: str) -> tuple[dict[str, str], str, float, float, float]:
    values: list[tuple[float, int, int, dict[str, str], str, float, float]] = []
    for row in rows:
        for index, code in enumerate(CODES):
            probability = float(row[f"p{code}"])
            predicted_sp = float(row[f"predicted_sp{code}"])
            q = float(row[f"q{code}"])
            if abs(q - probability * predicted_sp) > 2e-10:
                raise RuntimeError("q does not equal probability times predicted SP")
            values.append(((probability if score == "p" else q), int(row["match_idx"]), index, row, code, probability, predicted_sp))
    _, _, _, match, code, probability, predicted_sp = min(values)
    return match, code, probability, predicted_sp, float(match[f"q{code}"])


def load() -> tuple[dict[str, str], list[dict[str, str]], dict[tuple[str, str], list[dict[str, str]]]]:
    manifest = exact_source()
    features: dict[str, dict[str, str]] = {}
    with gzip.open(SOURCE / "scatter_coordinates.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["match_id"] in features:
                raise RuntimeError("match feature is not unique")
            features[row["match_id"]] = row
    frontiers: list[dict[str, str]] = []
    with gzip.open(SOURCE / "matched_frontier.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["arm"] in {"NO_BET_CONTROL", "MATCHED_FULL_N7"}:
                frontiers.append(row)
    roles: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    with gzip.open(SOURCE / "portfolio_role_assignments.csv.gz", "rt", newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            feature = features[row["match_id"]]
            enriched = {**row, **feature}
            for code in CODES:
                enriched[f"predicted_sp{code}"] = fmt(float(feature[f"q{code}"]) / float(feature[f"p{code}"]))
            roles[(row["variant_id"], row["portfolio_id"])].append(enriched)
    for group in roles.values():
        group.sort(key=lambda row: int(row["selection_rank"]))
        if len(group) != 7:
            raise RuntimeError("#127 portfolio does not contain seven roles")
    return manifest, frontiers, roles


def output_role(row: dict[str, str], arm: str, p_delete: tuple[dict[str, str], str, float, float, float],
                q_delete: tuple[dict[str, str], str, float, float, float]) -> dict[str, object]:
    deleted = p_delete if arm == "P_MIN_DELETE_N7" else q_delete
    deleted_match, deleted_code = deleted[0], deleted[1]
    allowed = "".join(code for code in CODES if not (row["match_id"] == deleted_match["match_id"] and code == deleted_code))
    return {"variant_id": row["variant_id"], "portfolio_id": row["portfolio_id"], "arm": arm, "issue": row["issue"],
            "fold": row["fold"], "year": row["year"], "pool_id": row["pool_id"], "match_id": row["match_id"],
            "match_idx": row["match_idx"], "selection_rank": row["selection_rank"], "e_sp": row["e_sp"], "p_min": row["p_min"],
            "p3": row["p3"], "p1": row["p1"], "p0": row["p0"], "predicted_sp3": fmt(float(row["q3"]) / float(row["p3"])),
            "predicted_sp1": fmt(float(row["q1"]) / float(row["p1"])), "predicted_sp0": fmt(float(row["q0"]) / float(row["p0"])),
            "q3": row["q3"], "q1": row["q1"], "q0": row["q0"], "p_min_deleted_match_id": p_delete[0]["match_id"],
            "p_min_deleted_code": p_delete[1], "q_min_deleted_match_id": q_delete[0]["match_id"],
            "q_min_deleted_code": q_delete[1], "allowed_codes": "310" if arm == "MATCHED_FULL_N7" else allowed}


def write_package(output: Path) -> dict[str, object]:
    if output.exists():
        raise RuntimeError(f"refusing immutable overwrite: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".bj132_gatea_", dir=output.parent))
    try:
        source_manifest, source_rows, roles = load()
        frontier_h = gzip_writer(stage / "matched_delete_score_frontier.csv.gz", FRONTIER_FIELDS)
        role_h = gzip_writer(stage / "portfolio_role_assignments.csv.gz", ROLE_FIELDS)
        disagreement_h = gzip_writer(stage / "ranker_disagreements.csv.gz", DISAGREEMENT_FIELDS)
        fw, rw, dw = frontier_h[-1], role_h[-1], disagreement_h[-1]
        summary: dict[str, Counter[str]] = defaultdict(Counter)
        frontier_count = role_count = disagreement_count = 0
        for source in source_rows:
            variant = source["variant_id"]
            summary[variant]["source_no_bet_rows" if source["arm"] == "NO_BET_CONTROL" else "source_portfolios"] += 1
            if source["arm"] == "NO_BET_CONTROL":
                fw.writerow({"issue": source["issue"], "fold": source["fold"], "year": source["year"], "pool_id": source["pool_id"],
                             "segment_index": source["segment_index"], "first_kickoff_ts": source["first_kickoff_ts"], "last_kickoff_ts": source["last_kickoff_ts"],
                             "variant_id": variant, "arm": "NO_BET_CONTROL", "portfolio_id": "", "selected_match_ids": "", "selected_n": 0,
                             "gm_e_sp": "", "disposition": "NO_BET", "reason": source["reason"], "p_min_deleted_match_id": "", "p_min_deleted_code": "",
                             "p_min_deleted_probability": "", "p_min_predicted_sp": "", "p_min_q": "", "q_min_deleted_match_id": "",
                             "q_min_deleted_code": "", "q_min_deleted_probability": "", "q_min_predicted_sp": "", "q_min_q": "", "rankers_disagree": "",
                             "formula_k": 0, "stake_yuan": 0, "matched_full_k": FULL_K, "matched_full_stake_yuan": FULL_K * UNIT_STAKE,
                             "stake_reduction_fraction": fmt(1 / 3), "descriptor_sha256": stable_id({"variant": variant, "pool": source["pool_id"], "reason": source["reason"]})})
                frontier_count += 1
                continue
            key = (variant, source["portfolio_id"])
            selected = roles.get(key)
            if selected is None:
                raise RuntimeError("missing #127 role assignment")
            p_delete = minimum(selected, "p")
            q_delete = minimum(selected, "q")
            if (p_delete[0]["match_id"], p_delete[1]) != (source["deleted_match_id"], source["deleted_code"]):
                raise RuntimeError("p-min deletion no longer reproduces #127")
            disagree = int((p_delete[0]["match_id"], p_delete[1]) != (q_delete[0]["match_id"], q_delete[1]))
            shared = {"issue": source["issue"], "fold": source["fold"], "year": source["year"], "pool_id": source["pool_id"],
                      "segment_index": source["segment_index"], "first_kickoff_ts": source["first_kickoff_ts"], "last_kickoff_ts": source["last_kickoff_ts"],
                      "variant_id": variant, "portfolio_id": source["portfolio_id"], "selected_match_ids": source["selected_match_ids"], "selected_n": 7,
                      "gm_e_sp": source["gm_e_sp"], "disposition": "AVAILABLE", "reason": "MATCHED_FROZEN_PAIR",
                      "p_min_deleted_match_id": p_delete[0]["match_id"], "p_min_deleted_code": p_delete[1], "p_min_deleted_probability": fmt(p_delete[2]),
                      "p_min_predicted_sp": fmt(p_delete[3]), "p_min_q": fmt(p_delete[4]), "q_min_deleted_match_id": q_delete[0]["match_id"],
                      "q_min_deleted_code": q_delete[1], "q_min_deleted_probability": fmt(q_delete[2]), "q_min_predicted_sp": fmt(q_delete[3]),
                      "q_min_q": fmt(q_delete[4]), "rankers_disagree": disagree, "matched_full_k": FULL_K,
                      "matched_full_stake_yuan": FULL_K * UNIT_STAKE, "stake_reduction_fraction": fmt(1 / 3)}
            for arm, k in (("MATCHED_FULL_N7", FULL_K), ("P_MIN_DELETE_N7", DELETE_K), ("Q_MIN_DELETE_N7", DELETE_K)):
                fw.writerow({**shared, "arm": arm, "formula_k": k, "stake_yuan": k * UNIT_STAKE,
                             "descriptor_sha256": stable_id({"contract": CONTRACT, "variant": variant, "arm": arm, "portfolio": source["portfolio_id"],
                                                               "matches": source["selected_match_ids"], "p_delete": (p_delete[0]["match_id"], p_delete[1]),
                                                               "q_delete": (q_delete[0]["match_id"], q_delete[1])})})
                summary[variant][{"MATCHED_FULL_N7": "matched_full_rows", "P_MIN_DELETE_N7": "p_min_delete_rows", "Q_MIN_DELETE_N7": "q_min_delete_rows"}[arm]] += 1
                summary[variant][{"MATCHED_FULL_N7": "full_stake_yuan", "P_MIN_DELETE_N7": "p_min_stake_yuan", "Q_MIN_DELETE_N7": "q_min_stake_yuan"}[arm]] += k * UNIT_STAKE
                frontier_count += 1
                for row in selected:
                    rw.writerow(output_role(row, arm, p_delete, q_delete))
                    role_count += 1
            if disagree:
                dw.writerow({"variant_id": variant, "portfolio_id": source["portfolio_id"], "issue": source["issue"], "fold": source["fold"], "year": source["year"],
                             "pool_id": source["pool_id"], "first_kickoff_ts": source["first_kickoff_ts"], "selector_stratum": variant,
                             "p_min_deleted_match_id": p_delete[0]["match_id"], "p_min_deleted_match_idx": p_delete[0]["match_idx"], "p_min_deleted_code": p_delete[1],
                             "p_min_probability": fmt(p_delete[2]), "p_min_predicted_sp": fmt(p_delete[3]), "p_min_q": fmt(p_delete[4]),
                             "q_min_deleted_match_id": q_delete[0]["match_id"], "q_min_deleted_match_idx": q_delete[0]["match_idx"], "q_min_deleted_code": q_delete[1],
                             "q_min_probability": fmt(q_delete[2]), "q_min_predicted_sp": fmt(q_delete[3]), "q_min_q": fmt(q_delete[4])})
                summary[variant]["ranker_disagreements"] += 1
                disagreement_count += 1
        for handles in (frontier_h, role_h, disagreement_h):
            close_gzip(handles)
        with (stage / "threshold_census.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS, lineterminator="\n")
            writer.writeheader()
            for variant in sorted(summary):
                writer.writerow({"variant_id": variant, **summary[variant], "stake_reduction_fraction": fmt(1 / 3)})
        card = {"issue": 132, "contract": CONTRACT, "generator_version": VERSION, "stage": "GATE_A_OUTCOME_UNEXPOSED_MATCHED_FREEZE",
                "input": {"package": "results/bj127_gate_a_preoutcome_v2", "manifest_sha256": BJ127_MANIFEST,
                          "files": {name: source_manifest[name] for name in ("matched_frontier.csv.gz", "portfolio_role_assignments.csv.gz", "scatter_coordinates.csv.gz")}},
                "arms": {"MATCHED_FULL_N7": {"tickets": FULL_K, "stake_yuan": FULL_K * UNIT_STAKE},
                         "P_MIN_DELETE_N7": {"tickets": DELETE_K, "stake_yuan": DELETE_K * UNIT_STAKE},
                         "Q_MIN_DELETE_N7": {"tickets": DELETE_K, "stake_yuan": DELETE_K * UNIT_STAKE}},
                "selection": "Copy each #127 available portfolio's exact seven match IDs and its p-min deletion. Compute q(code)=p_cal(code)*predicted_SP(code) from #127's outcome-unexposed scatter fields; q_min uses deterministic q, match_idx, code tie-breaks. No match is reselected.",
                "denominator": {"source_rows": len(source_rows), "frontier_rows": frontier_count, "role_rows": role_count, "ranker_disagreements": disagreement_count},
                "outcome_boundary": "No result, final SP, payout, tax, ROI, settlement source, or post-outcome artifact is read or emitted. Gate B is NOT_RUN and NOT_AUTHORIZED.",
                "scope": "Historical paper-only research; no purchase, production, or promotion."}
        (stage / "gate_a_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        shutil.copyfile(__file__, stage / "runner.py")
        (stage / "README.md").write_text("# #132 Gate A\n\nOutcome-unexposed matched comparison of FULL N7, global p-min deletion, and global q=p×predicted_SP deletion. Run `python3 runner.py --output <new-dir>`; settlement is not authorized.\n", encoding="utf-8")
        gzip_names = ("matched_delete_score_frontier.csv.gz", "portfolio_role_assignments.csv.gz", "ranker_disagreements.csv.gz")
        def decompressed(path: Path) -> tuple[str, int]:
            digest, size = hashlib.sha256(), 0
            with gzip.open(path, "rb") as handle:
                for block in iter(lambda: handle.read(1 << 20), b""):
                    digest.update(block); size += len(block)
            return digest.hexdigest(), size
        content = {"contract_version": CONTENT_VERSION,
                   "gzip_payloads": {name: {"canonical_decompressed_sha256": decompressed(stage / name)[0], "canonical_decompressed_bytes": decompressed(stage / name)[1]} for name in gzip_names},
                   "non_compressed_controls": {item.name: sha256(item) for item in sorted(stage.iterdir()) if item.is_file() and item.name not in gzip_names}}
        (stage / "CONTENT_IDENTITY.json").write_text(json.dumps(content, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        manifest = {item.name: sha256(item) for item in sorted(stage.iterdir()) if item.is_file()}
        (stage / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(stage, output)
        return {"manifest_sha256": sha256(output / "SHA256SUMS.json"), "frontier_rows": frontier_count, "role_rows": role_count, "ranker_disagreements": disagreement_count}
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    print(json.dumps(write_package(parser.parse_args().output.resolve()), sort_keys=True))


if __name__ == "__main__":
    main()
