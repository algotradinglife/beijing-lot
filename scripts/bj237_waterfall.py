#!/usr/bin/env python3
"""#237 REQ-PW06: independently reconstruct the #180 power support-loss waterfall.

R2 rework (C-02): EVERY gate is rebuilt from source primitives.  The
producer-written ``P_POWER_BJLINE_available`` flag is never used as a terminal
gate.  ``same_line`` requires BOTH sides non-null and exactly equal.  The
accepted figure "P_POWER_BJLINE = 234 cells / 9 issues" is re-derived from:

  G1  #229 inference cell exists (issue x match_idx x outcome)
  G2  P_POWER_BJLINE vector present (non-null triplet)
  G3  P_POWER_BJLINE_observed_at_utc <= feature_cutoff_ts_utc
      (decision-epoch causality, Asia/Shanghai -> UTC via #203)
  G4  #180 freeze row exists for (issue, match_idx)
  G5  freeze team_primary triplet complete
  G6  BJ_LINE_BOUNDARY non-null AND freeze handicap_line_norm non-null
      AND exactly equal (no missing-as-match)

Gate-level rows/issues are reported so the identity / league / causal-cutoff
loss chain is established independently of any producer flag.
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
    """Re-derive P_POWER_BJLINE availability from primitives (C-02).

    Never reads the producer-written ``P_POWER_BJLINE_available`` flag.  The
    causal time gate is ``P_POWER_BJLINE_observed_at_utc <=
    feature_cutoff_ts_utc`` (the #203 decision epoch); the line gate requires
    both the #229 BJ_LINE_BOUNDARY and the #180 freeze handicap line to be
    non-null and exactly equal.
    """
    cells = load_bj229_cells(root)
    freeze = load_bj180_freeze(root)

    # G1: cell exists (implicit — we are already in the inference-cell space).
    n_cells = int(len(cells))
    n_cells_issues = int(cells["issue"].nunique())

    # G2: P_POWER_BJLINE vector present.
    power_vector = cells["P_POWER_BJLINE"].notna()
    n_vector = int(power_vector.sum())
    n_vector_issues = int(cells.loc[power_vector, "issue"].nunique())

    # G3: observed_at <= decision epoch (primitive causality gate).
    observed = pd.to_datetime(
        cells["P_POWER_BJLINE_observed_at_utc"], utc=True, errors="coerce"
    )
    cutoff = pd.to_datetime(
        cells["feature_cutoff_ts_utc"], utc=True, errors="coerce"
    )
    timely = observed.notna() & cutoff.notna() & (observed <= cutoff)
    n_timely = int((power_vector & timely).sum())
    n_timely_issues = int(cells.loc[power_vector & timely, "issue"].nunique())

    # G4/G5: #180 freeze row exists with complete team_primary triplet.
    freeze_key = freeze[["issue", "match_idx"]].drop_duplicates()
    freeze_key["match_idx"] = freeze_key["match_idx"].astype(int)
    freeze_complete = freeze[
        freeze[["team_primary_p3", "team_primary_p1", "team_primary_p0"]].notna().all(axis=1)
    ][["issue", "match_idx", "handicap_line_norm"]].copy()
    freeze_complete["match_idx"] = freeze_complete["match_idx"].astype(int)

    merged = cells[power_vector & timely].merge(
        freeze_complete, on=["issue", "match_idx"], how="left",
        indicator=True,
    )
    has_freeze = merged["_merge"] == "both"
    n_freeze = int(has_freeze.sum())
    n_freeze_issues = int(merged.loc[has_freeze, "issue"].nunique())

    # G6: exact non-null line equality (freeze source line vs #229 boundary).
    source_line = pd.to_numeric(merged["handicap_line_norm"], errors="coerce")
    target_line = pd.to_numeric(merged["BJ_LINE_BOUNDARY"], errors="coerce")
    same_line = (
        source_line.notna() & target_line.notna()
        & (abs(source_line - target_line) < 1e-12)
    )
    publishable = has_freeze & same_line
    published = merged[publishable]

    return {
        "gate_cells_total": n_cells,
        "gate_issues_total": n_cells_issues,
        "g2_vector_cells": n_vector,
        "g2_vector_issues": n_vector_issues,
        "g3_causal_epoch_cells": int((power_vector & timely).sum()),
        "g3_causal_epoch_issues": n_timely_issues,
        "g4_freeze_row_cells": n_freeze,
        "g4_freeze_row_issues": n_freeze_issues,
        "g6_line_matched_cells": int((has_freeze & same_line).sum()),
        "g6_line_matched_issues": int(
            merged.loc[has_freeze & same_line, "issue"].nunique()
        ),
        "published_cells": int(len(published)),
        "published_issues": int(published["issue"].nunique()),
        "published_issues_list": sorted(published["issue"].unique().astype(str).tolist()),
        "gate_method": (
            "primitives only: vector present + observed_at <= feature_cutoff_ts_utc "
            "+ freeze triplet complete + exact non-null line equality; "
            "P_POWER_BJLINE_available flag NOT used"
        ),
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

    # C-01: native line present on target rows uses the FAIL-CLOSED predicate
    # (non-null, finite, grid member) — same predicate as the builder.
    m["line_ok"] = m["handicap_line_norm"].apply(lib.line_is_publishable)
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
                "label": "native line present (target rows, fail-closed)",
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
    parser.add_argument("--out", default="results/bj237_power_feature_support_v2",
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

    # #229 P_POWER intersection reconstruction (primitives only)
    inter = reconstruct_229_power_intersection(root)
    print("\n=== #229 P_POWER_BJLINE intersection reconstruction (primitives) ===")
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
