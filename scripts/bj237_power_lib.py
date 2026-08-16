#!/usr/bin/env python3
"""BJ-UNIFIED-POWER-FEATURE-SUPPORT-001 (#237) shared library — R2 rework.

Rebuild timestamp-safe league/team/matchup strength features on the canonical
fixture identity so the unified learner has an independent pre-event estimate.

Design contracts (frozen by the issue body):
- REQ-PW01: every feature value depends only on events before its decision epoch.
- REQ-PW02: team/league aliases are canonical, temporally valid, never silently
  fuzzy-matched.
- REQ-PW03: unseen/low-history entities carry masks and uncertainty instead of
  future imputation.
- REQ-PW04: score/goal-difference probabilities map exactly to the fixture's
  native BJ line and normalized 3/1/0 outcomes.
- REQ-PW05: internal versus external data contributions are separately countable.
- REQ-PW06: #180 support-loss waterfall is independently reconstructed.
- REQ-PW07: notebook reports support and calibration by issue/year/league/line
  without accessing 2024+ sealed labels for design.
- REQ-PW08: terminal result supplies positive timestamp-safe support or an exact
  UNRECOVERABLE_POWER_SUPPORT receipt.

R2 rework (EV R1 REJECT, 2026-08-16):
- C-01: native line is FAIL-CLOSED.  A missing / NaN / non-finite
  ``handicap_line_norm`` is NEVER coerced to 0.0; ``line_ok`` requires a
  non-null, finite, grid-member value.  No ``finite(value, default=0.0)``
  default anywhere in the publish path (builder, core call site, waterfall,
  summary, verifier, tests).
- C-02: every REQ-PW06 gate is rebuilt from source primitives; the
  producer-written ``P_POWER_BJLINE_available`` flag is never used as a
  terminal gate.  ``same_line`` requires BOTH sides non-null and equal.
- C-03: support/calibration aggregates are keyed by (issue, year, league, line)
  per contract; match counts are per-issue (no cross-issue folding).
- C-04: canonical fixture identity consumes the accepted #234 interface
  (``src/source_schema``): fixture_id = deterministic hash of
  (issue, match_idx); team/league source keys bind via alias semantics;
  unknown/duplicate keys are UNIDENTIFIED / AMBIGUOUS, never fuzzy-matched.

The feature engine is the accepted #180 team-matchup core (sequential state
machine, EWMA attack/defence, Elo, poisson handicap -> 3/1/0), driven on the
canonical identity and decision-epoch semantics of #203/#229.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Mapping

import pandas as pd

CONTRACT = "BJ-UNIFIED-POWER-FEATURE-SUPPORT-001"
VERSION = "bj237-power-feature-support-v2"

# Accepted #234 canonical identity contract (BJ-UNIFIED-DATA-SOURCE-SCHEMA-001).
IDENTITY_CANONICAL = "CANONICAL"
IDENTITY_ALIAS = "ALIAS"
IDENTITY_AMBIGUOUS = "AMBIGUOUS"
IDENTITY_UNIDENTIFIED = "UNIDENTIFIED"

# Absolute repository root where live data lives (data/ is gitignored).
DATA_ROOT = Path(
    "/home/drwho1985/workspace/soccer/beijing-lot/data"
)
XLSM_DB = DATA_ROOT / "derived/beidan_xlsm/beidan_xlsm.sqlite"
FEATURES_DB = DATA_ROOT / "beidan_features.db"
HISTORY_DB = DATA_ROOT / "beidan_history.db"
LIVE_DB = DATA_ROOT / "beidan_live.db"
FOOTBALL_DATA_DIR = DATA_ROOT / "raw/football-data"

# #203 decision-epoch package (issue-level feature cutoff).
BJ203_ISSUE_OFFSETS = Path(
    "results/bj203_causal_tensor_v2/inference/issue_offsets.parquet"
)
# #203 canonical dictionaries.
BJ203_LEAGUE_DICT = Path(
    "results/bj203_causal_tensor_v2/inference/league_dictionary.parquet"
)
BJ203_TEAM_DICT = Path(
    "results/bj203_causal_tensor_v2/inference/team_dictionary.parquet"
)
# #229 divergence profile (P_POWER_BJLINE baseline).
BJ229_INFERENCE_CELLS = Path(
    "results/bj229_divergence_profile_v1/inference_cells.parquet"
)
# #180 Gate A freeze (the power support being rebuilt).
BJ180_FREEZE = Path(
    "results/bj180_gate_a_preoutcome_v2/match_probability_freeze.csv.gz"
)
BJ180_CUTOFF_REGISTRY = Path(
    "results/bj180_gate_a_preoutcome_v2/issue_cutoff_registry.csv"
)
BJ180_FEATURE_COVERAGE = Path(
    "results/bj180_gate_a_preoutcome_v2/feature_coverage.csv"
)
BJ180_SOURCE_BINDING = Path(
    "results/bj180_gate_a_preoutcome_v2/source_binding.json"
)

# Completion embargo: the historical source has no completion timestamp
# (verified by #180 source binding), so a match's final score is only usable
# when its kickoff is at least this many minutes before the decision epoch.
COMPLETION_EMBARGO_MINUTES = 180

OUTCOME_CODES = ("3", "1", "0")
SEALED_LABEL_YEARS = {2024, 2025, 2026}  # 2024+ outcomes are sealed.

# Native BJ handicap grid (REQ-PW04).  A publishable line MUST be a member.
VALID_LINES = frozenset(
    {-3.0, -2.5, -2.0, -1.5, -1.0, -0.5, 0.0,
     0.5, 1.0, 1.5, 2.0, 2.5, 3.0}
)

# Reason codes for the support-loss waterfall.
REASON_IDENTITY_MISSING_TEAM = "IDENTITY_MISSING_TEAM_ID"
REASON_IDENTITY_DUP_KEY = "IDENTITY_DUPLICATE_ISSUE_MATCHIDX"
REASON_IDENTITY_LEAGUE_BLANK = "IDENTITY_LEAGUE_BLANK"
REASON_NO_DECISION_EPOCH = "NO_DECISION_EPOCH"          # issue outside #203 epochs
REASON_EMBARGO_EXCLUDED = "EMBARGO_EXCLUDED"            # kickoff > epoch - embargo
REASON_NOT_ELIGIBLE_HISTORY = "NOT_ELIGIBLE_HISTORY"    # no score / blank team
REASON_TARGET_NO_HISTORY = "TARGET_NO_HISTORY"          # target has zero prior history
REASON_LINE_BLANK = "LINE_BLANK"
REASON_LINE_MISMATCH = "LINE_MISMATCH"                  # source vs target line differ
REASON_INVALID_TRIPLET = "INVALID_TRIPLET"              # non-finite / not normalized


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Canonical identity (REQ-PW02, C-04) — consumes #234 accepted interface.
# ---------------------------------------------------------------------------
def canonical_fixture_id(issue_code: str, match_idx: int) -> str:
    """Deterministic canonical fixture_id per #234 contract.

    rule: fixture_id = fix_{issue_code}_{match_idx}_{sha256(issue:match)[:16]}
    unique within (issue_code, match_idx).
    """
    if not isinstance(match_idx, int) or match_idx < 1:
        raise ValueError(f"match_idx must be int >= 1, got {match_idx!r}")
    raw = f"{issue_code}:{match_idx}".encode("utf-8")
    return f"fix_{issue_code}_{match_idx}_{hashlib.sha256(raw).hexdigest()[:16]}"


def alias_active(
    valid_from_utc: object,
    valid_to_utc: object,
    asof_utc: object,
) -> bool:
    """#234 alias validity: valid_from <= asof < COALESCE(valid_to, +inf).

    NULL valid_to means "current".  A future alias (valid_from > asof) is
    never active — no future alias mutation can leak into the present.
    """
    if valid_from_utc is None or pd.isna(valid_from_utc):
        return False
    if asof_utc is None or pd.isna(asof_utc):
        return False
    if valid_from_utc > asof_utc:
        return False
    if valid_to_utc is not None and not pd.isna(valid_to_utc):
        if asof_utc >= valid_to_utc:
            return False
    return True


def resolve_team_identity(
    source_team_key: object,
    alias_rows: pd.DataFrame,
    asof_utc: object,
) -> tuple[str, str]:
    """Resolve one source team key through #234 alias semantics.

    Returns (team_id, identity_status).  Never fuzzy-matches: a key without an
    active alias row is UNIDENTIFIED; a key with >1 active alias rows is
    AMBIGUOUS (schema violation, blocks ingestion).
    """
    key = "" if source_team_key is None or pd.isna(source_team_key) else str(source_team_key)
    if not key:
        return "", IDENTITY_UNIDENTIFIED
    if alias_rows is None or alias_rows.empty:
        # No alias table supplied: the source key IS the canonical id only
        # when it is a first-party key (xlsm home/away team ids are canonical).
        return key, IDENTITY_CANONICAL
    active = alias_rows[
        (alias_rows["source_team_key"].astype(str) == key)
        & alias_rows.apply(
            lambda r: alias_active(r.get("valid_from_utc"), r.get("valid_to_utc"), asof_utc),
            axis=1,
        )
    ]
    if active.empty:
        return "", IDENTITY_UNIDENTIFIED
    if active["team_id"].nunique() > 1:
        return "", IDENTITY_AMBIGUOUS
    return str(active["team_id"].iloc[0]), IDENTITY_ALIAS


def fixture_identity_status(
    home_team_id: object,
    away_team_id: object,
    league: object,
    dup_key: bool,
) -> str:
    """Canonical fixture identity status per #234 semantics.

    - both team ids present, league present, unique (issue, match_idx)
        -> CANONICAL (first-party xlsm key is the canonical id)
    - duplicate (issue, match_idx) -> AMBIGUOUS (blocks publish)
    - blank team / league -> UNIDENTIFIED
    """
    if dup_key:
        return IDENTITY_AMBIGUOUS
    home_ok = home_team_id is not None and not pd.isna(home_team_id) and str(home_team_id) != ""
    away_ok = away_team_id is not None and not pd.isna(away_team_id) and str(away_team_id) != ""
    league_ok = league is not None and not pd.isna(league) and str(league) != ""
    if home_ok and away_ok and league_ok:
        return IDENTITY_CANONICAL
    return IDENTITY_UNIDENTIFIED


# ---------------------------------------------------------------------------
# Fail-closed line semantics (REQ-PW04, C-01)
# ---------------------------------------------------------------------------
def line_is_publishable(line: object) -> bool:
    """FAIL-CLOSED line gate: non-null, finite, member of the native grid.

    Never coerces NaN / None / inf to 0.0.  This is the ONLY line predicate in
    the publish path.
    """
    if line is None:
        return False
    try:
        value = float(line)
    except (TypeError, ValueError):
        return False
    if not math.isfinite(value):
        return False
    return value in VALID_LINES


def line_value(line: object) -> float | None:
    """Return the publishable line value or None (fail-closed)."""
    return float(line) if line_is_publishable(line) else None


def parse_ts(value: object) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


def load_xlsm_matches() -> pd.DataFrame:
    """Load canonical match identity + settlement-quality features from xlsm."""
    con = sqlite3.connect(f"file:{XLSM_DB}?mode=ro", uri=True)
    try:
        matches = pd.read_sql_query(
            """
            SELECT m.match_id, m.issue, m.match_idx, m.kickoff_ts, m.league,
                   m.home_team_id, m.away_team_id, m.handicap_line_norm,
                   m.sclassid,
                   mf.fthg, mf.ftag, mf.result_code, mf.season_year,
                   mf.handicap_line_norm AS mf_handicap_line_norm
              FROM matches m
              LEFT JOIN match_features mf ON mf.match_id = m.match_id
            """,
            con,
        )
    finally:
        con.close()
    matches["issue"] = matches["issue"].astype(str)
    return matches


def load_decision_epochs(root: Path) -> pd.DataFrame:
    """#203 issue-level feature cutoff (decision epoch) per issue."""
    path = root / BJ203_ISSUE_OFFSETS
    epochs = pd.read_parquet(path)
    epochs["issue"] = epochs["issue"].astype(str)
    epochs["feature_cutoff_ts_utc"] = pd.to_datetime(
        epochs["feature_cutoff_ts_utc"], utc=True
    )
    return epochs


def load_canonical_dictionaries(root: Path):
    league = pd.read_parquet(root / BJ203_LEAGUE_DICT)
    team = pd.read_parquet(root / BJ203_TEAM_DICT)
    return league, team


def kickoff_to_utc(series: pd.Series) -> pd.Series:
    """xlsm kickoff_ts is naive Beijing time (+08:00)."""
    parsed = pd.to_datetime(series, errors="coerce")
    return parsed.dt.tz_localize("Asia/Shanghai").dt.tz_convert("UTC")


def _safe_int(value: object) -> int:
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return -1
        return int(value)
    except (TypeError, ValueError):
        return -1


def build_identity_waterfall(matches: pd.DataFrame, epochs: pd.DataFrame) -> pd.DataFrame:
    """REQ-PW06 waterfall from raw source rows to decision-epoch eligible rows.

    Stages (every gate from primitives — C-02):
      0 raw rows
      1 identity: team ids present (both sides) and issue+match_idx unique
      2 league present
      3 decision epoch exists (#203 issue-level)
    History-eligibility (score present) is reported as a reason, not a stage:
    it qualifies rows as training history, not as publishable targets.
    """
    n0 = len(matches)
    has_both_ids = matches["home_team_id"].notna() & (
        matches["home_team_id"].astype(str) != ""
    ) & matches["away_team_id"].notna() & (matches["away_team_id"].astype(str) != "")
    dup_key = matches.duplicated(["issue", "match_idx"], keep=False)
    identity_ok = has_both_ids & ~dup_key
    n1 = int(identity_ok.sum())
    league_ok = identity_ok & matches["league"].notna() & (matches["league"].astype(str) != "")
    n2 = int(league_ok.sum())
    with_epoch = league_ok & matches["issue"].isin(set(epochs["issue"]))
    n3 = int(with_epoch.sum())
    scored = with_epoch & matches["fthg"].notna() & matches["ftag"].notna()
    n4 = int(scored.sum())

    def reason_counts(mask: pd.Series, reason: str) -> dict:
        subset = matches.loc[mask]
        return {
            "reason": reason,
            "rows": int(len(subset)),
            "issues": int(subset["issue"].nunique()),
        }

    rows = [
        {"stage": 0, "label": "raw source rows", "rows": n0,
         "issues": int(matches["issue"].nunique())},
        {"stage": 1, "label": "identity ok (team ids + unique key)",
         "rows": n1, "issues": int(matches.loc[identity_ok, "issue"].nunique())},
        {"stage": 2, "label": "league present",
         "rows": n2, "issues": int(matches.loc[league_ok, "issue"].nunique())},
        {"stage": 3, "label": "decision epoch exists (#203)",
         "rows": n3, "issues": int(matches.loc[with_epoch, "issue"].nunique())},
    ]
    reasons = [
        reason_counts(~has_both_ids, REASON_IDENTITY_MISSING_TEAM),
        reason_counts(has_both_ids & dup_key, REASON_IDENTITY_DUP_KEY),
        reason_counts(identity_ok & ~league_ok, REASON_IDENTITY_LEAGUE_BLANK),
        reason_counts(league_ok & ~with_epoch, REASON_NO_DECISION_EPOCH),
        reason_counts(with_epoch & ~scored, REASON_NOT_ELIGIBLE_HISTORY),
        reason_counts(scored, "HISTORY_ELIGIBLE_SCORE_PRESENT"),
    ]
    frame = pd.DataFrame(rows + reasons)
    return frame


def load_football_data_coverage() -> pd.DataFrame:
    """External (Football-Data) source census: competition coverage per file."""
    records = []
    for path in sorted(FOOTBALL_DATA_DIR.glob("*.csv")):
        try:
            head = pd.read_csv(path, nrows=1)
        except Exception as exc:  # noqa: BLE001
            records.append({"file": path.name, "rows": 0, "competition": "",
                            "first_date": "", "last_date": "", "error": str(exc)})
            continue
        competition = str(head["Div"].iloc[0]) if "Div" in head else ""
        rows = sum(1 for _ in open(path, encoding="utf-8", errors="replace")) - 1
        try:
            dates = pd.to_datetime(head["Date"], errors="coerce")
            first_date = last_date = ""
        except Exception:  # noqa: BLE001
            first_date = last_date = ""
        records.append({"file": path.name, "rows": rows,
                        "competition": competition, "first_date": first_date,
                        "last_date": last_date, "error": ""})
    return pd.DataFrame(records)


def source_receipt(root: Path, producer_commit: str) -> dict:
    """Exact source/model receipts (REQ-PW05 + deliverable receipts).

    R2 (E-02): only sources that actually participate in the builder are
    listed.  beidan_features.db / beidan_history.db / beidan_live.db are NOT
    read by the feature builder and therefore are not receipted here.
    """
    def db_receipt(path: Path) -> dict:
        return {
            "path": str(path.relative_to(DATA_ROOT)),
            "sha256": sha256_file(path) if path.exists() else None,
            "exists": path.exists(),
        }

    return {
        "contract": CONTRACT,
        "version": VERSION,
        "producer_commit_sha": producer_commit,
        "databases": {
            "xlsm": db_receipt(XLSM_DB),
        },
        "packages": {
            "bj203_issue_offsets": sha256_file(root / BJ203_ISSUE_OFFSETS)
            if (root / BJ203_ISSUE_OFFSETS).exists() else None,
            "bj229_inference_cells": sha256_file(root / BJ229_INFERENCE_CELLS)
            if (root / BJ229_INFERENCE_CELLS).exists() else None,
            "bj180_freeze": sha256_file(root / BJ180_FREEZE)
            if (root / BJ180_FREEZE).exists() else None,
        },
        "external_football_data_dir": {
            "path": str(FOOTBALL_DATA_DIR),
            "files": len(list(FOOTBALL_DATA_DIR.glob("*.csv"))),
        },
        "completion_embargo_minutes": COMPLETION_EMBARGO_MINUTES,
        "embargo_rule": "historical scores usable only when kickoff <= epoch - 180min",
        "decision_epoch_source": "bj203_causal_tensor_v2 issue_offsets "
                                 "(issue-level feature_cutoff_ts_utc)",
        "sealed_label_policy": "2024+ outcomes never opened for design; "
                               "development calibration uses <=2023 labels only",
    }
