#!/usr/bin/env python3
"""Outcome-unexposed Gate-A freeze for #89 rolling EURO calibration."""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import shutil
import sqlite3
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def repository_root() -> Path:
    """Work both from scripts/ and from the archived result bundle."""
    for candidate in (Path(__file__).resolve().parent, *Path(__file__).resolve().parents):
        if (candidate / "AGENTS.md").is_file() and (candidate / "scripts").is_dir():
            return candidate
    raise RuntimeError("unable to locate repository root from runner location")


ROOT = repository_root()
SOURCE_DB = ROOT.parent.parent / "data/derived/beidan_xlsm/beidan_xlsm.sqlite"
# v3 supersedes v2 only by making each calibration formula/objective exact.
# The cohort, folds, and quality-gate contract remain intact.
OUT = ROOT / "results/bj89_gate_a_preoutcome_v3"
WARMUP_YEAR = 2018
EVALUATION_YEARS = tuple(range(2019, 2026))
OUTCOMES = ("3", "1", "0")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def devig(odds: tuple[float, float, float]) -> tuple[float, float, float]:
    inv = [1.0 / value for value in odds]
    total = sum(inv)
    return tuple(value / total for value in inv)


def entropy(probabilities: tuple[float, float, float]) -> float:
    return -sum(value * math.log(value) for value in probabilities if value > 0)


def main() -> int:
    if OUT.exists():
        raise SystemExit(f"refusing to overwrite immutable output: {OUT}")
    if not SOURCE_DB.is_file():
        raise SystemExit(f"missing source: {SOURCE_DB}")
    stage = Path(tempfile.mkdtemp(prefix="bj89-gate-a-", dir=OUT.parent))
    try:
        # Explicitly pre-outcome query.  No match_features, score, result,
        # winning SP, settlement, action, or final snapshot is read here.
        sql = """
        SELECT m.match_id, m.issue, m.match_idx, m.kickoff_ts,
               m.handicap_line_norm,
               t.n_complete AS n_complete_10h,
               t.v1_avg AS euro_3_10h, t.v2_avg AS euro_1_10h, t.v3_avg AS euro_0_10h,
               t.v1_min AS euro_3_min_10h, t.v1_max AS euro_3_max_10h,
               t.v2_min AS euro_1_min_10h, t.v2_max AS euro_1_max_10h,
               t.v3_min AS euro_0_min_10h, t.v3_max AS euro_0_max_10h,
               i.v1_avg AS euro_3_initial, i.v2_avg AS euro_1_initial, i.v3_avg AS euro_0_initial
        FROM matches AS m
        JOIN market_consensus AS t
          ON t.match_id=m.match_id AND t.market='euro_1x2' AND t.snapshot='10h'
        LEFT JOIN market_consensus AS i
          ON i.match_id=m.match_id AND i.market='euro_1x2' AND i.snapshot='initial'
        WHERE m.handicap_line_norm=0
          AND substr(m.kickoff_ts,1,4) BETWEEN '2018' AND '2025'
          AND t.v1_avg>0 AND t.v2_avg>0 AND t.v3_avg>0
        ORDER BY m.kickoff_ts, m.issue, m.match_idx, m.match_id
        """
        conn = sqlite3.connect(f"file:{SOURCE_DB}?mode=ro", uri=True)
        description = [col[0] for col in conn.execute(sql).description]
        source_rows = [dict(zip(description, row)) for row in conn.execute(sql)]
        conn.close()

        rows = []
        for row in source_rows:
            year = int(str(row["kickoff_ts"])[:4])
            odds = tuple(float(row[f"euro_{code}_10h"]) for code in OUTCOMES)
            p = devig(odds)
            initial_values = [row[f"euro_{code}_initial"] for code in OUTCOMES]
            initial_complete = all(value is not None and float(value) > 0 for value in initial_values)
            if initial_complete:
                p_initial = devig(tuple(float(value) for value in initial_values))
                movement = sum(abs(math.log(max(current, 1e-15) / max(previous, 1e-15))) for current, previous in zip(p, p_initial))
            else:
                p_initial = (None, None, None)
                movement = None
            ranges = []
            for code, avg in zip(OUTCOMES, odds):
                lo, hi = row[f"euro_{code}_min_10h"], row[f"euro_{code}_max_10h"]
                ranges.append(None if lo is None or hi is None else (float(hi) - float(lo)) / avg)
            rank = sorted(range(3), key=lambda idx: (-p[idx], idx))
            rows.append({
                "match_id": row["match_id"], "issue": row["issue"], "match_idx": row["match_idx"],
                "kickoff_ts": row["kickoff_ts"], "year": year, "fold": "WARMUP" if year == WARMUP_YEAR else f"OOS_{year}",
                "handicap_line_norm": row["handicap_line_norm"], "n_complete_10h": row["n_complete_10h"],
                "euro_3_10h": odds[0], "euro_1_10h": odds[1], "euro_0_10h": odds[2],
                "p3_raw": p[0], "p1_raw": p[1], "p0_raw": p[2],
                "top1_code_raw": OUTCOMES[rank[0]], "top1_mass_raw": p[rank[0]], "top2_mass_raw": p[rank[0]] + p[rank[1]],
                "entropy_raw": entropy(p), "dispersion_mean_relative_range": None if any(value is None for value in ranges) else sum(ranges) / 3,
                "initial_status": "COMPLETE" if initial_complete else "MISSING_OR_INCOMPLETE",
                "p3_initial": p_initial[0], "p1_initial": p_initial[1], "p0_initial": p_initial[2],
                "initial_to_10h_log_probability_movement": movement,
            })

        folds = []
        for test_year in EVALUATION_YEARS:
            folds.append({
                "fold": f"OOS_{test_year}", "train_years": f"{WARMUP_YEAR}-{test_year - 1}",
                "test_year": test_year, "chronology": "expanding calendar-year; all model/gate fit uses train years only",
                "target_outcome_access": "FORBIDDEN_IN_GATE_A",
            })
        counts = Counter(row["year"] for row in rows)
        census = [{"year": year, "rows": counts[year], "fold": "WARMUP" if year == WARMUP_YEAR else f"OOS_{year}"} for year in range(2018, 2026)]

        methods = {
            "RAW_DEVIG_EURO": {
                "probability": "normalize reciprocal 10h EURO 1X2 consensus averages",
                "fit": "none", "status": "baseline",
            },
            "ROLLING_MULTINOMIAL_LOG_ODDS": {
                "features": ["log(p3_raw/p0_raw)", "log(p1_raw/p0_raw)"],
                "feature_transform": "none; raw log-odds are not standardised or otherwise fitted",
                "model": "three-class softmax with a 3x3 coefficient matrix: intercept, log(p3_raw/p0_raw), log(p1_raw/p0_raw)",
                "objective": "sum_i[-log softmax(X_i B)[y_i]] + ||B||_F^2/(2*C), minimized by deterministic L-BFGS-B from B=0",
                "regularization": {"l2_C": 0.10, "penalize_intercept": True, "selection": "fixed before outcome access; no C search"},
                "fit": "per fold, expanding prior years only",
            },
            "ROLLING_STRATIFIED_SHRINKAGE": {
                "strata": {"predicted_outcome": "top1_code_raw", "confidence_bands": [0.0, 0.40, 0.50, 0.60, 0.70, 1.0000001]},
                "estimate": "for each stratum s, p_s=(class_count_s + 100*global_observed_class_frequency)/(n_s+100); every test row in s receives p_s",
                "shrinkage_pseudocount": 100.0,
                "global_prior": "prior-fold empirical observed 3/1/0 class frequency",
                "fallback": "n_s=0 in the same fixed formula, equal to the global prior",
                "fit": "per fold, expanding prior years only",
            },
        }
        quality_contract = {
            "score": "method-independent prior-fold smoothed RAW-devig Top1 correctness estimate; calibration changes the probability vector, while this separately learned match-quality gate uses only pre-outcome market state",
            "stratum": ["raw_top1_code", "raw_top1_confidence_band", "raw_entropy_band", "dispersion_category", "initial_to_10h_movement_category"],
            "raw_top1_confidence_bands": [0.0, 0.40, 0.50, 0.60, 0.70, 1.0000001],
            "raw_entropy_bands": [0.0, 0.80, 0.95, 1.05, 1.1000001],
            "dispersion_categories": {"MISSING": "one or more 10h relative ranges missing", "LOW": "mean relative range <= 0.10", "HIGH": "mean relative range > 0.10"},
            "initial_to_10h_movement_categories": {"MISSING": "initial vector incomplete", "LOW": "sum abs(log(p10h/pinitial)) <= 0.05", "MEDIUM": "0.05 < movement <= 0.15", "HIGH": "movement > 0.15"},
            "smoothing_pseudocount": 100.0,
            "prior": "prior-fold global raw-devig Top1 hit rate",
            "formula": "(stratum_top1_hits + 100*prior_fold_global_top1_hit_rate)/(stratum_n + 100)",
            "fallback": "the same formula with stratum_n=0",
            "fixed_coverage_arms": [0.25, 0.50, 0.75, 1.00],
            "gate": "within each fold, retain the first ceil(coverage*test_n) rows after score DESC, then kickoff_ts ASC, issue ASC, match_idx ASC, match_id ASC; the gate is identical across calibration methods",
            "learning_boundary": "all score estimates and score cutoffs use only the fold training years; held-out outcomes never set a gate",
            "selection_boundary": "Gate B reports all fixed arms. A later policy nomination is not permitted unless PI accepts a separately explicit chronological selector; this Gate-A card therefore does not select a winner using held-out outcomes",
        }
        card = {
            "issue": 89, "stage": "GATE_A_OUTCOME_UNEXPOSED", "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "evidence_class": "RETROSPECTIVE_TIMING_PROXY", "source": {"path": str(SOURCE_DB), "sha256": sha256(SOURCE_DB)},
            "sql_read_whitelist": {"matches": ["match_id", "issue", "match_idx", "kickoff_ts", "handicap_line_norm"], "market_consensus": ["euro_1x2@10h averages/ranges/n_complete", "euro_1x2@initial averages"]},
            "explicitly_not_read": ["match_features", "score", "result", "result_code", "winning_sp", "official_sp", "outcome_features", "action_candidates", "settlement", "final snapshot", "Asian market"],
            "cohort": {"years": [2018, 2025], "warmup_year": WARMUP_YEAR, "evaluation_years": list(EVALUATION_YEARS), "handicap_line_norm": 0, "rows": len(rows), "folds": len(folds)},
            "methods": methods, "quality_gate": quality_contract,
            "prohibited": ["random split", "held-out outcome threshold search", "portfolio ROI", "SP cap", "N/K/stake", "production/PDF"],
        }
        write_csv(stage / "frozen_preoutcome_rows.csv", rows, list(rows[0]))
        write_csv(stage / "fold_plan.csv", folds, list(folds[0]))
        write_csv(stage / "source_census.csv", census, list(census[0]))
        (stage / "experiment_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        shutil.copyfile(__file__, stage / "freeze_runner.py")
        manifest = {path.name: sha256(path) for path in sorted(stage.iterdir()) if path.is_file()}
        (stage / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(stage, OUT)
        print(json.dumps({"output": str(OUT), "rows": len(rows), "folds": len(folds), "source_sha256": card["source"]["sha256"], "manifest_sha256": sha256(OUT / "SHA256SUMS.json")}, sort_keys=True))
        return 0
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


if __name__ == "__main__":
    sys.exit(main())
