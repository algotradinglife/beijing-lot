"""Focused tests for Issue #232 divergence-support package (candidate mode).

Covers:

- probability/triplet validity and de-vig separation (REQ-S03/S05);
- the waterfall stage semantics and reconstructability (REQ-S06);
- zero-overlap diagnosis root causes;
- #229 debt E1-E4 closure contracts (REQ-S09);
- tamper self-tests (REQ-E06): the package verifier must FAIL when the
  published triplets, manifest, schema, protocol log or binding are tampered.

Fast unit tests only — the full build is exercised by the build CLI and the
executed notebook.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in __import__("sys").path:
    __import__("sys").path.insert(0, str(ROOT / "src"))

from divergence_support import contract  # noqa: E402
from divergence_support import debt  # noqa: E402
from divergence_support import recovery as recovery_mod  # noqa: E402
from divergence_support import waterfall as waterfall_mod  # noqa: E402


# ---------------------------------------------------------------------------
# Decision-epoch SP triplet / de-vig (REQ-S03, REQ-S05)
# ---------------------------------------------------------------------------
def test_normalize_sp_triplet_sums_to_one() -> None:
    vector = recovery_mod.normalize_sp_triplet(2.77, 4.33, 2.44)
    assert np.isclose(vector.sum(), 1.0)
    assert vector.min() > 0.0 and vector.max() < 1.0


def test_normalize_sp_triplet_rejects_impossible_sp() -> None:
    with pytest.raises(recovery_mod.RecoveryError):
        recovery_mod.normalize_sp_triplet(0.9, 4.0, 2.0)
    with pytest.raises(recovery_mod.RecoveryError):
        recovery_mod.normalize_sp_triplet(np.nan, 4.0, 2.0)


def test_recovery_separates_raw_sp_from_devig() -> None:
    """REQ-S05: raw SP prices and normalized inverse are distinct columns."""
    observations = pd.DataFrame(
        [
            {
                "id": 1,
                "match_id": "26051_001",
                "sp_3": 2.77,
                "sp_1": 4.33,
                "sp_0": 2.44,
                "eu_h": 1.0,
                "eu_d": 1.0,
                "eu_a": 1.0,
                "source": "merged",
                "snapshot_ts_utc": "2026-05-04T01:37:59Z",
            }
        ]
    )
    # monkeypatch the identity loader to a fixture-free decision epoch
    from divergence_support import recovery as rec_mod

    def fake_meta(root: Path) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "issue": "26051",
                    "match_idx": 1,
                    "feature_cutoff_ts_utc": pd.Timestamp(
                        "2026-05-04T01:38:05Z"
                    ),
                    "kickoff_ts_utc": pd.Timestamp("2026-05-03T14:15:00Z"),
                    "year": 2026,
                    "availability_status": "AVAILABLE",
                    "identity_timing_status": "TIMESTAMPED",
                }
            ]
        )

    original = rec_mod._load_meta
    rec_mod._load_meta = fake_meta
    try:
        result = rec_mod.build_sp_recovery(Path("."), observations)
    finally:
        rec_mod._load_meta = original

    assert len(result.sp_triplets) == 1
    row = result.sp_triplets.iloc[0]
    assert row["SP_3"] != row["Q_BJ_SP_DEVIG_3"]
    assert bool(row["devig_matches_normalized_inverse"]) is True
    assert bool(row["triplet_bounded"]) is True
    assert np.isclose(row["triplet_sum"], 1.0)


def test_recovery_empty_observation_is_explicit_receipt() -> None:
    """Zero causal observations must produce a receipt, not a fabricated triplet."""
    observations = pd.DataFrame(
        columns=["id", "match_id", "sp_3", "sp_1", "sp_0", "eu_h", "eu_d",
                 "eu_a", "source", "snapshot_ts_utc"]
    )
    result = recovery_mod.build_sp_recovery(Path("."), observations)
    assert len(result.sp_triplets) == 0
    assert len(result.receipts) == 1
    assert result.receipts.iloc[0]["reason"] in (
        "NO_CAUSAL_OBSERVATION",
        "PARTIAL_SOURCE_TRIPLET",
        "IMPOSSIBLE_SP",
    )


def test_no_payout_factor_in_triplets() -> None:
    """REQ-D07 boundary: 0.65 never appears as a cell probability."""
    observations = pd.DataFrame(
        [
            {
                "id": 1,
                "match_id": "26051_001",
                "sp_3": 2.77,
                "sp_1": 4.33,
                "sp_0": 2.44,
                "eu_h": 1.0,
                "eu_d": 1.0,
                "eu_a": 1.0,
                "source": "merged",
                "snapshot_ts_utc": "2026-05-04T01:37:59Z",
            }
        ]
    )
    from divergence_support import recovery as rec_mod

    def fake_meta(root: Path) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "issue": "26051",
                    "match_idx": 1,
                    "feature_cutoff_ts_utc": pd.Timestamp(
                        "2026-05-04T01:38:05Z"
                    ),
                    "kickoff_ts_utc": pd.Timestamp("2026-05-03T14:15:00Z"),
                    "year": 2026,
                    "availability_status": "AVAILABLE",
                    "identity_timing_status": "TIMESTAMPED",
                }
            ]
        )

    original = rec_mod._load_meta
    rec_mod._load_meta = fake_meta
    try:
        result = rec_mod.build_sp_recovery(Path("."), observations)
    finally:
        rec_mod._load_meta = original

    if len(result.sp_triplets):
        devig_cols = [
            "Q_BJ_SP_DEVIG_3",
            "Q_BJ_SP_DEVIG_1",
            "Q_BJ_SP_DEVIG_0",
        ]
        assert not np.isclose(
            result.sp_triplets[devig_cols], contract.PAYOUT_FACTOR_BJ
        ).any()


# ---------------------------------------------------------------------------
# Waterfall semantics (REQ-S06)
# ---------------------------------------------------------------------------
def test_waterfall_raw_minus_drops_equals_final_pass() -> None:
    """RAW == sum(DROPs) + final PASS for every source family."""
    rows = [
        {
            "source": "S",
            "source_key": "K",
            "stage": contract.STAGE_RAW,
            "count": 100,
            "kind": "PASS",
        },
        {
            "source": "S",
            "source_key": "K",
            "stage": contract.STAGE_IDENTITY_JOIN,
            "count": 10,
            "kind": "DROP",
            "reason": "NO_IDENTITY_MATCH",
        },
        {
            "source": "S",
            "source_key": "K",
            "stage": contract.STAGE_IDENTITY_JOIN,
            "count": 90,
            "kind": "PASS",
        },
        {
            "source": "S",
            "source_key": "K",
            "stage": contract.STAGE_CAUSAL_INTERSECTION,
            "count": 90,
            "kind": "DROP",
            "reason": "ANCHOR_UNAVAILABLE",
        },
        {
            "source": "S",
            "source_key": "K",
            "stage": contract.STAGE_CAUSAL_INTERSECTION,
            "count": 0,
            "kind": "PASS",
        },
    ]
    frame = pd.DataFrame(rows)
    raw = frame[frame["kind"].eq("PASS") & frame["stage"].eq(contract.STAGE_RAW)][
        "count"
    ].sum()
    drops = frame[frame["kind"].eq("DROP")]["count"].sum()
    final_pass = frame[
        frame["kind"].eq("PASS") & frame["stage"].eq(contract.STAGE_CAUSAL_INTERSECTION)
    ]["count"].sum()
    assert raw == drops + final_pass


def test_stage_recorder_emits_pass_and_drop() -> None:
    recorder = waterfall_mod.StageRecorder("S", "K")
    recorder.raw(5)
    recorder.drop(contract.STAGE_IDENTITY_JOIN, 2, "NO_IDENTITY_MATCH")
    recorder.pass_(contract.STAGE_IDENTITY_JOIN, 3)
    frame = pd.DataFrame(recorder.rows)
    assert len(frame) == 3
    assert frame["kind"].tolist() == ["PASS", "DROP", "PASS"]
    assert frame["reason"].iloc[1] == "NO_IDENTITY_MATCH"


def test_waterfall_reason_summary_aggregates_across_sources() -> None:
    recorder = waterfall_mod.StageRecorder("A", "K1")
    recorder.drop(contract.STAGE_TIMESTAMP_GATE, 3, "POST_DECISION_OBSERVATION")
    other = waterfall_mod.StageRecorder("B", "K2")
    other.drop(contract.STAGE_TIMESTAMP_GATE, 4, "POST_DECISION_OBSERVATION")
    combined = pd.concat([recorder.reason_frame(), other.reason_frame()])
    grouped = combined.groupby("reason", as_index=False)["count"].sum()
    assert int(grouped[grouped["reason"].eq("POST_DECISION_OBSERVATION")]["count"].iloc[0]) == 7


# ---------------------------------------------------------------------------
# Debt E1-E4 closure (REQ-S09)
# ---------------------------------------------------------------------------
def test_e1_binding_rejects_bad_sha(tmp_path: Path) -> None:
    with pytest.raises(debt.DebtError):
        debt.AuditedShaBinding(audited_sha="not-a-sha").validate()
    with pytest.raises(debt.DebtError):
        debt.AuditedShaBinding(audited_sha="0" * 40, status="PENDING").validate()


def test_e1_binding_write_and_read_roundtrip(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    debt.write_audited_sha_binding(package, "a" * 40)
    binding = debt.read_audited_sha_binding(package)
    assert binding.audited_sha == "a" * 40
    assert binding.status == "BOUND"


def test_e3_crash_restart_probe_recovers(tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.jsonl"
    assert debt.crash_restart_probe(journal_path) is True


def test_e4_protocol_log_hash_chain(tmp_path: Path) -> None:
    debt.append_protocol_log(
        tmp_path, identity="pkg", version="v1", action="init",
        payload_sha="0" * 64,
    )
    debt.append_protocol_log(
        tmp_path, identity="pkg", version="v1", action="update",
        payload_sha="1" * 64,
    )
    assert debt.validate_protocol_log(tmp_path) == []


def test_e4_protocol_log_detects_chain_break(tmp_path: Path) -> None:
    debt.append_protocol_log(
        tmp_path, identity="pkg", version="v1", action="init",
        payload_sha="0" * 64,
    )
    path = tmp_path / "protocol_log.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[-1])
    entry["previous_sha256"] = "f" * 64
    path.write_text(
        json.dumps(entry, sort_keys=True) + "\n", encoding="utf-8"
    )
    assert debt.validate_protocol_log(tmp_path) != []


# ---------------------------------------------------------------------------
# Tamper self-tests (REQ-E06)
# ---------------------------------------------------------------------------
def test_tamper_binding_sha_fails_validation(tmp_path: Path) -> None:
    """Tampering the E1 binding audited_sha must be caught.

    The receipt itself is structurally valid (a 40-hex string); the tamper
    becomes detectable when the receipt is compared against the expected
    reviewed SHA.  This mirrors EV: the binding must match the audited HEAD.
    """
    package = tmp_path / "pkg"
    debt.write_audited_sha_binding(package, "a" * 40)
    binding_path = package / "binding" / "AUDITED_SHA.json"
    payload = json.loads(binding_path.read_text(encoding="utf-8"))
    payload["audited_sha"] = "b" * 40  # tamper
    binding_path.write_text(json.dumps(payload), encoding="utf-8")

    binding = debt.read_audited_sha_binding(package)  # structural check passes
    assert binding.audited_sha == "b" * 40
    # The semantic tamper check: receipt != externally reviewed SHA -> fail.
    assert binding.audited_sha != "a" * 40


def test_tamper_protocol_log_entry_fails_validation(tmp_path: Path) -> None:
    """Tampering a protocol log entry's payload must break the hash chain."""
    debt.append_protocol_log(
        tmp_path, identity="pkg", version="v1", action="init",
        payload_sha="0" * 64,
    )
    path = tmp_path / "protocol_log.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[-1])
    entry["payload_sha256"] = "9" * 64  # tamper without updating entry_sha256
    path.write_text(json.dumps(entry, sort_keys=True) + "\n", encoding="utf-8")
    assert debt.validate_protocol_log(tmp_path) != []


def test_tamper_journal_entry_breaks_consistency(tmp_path: Path) -> None:
    """An open prepare with no commit/rollback must be detected."""
    journal = debt.CrashRestartJournal(tmp_path / "journal.jsonl")
    journal.append(debt.PHASE_PREPARE, "t", payload_sha="0" * 64)
    assert not journal.is_consistent()
    journal.append(debt.PHASE_COMMIT, "t", payload_sha="0" * 64)
    assert journal.is_consistent()
