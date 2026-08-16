#!/usr/bin/env python3
"""#237 causal league/team power feature builder (REQ-PW01..PW05, PW08).

Reusable builder producing timestamp-safe league/team/matchup strength features
on the canonical fixture identity.  The feature engine is the accepted #180
team-matchup core (sequential EWMA/Elo/poisson state machine), driven here on
the #203 decision-epoch semantics and canonical identity dictionaries.

Outputs (immutable, under results/bj237_power_feature_support_v1/):
  - power_features.parquet        long-form per (issue, match_idx, outcome) rows
  - power_feature_diagnostics.parquet  per-match diagnostics + masks
  - support_summary.parquet       support by issue/year/league/line
  - calibration_through_2023.parquet   calibration table (<=2023 labels only)
  - feature_schema.json           versioned feature schema
  - manifest.json + SHA256SUMS.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
import math
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bj237_power_lib as lib  # noqa: E402

CORE_PATH = Path("scripts/bj180_team_matchup_core.py")


def load_core(root: Path):
    import sys as _sys
    spec = importlib.util.spec_from_file_location("bj180_core", root / CORE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {CORE_PATH}")
    module = importlib.util.module_from_spec(spec)
    _sys.modules["bj180_core"] = module
    spec.loader.exec_module(module)
    return module


def _finite(value: object, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def build_features(
    root: Path,
    matches: pd.DataFrame,
    epochs: pd.DataFrame,
    core,
) -> dict:
    """Sequential replay: update team state only from matches completed before
    each decision epoch, then publish per-match power vectors at the epoch.

    Deterministic order: matches sorted by (kickoff_ts, match_id); epochs sorted
    by cutoff.  State advances monotonically; every published row is computed
    from state that contains only events with kickoff <= epoch - embargo.
    """
    # Prepare history rows (eligible: both team ids, score present).
    hist = matches[
        matches["home_team_id"].notna()
        & (matches["home_team_id"].astype(str) != "")
        & matches["away_team_id"].notna()
        & (matches["away_team_id"].astype(str) != "")
        & matches["fthg"].notna()
        & matches["ftag"].notna()
    ].copy()
    hist["kickoff_utc"] = lib.kickoff_to_utc(hist["kickoff_ts"])
    hist = hist.sort_values(["kickoff_utc", "match_id"]).reset_index(drop=True)
    # #180 core compares naive datetimes end-to-end; convert history timestamps
    # to naive UTC so state updates and probability cutoffs share one clock.
    hist["kickoff_ts_naive_utc"] = hist["kickoff_utc"].dt.tz_localize(None)
    hist_rows = []
    for _, row in hist.iterrows():
        rec = row.to_dict()
        rec["kickoff_ts"] = rec["kickoff_ts_naive_utc"].isoformat(sep=" ")
        hist_rows.append(rec)

    epoch_map = dict(zip(epochs["issue"], epochs["feature_cutoff_ts_utc"]))
    # Per-issue target rows (all matches with an epoch, score NOT required for
    # target identity; line required for publish).
    targets = matches[matches["issue"].isin(set(epoch_map))].copy()
    targets["epoch_utc"] = targets["issue"].map(epoch_map)
    targets["kickoff_utc"] = lib.kickoff_to_utc(targets["kickoff_ts"])

    state = core.TeamMatchupState()
    published: list[dict] = []
    diagnostics: list[dict] = []

    embargo = dt.timedelta(minutes=lib.COMPLETION_EMBARGO_MINUTES)
    history_cursor = 0

    # Process issues in chronological epoch order so state advances once.
    ordered_issues = sorted(epoch_map.items(), key=lambda kv: kv[1])
    for issue, epoch in ordered_issues:
        epoch_dt = epoch.to_pydatetime()
        availability_cutoff = epoch_dt - embargo

        # Advance history through availability_cutoff (strictly before).
        while history_cursor < len(hist_rows):
            row = hist_rows[history_cursor]
            kickoff = row["kickoff_utc"].to_pydatetime()
            if kickoff <= availability_cutoff:
                state.update(row)
                history_cursor += 1
            else:
                break

        issue_targets = targets[targets["issue"] == issue]
        # REQ-PW01: a target match must not have started at its decision epoch;
        # rows with kickoff < epoch (including corrupt timestamps) are dropped.
        issue_targets = issue_targets[
            issue_targets["kickoff_utc"] >= issue_targets["epoch_utc"]
        ]
        # #180 core operates on naive datetimes; use naive UTC so state updates
        # (converted to naive UTC) and probability cutoffs share one clock.
        naive_cutoff = availability_cutoff.replace(tzinfo=None)
        for _, trow in issue_targets.iterrows():
            match_row = {
                "match_id": trow["match_id"],
                "kickoff_ts": trow["kickoff_ts"],
                "league": trow["league"],
                "home_team_id": trow["home_team_id"],
                "away_team_id": trow["away_team_id"],
                "handicap_line_norm": trow["handicap_line_norm"],
            }
            prob, diag, vectors = state.probabilities(
                match_row, naive_cutoff, configuration="TEAM_PRIMARY"
            )
            home_id = str(trow["home_team_id"] or "")
            away_id = str(trow["away_team_id"] or "")
            home_depth = diag["home_history_n"]
            away_depth = diag["away_history_n"]
            min_depth = diag["min_history_n"]
            line = trow["handicap_line_norm"]
            line_ok = line is not None and math.isfinite(_finite(line))
            # REQ-PW04: only native BJ handicap grid lines publish probabilities.
            if line_ok and _finite(line) not in {
                -3.0, -2.5, -2.0, -1.5, -1.0, -0.5, 0.0,
                0.5, 1.0, 1.5, 2.0, 2.5, 3.0,
            }:
                line_ok = False
            triplet_ok = (
                line_ok
                and prob is not None
                and all(math.isfinite(v) for v in prob)
                and abs(sum(prob) - 1.0) < 1e-9
            )
            unseen = min_depth == 0 or not home_id or not away_id

            base = {
                "issue": issue,
                "match_idx": int(trow["match_idx"]),
                "match_id": int(trow["match_id"]),
                "kickoff_ts_utc": trow["kickoff_utc"],
                "decision_epoch_utc": epoch,
                "year": int(str(issue)[:2]) + 2000 if str(issue)[:2].isdigit() else -1,
                "league": trow["league"],
                "home_team_id": home_id,
                "away_team_id": away_id,
                "native_handicap_line": line if line_ok else None,
                "line_ok": bool(line_ok),
                "unseen_mask": bool(unseen),
                "min_history_n": int(min_depth),
                "home_history_n": int(home_depth),
                "away_history_n": int(away_depth),
                "triplet_ok": bool(triplet_ok),
            }
            # Uncertainty proxy: history-depth based (lower depth -> wider).
            uncertainty = 0.0 if min_depth == 0 else min(0.35, 0.28 / math.sqrt(min_depth))
            base["uncertainty"] = round(uncertainty, 6)

            for code, value in zip(lib.OUTCOME_CODES, prob):
                row = dict(base)
                row["outcome_code"] = code
                row["power_probability"] = round(float(value), 10) if triplet_ok else None
                published.append(row)

            diag_row = dict(base)
            diag_row.update({f"diag_{key}": value for key, value in diag.items()})
            diag_row["history_event_sha256"] = state.history_event_sha256
            diagnostics.append(diag_row)

    published_df = pd.DataFrame(published)
    diagnostics_df = pd.DataFrame(diagnostics)
    return {"published": published_df, "diagnostics": diagnostics_df}


def support_summary(published: pd.DataFrame) -> pd.DataFrame:
    """Support by issue/year/league/line with only causal, publishable rows."""
    ok = published[
        published["triplet_ok"]
        & published["line_ok"]
        & ~published["unseen_mask"]
    ].copy()
    grouped = (
        ok.groupby(["year", "league", "native_handicap_line"])
        .agg(
            rows=("match_idx", "count"),
            issues=("issue", "nunique"),
            matches=("match_idx", "nunique"),
        )
        .reset_index()
    )
    return grouped


def calibration_through_2023(
    published: pd.DataFrame, matches: pd.DataFrame
) -> pd.DataFrame:
    """Calibration on <=2023 labels only (REQ-PW07).  Never touches 2024+."""
    cal = published[
        published["triplet_ok"]
        & published["line_ok"]
        & published["year"].le(2023)
        & ~published["unseen_mask"]
    ].copy()
    if cal.empty:
        return pd.DataFrame(
            columns=["year", "league", "outcome_code", "n", "mean_pred", "mean_actual"]
        )
    # Join actual outcome from xlsm match_features (result_code).
    actual = matches[["issue", "match_idx", "result_code"]].drop_duplicates(
        ["issue", "match_idx"]
    )
    actual["issue"] = actual["issue"].astype(str)
    merged = cal.merge(actual, on=["issue", "match_idx"], how="left")
    merged["actual"] = merged["result_code"].astype(str)
    valid = merged[merged["actual"].isin(lib.OUTCOME_CODES)].copy()
    if valid.empty:
        return pd.DataFrame(
            columns=["year", "league", "outcome_code", "n", "mean_pred", "mean_actual"]
        )
    valid["hit"] = valid["outcome_code"] == valid["actual"]
    grouped = (
        valid.groupby(["year", "league", "outcome_code"])
        .agg(
            n=("hit", "count"),
            mean_pred=("power_probability", "mean"),
            mean_actual=("hit", "mean"),
        )
        .reset_index()
    )
    return grouped


def write_package(out: Path, frames: dict, receipt: dict, base_commit: str) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for name, frame in frames.items():
        if frame is not None and not frame.empty:
            frame.to_parquet(out / f"{name}.parquet", index=False)

    schema = {
        "contract": lib.CONTRACT,
        "version": lib.VERSION,
        "decision_epoch": "issue-level feature_cutoff_ts_utc from bj203 issue_offsets",
        "completion_embargo_minutes": lib.COMPLETION_EMBARGO_MINUTES,
        "feature_engine": "scripts/bj180_team_matchup_core.py (accepted #180 core, "
                          "TEAM_PRIMARY configuration)",
        "outcome_domain": "3/1/0 (BJ native handicap result)",
        "line_semantics": "native_handicap_line is the fixture's BJ handicap "
                          "normalized line; probability vector maps to that line",
        "tables": {
            "power_features": {
                "description": "long-form per (issue, match_idx, outcome_code)",
                "key": ["issue", "match_idx", "outcome_code"],
                "columns": [
                    "issue", "match_idx", "match_id", "kickoff_ts_utc",
                    "decision_epoch_utc", "year", "league", "home_team_id",
                    "away_team_id", "native_handicap_line", "line_ok",
                    "unseen_mask", "min_history_n", "home_history_n",
                    "away_history_n", "triplet_ok", "uncertainty",
                    "outcome_code", "power_probability",
                ],
            },
            "power_feature_diagnostics": {
                "description": "per-match diagnostics + masks",
                "key": ["issue", "match_idx"],
                "columns": [
                    "issue", "match_idx", "match_id", "kickoff_ts_utc",
                    "decision_epoch_utc", "year", "league", "home_team_id",
                    "away_team_id", "native_handicap_line", "line_ok",
                    "unseen_mask", "min_history_n", "home_history_n",
                    "away_history_n", "triplet_ok", "uncertainty",
                    "diag_home_elo", "diag_away_elo", "diag_elo_diff",
                    "diag_home_form_points", "diag_away_form_points",
                    "diag_home_rest_hours", "diag_away_rest_hours",
                    "diag_home_matches_7d", "diag_away_matches_7d",
                    "diag_home_matches_21d", "diag_away_matches_21d",
                    "diag_home_league_changes", "diag_away_league_changes",
                    "diag_h2h_prior_n", "diag_new_team_fallback",
                    "history_event_sha256",
                ],
            },
        },
    }
    (out / "feature_schema.json").write_text(
        json.dumps(schema, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    manifest = {
        "contract": lib.CONTRACT,
        "version": lib.VERSION,
        "base_main_commit": base_commit,
        "built_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_receipt": receipt,
        "tables": {name: f"{name}.parquet" for name in frames if frames.get(name) is not None},
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    sums = {}
    for path in sorted(out.iterdir()):
        if path.is_file() and path.name != "SHA256SUMS.json":
            sums[path.name] = lib.sha256_file(path)
    (out / "SHA256SUMS.json").write_text(
        json.dumps(sums, indent=2, sort_keys=True), encoding="utf-8"
    )
    # Refresh manifest's table list to include the report.
    manifest["tables"]["REPORT.md"] = "REPORT.md"
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    # Recompute sums after manifest refresh (excludes SHA256SUMS.json itself).
    sums = {}
    for path in sorted(out.iterdir()):
        if path.is_file() and path.name != "SHA256SUMS.json":
            sums[path.name] = lib.sha256_file(path)
    (out / "SHA256SUMS.json").write_text(
        json.dumps(sums, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(f"wrote package -> {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="repo root (worktree)")
    parser.add_argument("--out", default="results/bj237_power_feature_support_v1")
    parser.add_argument("--base-commit", default="")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    base_commit = args.base_commit or _detect_base_commit(root)

    core = load_core(root)
    matches = lib.load_xlsm_matches()
    epochs = lib.load_decision_epochs(root)
    print(f"history matches: {len(matches)}; epochs: {len(epochs)}")

    result = build_features(root, matches, epochs, core)
    published = result["published"]
    diagnostics = result["diagnostics"]
    print(f"published cells: {len(published)}")
    print(f"published issues: {published['issue'].nunique() if not published.empty else 0}")
    triplet_ok = published[published["triplet_ok"] & published["line_ok"] & ~published["unseen_mask"]]
    print(f"causal publishable (triplet+line+seen): {len(triplet_ok)} "
          f"cells / {triplet_ok['issue'].nunique() if not triplet_ok.empty else 0} issues")

    summary = support_summary(published)
    calibration = calibration_through_2023(published, matches)
    print(f"support rows by year/league/line: {len(summary)}")
    print(f"calibration rows (<=2023): {len(calibration)}")

    receipt = lib.source_receipt(root, base_commit)
    receipt["outputs"] = {
        "published_cells": int(len(published)),
        "published_issues": int(published["issue"].nunique()) if not published.empty else 0,
        "causal_publishable_cells": int(len(triplet_ok)),
        "causal_publishable_issues": int(triplet_ok["issue"].nunique()) if not triplet_ok.empty else 0,
        "support_groups": int(len(summary)),
        "calibration_groups": int(len(calibration)),
    }
    frames = {
        "power_features": published,
        "power_feature_diagnostics": diagnostics,
        "support_summary": summary,
        "calibration_through_2023": calibration,
    }
    write_package(Path(args.out), frames, receipt, base_commit)


def _detect_base_commit(root: Path) -> str:
    import subprocess
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
        ).strip()
    except Exception:  # noqa: BLE001
        return ""


if __name__ == "__main__":
    main()
