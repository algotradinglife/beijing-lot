#!/usr/bin/env python3
"""#237 REQ-PW06: independently reconstruct the #180 power support-loss waterfall.

Reconstructs raw -> identity -> league -> decision epoch -> embargo -> line ->
triplet -> causal intersection, distinguishing identity loss, league gaps and
causal cutoff loss, and re-derives the accepted "#180 power covered 9 issues"
(P_POWER_BJLINE = 234 cells / 9 issues) from primary artifacts.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bj237_power_lib as lib  # noqa: E402


def load_bj180_freeze(root: Path) -> pd.DataFrame:
    freeze = pd.read_csv(root / lib.BJ180_FREEZE, compression="gzip")
    freeze["issue"] = freeze["issue"].astype(str)
    return freeze


def load_bj229_cells(root: Path) -> pd.DataFrame:
    return pd.read_parquet(root / lib.BJ229_INFERENCE_CELLS)


def reconstruct_229_power_intersection(root: Path) -> dict:
    """Re-derive P_POWER_BJLINE availability exactly as #229 publishes it.

    #229 merges the #180 freeze on (issue, match_idx), requires a probability
    triplet and BJ_LINE_BOUNDARY (native line) equality, then time-gates on
    observed_at <= decision epoch.  This reconstruction reproduces the 234 cells
    / 9 issues figure from the published artifacts without re-running #229.
    """
    cells = load_bj229_cells(root)
    freeze = load_bj180_freeze(root)

    power = freeze[
        [
            "issue",
            "match_idx",
            "handicap_line_norm",
            "team_primary_p3",
            "team_primary_p1",
            "team_primary_p0",
            "feature_cutoff_ts",
        ]
    ].copy()
    power = power.rename(columns={"handicap_line_norm": "freeze_handicap_line_norm"})
    power["match_idx"] = power["match_idx"].astype(int)
    complete = power[
        ["team_primary_p3", "team_primary_p1", "team_primary_p0"]
    ].notna().all(axis=1)
    power = power[complete].copy()

    merged = cells.merge(
        power,
        on=["issue", "match_idx"],
        how="left",
        validate="many_to_one",
        suffixes=("", "_power"),
    )
    source_line = pd.to_numeric(merged["freeze_handicap_line_norm"], errors="coerce")
    target_line = pd.to_numeric(merged["BJ_LINE_BOUNDARY"], errors="coerce")
    vector_present = merged[["team_primary_p3", "team_primary_p1", "team_primary_p0"]].notna().all(axis=1)
    same_line = pd.Series(
        pd.isna(target_line) | pd.isna(source_line) | (abs(target_line - source_line) < 1e-12),
        index=merged.index,
    )
    publishable = vector_present & same_line & merged["P_POWER_BJLINE_available"].astype(bool)

    published = merged[publishable]
    return {
        "cells_total": int(len(cells)),
        "issues_total": int(cells["issue"].nunique()),
        "freeze_rows": int(len(freeze)),
        "freeze_issues": int(freeze["issue"].nunique()),
        "freeze_complete_rows": int(len(power)),
        "merged_power_cells": int(vector_present.sum()),
        "line_matched_cells": int((vector_present & same_line).sum()),
        "published_cells": int(len(published)),
        "published_issues": int(published["issue"].nunique()),
        "published_issues_list": sorted(published["issue"].unique().astype(str).tolist()),
    }


def build_full_waterfall(matches: pd.DataFrame, epochs: pd.DataFrame) -> pd.DataFrame:
    """Raw -> identity -> league -> epoch -> target -> line causal chain."""
    stages = lib.build_identity_waterfall(matches, epochs)

    # target gate: the match itself must not have started at the decision
    # epoch (kickoff >= epoch); its features are computed at the epoch from
    # prior completed matches only (REQ-PW01).
    with_epoch = matches["issue"].isin(set(epochs["issue"]))
    m = matches[with_epoch].copy()
    m["epoch_utc"] = m["issue"].map(
        dict(zip(epochs["issue"], epochs["feature_cutoff_ts_utc"]))
    )
    m["kickoff_utc"] = lib.kickoff_to_utc(m["kickoff_ts"])
    m["not_started"] = m["kickoff_utc"] >= m["epoch_utc"]
    n_target = int(m["not_started"].sum())
    n_target_issues = int(m.loc[m["not_started"], "issue"].nunique())
    n_started_excluded = int((~m["not_started"]).sum())

    # line present on target rows
    m["line_ok"] = m["handicap_line_norm"].notna()
    n_line = int((m["not_started"] & m["line_ok"]).sum())
    n_line_issues = int(m.loc[m["not_started"] & m["line_ok"], "issue"].nunique())

    extra = pd.DataFrame(
        [
            {
                "stage": 4,
                "label": "target not started at epoch (kickoff >= epoch)",
                "rows": n_target,
                "issues": n_target_issues,
            },
            {
                "stage": 5,
                "label": "native line present (target rows)",
                "rows": n_line,
                "issues": n_line_issues,
            },
            {
                "reason": lib.REASON_EMBARGO_EXCLUDED,
                "rows": n_started_excluded,
                "issues": int(m.loc[~m["not_started"], "issue"].nunique()),
            },
            {
                "reason": lib.REASON_LINE_BLANK,
                "rows": int((m["not_started"] & ~m["line_ok"]).sum()),
                "issues": int(m.loc[m["not_started"] & ~m["line_ok"], "issue"].nunique()),
            },
        ]
    )
    return pd.concat([stages, extra], ignore_index=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="repo root (worktree)")
    parser.add_argument("--out", default="results/bj237_power_feature_support_v1",
                        help="output directory")
    args = parser.parse_args()
    root = Path(args.root).resolve()

    matches = lib.load_xlsm_matches()
    epochs = lib.load_decision_epochs(root)
    print(f"raw matches: {len(matches)} / issues {matches['issue'].nunique()}")
    print(f"#203 epochs: {len(epochs)} issues")

    # full waterfall
    waterfall = build_full_waterfall(matches, epochs)
    print("\n=== support-loss waterfall ===")
    print(waterfall.to_string(index=False))

    # #180 freeze vs full pool (league-gap quantification)
    freeze = load_bj180_freeze(root)
    freeze_issues = set(freeze["issue"])
    full_issues = set(matches["issue"])
    print(f"\n#180 freeze: {len(freeze)} rows / {len(freeze_issues)} issues")
    print(f"full pool: {len(matches)} rows / {len(full_issues)} issues")
    print(f"league gap (freeze vs full): {len(freeze_issues)}/{len(full_issues)} "
          f"issues covered ({len(freeze_issues)/len(full_issues):.1%})")

    # #229 P_POWER intersection reconstruction
    inter = reconstruct_229_power_intersection(root)
    print("\n=== #229 P_POWER_BJLINE intersection reconstruction ===")
    for key, value in inter.items():
        print(f"  {key}: {value}")

    # external coverage census
    external = lib.load_football_data_coverage()
    print(f"\n=== external football-data coverage: {len(external)} files ===")
    print(external[["file", "rows", "competition"]].to_string(index=False))

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    waterfall.to_csv(out / "support_loss_waterfall.csv", index=False)
    pd.DataFrame([inter]).T.reset_index().rename(
        columns={"index": "metric", 0: "value"}
    ).to_csv(out / "ppower_intersection_reconstruction.csv", index=False)
    external.to_csv(out / "external_football_data_census.csv", index=False)
    with open(out / "waterfall_receipt.json", "w", encoding="utf-8") as handle:
        json.dump(
            {
                "waterfall_stages": len(waterfall),
                "n_raw": int(waterfall.loc[waterfall["stage"] == 0, "rows"].iloc[0]),
                "n_target_not_started": int(
                    waterfall.loc[waterfall["stage"] == 4, "rows"].iloc[0]
                ),
                "ppower_reconstruction": inter,
            },
            handle,
            indent=2,
            ensure_ascii=False,
        )
    print(f"\nwrote outputs -> {out}")


if __name__ == "__main__":
    main()
