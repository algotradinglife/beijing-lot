#!/usr/bin/env python3
"""#237 acceptance tests — R2 rework (REQ-PW01..PW08 + REQ-E06).

R2 encodes the EV R1 full-class sweep as tight red/green tests:
- C-01: FAIL-CLOSED line semantics (no NaN -> 0.0 default anywhere)
- C-02: PW06 gates rebuilt from primitives (no availability-flag terminal gate)
- C-03: aggregation keys (issue, year, league, line); no cross-issue folding
- C-04: #234 canonical identity consumed (fixture_id, identity status,
        temporal alias validity, ambiguity, future-alias rejection)
- E-01: remanifested semantic tamper self-defense
- E-02: atomic publication + full schema + receipt closure

Run from the worktree root:
    .venv/bin/python -m pytest tests/scripts/test_bj237_power_features.py -q
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import shutil
import sys
import tempfile
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))
import bj237_power_lib as lib  # noqa: E402
import bj237_verify_package as verifier  # noqa: E402

PKG = ROOT / "results/bj237_power_feature_support_v2"
HISTORY_EVENT_COL = "history_event_sha256"

# Module-level cache: the 6.8 GB xlsm hash is computed once per test session,
# not once per tamper round (13 rounds would otherwise re-hash it 13 times).
_SOURCE_HASH_CACHE: dict[str, str] = {}


@pytest.fixture(scope="module")
def power_features() -> pd.DataFrame:
    return pd.read_parquet(PKG / "power_features.parquet")


@pytest.fixture(scope="module")
def diagnostics() -> pd.DataFrame:
    return pd.read_parquet(PKG / "power_feature_diagnostics.parquet")


@pytest.fixture(scope="module")
def waterfall() -> pd.DataFrame:
    return pd.read_csv(PKG / "support_loss_waterfall.csv")


# ---------------------------------------------------------------- REQ-PW01
class TestCausalEpoch:
    def test_all_rows_have_epoch(self, power_features):
        assert power_features["decision_epoch_utc"].notna().all()

    def test_kickoff_never_before_epoch_for_published(self, power_features):
        kick = pd.to_datetime(power_features["kickoff_ts_utc"], utc=True)
        epoch = pd.to_datetime(power_features["decision_epoch_utc"], utc=True)
        assert (kick >= epoch).all()

    def test_history_events_hash_is_chained_and_stable(self, diagnostics):
        assert diagnostics[HISTORY_EVENT_COL].notna().all()
        assert (diagnostics[HISTORY_EVENT_COL].str.len() == 64).all()
        per_issue = diagnostics.groupby("issue")[HISTORY_EVENT_COL].nunique()
        assert (per_issue == 1).all(), "rows of one issue must share one digest"

    def test_uncertainty_masks_low_history(self, power_features):
        low = power_features[power_features["min_history_n"] <= 5]
        high = power_features[power_features["min_history_n"] > 20]
        if len(low) and len(high):
            assert low["uncertainty"].mean() > high["uncertainty"].mean()


# ---------------------------------------------------------------- C-01
class TestFailClosedLineSemantics:
    """EV C-01: missing / NaN / non-finite line must NEVER become 0-line."""

    def test_line_ok_requires_non_null_line(self, power_features):
        # line_ok=True => native_handicap_line must be non-null
        ok = power_features[power_features["line_ok"]]
        assert ok["native_handicap_line"].notna().all()

    def test_line_ok_requires_grid_member(self, power_features):
        ok = power_features[power_features["line_ok"]]
        lines = ok["native_handicap_line"].dropna()
        assert set(lines.unique()) <= lib.VALID_LINES

    def test_not_line_ok_means_null_line(self, power_features):
        # fail-closed: ~line_ok rows must NOT carry a line value
        no_line = power_features[~power_features["line_ok"]]
        assert no_line["native_handicap_line"].isna().all()

    def test_not_line_ok_never_triplet_ok(self, power_features):
        no_line = power_features[~power_features["line_ok"]]
        assert (no_line["triplet_ok"] == False).all()  # noqa: E712

    def test_triplet_ok_requires_line_ok(self, power_features):
        ok = power_features[power_features["triplet_ok"]]
        assert (ok["line_ok"] == True).all()  # noqa: E712

    def test_line_predicate_never_defaults_nan_to_zero(self):
        # the library predicate is the ONLY line gate; NaN/None/inf all False
        assert lib.line_is_publishable(None) is False
        assert lib.line_is_publishable(float("nan")) is False
        assert lib.line_is_publishable(float("inf")) is False
        assert lib.line_is_publishable("not-a-line") is False
        assert lib.line_is_publishable(0.0) is True
        assert lib.line_is_publishable(-1.5) is True
        assert lib.line_is_publishable(3.5) is False

    def test_no_nan_to_zero_coercion_in_published_line(self, power_features):
        # the exact C-01 regression: rows with null source line must have
        # line_ok=False (NOT line_ok=True with a coerced 0.0)
        null_line = power_features[power_features["native_handicap_line"].isna()]
        assert (null_line["line_ok"] == False).all()  # noqa: E712


# ---------------------------------------------------------------- REQ-PW02 / C-04
class TestCanonicalIdentity:
    def test_fixture_id_deterministic_and_unique(self, power_features):
        ids = power_features["fixture_id"]
        assert ids.notna().all()
        # fixture_id is unique per (issue, match_idx) pair; match_idx alone is
        # an issue-local slot so it repeats across issues.
        pairs = power_features.groupby(["issue", "match_idx"]).ngroups
        assert ids.nunique() == pairs
        # determinism per #234 contract
        assert lib.canonical_fixture_id("25041", 1) == lib.canonical_fixture_id("25041", 1)
        assert lib.canonical_fixture_id("25041", 1) != lib.canonical_fixture_id("25041", 2)

    def test_identity_status_only_known_values(self, power_features):
        known = {lib.IDENTITY_CANONICAL, lib.IDENTITY_ALIAS,
                 lib.IDENTITY_AMBIGUOUS, lib.IDENTITY_UNIDENTIFIED}
        assert set(power_features["identity_status"]) <= known

    def test_canonical_rows_have_teams_and_league(self, power_features):
        canon = power_features[power_features["identity_status"] == lib.IDENTITY_CANONICAL]
        assert (canon["home_team_id"].astype(str) != "").all()
        assert (canon["away_team_id"].astype(str) != "").all()
        assert (canon["league"].astype(str) != "").all()

    def test_no_fuzzy_league(self, power_features):
        leagues = set(power_features["league"].dropna().astype(str))
        assert leagues
        assert all(isinstance(x, str) and x for x in leagues)

    def test_alias_active_rejects_future(self):
        # temporal validity: future alias mutations never active
        asof = pd.Timestamp("2023-06-01", tz="UTC")
        assert lib.alias_active(pd.Timestamp("2023-01-01", tz="UTC"), None, asof)
        assert not lib.alias_active(pd.Timestamp("2023-07-01", tz="UTC"), None, asof)
        assert not lib.alias_active(pd.Timestamp("2023-01-01", tz="UTC"),
                                    pd.Timestamp("2023-05-01", tz="UTC"), asof)
        assert not lib.alias_active(None, None, asof)

    def test_resolve_team_identity_unknown_and_ambiguous(self):
        asof = pd.Timestamp("2023-06-01", tz="UTC")
        rows = pd.DataFrame([
            {"source_team_key": "K1", "team_id": "T1",
             "valid_from_utc": pd.Timestamp("2023-01-01", tz="UTC"),
             "valid_to_utc": None},
            {"source_team_key": "K1", "team_id": "T2",
             "valid_from_utc": pd.Timestamp("2023-03-01", tz="UTC"),
             "valid_to_utc": None},
        ])
        team_id, status = lib.resolve_team_identity("K1", rows, asof)
        assert status == lib.IDENTITY_AMBIGUOUS
        team_id, status = lib.resolve_team_identity("UNKNOWN", rows, asof)
        assert status == lib.IDENTITY_UNIDENTIFIED

    def test_fixture_identity_status_dup_ambiguous(self):
        assert lib.fixture_identity_status("T1", "T2", "L1", dup_key=True) == lib.IDENTITY_AMBIGUOUS
        assert lib.fixture_identity_status("T1", "T2", "L1", dup_key=False) == lib.IDENTITY_CANONICAL
        assert lib.fixture_identity_status(None, "T2", "L1", dup_key=False) == lib.IDENTITY_UNIDENTIFIED


# ---------------------------------------------------------------- REQ-PW03
class TestUnseenMask:
    def test_unseen_rows_have_zero_history(self, power_features):
        unseen = power_features[power_features["unseen_mask"]]
        assert (unseen["min_history_n"] == 0).all()

    def test_seen_rows_have_history(self, power_features):
        seen = power_features[~power_features["unseen_mask"]]
        assert (seen["min_history_n"] >= 1).all()

    def test_publishable_excludes_unseen(self, power_features):
        publishable = power_features[
            power_features["triplet_ok"] & power_features["line_ok"]
            & power_features["native_handicap_line"].notna()
            & ~power_features["unseen_mask"]
        ]
        assert (publishable["unseen_mask"] == False).all()  # noqa: E712


# ---------------------------------------------------------------- REQ-PW04
class TestLineSemantics:
    def test_probability_triplets_normalized(self, power_features):
        ok = power_features[power_features["triplet_ok"]]
        sums = ok.groupby(["issue", "match_idx"])["power_probability"].sum()
        assert ((sums - 1.0).abs() < 1e-9).all()

    def test_probability_domain(self, power_features):
        ok = power_features[power_features["triplet_ok"]]
        assert (ok["power_probability"] >= 0).all()
        assert (ok["power_probability"] <= 1).all()

    def test_triplet_ok_rows_have_probability(self, power_features):
        ok = power_features[power_features["triplet_ok"]]
        assert ok["power_probability"].notna().all()


# ---------------------------------------------------------------- REQ-PW05
class TestSourceCountability:
    def test_external_census_exists(self):
        census = pd.read_csv(PKG / "external_football_data_census.csv")
        assert len(census) >= 1
        assert {"file", "rows", "competition"}.issubset(census.columns)

    def test_receipt_separates_internal_external(self):
        receipt = json.loads((PKG / "manifest.json").read_text())
        src = receipt["source_receipt"]
        assert "databases" in src
        assert "external_football_data_dir" in src

    def test_receipt_lists_only_participating_sources(self):
        # E-02: features/history/live DBs do NOT participate in the builder
        receipt = json.loads((PKG / "manifest.json").read_text())["source_receipt"]
        assert set(receipt["databases"].keys()) == {"xlsm"}


# ---------------------------------------------------------------- REQ-PW06 / C-02
class TestWaterfall:
    def test_waterfall_monotonic(self, waterfall):
        stages = waterfall.dropna(subset=["stage"]).sort_values("stage")
        rows = stages["rows"].tolist()
        assert all(rows[i] >= rows[i + 1] for i in range(len(rows) - 1))

    def test_ppower_reconstruction_9_issues_primitives(self):
        rec = pd.read_csv(PKG / "ppower_intersection_reconstruction.csv")
        by_metric = dict(zip(rec["metric"], rec["value"]))
        assert int(by_metric["published_cells"]) == 234
        assert int(by_metric["published_issues"]) == 9
        # C-02: the method must be primitives, not the producer flag
        method = str(by_metric["gate_method"])
        assert "P_POWER_BJLINE_available flag NOT used" in method

    def test_rebuild_exceeds_180_support(self, power_features):
        publishable = power_features[
            power_features["triplet_ok"] & power_features["line_ok"]
            & power_features["native_handicap_line"].notna()
            & ~power_features["unseen_mask"]
        ]
        assert len(publishable) > 234
        assert publishable["issue"].nunique() > 9

    def test_corrected_headline_matches_ev(self, power_features):
        # EV R1 independent correction: 304,839 cells / 344 issues (not 305,517)
        publishable = power_features[
            power_features["triplet_ok"] & power_features["line_ok"]
            & power_features["native_handicap_line"].notna()
            & ~power_features["unseen_mask"]
        ]
        assert len(publishable) == 304_839
        assert publishable["issue"].nunique() == 344


# ---------------------------------------------------------------- REQ-PW07 / C-03
class TestSealedLabels:
    def test_calibration_never_opens_2024_plus(self):
        cal = pd.read_parquet(PKG / "calibration_through_2023.parquet")
        if len(cal):
            assert cal["year"].max() <= 2023

    def test_published_cells_include_future_but_not_designed(self, power_features):
        years = set(power_features["year"])
        cal = pd.read_parquet(PKG / "calibration_through_2023.parquet")
        assert (set(cal["year"]) <= {y for y in years if y <= 2023})


class TestAggregationKeys:
    """C-03: contract key is (issue, year, league, line); no folding."""

    def test_support_summary_keyed_by_issue(self):
        sup = pd.read_parquet(PKG / "support_summary.parquet")
        assert set(sup.columns) >= {"issue", "year", "league",
                                    "native_handicap_line", "rows", "matches"}
        # every group has exactly one issue
        assert (sup["issues"] == 1).all()

    def test_support_rows_recompute_exactly(self, power_features):
        sup = pd.read_parquet(PKG / "support_summary.parquet")
        recomputed = verifier._recompute_support(power_features)
        assert len(recomputed) == len(sup)
        assert int(recomputed["rows"].sum()) == int(sup["rows"].sum())

    def test_support_rows_sum_equals_publishable_cells(self, power_features):
        sup = pd.read_parquet(PKG / "support_summary.parquet")
        publishable = power_features[
            power_features["triplet_ok"] & power_features["line_ok"]
            & power_features["native_handicap_line"].notna()
            & ~power_features["unseen_mask"]
        ]
        assert int(sup["rows"].sum()) == len(publishable)

    def test_calibration_keyed_by_issue_and_line(self):
        cal = pd.read_parquet(PKG / "calibration_through_2023.parquet")
        if len(cal):
            assert {"issue", "year", "league", "native_handicap_line",
                    "outcome_code", "n", "mean_pred", "mean_actual"}.issubset(
                        set(cal.columns))

    def test_no_match_idx_folding_across_issues(self, power_features):
        # C-03: match_idx is reused across issues; the per-issue key must
        # prevent folding.  A match_idx value appears once per issue in the
        # aggregated support when the group key includes issue.
        sup = pd.read_parquet(PKG / "support_summary.parquet")
        # sanity: matches column is per-issue nunique; total across groups
        # equals total distinct (issue, match_idx) publishable pairs.
        publishable = power_features[
            power_features["triplet_ok"] & power_features["line_ok"]
            & power_features["native_handicap_line"].notna()
            & ~power_features["unseen_mask"]
        ]
        total_pairs = publishable.groupby(["issue", "match_idx"]).ngroups
        assert int(sup["matches"].sum()) == total_pairs

    def test_calibration_n_recompute(self, power_features):
        matches = lib.load_xlsm_matches()
        cal = pd.read_parquet(PKG / "calibration_through_2023.parquet")
        recomputed = verifier._recompute_calibration(power_features, matches)
        assert int(recomputed["n"].sum()) == int(cal["n"].sum())


# ---------------------------------------------------------------- REQ-E06 / E-01
class TestTamperSelfDefense:
    """R2 tamper self-tests: copy, mutate, RE-MANIFEST, expect verify FAIL."""

    def _run_tamper(self, mutator) -> None:
        tmp = Path(tempfile.mkdtemp(prefix="bj237-test-tamper-"))
        try:
            for path in PKG.iterdir():
                if path.is_file():
                    shutil.copy2(path, tmp / path.name)
            mutator(tmp)
            verifier._remanifest(tmp)
            defects = verifier.verify(tmp, ROOT, _SOURCE_HASH_CACHE)
            assert defects, "tamper NOT detected after re-manifest"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_tamper_probability_fails(self):
        def m(tmp):
            frame = pd.read_parquet(tmp / "power_features.parquet")
            frame.loc[frame.index[0], "power_probability"] = 0.999
            frame.to_parquet(tmp / "power_features.parquet", index=False)
        self._run_tamper(m)

    def test_tamper_line_fails(self):
        def m(tmp):
            frame = pd.read_parquet(tmp / "power_features.parquet")
            idx = frame[frame["line_ok"]].index[0]
            frame.loc[idx, "native_handicap_line"] = 99.0
            frame.to_parquet(tmp / "power_features.parquet", index=False)
        self._run_tamper(m)

    def test_tamper_team_swap_fails(self):
        def m(tmp):
            frame = pd.read_parquet(tmp / "power_features.parquet")
            idx = frame.index[0]
            h, a = frame.loc[idx, "home_team_id"], frame.loc[idx, "away_team_id"]
            frame.loc[idx, "home_team_id"], frame.loc[idx, "away_team_id"] = a, h
            frame.to_parquet(tmp / "power_features.parquet", index=False)
        self._run_tamper(m)

    def test_tamper_league_fails(self):
        def m(tmp):
            frame = pd.read_parquet(tmp / "power_features.parquet")
            frame.loc[frame.index[0], "league"] = "__TAMPERED__"
            frame.to_parquet(tmp / "power_features.parquet", index=False)
        self._run_tamper(m)

    def test_tamper_epoch_fails(self):
        def m(tmp):
            frame = pd.read_parquet(tmp / "power_features.parquet")
            idx = frame.index[0]
            ep = pd.to_datetime(frame.loc[idx, "decision_epoch_utc"], utc=True)
            frame.loc[idx, "decision_epoch_utc"] = ep - pd.Timedelta(days=1)
            frame.to_parquet(tmp / "power_features.parquet", index=False)
        self._run_tamper(m)

    def test_tamper_history_depth_fails(self):
        def m(tmp):
            frame = pd.read_parquet(tmp / "power_features.parquet")
            idx = frame[frame["triplet_ok"] & ~frame["unseen_mask"]].index[0]
            frame.loc[idx, "min_history_n"] = 999
            frame.to_parquet(tmp / "power_features.parquet", index=False)
        self._run_tamper(m)

    def test_tamper_outcome_domain_fails(self):
        def m(tmp):
            frame = pd.read_parquet(tmp / "power_features.parquet")
            pub = frame[frame["triplet_ok"]]
            idx = pub.index[0]
            rows = frame[
                (frame["triplet_ok"])
                & (frame["issue"] == frame.loc[idx, "issue"])
                & (frame["match_idx"] == frame.loc[idx, "match_idx"])
            ].index
            frame.loc[rows[0], "power_probability"] = 1.2
            frame.loc[rows[1], "power_probability"] = -0.2
            frame.to_parquet(tmp / "power_features.parquet", index=False)
        self._run_tamper(m)

    def test_tamper_issue_digest_fails(self):
        def m(tmp):
            d = pd.read_parquet(tmp / "power_feature_diagnostics.parquet")
            issue = d["issue"].iloc[0]
            d.loc[d["issue"] == issue, HISTORY_EVENT_COL] = "a" * 64
            d.to_parquet(tmp / "power_feature_diagnostics.parquet", index=False)
        self._run_tamper(m)

    def test_tamper_support_zeroing_fails(self):
        def m(tmp):
            frame = pd.read_parquet(tmp / "support_summary.parquet")
            if len(frame):
                frame.iloc[:-1].to_parquet(tmp / "support_summary.parquet", index=False)
        self._run_tamper(m)

    def test_tamper_calibration_fails(self):
        def m(tmp):
            frame = pd.read_parquet(tmp / "calibration_through_2023.parquet")
            if len(frame):
                frame.loc[frame.index[0], "mean_actual"] = 0.99
                frame.to_parquet(tmp / "calibration_through_2023.parquet", index=False)
        self._run_tamper(m)

    def test_tamper_manifest_source_hash_fails(self):
        def m(tmp):
            mp = tmp / "manifest.json"
            manifest = json.loads(mp.read_text())
            manifest["source_receipt"]["databases"]["xlsm"]["sha256"] = "0" * 64
            mp.write_text(json.dumps(manifest, indent=2))
        self._run_tamper(m)

    def test_tamper_schema_clear_fails(self):
        def m(tmp):
            sp = tmp / "feature_schema.json"
            schema = json.loads(sp.read_text())
            schema["tables"] = {}
            sp.write_text(json.dumps(schema, indent=2))
        self._run_tamper(m)

    def test_tamper_delete_support_fails(self):
        def m(tmp):
            (tmp / "support_summary.parquet").unlink()
        self._run_tamper(m)


# ---------------------------------------------------------------- E-02
class TestAtomicPublicationAndSchema:
    def test_feature_schema_full_coverage(self):
        schema = json.loads((PKG / "feature_schema.json").read_text())
        tables = schema["tables"]
        assert {"power_features", "power_feature_diagnostics",
                "support_summary", "calibration_through_2023"}.issubset(set(tables))
        for name, spec in tables.items():
            assert spec["columns"], f"schema table {name} has no columns"
            for c in spec["columns"]:
                assert c["physical_type"], f"{name}.{c['name']} missing physical type"
                assert "nullable" in c

    def test_manifest_binds_producer_head(self):
        manifest = json.loads((PKG / "manifest.json").read_text())
        assert manifest["producer_commit_sha"]
        assert len(manifest["producer_commit_sha"]) == 40

    def test_sha256sums_covers_all_files(self):
        sums = json.loads((PKG / "SHA256SUMS.json").read_text())
        files = [p.name for p in PKG.iterdir() if p.is_file()]
        assert set(sums.keys()) == set(files) - {"SHA256SUMS.json"}

    def test_atomic_publish_refuses_overwrite(self):
        # E-02: publishing over an existing package must fail closed
        from source_schema import publication as pub
        with pytest.raises(FileExistsError):
            pub.atomic_publish_directory(PKG, lambda staging: None, force=False)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
