#!/usr/bin/env python3
"""Render compact committed #236 evidence from external materialized views."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=ROOT / "results" / "bj236_eu_odds_timeseries_v1")
    args = parser.parse_args()
    package = args.data_root / "derived" / "bj236" / "eu_odds_proxy_v1"
    manifest = json.loads((package / "MANIFEST.json").read_text(encoding="utf-8"))
    facts = json.loads((package / "report_facts.json").read_text(encoding="utf-8"))
    if manifest["market_type"] != "euro_1x2" or manifest["causal_grade"] != "RETROSPECTIVE_RELATIVE_PROXY":
        raise ValueError("external view is not the declared #236 European proxy lane")
    probabilities = pd.concat([pd.read_parquet(p) for p in sorted((package / "probabilities").glob("*.parquet"))], ignore_index=True)
    translations = pd.concat([pd.read_parquet(p) for p in sorted((package / "translation_readiness").glob("*.parquet"))], ignore_index=True)
    sums = probabilities.groupby(["canonical_fixture_key", "snapshot_kind"])["probability"].sum()
    if not ((sums - 1.0).abs() < 1e-12).all():
        raise ValueError("probability triplet check failed")
    coverage = probabilities.groupby("snapshot_kind").agg(
        matched_fixture_count=("canonical_fixture_key", "nunique"),
        probability_rows=("outcome_code", "size"),
        available_books_median=("n_available_books", "median"),
    ).reindex(["initial", "10h", "1h"]).reset_index()
    decisions = translations.groupby("translation_status").size().rename("fixture_horizon_count").reset_index()
    args.out.mkdir(parents=True, exist_ok=True)
    coverage.to_csv(args.out / "HORIZON_COVERAGE.csv", index=False)
    decisions.to_csv(args.out / "TRANSLATION_READINESS.csv", index=False)
    report = {
        "contract": manifest["contract"], "source_sha256": manifest["source_sha256"],
        "market_type": manifest["market_type"], "causal_grade": manifest["causal_grade"],
        "facts": facts, "horizon_coverage": coverage.to_dict(orient="records"),
        "translation_readiness": decisions.to_dict(orient="records"),
        "strict_forward_decision": "UNAVAILABLE: relative provider labels lack exact shared observation clocks",
        "nonzero_line_decision": "UNAVAILABLE: requires an explicit score/goal-difference distribution",
    }
    (args.out / "COVERAGE_REPORT.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.bar(coverage["snapshot_kind"], coverage["matched_fixture_count"], color="#336699")
    ax.set_title("#236 matched fixtures by historical European proxy horizon")
    ax.set_xlabel("provider relative horizon label")
    ax.set_ylabel("matched canonical issue slots")
    fig.tight_layout()
    fig.savefig(args.out / "horizon_coverage.png", dpi=150)
    plt.close(fig)
    print(json.dumps(report, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
