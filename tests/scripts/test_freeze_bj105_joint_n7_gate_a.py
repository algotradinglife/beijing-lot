from __future__ import annotations

import importlib.util
import csv
import gzip
import hashlib
import io
import json
import math
import shutil
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "freeze_bj105_joint_n7_gate_a.py"
SPEC = importlib.util.spec_from_file_location("freeze_bj105_joint_n7_gate_a", SCRIPT)
assert SPEC and SPEC.loader
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_manifest(bundle: Path) -> None:
    entries = {
        path.name: MOD.sha256(path)
        for path in bundle.iterdir()
        if path.is_file() and path.name != "SHA256SUMS.json"
    }
    (bundle / "SHA256SUMS.json").write_text(
        json.dumps(entries, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def write_portable_bundle(
    bundle: Path,
    *,
    frontier_content: bytes,
    role_content: bytes,
    replay_frontier: bytes,
    replay_roles: bytes,
    control: bytes = b"stable-control\n",
) -> None:
    bundle.mkdir()
    (bundle / "joint_n7_frontier.csv.gz").write_bytes(replay_frontier)
    (bundle / "role_assignments.csv.gz").write_bytes(replay_roles)
    (bundle / "control.txt").write_bytes(control)
    identity = {
        "contract_version": MOD.CONTENT_IDENTITY_VERSION,
        "gzip_payloads": {
            "joint_n7_frontier.csv.gz": {
                "container_type": "gzip",
                "canonical_decompressed_sha256": digest(frontier_content),
                "canonical_decompressed_bytes": len(frontier_content),
            },
            "role_assignments.csv.gz": {
                "container_type": "gzip",
                "canonical_decompressed_sha256": digest(role_content),
                "canonical_decompressed_bytes": len(role_content),
            },
        },
        "non_compressed_controls": {"control.txt": digest(b"stable-control\n")},
    }
    (bundle / "CONTENT_IDENTITY.json").write_text(
        json.dumps(identity, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    write_manifest(bundle)


def raises_runtime_error(callback) -> None:
    try:
        callback()
    except RuntimeError:
        return
    raise AssertionError("expected RuntimeError")


def leg(position: int, *, p3: float, p1: float, p0: float, top_sp: float = 3.2) -> dict[str, object]:
    probability = {"3": p3, "1": p1, "0": p0}
    high = MOD.argmax(probability)
    low = MOD.argmin(probability)
    sp = {"3": 3.0, "1": 3.1, "0": 3.2}
    sp[high] = top_sp
    q = {code: probability[code] * sp[code] for code in MOD.CODES}
    other = [q[code] for code in MOD.CODES if code != low]
    return {
        "issue": "26001", "fold": "2020", "year": "2020", "pool_id": "26001-2020-S01",
        "match_id": f"26001_{position:03d}", "match_idx": str(position), "p": probability,
        "p_min": probability[low], "p_max": probability[high], "argmin_code": low,
        "argmax_code": high, "e_sp": sum(q.values()), "q_max": q[high],
        "d_ratio": q[low] / (sum(other) / 2), "predicted_top_sp": top_sp,
    }


def selected() -> list[dict[str, object]]:
    return [leg(index, p3=0.62 - index / 100, p1=0.28, p0=0.10 + index / 100) for index in range(1, 8)]


def test_fixed_depth_two_has_exact_k_mass_and_stake() -> None:
    rows = selected()
    frontier, roles = MOD.make_portfolio(rows, 0.20, 2.90, 2, "FIXED_ARGMIN")
    assert frontier["disposition"] == "AVAILABLE"
    assert frontier["full_legs"] == 5
    assert frontier["double_legs"] == 2
    assert frontier["single_legs"] == 0
    assert frontier["formula_k"] == 3**5 * 2**2
    assert float(frontier["stake_yuan"]) == 2 * 3**5 * 2**2
    doubles = [row for row in roles if row["role"] == "DOUBLE"]
    expected_mass = math.prod(1 - next(item for item in rows if item["match_id"] == row["match_id"])["p"][row["omitted_codes"]] for row in doubles)
    assert math.isclose(float(frontier["expected_portfolio_mass"]), expected_mass, abs_tol=1e-12)
    assert math.isclose(
        float(frontier["g_be_pre_tax"]),
        (frontier["formula_k"] / (0.65 * expected_mass)) ** (1 / 7),
        abs_tol=1e-12,
    )


def test_joint_role_includes_one_single_and_m_doubles() -> None:
    frontier, roles = MOD.make_portfolio(selected(), 0.20, 2.90, 2, "JOINT_ROLE")
    assert frontier["disposition"] == "AVAILABLE"
    assert (frontier["full_legs"], frontier["double_legs"], frontier["single_legs"]) == (4, 2, 1)
    assert frontier["formula_k"] == 3**4 * 2**2
    single = next(row for row in roles if row["role"] == "SINGLE")
    source = next(row for row in selected() if row["match_id"] == single["match_id"])
    assert single["allowed_codes"] == source["argmax_code"]


def test_threshold_and_gm_gates_fail_closed() -> None:
    rows = selected()
    threshold, threshold_roles = MOD.make_portfolio(rows, 0.05, 2.90, 3, "FIXED_ARGMIN")
    gm, _ = MOD.make_portfolio(rows, 0.20, 3.30, 1, "FIXED_ARGMIN")
    assert threshold["disposition"] == "UNAVAILABLE_THRESHOLD"
    assert threshold["formula_k"] == 3**4 * 2**3
    assert threshold["active_k"] == 0
    assert float(threshold["stake_yuan"]) == 0
    assert threshold_roles == []
    assert gm["disposition"] == "FAIL_GM_GATE"
    assert gm["active_k"] == 0
    assert float(gm["stake_yuan"]) == 0


def test_hash_and_weighted_controls_are_deterministic() -> None:
    row = selected()[0]
    assert MOD.hash_code(row, 2) == MOD.hash_code(row, 2)
    assert MOD.weighted_code(row, 2) == MOD.weighted_code(row, 2)
    assert MOD.hash_code(row, 2) in MOD.CODES
    assert MOD.weighted_code(row, 2) in MOD.CODES


def test_gate_a_schemas_exclude_settlement_fields() -> None:
    forbidden = ("result", "winning", "payout", "roi", "score")
    for fields in (MOD.SCATTER_FIELDS, MOD.FRONTIER_FIELDS, MOD.ROLE_FIELDS):
        assert not any(term in field.lower() for field in fields for term in forbidden)


def test_current_gate_a_does_not_ingest_the_no_promotion_q_atlas() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "bj106_gate" not in source
    assert MOD.OUT.name == "bj105_gate_a_preoutcome_v2r3"


def test_portable_replay_accepts_wrapper_only_gzip_variation() -> None:
    frontier, roles = b"frontier\n", b"roles\n"
    committed_frontier = gzip.compress(frontier, compresslevel=9, mtime=0)
    committed_roles = gzip.compress(roles, compresslevel=9, mtime=0)
    replay_frontier = gzip.compress(frontier, compresslevel=1, mtime=1)
    replay_roles = gzip.compress(roles, compresslevel=1, mtime=2)
    assert committed_frontier != replay_frontier
    assert committed_roles != replay_roles
    with tempfile.TemporaryDirectory(prefix="bj105_portable_") as directory:
        root = Path(directory)
        committed, replay = root / "committed", root / "replay"
        write_portable_bundle(
            committed, frontier_content=frontier, role_content=roles,
            replay_frontier=committed_frontier, replay_roles=committed_roles,
        )
        write_portable_bundle(
            replay, frontier_content=frontier, role_content=roles,
            replay_frontier=replay_frontier, replay_roles=replay_roles,
        )
        assert MOD.verify_portable_replay(replay, committed) == {
            "status": "PASS", "gzip_wrapper_byte_identical": False,
            "gzip_payloads": 2, "non_compressed_controls": 1,
        }


def test_portable_replay_rejects_canonical_content_and_control_drift() -> None:
    frontier, roles = b"frontier\n", b"roles\n"
    compressed_frontier, compressed_roles = gzip.compress(frontier, mtime=0), gzip.compress(roles, mtime=0)
    with tempfile.TemporaryDirectory(prefix="bj105_portable_drift_") as directory:
        root = Path(directory)
        committed, drifted_content, drifted_control = root / "committed", root / "content", root / "control"
        write_portable_bundle(
            committed, frontier_content=frontier, role_content=roles,
            replay_frontier=compressed_frontier, replay_roles=compressed_roles,
        )
        write_portable_bundle(
            drifted_content, frontier_content=frontier, role_content=roles,
            replay_frontier=compressed_frontier, replay_roles=gzip.compress(b"roles-drift\n", mtime=0),
        )
        write_portable_bundle(
            drifted_control, frontier_content=frontier, role_content=roles,
            replay_frontier=compressed_frontier, replay_roles=compressed_roles,
            control=b"drifted-control\n",
        )
        raises_runtime_error(lambda: MOD.verify_portable_replay(drifted_content, committed))
        raises_runtime_error(lambda: MOD.verify_portable_replay(drifted_control, committed))


def write_authenticated_inputs(root: Path) -> tuple[Path, Path]:
    bj101, bj90 = root / "bj101", root / "bj90"
    bj101.mkdir()
    bj90.mkdir()
    membership = []
    predictions = []
    for index in range(1, 8):
        membership.append({
            "issue": "26001", "fold": "2020", "year": "2020", "pool_id": "26001-2020-S01",
            "segment_index": "1", "pool_disposition": "AVAILABLE", "match_id": f"26001_{index:03d}",
            "match_idx": str(index), "kickoff_ts": f"2020-01-0{index}T12:00:00Z", "p3": "0.60",
            "p1": "0.30", "p0": "0.10", "deleted_code": "0", "p_min": "0.10",
            "p_min_rank": str(index), "p_min_bucket": "LE_0_10", "eligible_t05": "0",
            "eligible_t10": "1", "eligible_t15": "1", "eligible_t20": "1",
        })
        predictions.append({
            "match_id": f"26001_{index:03d}", "issue": "26001", "match_idx": str(index),
            "year": "2020", "fold": "2020", "deployed_method": "TEST", "deployed_sp_3": "3.00",
            "deployed_sp_1": "3.10", "deployed_sp_0": "3.20", "m2_conservative_sp_3": "2.80",
            "m2_conservative_sp_1": "2.90", "m2_conservative_sp_0": "3.00",
        })
    MOD.write_csv(bj101 / "issue_pool_membership.csv", MOD.MEMBERSHIP_FIELDS, membership)
    MOD.write_csv(bj101 / "issue_pool_census.csv", MOD.POOL_FIELDS, [{
        "issue": "26001", "fold": "2020", "year": "2020", "pool_id": "26001-2020-S01",
        "segment_index": "1", "pool_disposition": "AVAILABLE", "eligible_match_count": "7",
        "pool_match_count": "7", "first_kickoff_ts": "2020-01-01T12:00:00Z",
        "last_kickoff_ts": "2020-01-07T12:00:00Z", "window_hours": "144", "terminal_remainder": "0",
    }])
    prediction_csv = io.StringIO(newline="")
    writer = csv.DictWriter(prediction_csv, fieldnames=MOD.SP_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(predictions)
    (bj90 / "oos_prediction_vectors.csv.gz").write_bytes(
        gzip.compress(prediction_csv.getvalue().encode("utf-8"), mtime=0)
    )
    write_manifest(bj101)
    write_manifest(bj90)
    return bj101, bj90


def test_real_builder_replay_accepts_wrapper_only_variation_and_rejects_drift() -> None:
    with tempfile.TemporaryDirectory(prefix="bj105_builder_replay_") as directory:
        root = Path(directory)
        bj101, bj90 = write_authenticated_inputs(root)
        committed, replay = root / "committed", root / "replay"
        original = MOD.BJ101_MANIFEST, MOD.BJ90_MANIFEST
        MOD.BJ101_MANIFEST, MOD.BJ90_MANIFEST = MOD.sha256(bj101 / "SHA256SUMS.json"), MOD.sha256(bj90 / "SHA256SUMS.json")
        try:
            MOD.build(committed, bj101, bj90)
            MOD.build(replay, bj101, bj90)
        finally:
            MOD.BJ101_MANIFEST, MOD.BJ90_MANIFEST = original
        assert (committed / "CONTENT_IDENTITY.json").read_bytes() == (replay / "CONTENT_IDENTITY.json").read_bytes()
        for name, mtime in (("joint_n7_frontier.csv.gz", 1), ("role_assignments.csv.gz", 2)):
            payload = gzip.decompress((replay / name).read_bytes())
            (replay / name).write_bytes(gzip.compress(payload, compresslevel=1, mtime=mtime))
        write_manifest(replay)
        result = MOD.verify_portable_replay(replay, committed)
        assert result["status"] == "PASS"
        assert result["gzip_wrapper_byte_identical"] is False
        drifted_content, drifted_control = root / "content_drift", root / "control_drift"
        shutil.copytree(replay, drifted_content)
        shutil.copytree(replay, drifted_control)
        role_payload = gzip.decompress((drifted_content / "role_assignments.csv.gz").read_bytes())
        (drifted_content / "role_assignments.csv.gz").write_bytes(gzip.compress(role_payload + b"drift\n", mtime=3))
        write_manifest(drifted_content)
        (drifted_control / "candidate_scatter.csv").write_text("drift\n", encoding="utf-8")
        write_manifest(drifted_control)
        raises_runtime_error(lambda: MOD.verify_portable_replay(drifted_content, committed))
        raises_runtime_error(lambda: MOD.verify_portable_replay(drifted_control, committed))
