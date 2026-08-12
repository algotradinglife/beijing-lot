from __future__ import annotations

import importlib.util
import gzip
import hashlib
import json
import math
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "freeze_bj106_q_atlas_gate_a.py"
SPEC = importlib.util.spec_from_file_location("freeze_bj106_q_atlas_gate_a", SCRIPT)
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_manifest(bundle: Path) -> None:
    entries = {
        path.name: MOD.sha256(path)
        for path in sorted(bundle.iterdir())
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    (bundle / "SHA256SUMS.json").write_text(
        json.dumps(entries, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def write_portable_bundle(
    bundle: Path,
    *,
    content: bytes,
    committed_gzip: bytes,
    replay_gzip: bytes,
    control: bytes = b"stable-control\n",
) -> None:
    bundle.mkdir()
    (bundle / "q_atlas.csv.gz").write_bytes(replay_gzip)
    (bundle / "control.txt").write_bytes(control)
    metadata = {
        "contract_version": MOD.CONTENT_IDENTITY_VERSION,
        "gzip_payloads": {
            "q_atlas.csv.gz": {
                "container_type": "gzip",
                "committed_artifact_sha256": digest(committed_gzip),
                "canonical_decompressed_sha256": digest(content),
                "canonical_decompressed_bytes": len(content),
            }
        },
        "non_compressed_controls": {"control.txt": digest(b"stable-control\n")},
    }
    (bundle / "CONTENT_IDENTITY.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_manifest(bundle)


def raises_runtime_error(callback) -> None:
    try:
        callback()
    except RuntimeError:
        return
    raise AssertionError("expected RuntimeError")


def test_fixed_probability_sp_and_q_bands() -> None:
    assert MOD.probability_band(0.0999) == "P00_10"
    assert MOD.probability_band(0.10) == "P10_20"
    assert MOD.sp_band(4.999) == "SP3_5"
    assert MOD.sp_band(5.0) == "SP5_10"
    assert MOD.q_band(MOD.Q_HIGH_BAND_BOUNDARY - 1e-9) == "Q135_1538"
    assert MOD.q_band(MOD.Q_HIGH_BAND_BOUNDARY) == "Q1538_200"


def test_n4_n9_gm_break_even_applies_factor_once_per_complete_ticket() -> None:
    assert set(MOD.GM_REFERENCE_THRESHOLDS) == set(range(4, 10))
    for n_legs, threshold in MOD.GM_REFERENCE_THRESHOLDS.items():
        assert math.isclose(
            MOD.complete_ticket_gross((threshold,) * n_legs),
            1.0,
            rel_tol=0.0,
            abs_tol=1e-12,
        )


def test_comparison_family_has_no_per_leg_q_gate() -> None:
    assert MOD.comparison_eligible(MOD.MIN_SUPPORT, 3, "L3_CODE_P_QLB")
    assert not MOD.comparison_eligible(MOD.MIN_SUPPORT - 1, 3, "L3_CODE_P_QLB")
    assert not MOD.comparison_eligible(MOD.MIN_SUPPORT, 2, "L3_CODE_P_QLB")
    assert not MOD.comparison_eligible(MOD.MIN_SUPPORT, 3, "L5_CODE_ONLY")


def test_sparse_stratum_fallback_order_is_deterministic() -> None:
    row = {
        "candidate_code": "3",
        "probability_band": "P35_50",
        "q_lb_band": "Q110_135",
        "handicap_line_norm": "0.0",
        "handicap_sign": "HZERO",
    }
    candidates = MOD.stratum_candidates(row)
    assert [level for _candidate, level in candidates] == [
        "L1_EXACT_HANDICAP",
        "L2_HANDICAP_SIGN",
        "L3_CODE_P_QLB",
        "L4_CODE_QLB",
        "L5_CODE_ONLY",
    ]
    assert candidates[0][0] == "CODE=3|P=P35_50|QLB=Q110_135|H=0.0"


def test_gate_a_atlas_uses_candidate_code_not_observed_result() -> None:
    lowered = [field.lower() for field in MOD.ATLAS_FIELDS]
    assert "candidate_code" in lowered
    assert not any(
        "result" in field or "winning" in field or "payout" in field or "roi" in field
        for field in lowered
    )


def test_handicap_sign_is_numeric_and_neutral_safe() -> None:
    assert MOD.handicap_sign("-0.5") == "HNEG"
    assert MOD.handicap_sign("0.0") == "HZERO"
    assert MOD.handicap_sign("0.5") == "HPOS"


def test_portable_replay_accepts_gzip_wrapper_variation() -> None:
    content = b"a,b\n1,2\n"
    committed_gzip = gzip.compress(content, compresslevel=9, mtime=0)
    replay_gzip = gzip.compress(content, compresslevel=1, mtime=1)
    assert committed_gzip != replay_gzip
    with tempfile.TemporaryDirectory(prefix="bj106_portable_") as directory:
        root = Path(directory)
        committed, replay = root / "committed", root / "replay"
        write_portable_bundle(
            committed,
            content=content,
            committed_gzip=committed_gzip,
            replay_gzip=committed_gzip,
        )
        write_portable_bundle(
            replay,
            content=content,
            committed_gzip=committed_gzip,
            replay_gzip=replay_gzip,
        )
        result = MOD.verify_portable_replay(replay, committed)
        assert result == {
            "status": "PASS",
            "gzip_wrapper_byte_identical": False,
            "gzip_payloads": 1,
            "non_compressed_controls": 1,
        }


def test_portable_replay_rejects_canonical_content_drift() -> None:
    content = b"a,b\n1,2\n"
    committed_gzip = gzip.compress(content, mtime=0)
    drifted_gzip = gzip.compress(b"a,b\n1,3\n", mtime=0)
    with tempfile.TemporaryDirectory(prefix="bj106_content_drift_") as directory:
        root = Path(directory)
        committed, replay = root / "committed", root / "replay"
        write_portable_bundle(
            committed,
            content=content,
            committed_gzip=committed_gzip,
            replay_gzip=committed_gzip,
        )
        write_portable_bundle(
            replay,
            content=content,
            committed_gzip=committed_gzip,
            replay_gzip=drifted_gzip,
        )
        raises_runtime_error(lambda: MOD.verify_portable_replay(replay, committed))


def test_portable_replay_rejects_non_compressed_control_drift() -> None:
    content = b"a,b\n1,2\n"
    compressed = gzip.compress(content, mtime=0)
    with tempfile.TemporaryDirectory(prefix="bj106_control_drift_") as directory:
        root = Path(directory)
        committed, replay = root / "committed", root / "replay"
        write_portable_bundle(
            committed,
            content=content,
            committed_gzip=compressed,
            replay_gzip=compressed,
        )
        write_portable_bundle(
            replay,
            content=content,
            committed_gzip=compressed,
            replay_gzip=compressed,
            control=b"drifted-control\n",
        )
        raises_runtime_error(lambda: MOD.verify_portable_replay(replay, committed))
