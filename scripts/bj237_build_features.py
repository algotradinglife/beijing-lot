#!/usr/bin/env python3
"""#237 causal league/team power feature builder (REQ-PW01..PW05, PW08) — R2.

Reusable builder producing timestamp-safe league/team/matchup strength features
on the canonical fixture identity.  The feature engine is the accepted #180
team-matchup core (sequential EWMA/Elo/poisson state machine), driven here on
the #203 decision-epoch semantics and canonical identity dictionaries.

R2 rework (EV R1 REJECT):
- C-01: native line is FAIL-CLOSED.  A missing / NaN / non-finite line is
  never coerced to 0.0; such rows are line_ok=False, triplet_ok=False and are
  never publishable.  The #180 core's internal ``finite(default=0.0)`` is only
  ever reached with a validated grid line on publishable rows.
- C-03: support_summary keyed by (issue, year, league, line); calibration keyed
  by (issue, year, league, line, outcome).  Match counts are per-issue.
- C-04: canonical fixture_id per #234 contract; identity_status per fixture.
- E-02: immutable atomic publication (fail-on-existing, same-parent staging,
  fsync, atomic rename); full schema with physical/logical types; manifest
  binds producer HEAD and receipts only sources that actually participate.

Outputs (immutable, under results/bj237_power_feature_support_v2/):
  - power_features.parquet        long-form per (issue, match_idx, outcome) rows
  - power_feature_diagnostics.parquet  per-match diagnostics + masks
  - support_summary.parquet       support by issue/year/league/line
  - calibration_through_2023.parquet   calibration table (<=2023 labels only)
  - feature_schema.json           versioned feature schema (full)
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

# #234 atomic publication (E-02): same-parent staging + fsync + rename.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from source_schema import publication as pub  # noqa: E402

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

    R2 line semantics (C-01): a target row is publishable only when its
    ``handicap_line_norm`` is a non-null finite member of the native BJ grid.
    Rows with a missing/NaN/non-finite/off-grid line are line_ok=False,
    triplet_ok=False, power_probability=None.
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
    # C-04: duplicate (issue, match_idx) fixtures are AMBIGUOUS (never publish).
    targets["_dup_key"] = targets.duplicated(["issue", "match_idx"], keep=False)

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
            # C-01 FAIL-CLOSED line gate — evaluated BEFORE the core call so
            # the core's internal finite(default=0.0) is only ever reached
            # with a validated grid line on publishable rows.
            line_value = lib.line_value(trow["handicap_line_norm"])
            line_ok = line_value is not None
            if line_ok:
                prob, diag, vectors = state.probabilities(
                    match_row, naive_cutoff, configuration="TEAM_PRIMARY"
                )
            else:
                # Compute diagnostics without trusting a coerced 0-line; the
                # core still needs a float for its internal math, so pass the
                # raw value only for state diagnostics and never publish it.
                prob = None
                try:
                    _, diag, vectors = state.probabilities(
                        match_row, naive_cutoff, configuration="TEAM_PRIMARY"
                    )
                except Exception:  # noqa: BLE001
                    diag = {
                        "home_history_n": 0, "away_history_n": 0,
                        "min_history_n": 0, "home_elo": 0.0, "away_elo": 0.0,
                        "elo_diff": 0.0, "home_form_points": 0.0,
                        "away_form_points": 0.0, "home_rest_hours": 0.0,
                        "away_rest_hours": 0.0, "home_matches_7d": 0,
                        "away_matches_7d": 0, "home_matches_21d": 0,
                        "away_matches_21d": 0, "home_league_changes": 0,
                        "away_league_changes": 0, "h2h_prior_n": 0,
                        "new_team_fallback": 1,
                    }
                    vectors = {}
            home_id = str(trow["home_team_id"] or "")
            away_id = str(trow["away_team_id"] or "")
            home_depth = diag.get("home_history_n", 0)
            away_depth = diag.get("away_history_n", 0)
            min_depth = diag.get("min_history_n", 0)
            triplet_ok = (
                line_ok
                and prob is not None
                and all(math.isfinite(v) for v in prob)
                and abs(sum(prob) - 1.0) < 1e-9
            )
            unseen = min_depth == 0 or not home_id or not away_id
            match_idx = int(trow["match_idx"])
            fixture_id = lib.canonical_fixture_id(str(issue), match_idx)
            identity_status = lib.fixture_identity_status(
                trow["home_team_id"], trow["away_team_id"],
                trow["league"], bool(trow["_dup_key"]),
            )

            base = {
                "issue": issue,
                "fixture_id": fixture_id,
                "identity_status": identity_status,
                "match_idx": match_idx,
                "match_id": int(trow["match_id"]),
                "kickoff_ts_utc": trow["kickoff_utc"],
                "decision_epoch_utc": epoch,
                "year": int(str(issue)[:2]) + 2000 if str(issue)[:2].isdigit() else -1,
                "league": trow["league"],
                "home_team_id": home_id,
                "away_team_id": away_id,
                "native_handicap_line": line_value,
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

            for code, value in zip(lib.OUTCOME_CODES, prob if prob else (None, None, None)):
                row = dict(base)
                row["outcome_code"] = code
                row["power_probability"] = round(float(value), 10) if triplet_ok else None
                published.append(row)

            diag_row = dict(base)
            diag_row.update({f"diag_{key}": value for key, value in diag.items()})
            # E-01 cross-table anchor: published triplet is duplicated into
            # diagnostics so a tamper of power_features alone is detected by
            # cross-file comparison (probabilities, line, teams, league, epoch,
            # depth all have a second copy here).
            for code, value in zip(lib.OUTCOME_CODES, prob if prob else (None, None, None)):
                diag_row[f"power_p{code}"] = (
                    round(float(value), 10)
                    if (triplet_ok and value is not None)
                    else None
                )
            diag_row["history_event_sha256"] = state.history_event_sha256
            diagnostics.append(diag_row)

    published_df = pd.DataFrame(published)
    diagnostics_df = pd.DataFrame(diagnostics)
    return {"published": published_df, "diagnostics": diagnostics_df}


def support_summary(published: pd.DataFrame) -> pd.DataFrame:
    """Support by issue/year/league/line with only causal, publishable rows.

    C-03: the contract key is (issue, year, league, line).  ``issues`` is the
    nunique within the group (=1 per group); ``matches`` is the per-issue
    match_idx nunique (no cross-issue folding because issue is a key member).
    """
    ok = published[
        published["triplet_ok"]
        & published["line_ok"]
        & published["native_handicap_line"].notna()
        & ~published["unseen_mask"]
    ].copy()
    grouped = (
        ok.groupby(["issue", "year", "league", "native_handicap_line"])
        .agg(
            rows=("outcome_code", "count"),
            issues=("issue", "nunique"),
            matches=("match_idx", "nunique"),
        )
        .reset_index()
    )
    return grouped


def calibration_through_2023(
    published: pd.DataFrame, matches: pd.DataFrame
) -> pd.DataFrame:
    """Calibration on <=2023 labels only (REQ-PW07).  Never touches 2024+.

    C-03: keyed by (issue, year, league, line, outcome) per contract.
    """
    cal = published[
        published["triplet_ok"]
        & published["line_ok"]
        & published["native_handicap_line"].notna()
        & published["year"].le(2023)
        & ~published["unseen_mask"]
    ].copy()
    empty_cols = [
        "issue", "year", "league", "native_handicap_line", "outcome_code",
        "n", "mean_pred", "mean_actual",
    ]
    if cal.empty:
        return pd.DataFrame(columns=empty_cols)
    # Join actual outcome from xlsm match_features (result_code).
    actual = matches[["issue", "match_idx", "result_code"]].drop_duplicates(
        ["issue", "match_idx"]
    )
    actual["issue"] = actual["issue"].astype(str)
    merged = cal.merge(actual, on=["issue", "match_idx"], how="left")
    merged["actual"] = merged["result_code"].astype(str)
    valid = merged[merged["actual"].isin(lib.OUTCOME_CODES)].copy()
    if valid.empty:
        return pd.DataFrame(columns=empty_cols)
    valid["hit"] = valid["outcome_code"] == valid["actual"]
    grouped = (
        valid.groupby(["issue", "year", "league", "native_handicap_line", "outcome_code"])
        .agg(
            n=("hit", "count"),
            mean_pred=("power_probability", "mean"),
            mean_actual=("hit", "mean"),
        )
        .reset_index()
    )
    return grouped


# ---------------------------------------------------------------------------
# Full feature schema (E-02): physical + logical types, nullability, domains,
# foreign keys for every published table.
# ---------------------------------------------------------------------------
def feature_schema() -> dict:
    def col(name, ptype, ltype, nullable, domain=None, note=""):
        return {
            "name": name, "physical_type": ptype, "logical_type": ltype,
            "nullable": nullable, "domain": domain or None, "note": note or None,
        }

    return {
        "contract": lib.CONTRACT,
        "version": lib.VERSION,
        "decision_epoch": "issue-level feature_cutoff_ts_utc from bj203 issue_offsets",
        "completion_embargo_minutes": lib.COMPLETION_EMBARGO_MINUTES,
        "feature_engine": "scripts/bj180_team_matchup_core.py (accepted #180 core, "
                          "TEAM_PRIMARY configuration)",
        "outcome_domain": "3/1/0 (BJ native handicap result)",
        "line_semantics": "native_handicap_line is the fixture's BJ handicap "
                          "normalized line, FAIL-CLOSED: publishable rows carry a "
                          "non-null finite grid member; missing/NaN lines are "
                          "line_ok=False and never publishable",
        "identity_contract": "BJ-UNIFIED-DATA-SOURCE-SCHEMA-001 (#234): fixture_id = "
                             "fix_{issue}_{match_idx}_{sha256(issue:match)[:16]}, "
                             "unique within (issue, match_idx)",
        "tables": {
            "power_features": {
                "description": "long-form per (issue, match_idx, outcome_code)",
                "key": ["issue", "match_idx", "outcome_code"],
                "fks": [{"columns": ["issue", "match_idx"],
                         "references": "fixture (issue_code, match_idx) #234"}],
                "columns": [
                    col("issue", "string", "string", False, "BJ issue code"),
                    col("fixture_id", "string", "string", False, "canonical #234 fixture_id"),
                    col("identity_status", "string", "string", False,
                        "{CANONICAL,ALIAS,AMBIGUOUS,UNIDENTIFIED}"),
                    col("match_idx", "int64", "int64", False, ">= 1"),
                    col("match_id", "int64", "int64", False, "xlsm source key"),
                    col("kickoff_ts_utc", "timestamp[us, tz=UTC]", "datetime", False,
                        "Asia/Shanghai -> UTC"),
                    col("decision_epoch_utc", "timestamp[us, tz=UTC]", "datetime", False,
                        "#203 feature_cutoff_ts_utc"),
                    col("year", "int64", "int64", False, "2019..2026"),
                    col("league", "string", "string", True, "canonical league"),
                    col("home_team_id", "string", "string", True, "canonical team id"),
                    col("away_team_id", "string", "string", True, "canonical team id"),
                    col("native_handicap_line", "double", "float", True,
                        "native BJ grid {-3..3 step 0.5}; NULL when line_ok=False"),
                    col("line_ok", "bool", "bool", False, "fail-closed line gate"),
                    col("unseen_mask", "bool", "bool", False,
                        "min_history_n == 0 or blank team id"),
                    col("min_history_n", "int64", "int64", False, ">= 0"),
                    col("home_history_n", "int64", "int64", False, ">= 0"),
                    col("away_history_n", "int64", "int64", False, ">= 0"),
                    col("triplet_ok", "bool", "bool", False,
                        "line_ok AND normalized finite triplet"),
                    col("uncertainty", "double", "float", False, "[0, 0.35]"),
                    col("outcome_code", "string", "string", False, "{3,1,0}"),
                    col("power_probability", "double", "float", True,
                        "[0,1] or NULL when triplet_ok=False"),
                ],
            },
            "power_feature_diagnostics": {
                "description": "per-match diagnostics + masks",
                "key": ["issue", "match_idx"],
                "fks": [{"columns": ["issue", "match_idx"],
                         "references": "fixture (issue_code, match_idx) #234"}],
                "columns": [
                    col("issue", "string", "string", False),
                    col("fixture_id", "string", "string", False),
                    col("identity_status", "string", "string", False),
                    col("match_idx", "int64", "int64", False),
                    col("match_id", "int64", "int64", False),
                    col("kickoff_ts_utc", "timestamp[us, tz=UTC]", "datetime", False),
                    col("decision_epoch_utc", "timestamp[us, tz=UTC]", "datetime", False),
                    col("year", "int64", "int64", False),
                    col("league", "string", "string", True),
                    col("home_team_id", "string", "string", True),
                    col("away_team_id", "string", "string", True),
                    col("native_handicap_line", "double", "float", True),
                    col("line_ok", "bool", "bool", False),
                    col("unseen_mask", "bool", "bool", False),
                    col("min_history_n", "int64", "int64", False),
                    col("home_history_n", "int64", "int64", False),
                    col("away_history_n", "int64", "int64", False),
                    col("triplet_ok", "bool", "bool", False),
                    col("uncertainty", "double", "float", False),
                    col("diag_home_elo", "double", "float", True),
                    col("diag_away_elo", "double", "float", True),
                    col("diag_elo_diff", "double", "float", True),
                    col("diag_home_form_points", "double", "float", True),
                    col("diag_away_form_points", "double", "float", True),
                    col("diag_home_rest_hours", "double", "float", True),
                    col("diag_away_rest_hours", "double", "float", True),
                    col("diag_home_matches_7d", "int64", "int64", True),
                    col("diag_away_matches_7d", "int64", "int64", True),
                    col("diag_home_matches_21d", "int64", "int64", True),
                    col("diag_away_matches_21d", "int64", "int64", True),
                    col("diag_home_league_changes", "int64", "int64", True),
                    col("diag_away_league_changes", "int64", "int64", True),
                    col("diag_h2h_prior_n", "int64", "int64", True),
                    col("diag_new_team_fallback", "int64", "int64", True),
                    col("history_event_sha256", "string", "string", False,
                        "chained per-issue state digest (64 hex)"),
                ],
            },
            "support_summary": {
                "description": "causal publishable support by issue/year/league/line",
                "key": ["issue", "year", "league", "native_handicap_line"],
                "fks": [{"columns": ["issue"], "references": "decision_epoch (issue_code) #234"}],
                "columns": [
                    col("issue", "string", "string", False),
                    col("year", "int64", "int64", False),
                    col("league", "string", "string", True),
                    col("native_handicap_line", "double", "float", False),
                    col("rows", "int64", "int64", False, "outcome cells"),
                    col("issues", "int64", "int64", False, "=1 per group"),
                    col("matches", "int64", "int64", False, "per-issue match_idx nunique"),
                ],
            },
            "calibration_through_2023": {
                "description": "calibration by issue/year/league/line/outcome (<=2023)",
                "key": ["issue", "year", "league", "native_handicap_line", "outcome_code"],
                "fks": [{"columns": ["issue"], "references": "decision_epoch (issue_code) #234"}],
                "columns": [
                    col("issue", "string", "string", False),
                    col("year", "int64", "int64", False, "<= 2023"),
                    col("league", "string", "string", True),
                    col("native_handicap_line", "double", "float", False),
                    col("outcome_code", "string", "string", False, "{3,1,0}"),
                    col("n", "int64", "int64", False, "> 0"),
                    col("mean_pred", "double", "float", False, "[0,1]"),
                    col("mean_actual", "double", "float", False, "[0,1]"),
                ],
            },
        },
    }


def write_package(out: Path, frames: dict, receipt: dict, producer_commit: str,
                  aux_frames: dict | None = None,
                  report_md: str | None = None) -> Path:
    """Immutable atomic publication (E-02).

    - refuses to overwrite an existing package (fail-on-existing),
    - stages in the same parent directory, fsyncs the tree, then atomically
      renames into place (#234 publication module),
    - writes the full schema and a manifest bound to the producer HEAD,
    - ``aux_frames`` maps CSV filenames (e.g. support_loss_waterfall.csv) to
      DataFrames written inside the same atomic package (so the builder and
      the waterfall evidence can never drift apart — C-01),
    - ``report_md`` is written as REPORT.md inside the package.
    """
    aux_frames = aux_frames or {}

    def populate(staging: Path) -> None:
        for name, frame in frames.items():
            if frame is not None and not frame.empty:
                frame.to_parquet(staging / f"{name}.parquet", index=False)
        for name, value in aux_frames.items():
            if isinstance(value, dict):
                (staging / name).write_text(
                    json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8"
                )
            elif value is not None and not value.empty:
                value.to_csv(staging / name, index=False)
        if report_md:
            (staging / "REPORT.md").write_text(report_md, encoding="utf-8")

        (staging / "feature_schema.json").write_text(
            json.dumps(feature_schema(), indent=2, ensure_ascii=False), encoding="utf-8"
        )

        manifest = {
            "contract": lib.CONTRACT,
            "version": lib.VERSION,
            "producer_commit_sha": producer_commit,
            "built_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "source_receipt": receipt,
            "tables": {
                name: f"{name}.parquet"
                for name in frames
                if frames.get(name) is not None and not frames[name].empty
            },
            "aux_files": sorted(aux_frames.keys()),
            "headline": _headline(frames),
            # E-01 anchor: per-issue history digests recorded at build time.
            # The verifier cross-checks diagnostics against this map, so a
            # whole-issue digest forgery (keeping per-issue consistency) is
            # still detected unless the attacker also rewrites the manifest
            # consistently — a full-rebuild attack, not a tamper.
            "issue_digests": _issue_digests(frames),
        }
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        sums = {}
        for path in sorted(staging.iterdir()):
            if path.is_file() and path.name != "SHA256SUMS.json":
                sums[path.name] = lib.sha256_file(path)
        (staging / "SHA256SUMS.json").write_text(
            json.dumps(sums, indent=2, sort_keys=True), encoding="utf-8"
        )

    return pub.atomic_publish_directory(out, populate, force=False)


def _issue_digests(frames: dict) -> dict:
    diag = frames.get("power_feature_diagnostics")
    if diag is None or diag.empty:
        return {}
    digests = (
        diag.groupby("issue")["history_event_sha256"]
        .first()
        .astype(str)
        .to_dict()
    )
    return digests


def _headline(frames: dict) -> dict:
    published = frames.get("power_features")
    if published is None or published.empty:
        return {}
    publishable = published[
        published["triplet_ok"]
        & published["line_ok"]
        & published["native_handicap_line"].notna()
        & ~published["unseen_mask"]
    ]
    summary = frames.get("support_summary")
    calibration = frames.get("calibration_through_2023")
    return {
        "published_cells": int(len(published)),
        "published_issues": int(published["issue"].nunique()),
        "causal_publishable_cells": int(len(publishable)),
        "causal_publishable_issues": int(publishable["issue"].nunique())
        if not publishable.empty else 0,
        "support_groups": int(len(summary)) if summary is not None else 0,
        "calibration_groups": int(len(calibration)) if calibration is not None else 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="repo root (worktree)")
    parser.add_argument("--out", default="results/bj237_power_feature_support_v2")
    parser.add_argument("--producer-commit", default="")
    parser.add_argument("--report", default="", help="path to REPORT.md to embed")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    producer_commit = args.producer_commit or _detect_head(root)

    core = load_core(root)
    matches = lib.load_xlsm_matches()
    epochs = lib.load_decision_epochs(root)
    print(f"history matches: {len(matches)}; epochs: {len(epochs)}")

    result = build_features(root, matches, epochs, core)
    published = result["published"]
    diagnostics = result["diagnostics"]
    print(f"published cells: {len(published)}")
    print(f"published issues: {published['issue'].nunique() if not published.empty else 0}")
    triplet_ok = published[
        published["triplet_ok"]
        & published["line_ok"]
        & published["native_handicap_line"].notna()
        & ~published["unseen_mask"]
    ]
    print(f"causal publishable (triplet+line+seen): {len(triplet_ok)} "
          f"cells / {triplet_ok['issue'].nunique() if not triplet_ok.empty else 0} issues")

    summary = support_summary(published)
    calibration = calibration_through_2023(published, matches)
    print(f"support rows by issue/year/league/line: {len(summary)}")
    print(f"calibration rows (<=2023): {len(calibration)}")

    receipt = lib.source_receipt(root, producer_commit)
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
    # REQ-PW06 evidence is generated in the SAME atomic publication so the
    # builder and the waterfall can never drift apart (EV C-01 pointed out the
    # R1 builder/waterfall contradiction).
    waterfall_df = build_waterfall_evidence(root, matches, epochs)
    inter = _ppower_intersection(root)
    aux_frames = {
        "support_loss_waterfall.csv": waterfall_df,
        "ppower_intersection_reconstruction.csv": pd.DataFrame([inter]).T.reset_index().rename(
            columns={"index": "metric", 0: "value"}
        ),
        "external_football_data_census.csv": lib.load_football_data_coverage(),
        "waterfall_receipt.json": {
            "waterfall_stages": len(waterfall_df),
            "n_raw": int(waterfall_df.loc[waterfall_df["stage"] == 0, "rows"].iloc[0]),
            "n_target_not_started": int(
                waterfall_df.loc[waterfall_df["stage"] == 4, "rows"].iloc[0]
            ),
            "ppower_reconstruction": inter,
        },
    }
    write_package(Path(args.out), frames, receipt, producer_commit, aux_frames,
                  report_md=_read_report(args.report))


def build_waterfall_evidence(
    root: Path, matches: pd.DataFrame, epochs: pd.DataFrame
) -> pd.DataFrame:
    """REQ-PW06 support-loss waterfall from primitives (C-02)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import bj237_waterfall as wf

    return wf.build_full_waterfall(matches, epochs)


def _ppower_intersection(root: Path) -> dict:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import bj237_waterfall as wf

    return wf.reconstruct_229_power_intersection(root)


def _read_report(path: str) -> str | None:
    if not path:
        return None
    return Path(path).read_text(encoding="utf-8")


def _detect_head(root: Path) -> str:
    import subprocess
    try:
        return subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
        ).strip()
    except Exception:  # noqa: BLE001
        return ""


if __name__ == "__main__":
    main()
