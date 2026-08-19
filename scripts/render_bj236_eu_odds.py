#!/usr/bin/env python3
"""Render compact committed #236 evidence from external materialized views."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eu_odds_timeseries.profiling import HORIZONS, build_profiles  # noqa: E402


TABLE_FILES = {
    "horizon_coverage": "HORIZON_COVERAGE.csv",
    "year_coverage": "YEAR_COVERAGE.csv",
    "issue_coverage": "ISSUE_COVERAGE.csv",
    "bookmaker_coverage": "BOOKMAKER_COVERAGE.csv",
    "missingness": "MISSINGNESS.csv",
    "odds_distribution": "ODDS_DISTRIBUTION.csv",
    "probability_distribution": "PROBABILITY_DISTRIBUTION.csv",
    "line_availability": "LINE_AVAILABILITY.csv",
    "line_provenance": "LINE_PROVENANCE.csv",
    "auxiliary_market_support": "AUXILIARY_MARKET_SUPPORT.csv",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=ROOT / "results" / "bj236_eu_odds_timeseries_v1")
    args = parser.parse_args()
    workbook = args.data_root / "derived" / "beidan_xlsm" / "beidan_xlsm.sqlite"
    package = args.data_root / "derived" / "bj236" / "eu_odds_proxy_v1"
    manifest = json.loads((package / "MANIFEST.json").read_text(encoding="utf-8"))
    facts = json.loads((package / "report_facts.json").read_text(encoding="utf-8"))
    if manifest["market_type"] != "euro_1x2" or manifest["causal_grade"] != "RETROSPECTIVE_RELATIVE_PROXY":
        raise ValueError("external view is not the declared #236 European proxy lane")
    profiles = build_profiles(workbook, package)
    coverage = profiles["horizon_coverage"]
    decisions = profiles["line_availability"]
    args.out.mkdir(parents=True, exist_ok=True)
    for key, filename in TABLE_FILES.items():
        profiles[key].to_csv(args.out / filename, index=False)
    report = {
        "contract": manifest["contract"], "source_sha256": manifest["source_sha256"],
        "market_type": manifest["market_type"], "causal_grade": manifest["causal_grade"],
        "source_role": manifest["source_role"],
        "facts": facts, "horizon_coverage": coverage.to_dict(orient="records"),
        "profile_summary": profiles["summary"],
        "translation_readiness": decisions.to_dict(orient="records"),
        "profile_tables": TABLE_FILES,
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

    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    axes[0, 0].bar(
        coverage["snapshot_kind"],
        100 * coverage["valid_proxy_match_rate"],
        color="#336699",
    )
    axes[0, 0].set_title("Valid proxy match rate")
    axes[0, 0].set_ylabel("eligible issue slots (%)")

    year = profiles["year_coverage"]
    year = year.loc[year.year.ne("UNKNOWN")].copy()
    for horizon in HORIZONS:
        subset = year.loc[year.snapshot_kind.eq(horizon)].sort_values("year")
        axes[0, 1].plot(subset.year, subset.matched_fixture_count, marker="o", label=horizon)
    axes[0, 1].set_title("Matched fixtures by kickoff year")
    axes[0, 1].tick_params(axis="x", rotation=45)
    axes[0, 1].legend()

    probability = profiles["probability_distribution"]
    for outcome in ("3", "1", "0"):
        subset = probability.loc[probability.outcome_code.eq(outcome)].set_index("snapshot_kind").reindex(HORIZONS)
        axes[1, 0].plot(HORIZONS, subset["median"], marker="o", label=f"outcome {outcome}")
        axes[1, 0].fill_between(HORIZONS, subset.p05, subset.p95, alpha=0.12)
    axes[1, 0].set_title("De-vig probability median and p05–p95")
    axes[1, 0].set_ylabel("probability")
    axes[1, 0].legend()

    line = profiles["line_availability"].pivot(
        index="snapshot_kind", columns="translation_status", values="within_horizon_rate"
    ).fillna(0).reindex(HORIZONS)
    line.plot(kind="bar", stacked=True, ax=axes[1, 1], legend=True)
    axes[1, 1].set_title("BJ-line translation readiness")
    axes[1, 1].set_ylabel("within-horizon share")
    axes[1, 1].tick_params(axis="x", rotation=0)
    axes[1, 1].legend(title="translation status", fontsize=6, title_fontsize=7)

    fig.tight_layout()
    fig.savefig(args.out / "data_profile_overview.png", dpi=150)
    plt.close(fig)
    print(json.dumps(report, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
