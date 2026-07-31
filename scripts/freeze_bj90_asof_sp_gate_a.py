#!/usr/bin/env python3
"""Outcome-free Gate-A source/fold/model-card freeze for Issue #90."""
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
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


def repository_root() -> Path:
    for candidate in (Path(__file__).resolve().parent, *Path(__file__).resolve().parents):
        if (candidate / "AGENTS.md").is_file() and (candidate / "scripts").is_dir():
            return candidate
    raise RuntimeError("unable to locate repository root")


ROOT = repository_root()
SOURCE = ROOT.parent.parent / "data/derived/beidan_xlsm/beidan_xlsm.sqlite"
OUT = ROOT / "results/bj90_gate_a_preoutcome_v4"
SNAPSHOTS = ("euro_1x2", "asian_handicap", "over_under")


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    fields = fields or sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def complete(prefix: str, row: sqlite3.Row) -> bool:
    return all(row[f"{prefix}_{field}"] is not None for field in ("n", "v1", "v2", "v3", "i_v1", "i_v2", "i_v3")) and int(row[f"{prefix}_n"]) > 0


def main() -> int:
    if OUT.exists():
        raise SystemExit(f"refusing to overwrite immutable output: {OUT}")
    stage = Path(tempfile.mkdtemp(prefix="bj90-gate-a-", dir=OUT.parent))
    try:
        source_sha = digest(SOURCE)
        conn = sqlite3.connect(f"file:{SOURCE}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        # Gate A is strictly target-unexposed.  Later price labels are not joined,
        # selected, or used to determine this frozen universe.
        query = """
        SELECT m.match_id,m.issue,m.match_idx,m.kickoff_ts,m.league,m.handicap_line_norm,
               e.n_complete euro_n,e.v1_avg euro_v1,e.v2_avg euro_v2,e.v3_avg euro_v3,e.v1_min euro_min1,e.v2_min euro_min2,e.v3_min euro_min3,e.v1_max euro_max1,e.v2_max euro_max2,e.v3_max euro_max3,
               ei.v1_avg euro_i_v1,ei.v2_avg euro_i_v2,ei.v3_avg euro_i_v3,
               a.n_complete asian_n,a.v1_avg asian_v1,a.v2_avg asian_v2,a.v3_avg asian_v3,a.v1_min asian_min1,a.v2_min asian_min2,a.v3_min asian_min3,a.v1_max asian_max1,a.v2_max asian_max2,a.v3_max asian_max3,
               ai.v1_avg asian_i_v1,ai.v2_avg asian_i_v2,ai.v3_avg asian_i_v3,
               o.n_complete ou_n,o.v1_avg ou_v1,o.v2_avg ou_v2,o.v3_avg ou_v3,o.v1_min ou_min1,o.v2_min ou_min2,o.v3_min ou_min3,o.v1_max ou_max1,o.v2_max ou_max2,o.v3_max ou_max3,
               oi.v1_avg ou_i_v1,oi.v2_avg ou_i_v2,oi.v3_avg ou_i_v3
          FROM matches m
          LEFT JOIN market_consensus e  ON e.match_id=m.match_id AND e.market='euro_1x2' AND e.snapshot='10h'
          LEFT JOIN market_consensus ei ON ei.match_id=m.match_id AND ei.market='euro_1x2' AND ei.snapshot='initial'
          LEFT JOIN market_consensus a  ON a.match_id=m.match_id AND a.market='asian_handicap' AND a.snapshot='10h'
          LEFT JOIN market_consensus ai ON ai.match_id=m.match_id AND ai.market='asian_handicap' AND ai.snapshot='initial'
          LEFT JOIN market_consensus o  ON o.match_id=m.match_id AND o.market='over_under' AND o.snapshot='10h'
          LEFT JOIN market_consensus oi ON oi.match_id=m.match_id AND oi.market='over_under' AND oi.snapshot='initial'
         WHERE m.kickoff_ts >= '2018-01-01' AND m.kickoff_ts < '2026-01-01'
        """
        all_rows = list(conn.execute(query))
        conn.close()
        pre_columns = (
            "euro_n","euro_v1","euro_v2","euro_v3","euro_i_v1","euro_i_v2","euro_i_v3","euro_min1","euro_min2","euro_min3","euro_max1","euro_max2","euro_max3",
            "asian_n","asian_v1","asian_v2","asian_v3","asian_i_v1","asian_i_v2","asian_i_v3","asian_min1","asian_min2","asian_min3","asian_max1","asian_max2","asian_max3",
            "ou_n","ou_v1","ou_v2","ou_v3","ou_i_v1","ou_i_v2","ou_i_v3","ou_min1","ou_min2","ou_min3","ou_max1","ou_max2","ou_max3",
        )
        identities: list[dict] = []
        census: dict[int, Counter] = defaultdict(Counter)
        for row in all_rows:
            year = int(str(row["kickoff_ts"])[:4])
            c = census[year]
            c["total"] += 1
            line_ok = row["handicap_line_norm"] is not None
            market_ok = all(complete(name, row) for name in ("euro", "asian", "ou"))
            c["line_ok"] += line_ok
            c["market_ok"] += market_ok
            if line_ok and market_ok:
                signed_line_fields = ("asian_v2", "asian_i_v2", "asian_min2", "asian_max2", "ou_v2", "ou_i_v2", "ou_min2", "ou_max2")
                if not all(math.isfinite(float(row[field])) for field in signed_line_fields):
                    raise RuntimeError(f"non-finite signed market line for match_id={row['match_id']}")
                c["eligible"] += 1
                identities.append({
                    "match_id": row["match_id"], "issue": row["issue"], "match_idx": row["match_idx"],
                    "kickoff_ts": row["kickoff_ts"], "year": year, "league": row["league"],
                    "handicap_line_norm": row["handicap_line_norm"], "fold": "WARMUP_2018" if year == 2018 else f"OOS_{year}",
                    **{name: row[name] for name in pre_columns},
                })
        if len(identities) != len({row["match_id"] for row in identities}):
            raise RuntimeError("non-unique eligible match_id")
        if not identities or min(row["year"] for row in identities) != 2018:
            raise RuntimeError("expected 2018 warm-up is unavailable")
        fold_plan = []
        for year in range(2019, 2026):
            train = sum(census[past]["eligible"] for past in range(2018, year))
            test = census[year]["eligible"]
            if not train or not test:
                raise RuntimeError(f"empty expanding fold {year}")
            fold_plan.append({"fold": f"OOS_{year}", "train_years": f"2018-{year - 1}", "test_year": year, "train_n": train, "test_n": test})
        source_census = [
            {"year": year, "total": c["total"], "line_ok": c["line_ok"], "market10h_and_initial_complete": c["market_ok"], "eligible": c["eligible"]}
            for year, c in sorted(census.items())
        ]
        card = {
            "issue": 90,
            "stage": "GATE_A_OUTCOME_UNEXPOSED_SOURCE_AND_MODEL_CARD",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "source": {"path": str(SOURCE), "sha256": source_sha},
            "eligibility": "kickoff in 2018-2025; normalized BJDC line; complete 10h+initial EURO/Asian/OU consensus",
            "chronology": "2018 warm-up; strict expanding OOS years 2019-2025. A fold can use only earlier years for any target-fitted mapping.",
            "allowed_pre10h_features": [
                "euro_1x2 10h/initial consensus means and 10h bookmaker count",
                "asian_handicap 10h/initial consensus means and 10h bookmaker count",
                "over_under 10h/initial consensus means and 10h bookmaker count",
                "normalized BJDC handicap, league, kickoff time context",
            ],
            "gate_a_boundary": "No later price label or target-availability field is read, selected, or used for eligibility. Such availability is recorded only by the one Gate-B ledger.",
            "forbidden": ["score", "result_label", "result_code", "winning_sp", "outcome_features", "ROI", "portfolio", "N", "K", "stake", "SP-cap search"],
            "feature_vector_v3": {
                "code_mapping": "for EURO and target vectors, v1->code 3, v2->code 1, v3->code 0",
                "numeric_order": "EURO positions 1,2,3 each contribute logclip(10h_avg), logclip(initial_avg), log movement and log min/max dispersion; Asian positions 1 and 3 contribute the same price transforms, then Asian position 2 contributes raw 10h line, raw initial line, raw delta and raw range; OU positions 1 and 3 contribute the same price transforms, then OU position 2 contributes raw 10h line, raw initial line, raw delta and raw range; then log1p(n_complete) for euro,asian,ou; then handicap_line_norm; then sin(2*pi*minute_of_day/1440), cos(2*pi*minute_of_day/1440)",
                "price_transforms": "logclip(x)=log(max(0.01, x)) with NULL/non-finite treated as 0.01; movement=logclip(10h_avg)-logclip(initial_avg); dispersion=logclip(10h_max)-logclip(10h_min)",
                "signed_line_transforms": "for Asian/OU position 2 only: line_10h=v2_avg, line_initial=v2_avg_initial, delta=line_10h-line_initial, range=v2_max-v2_min. All four source values must be finite; otherwise fail closed. They are never log-transformed and their signs are unchanged.",
                "context_transforms": "log1p(n)=log(1+max(0,n)); minute_of_day is parsed from literal kickoff_ts as YYYY-MM-DD HH:MM:SS without timezone conversion",
                "league": "one indicator per UTF-8-sorted distinct training league string, with NULL mapped to __MISSING__; an unseen test league is all-zero",
            },
            "bounded_models": {
                "M0_EURO_10H": "predict [sp_3,sp_1,sp_0]=[max(.01,euro_v1),max(.01,euro_v2),max(.01,euro_v3)]; no fitted parameter",
                "M1_RIDGE_LOG_SP": "for each target code 3,1,0 independently: train-standardize every numeric feature by training mean and population standard deviation (zero SD -> 0); append training-only league indicators; fit intercept plus coefficients by minimizing sum squared log-SP residuals plus 10*sum(non-intercept coefficients squared); intercept unpenalized; fixed lambda=10; exponentiate predictions after clipping log prediction to [-10,10]",
                "M2_CONSERVATIVE_Q20": "for each code, take M1 residual r=log(target)-log(M1 prediction) on all prior OOS rows only; add the empirical q=.20 residual using sorted values and index floor(.20*(n-1)); no prior OOS residuals (2019) -> shift 0. M2 is not a primary-model selector candidate.",
            },
            "future_selector": "For 2019 deploy M0. Before each y>=2020, select M0 or M1 using only prior OOS years 2019..y-1: minimize equal-issue three-code log-MAE (per row mean over codes, then unweighted mean over issue); tie minimize equal-issue mean absolute rank displacement, ranks descending SP with ties resolved 3 then 1 then 0; final tie M0 before M1. M2 is always the fixed conservative vector. No result/ROI metric may enter selection.",
            "future_diagnostics": ["three-code log error", "rank agreement/displacement", "SP-band calibration", "high-SP tail error", "quote-to-final retention", "league/line/dispersion slices", "leave-one-year-out stability"],
            "label": "RETROSPECTIVE_PRICE_TARGET; NOT_OBSERVED_PREBET_BJDC_QUOTE",
        }
        write_csv(stage / "frozen_preoutcome_rows.csv", identities)
        write_csv(stage / "fold_plan.csv", fold_plan)
        write_csv(stage / "source_census.csv", source_census)
        (stage / "experiment_card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n")
        shutil.copyfile(__file__, stage / "freeze_runner.py")
        manifest = {path.name: digest(path) for path in sorted(stage.iterdir()) if path.is_file()}
        (stage / "SHA256SUMS.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        os.replace(stage, OUT)
        print(json.dumps({"output": str(OUT), "source_sha256": source_sha, "eligible": len(identities), "manifest_sha256": digest(OUT / "SHA256SUMS.json")}, sort_keys=True))
        return 0
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


if __name__ == "__main__":
    sys.exit(main())
