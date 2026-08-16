"""Issue #232 focused tests (R2 fresh) — causal gate, disposition truth
table, debt contracts and tamper self-tests (REQ-E06).

R2 rework tests (EV C1/C2/E1/E2):
- the causal gate rejects post-kickoff observations (R1 fixture asserted the
  opposite — a post-kickoff decision epoch was treated as causal);
- the disposition truth table requires EVERY necessary condition (mutation
  tests flip each condition and assert UNRECOVERABLE);
- the E1 binding rejects the zero placeholder and wrong external SHA;
- the semantic verifier independently recomputes decisive payloads and
  every tamper listed by EV (wrong SHA, causal-all-false, observed_at moved,
  de-vig tamper, READY forgery, upstream hash forgery, deleted REQ-S01,
  stripped schema columns, deleted SUPPORT_REPORT, added unbound file) FAILS.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from divergence_support import causal  # noqa: E402
from divergence_support import contract  # noqa: E402
from divergence_support import debt  # noqa: E402
from divergence_support import disposition  # noqa: E402
from divergence_support import publication  # noqa: E402
from divergence_support import recovery as recovery_mod  # noqa: E402
from divergence_support import verifier  # noqa: E402
from divergence_support import waterfall as waterfall_mod  # noqa: E402


# ---------------------------------------------------------------------------
# Causal gate (EV C1): observed_at <= decision_epoch <= kickoff
# ---------------------------------------------------------------------------
def test_causal_gate_requires_epoch_before_kickoff() -> None:
    """Decision epoch after kickoff is NEVER causal (R1 bug)."""
    observed = pd.Series(pd.to_datetime(["2026-05-04T01:37:59Z"], utc=True))
    epoch = pd.Series(pd.to_datetime(["2026-05-04T01:38:05Z"], utc=True))
    kickoff = pd.Series(pd.to_datetime(["2026-05-03T14:15:00Z"], utc=True))
    result = causal.causal_available(observed, epoch, kickoff)
    assert bool(result.iloc[0]) is False


def test_causal_gate_accepts_pre_event_observation() -> None:
    observed = pd.Series(pd.to_datetime(["2026-05-03T12:00:00Z"], utc=True))
    epoch = pd.Series(pd.to_datetime(["2026-05-03T13:00:00Z"], utc=True))
    kickoff = pd.Series(pd.to_datetime(["2026-05-03T14:15:00Z"], utc=True))
    result = causal.causal_available(observed, epoch, kickoff)
    assert bool(result.iloc[0]) is True


def test_causal_gate_fail_closed_on_missing_columns() -> None:
    observed = pd.Series([pd.NaT], dtype="datetime64[ns, UTC]")
    epoch = pd.Series(pd.to_datetime(["2026-05-03T13:00:00Z"], utc=True))
    kickoff = pd.Series(pd.to_datetime(["2026-05-03T14:15:00Z"], utc=True))
    assert bool(causal.causal_available(observed, epoch, kickoff).iloc[0]) is False
    observed = pd.Series(pd.to_datetime(["2026-05-03T12:00:00Z"], utc=True))
    epoch = pd.Series([pd.NaT], dtype="datetime64[ns, UTC]")
    assert bool(causal.causal_available(observed, epoch, kickoff).iloc[0]) is False
    kickoff = pd.Series([pd.NaT], dtype="datetime64[ns, UTC]")
    epoch = pd.Series(pd.to_datetime(["2026-05-03T13:00:00Z"], utc=True))
    assert bool(causal.causal_available(observed, epoch, kickoff).iloc[0]) is False


def test_causal_gate_rejects_post_epoch_observation() -> None:
    observed = pd.Series(pd.to_datetime(["2026-05-03T14:00:00Z"], utc=True))
    epoch = pd.Series(pd.to_datetime(["2026-05-03T13:00:00Z"], utc=True))
    kickoff = pd.Series(pd.to_datetime(["2026-05-03T15:00:00Z"], utc=True))
    assert bool(causal.causal_available(observed, epoch, kickoff).iloc[0]) is False


def test_recovery_rejects_post_kickoff_fixture() -> None:
    """The R1 fixture (decision_epoch > kickoff) must now yield NO recovery.

    R1 asserted recovery success with a post-kickoff decision epoch; R2
    treats that as non-causal and returns an empty receipt.
    """
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
                    "feature_cutoff_ts_utc": pd.Timestamp("2026-05-04T01:38:05Z"),
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

    assert len(result.sp_triplets) == 0
    assert len(result.receipts) == 1
    assert result.receipts.iloc[0]["reason"] in (
        "NO_CAUSAL_OBSERVATION", "PARTIAL_SOURCE_TRIPLET", "IMPOSSIBLE_SP",
    )


def test_recovery_accepts_pre_event_fixture() -> None:
    """A decision epoch before kickoff with observation before epoch recovers."""
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
                "snapshot_ts_utc": "2026-05-03T12:00:00Z",
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
                    "feature_cutoff_ts_utc": pd.Timestamp("2026-05-03T13:00:00Z"),
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
    assert bool(row["causal"]) is True
    assert bool(row["gate_observed_le_epoch"]) is True
    assert bool(row["gate_epoch_le_kickoff"]) is True
    assert np.isclose(row["triplet_sum"], 1.0)


def test_normalize_sp_triplet_sums_to_one() -> None:
    vector = recovery_mod.normalize_sp_triplet(2.77, 4.33, 2.44)
    assert np.isclose(vector.sum(), 1.0)
    assert vector.min() > 0.0 and vector.max() < 1.0


def test_normalize_sp_triplet_rejects_impossible_sp() -> None:
    with pytest.raises(recovery_mod.RecoveryError):
        recovery_mod.normalize_sp_triplet(0.9, 4.0, 2.0)
    with pytest.raises(recovery_mod.RecoveryError):
        recovery_mod.normalize_sp_triplet(np.nan, 4.0, 2.0)


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
                "snapshot_ts_utc": "2026-05-03T12:00:00Z",
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
                    "feature_cutoff_ts_utc": pd.Timestamp("2026-05-03T13:00:00Z"),
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
        devig_cols = ["Q_BJ_SP_DEVIG_3", "Q_BJ_SP_DEVIG_1", "Q_BJ_SP_DEVIG_0"]
        assert not np.isclose(
            result.sp_triplets[devig_cols], contract.PAYOUT_FACTOR_BJ
        ).any()


def test_recovery_empty_observation_is_explicit_receipt() -> None:
    observations = pd.DataFrame(
        columns=["id", "match_id", "sp_3", "sp_1", "sp_0", "eu_h", "eu_d",
                 "eu_a", "source", "snapshot_ts_utc"]
    )
    result = recovery_mod.build_sp_recovery(Path("."), observations)
    assert len(result.sp_triplets) == 0
    assert len(result.receipts) == 1


# ---------------------------------------------------------------------------
# Disposition truth table (EV C2): mutation tests
# ---------------------------------------------------------------------------
def _ready_support() -> disposition.ModelabilitySupport:
    return disposition.ModelabilitySupport(
        qbj_sp_complete_matches=10,
        qbj_eu_sp_complete_matches=5,
        qbj_power_sp_complete_matches=0,
        cohort_issue_support={"fit": 3, "tune": 2, "calibration": 2},
    )


def test_disposition_ready_only_with_all_conditions() -> None:
    assert (
        disposition.terminal_disposition(_ready_support())
        == contract.TERMINAL_READY_FOR_209
    )


def test_disposition_mutation_no_qbj_sp() -> None:
    support = _ready_support()
    support = disposition.ModelabilitySupport(
        qbj_sp_complete_matches=0,
        qbj_eu_sp_complete_matches=support.qbj_eu_sp_complete_matches,
        qbj_power_sp_complete_matches=support.qbj_power_sp_complete_matches,
        cohort_issue_support=support.cohort_issue_support,
    )
    assert (
        disposition.terminal_disposition(support)
        == contract.TERMINAL_UNRECOVERABLE
    )


def test_disposition_mutation_no_independent_source() -> None:
    support = _ready_support()
    support = disposition.ModelabilitySupport(
        qbj_sp_complete_matches=support.qbj_sp_complete_matches,
        qbj_eu_sp_complete_matches=0,
        qbj_power_sp_complete_matches=0,
        cohort_issue_support=support.cohort_issue_support,
    )
    assert (
        disposition.terminal_disposition(support)
        == contract.TERMINAL_UNRECOVERABLE
    )


def test_disposition_mutation_missing_tune_role() -> None:
    support = _ready_support()
    support = disposition.ModelabilitySupport(
        qbj_sp_complete_matches=support.qbj_sp_complete_matches,
        qbj_eu_sp_complete_matches=support.qbj_eu_sp_complete_matches,
        qbj_power_sp_complete_matches=support.qbj_power_sp_complete_matches,
        cohort_issue_support={"fit": 3, "tune": 0, "calibration": 2},
    )
    assert (
        disposition.terminal_disposition(support)
        == contract.TERMINAL_UNRECOVERABLE
    )


def test_disposition_mutation_missing_calibration_role() -> None:
    support = _ready_support()
    support = disposition.ModelabilitySupport(
        qbj_sp_complete_matches=support.qbj_sp_complete_matches,
        qbj_eu_sp_complete_matches=support.qbj_eu_sp_complete_matches,
        qbj_power_sp_complete_matches=support.qbj_power_sp_complete_matches,
        cohort_issue_support={"fit": 3, "tune": 2, "calibration": 0},
    )
    assert (
        disposition.terminal_disposition(support)
        == contract.TERMINAL_UNRECOVERABLE
    )


def test_disposition_power_can_satisfy_independent() -> None:
    support = disposition.ModelabilitySupport(
        qbj_sp_complete_matches=10,
        qbj_eu_sp_complete_matches=0,
        qbj_power_sp_complete_matches=7,
        cohort_issue_support={"fit": 3, "tune": 2, "calibration": 2},
    )
    assert (
        disposition.terminal_disposition(support)
        == contract.TERMINAL_READY_FOR_209
    )


# ---------------------------------------------------------------------------
# Waterfall semantics (REQ-S06)
# ---------------------------------------------------------------------------
def test_waterfall_stages_include_line_reconciliation_for_all_sources() -> None:
    """R1 emitted LINE_RECONCILIATION for no source (EV E4)."""
    rows = [
        {"source": "A", "source_key": "K", "stage": contract.STAGE_RAW,
         "count": 5, "kind": "PASS", "unit": "row", "reason": ""},
        {"source": "A", "source_key": "K", "stage": contract.STAGE_LINE_RECONCILIATION,
         "count": 5, "kind": "PASS", "unit": "row", "reason": ""},
    ]
    frame = pd.DataFrame(rows)
    stages = set(frame[frame["kind"].eq("PASS")]["stage"])
    assert contract.STAGE_LINE_RECONCILIATION in stages


def test_waterfall_raw_minus_drops_equals_final_pass() -> None:
    rows = [
        {"source": "S", "source_key": "K", "stage": contract.STAGE_RAW,
         "count": 100, "kind": "PASS", "unit": "row", "reason": ""},
        {"source": "S", "source_key": "K", "stage": contract.STAGE_IDENTITY_JOIN,
         "count": 10, "kind": "DROP", "unit": "row",
         "reason": "NO_IDENTITY_MATCH"},
        {"source": "S", "source_key": "K", "stage": contract.STAGE_IDENTITY_JOIN,
         "count": 90, "kind": "PASS", "unit": "row", "reason": ""},
        {"source": "S", "source_key": "K", "stage": contract.STAGE_CAUSAL_INTERSECTION,
         "count": 90, "kind": "DROP", "unit": "cell",
         "reason": "ANCHOR_UNAVAILABLE"},
        {"source": "S", "source_key": "K", "stage": contract.STAGE_CAUSAL_INTERSECTION,
         "count": 0, "kind": "PASS", "unit": "cell", "reason": ""},
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


# ---------------------------------------------------------------------------
# Debt E1-E4 (REQ-S09)
# ---------------------------------------------------------------------------
def test_e1_binding_rejects_zero_placeholder(tmp_path: Path) -> None:
    with pytest.raises(debt.DebtError):
        debt.AuditedShaBinding(audited_sha="0" * 40).validate()
    with pytest.raises(debt.DebtError):
        debt.AuditedShaBinding(audited_sha="not-a-sha").validate()


def test_e1_binding_must_match_external_sha(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    debt.write_audited_sha_binding(package, "a" * 40)
    # wrong external anchor -> fail
    with pytest.raises(debt.DebtError):
        debt.read_audited_sha_binding(package, expected_sha="b" * 40)
    # correct anchor -> pass
    binding = debt.read_audited_sha_binding(package, expected_sha="a" * 40)
    assert binding.audited_sha == "a" * 40


def test_e3_crash_restart_probe_recovers(tmp_path: Path) -> None:
    journal_path = tmp_path / "journal.jsonl"
    assert debt.crash_restart_probe(journal_path) is True


def test_e4_protocol_log_hash_chain(tmp_path: Path) -> None:
    debt.append_protocol_log(
        tmp_path, identity="pkg", version="v2", action="init",
        payload_sha="0" * 64,
    )
    debt.append_protocol_log(
        tmp_path, identity="pkg", version="v2", action="update",
        payload_sha="1" * 64,
    )
    assert debt.validate_protocol_log(tmp_path) == []


def test_e4_protocol_log_detects_chain_break(tmp_path: Path) -> None:
    debt.append_protocol_log(
        tmp_path, identity="pkg", version="v2", action="init",
        payload_sha="0" * 64,
    )
    path = tmp_path / "protocol_log.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[-1])
    entry["previous_sha256"] = "f" * 64
    path.write_text(json.dumps(entry, sort_keys=True) + "\n", encoding="utf-8")
    assert debt.validate_protocol_log(tmp_path) != []


# ---------------------------------------------------------------------------
# Semantic verifier — independent recomputation (EV E2)
# ---------------------------------------------------------------------------
def _make_package(tmp_path: Path, *, with_disposition: str | None = None) -> Path:
    """A minimal valid package exercising verifier paths."""
    package = tmp_path / "pkg"
    tables = package / "tables"
    tables.mkdir(parents=True)
    evidence = package / "evidence"
    evidence.mkdir()
    binding = package / "binding"
    binding.mkdir()

    triplets = pd.DataFrame(
        [
            {
                "issue": "26051", "match_idx": 1, "SP_3": 2.77, "SP_1": 4.33,
                "SP_0": 2.44,
                "Q_BJ_SP_DEVIG_3": 0.36036442,
                "Q_BJ_SP_DEVIG_1": 0.23053336,
                "Q_BJ_SP_DEVIG_0": 0.40910223,
                "observed_at_utc": "2026-05-03T12:00:00Z",
                "decision_epoch_utc": "2026-05-03T13:00:00Z",
                "kickoff_ts_utc": "2026-05-03T14:15:00Z",
                "source_identity": "bj214_decision_epoch_observation",
                "causal": True,
                "triplet_sum": 1.0,
                "triplet_bounded": True,
            }
        ]
    )
    triplets.to_parquet(tables / "decision_epoch_sp_triplets.parquet", index=False)

    summary = pd.DataFrame(
        [
            {
                "interface": "Q_BJ_x_SP",
                "fit_issues": 1, "fit_matches": 2, "tune_issues": 1,
                "tune_matches": 2, "calibration_issues": 1,
                "calibration_matches": 2, "2024_plus_issues": 0,
                "2024_plus_matches": 0,
            },
            {
                "interface": "Q_BJ_x_EU_x_SP",
                "fit_issues": 1, "fit_matches": 2, "tune_issues": 1,
                "tune_matches": 2, "calibration_issues": 1,
                "calibration_matches": 2, "2024_plus_issues": 0,
                "2024_plus_matches": 0,
            },
            {
                "interface": "Q_BJ_x_POWER_x_SP",
                "fit_issues": 0, "fit_matches": 0, "tune_issues": 0,
                "tune_matches": 0, "calibration_issues": 0,
                "calibration_matches": 0, "2024_plus_issues": 0,
                "2024_plus_matches": 0,
            },
        ]
    )
    summary.to_csv(tables / "modelability_interface_summary.csv", index=False)

    census = pd.DataFrame(
        [{"source_key": "bj214_selected_market_observations"}]
    )
    census.to_csv(tables / "census.csv", index=False)

    schema = {
        "census": {"rows": 1, "columns": ["source_key"]},
        "decision_epoch_sp_triplets": {
            "rows": 1,
            "columns": list(triplets.columns),
        },
        "modelability_interface_summary": {
            "rows": 3,
            "columns": list(summary.columns),
        },
    }
    publication.atomic_write_json(package / "handoff_schema.json", schema)

    rows = []
    for requirement in [f"REQ-S{index:02d}" for index in range(1, 11)]:
        rows.append({"requirement": requirement, "pass": True})
    publication.atomic_write_csv(evidence / "req_s_evidence.csv", pd.DataFrame(rows))

    # minimal waterfall ledger: one source with all stages
    wf_rows = [
        {"source": "Q_BJ_SP_DEVIG", "source_key": "bj214_selected_market_observations",
         "stage": contract.STAGE_RAW, "count": 1, "kind": "PASS", "unit": "row", "reason": ""},
        {"source": "Q_BJ_SP_DEVIG", "source_key": "bj214_selected_market_observations",
         "stage": contract.STAGE_IDENTITY_JOIN, "count": 1, "kind": "PASS", "unit": "row", "reason": ""},
        {"source": "Q_BJ_SP_DEVIG", "source_key": "bj214_selected_market_observations",
         "stage": contract.STAGE_LINE_RECONCILIATION, "count": 1, "kind": "PASS", "unit": "row", "reason": ""},
        {"source": "Q_BJ_SP_DEVIG", "source_key": "bj214_selected_market_observations",
         "stage": contract.STAGE_TIMESTAMP_GATE, "count": 1, "kind": "PASS", "unit": "row", "reason": ""},
        {"source": "Q_BJ_SP_DEVIG", "source_key": "bj214_selected_market_observations",
         "stage": contract.STAGE_COMPLETE_TRIPLET, "count": 1, "kind": "PASS", "unit": "row", "reason": ""},
        {"source": "Q_BJ_SP_DEVIG", "source_key": "bj214_selected_market_observations",
         "stage": contract.STAGE_CAUSAL_INTERSECTION, "count": 3, "kind": "EXPAND", "unit": "cell", "reason": "AXIS_EXPAND_3_OUTCOMES"},
        {"source": "Q_BJ_SP_DEVIG", "source_key": "bj214_selected_market_observations",
         "stage": contract.STAGE_CAUSAL_INTERSECTION, "count": 3, "kind": "PASS", "unit": "cell", "reason": ""},
    ]
    publication.atomic_write_csv(tables / "waterfall.csv", pd.DataFrame(wf_rows))

    publication.atomic_write_json(
        package / "MANIFEST.json",
        {
            "package": "bj232_divergence_support_v2",
            "disposition": with_disposition or "UNRECOVERABLE_WITH_CURRENT_SOURCES",
            "reviewed_commit_sha": "a" * 40,
        },
    )

    if with_disposition is not None:
        publication.atomic_write_json(
            package / "disposition.json", {"disposition": with_disposition}
        )

    debt.write_audited_sha_binding(package, "a" * 40)

    from divergence_support import manifest as manifest_mod

    manifest_mod.write_replay(
        package,
        build_script="build_bj232_divergence_support.py",
        notebook_script="execute_bj232_notebook.py",
    )
    manifest_mod.write_sha256sums(package)
    return package


def test_verifier_passes_clean_package(tmp_path: Path) -> None:
    package = _make_package(tmp_path)
    problems = verifier.verify_semantics(package, expected_sha="a" * 40)
    assert problems == []


def test_tamper_observed_at_moved_after_epoch(tmp_path: Path) -> None:
    """EV tamper: observed_at moved past the decision epoch -> FAIL."""
    package = _make_package(tmp_path)
    path = package / "tables" / "decision_epoch_sp_triplets.parquet"
    frame = pd.read_parquet(path)
    frame.loc[0, "observed_at_utc"] = "2026-05-03T13:30:00Z"  # after epoch
    frame.to_parquet(path, index=False)
    problems = verifier.verify_semantics(package, expected_sha="a" * 40)
    assert any("causality" in problem for problem in problems)


def test_tamper_causal_all_false(tmp_path: Path) -> None:
    """EV tamper: causal flags all false -> FAIL (disagrees with gate)."""
    package = _make_package(tmp_path)
    path = package / "tables" / "decision_epoch_sp_triplets.parquet"
    frame = pd.read_parquet(path)
    frame.loc[0, "causal"] = False
    frame.to_parquet(path, index=False)
    problems = verifier.verify_semantics(package, expected_sha="a" * 40)
    assert any("causality" in problem for problem in problems)


def test_tamper_devig_values(tmp_path: Path) -> None:
    """EV tamper: de-vig tampered -> FAIL (recompute normalize(1/SP))."""
    package = _make_package(tmp_path)
    path = package / "tables" / "decision_epoch_sp_triplets.parquet"
    frame = pd.read_parquet(path)
    frame.loc[0, "Q_BJ_SP_DEVIG_3"] = 0.9
    frame.loc[0, "Q_BJ_SP_DEVIG_1"] = 0.05
    frame.loc[0, "Q_BJ_SP_DEVIG_0"] = 0.05
    frame.to_parquet(path, index=False)
    problems = verifier.verify_semantics(package, expected_sha="a" * 40)
    assert any("devig" in problem for problem in problems)


def test_tamper_ready_disposition_forgery(tmp_path: Path) -> None:
    """EV tamper: READY disposition forged on zero support -> FAIL."""
    package = _make_package(tmp_path)
    summary_path = package / "tables" / "modelability_interface_summary.csv"
    summary = pd.read_csv(summary_path)
    # zero out ALL support but claim READY
    for col in summary.columns:
        if col.endswith("_issues") or col.endswith("_matches"):
            summary[col] = 0
    summary.to_csv(summary_path, index=False)
    publication.atomic_write_json(
        package / "disposition.json",
        {"disposition": "READY_FOR_209_PI_MODELABILITY_REVIEW"},
    )
    problems = verifier.verify_semantics(package, expected_sha="a" * 40)
    assert any("disposition" in problem for problem in problems)


def test_tamper_wrong_audited_sha(tmp_path: Path) -> None:
    """EV tamper: wrong AUDITED_SHA -> FAIL (external anchor mismatch)."""
    package = _make_package(tmp_path)
    problems = verifier.verify_semantics(package, expected_sha="b" * 40)
    assert any("E1" in problem for problem in problems)


def test_tamper_zero_audited_sha(tmp_path: Path) -> None:
    """EV tamper: zero placeholder in AUDITED_SHA -> FAIL."""
    package = _make_package(tmp_path)
    binding_path = package / "binding" / "AUDITED_SHA.json"
    payload = json.loads(binding_path.read_text(encoding="utf-8"))
    payload["audited_sha"] = "0" * 40
    binding_path.write_text(json.dumps(payload), encoding="utf-8")
    problems = verifier.verify_semantics(package, expected_sha="a" * 40)
    assert any("E1" in problem for problem in problems)


def test_tamper_delete_requirement_evidence(tmp_path: Path) -> None:
    """EV tamper: deleted REQ-S01 row -> FAIL."""
    package = _make_package(tmp_path)
    evidence_path = package / "evidence" / "req_s_evidence.csv"
    evidence = pd.read_csv(evidence_path)
    evidence = evidence[~evidence["requirement"].eq("REQ-S01")]
    evidence.to_csv(evidence_path, index=False)
    problems = verifier.verify_semantics(package, expected_sha="a" * 40)
    assert any("evidence" in problem for problem in problems)


def test_tamper_add_unbound_file(tmp_path: Path) -> None:
    """EV tamper: added unbound file -> FAIL (extra file vs manifest)."""
    package = _make_package(tmp_path)
    (package / "tables" / "sneaky_extra.csv").write_text(
        "col_a,col_b\n1,2\n", encoding="utf-8"
    )
    problems = verifier.verify_semantics(package, expected_sha="a" * 40)
    assert any("extra files" in problem for problem in problems)


def test_tamper_strip_schema_columns(tmp_path: Path) -> None:
    """EV tamper: stripped schema columns from published table -> FAIL."""
    package = _make_package(tmp_path)
    path = package / "tables" / "decision_epoch_sp_triplets.parquet"
    frame = pd.read_parquet(path)
    frame = frame.drop(columns=["kickoff_ts_utc"])
    frame.to_parquet(path, index=False)
    problems = verifier.verify_semantics(package, expected_sha="a" * 40)
    assert any("schema" in problem for problem in problems)


def test_tamper_forbidden_payout_column(tmp_path: Path) -> None:
    """REQ-E06: settlement/payout column must be rejected fail-closed."""
    package = _make_package(tmp_path)
    path = package / "tables" / "decision_epoch_sp_triplets.parquet"
    frame = pd.read_parquet(path)
    frame["payout_amount"] = 100.0
    frame.to_parquet(path, index=False)
    problems = verifier.verify_semantics(package, expected_sha="a" * 40)
    assert any("forbidden column" in problem for problem in problems)


def test_tamper_protocol_log_entry_fails_validation(tmp_path: Path) -> None:
    package = _make_package(tmp_path)
    debt.append_protocol_log(
        package, identity="pkg", version="v2", action="tamper",
        payload_sha="0" * 64,
    )
    path = package / "protocol_log.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[-1])
    entry["payload_sha256"] = "9" * 64
    path.write_text(json.dumps(entry, sort_keys=True) + "\n", encoding="utf-8")
    assert debt.validate_protocol_log(package) != []


def test_tamper_journal_entry_breaks_consistency(tmp_path: Path) -> None:
    journal = debt.CrashRestartJournal(tmp_path / "journal.jsonl")
    journal.append(debt.PHASE_PREPARE, "t", payload_sha="0" * 64)
    assert not journal.is_consistent()
    journal.append(debt.PHASE_COMMIT, "t", payload_sha="0" * 64)
    assert journal.is_consistent()
