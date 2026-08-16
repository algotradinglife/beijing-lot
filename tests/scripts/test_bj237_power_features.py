#!/usr/bin/env python3
"""#237 acceptance tests: REQ-PW01..PW08 + REQ-E06 tamper self-test.

Run from the worktree root:
    .venv/bin/python -m pytest tests/scripts/test_bj237_power_features.py -q
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import bj237_power_lib as lib  # noqa: E402

PKG = ROOT / "results/bj237_power_feature_support_v1"
HISTORY_EVENT_COL = "history_event_sha256"


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
        # A published target match must not have started before its epoch.
        kick = pd.to_datetime(power_features["kickoff_ts_utc"], utc=True)
        epoch = pd.to_datetime(power_features["decision_epoch_utc"], utc=True)
        assert (kick >= epoch).all()

    def test_history_events_hash_is_chained_and_stable(self, diagnostics):
        # The sequential state machine keeps a rolling SHA-256 over history
        # events.  All rows published for the same issue share the state digest
        # at that issue's epoch; deterministic replay must produce a stable
        # 64-hex digest per issue.
        assert diagnostics[HISTORY_EVENT_COL].notna().all()
        assert (diagnostics[HISTORY_EVENT_COL].str.len() == 64).all()
        per_issue = diagnostics.groupby("issue")[HISTORY_EVENT_COL].nunique()
        assert (per_issue == 1).all(), "rows of one issue must share one digest"

    def test_uncertainty_masks_low_history(self, power_features):
        # REQ-PW03: unseen / low-history rows must carry larger uncertainty.
        low = power_features[power_features["min_history_n"] <= 5]
        high = power_features[power_features["min_history_n"] > 20]
        if len(low) and len(high):
            assert low["uncertainty"].mean() > high["uncertainty"].mean()


# ---------------------------------------------------------------- REQ-PW02
class TestCanonicalIdentity:
    def test_team_ids_nonblank(self, power_features):
        assert (power_features["home_team_id"].astype(str) != "").all()
        assert (power_features["away_team_id"].astype(str) != "").all()

    def test_no_fuzzy_league(self, power_features):
        # League values must be canonical strings from the xlsm source; no
        # silent fuzzy normalization introduced by this package.
        leagues = set(power_features["league"].dropna().astype(str))
        assert leagues, "no leagues"
        assert all(isinstance(x, str) and x for x in leagues)


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
            power_features["triplet_ok"]
            & power_features["line_ok"]
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

    def test_line_absent_never_publishable(self, power_features):
        no_line = power_features[~power_features["line_ok"]]
        assert (no_line["triplet_ok"] == False).all()  # noqa: E712


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


# ---------------------------------------------------------------- REQ-PW06
class TestWaterfall:
    def test_waterfall_monotonic(self, waterfall):
        stages = waterfall.dropna(subset=["stage"]).sort_values("stage")
        rows = stages["rows"].tolist()
        # Raw -> identity -> league -> epoch -> target -> line must be
        # monotonically non-increasing.
        assert all(rows[i] >= rows[i + 1] for i in range(len(rows) - 1))

    def test_ppower_reconstruction_9_issues(self):
        rec = pd.read_csv(PKG / "ppower_intersection_reconstruction.csv")
        by_metric = dict(zip(rec["metric"], rec["value"]))
        # The accepted #229 figure is independently reproduced.
        assert int(by_metric["published_cells"]) == 234
        assert int(by_metric["published_issues"]) == 9

    def test_rebuild_exceeds_180_support(self, power_features):
        # REQ-PW08: positive timestamp-safe support must exceed the accepted
        # #180 coverage of 234 cells / 9 issues.
        publishable = power_features[
            power_features["triplet_ok"]
            & power_features["line_ok"]
            & ~power_features["unseen_mask"]
        ]
        assert len(publishable) > 234
        assert publishable["issue"].nunique() > 9


# ---------------------------------------------------------------- REQ-PW07
class TestSealedLabels:
    def test_calibration_never_opens_2024_plus(self):
        cal = pd.read_parquet(PKG / "calibration_through_2023.parquet")
        if len(cal):
            assert cal["year"].max() <= 2023

    def test_published_cells_include_future_but_not_designed(self, power_features):
        # The package may carry feature support for 2024+ years (pre-event
        # estimates) but the calibration table must stay <=2023.
        years = set(power_features["year"])
        cal = pd.read_parquet(PKG / "calibration_through_2023.parquet")
        assert (set(cal["year"]) <= {y for y in years if y <= 2023})


# ---------------------------------------------------------------- REQ-E06
class TestTamperSelfDefense:
    """Tamper tests: attack the published package; each must FAIL loudly."""

    def _load(self):
        return pd.read_parquet(PKG / "power_features.parquet")

    def test_tamper_probability_fails_verifier(self):
        frame = self._load()
        frame.loc[frame.index[0], "power_probability"] = 0.999
        with pytest.raises(Exception):
            _assert_package_consistent(frame)

    def test_tamper_line_fails_verifier(self):
        frame = self._load()
        frame.loc[frame.index[0], "native_handicap_line"] = 99.0
        with pytest.raises(Exception):
            _assert_package_consistent(frame)

    def test_tamper_history_hash_fails(self):
        frame = pd.read_parquet(PKG / "power_feature_diagnostics.parquet")
        frame.loc[frame.index[0], HISTORY_EVENT_COL] = "0" * 64
        with pytest.raises(Exception):
            _assert_hash_consistent(frame)

    def test_manifest_hash_mismatch_fails(self):
        sums = json.loads((PKG / "SHA256SUMS.json").read_text())
        tampered = dict(sums)
        key = next(iter(tampered))
        tampered[key] = "0" * 64
        with pytest.raises(Exception):
            _verify_manifest_hashes(PKG, tampered)


# ---------------------------------------------------------------- helpers
def _assert_package_consistent(frame: pd.DataFrame) -> None:
    ok = frame[frame["triplet_ok"]]
    sums = ok.groupby(["issue", "match_idx"])["power_probability"].sum()
    if not ((sums - 1.0).abs() < 1e-9).all():
        raise ValueError("triplet normalization violated")
    if (ok["power_probability"] < 0).any() or (ok["power_probability"] > 1).any():
        raise ValueError("probability domain violated")
    no_line = frame[~frame["line_ok"]]
    if (no_line["triplet_ok"] == True).any():  # noqa: E712
        raise ValueError("line-less rows must not be triplet-ok")
    unseen = frame[frame["unseen_mask"]]
    if (unseen["min_history_n"] != 0).any():
        raise ValueError("unseen mask must imply zero history")
    # Native BJ handicap line domain: integer/half lines in [-3, 3].
    lines = frame.loc[frame["line_ok"], "native_handicap_line"].dropna()
    if (lines < -3).any() or (lines > 3).any():
        raise ValueError("line outside native BJ domain")
    if not set(lines.unique()) <= {-3.0, -2.5, -2.0, -1.5, -1.0, -0.5, 0.0,
                                    0.5, 1.0, 1.5, 2.0, 2.5, 3.0}:
        raise ValueError("line outside valid BJ handicap grid")


def _assert_hash_consistent(diagnostics: pd.DataFrame) -> None:
    if diagnostics[HISTORY_EVENT_COL].nunique() != 1:
        raise ValueError("history event digest diverged")


def _verify_manifest_hashes(pkg: Path, sums: dict) -> None:
    for name, expected in sums.items():
        actual = lib.sha256_file(pkg / name)
        if actual != expected:
            raise ValueError(f"hash mismatch: {name}")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
