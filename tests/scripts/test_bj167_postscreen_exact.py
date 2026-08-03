"""Production-path checks for the bounded #167 post-screening evidence pass."""
from __future__ import annotations

import array, csv, gzip, importlib.util, json, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / ".scratch" / "bj167_postscreen_fixture"
spec = importlib.util.spec_from_file_location("bj167_postscreen", ROOT / "scripts" / "settle_bj167_atlas_postscreen_exact.py")
POST = importlib.util.module_from_spec(spec); assert spec.loader is not None; spec.loader.exec_module(POST)


def test_candidate_freeze_union_and_shared_paired_bootstrap():
    if FIXTURE.exists(): shutil.rmtree(FIXTURE)
    screen = FIXTURE / "screen"; out = FIXTURE / "out"; screen.mkdir(parents=True); out.mkdir()
    fields = ["selector_id", "weight_source", "mechanism", "cap", "M", "seed", "seed_scope", "global_cell", "no_tax_roi", "stake_yuan", "matched_full_lift"]
    rows = [
        dict(selector_id="S0", weight_source="Q_WEIGHT", mechanism="WOR_DISTINCT", cap="NA", M="64", seed="ENSEMBLE_100", seed_scope="ENSEMBLE_100", global_cell="", no_tax_roi="0.10", stake_yuan="100", matched_full_lift="0.20"),
        dict(selector_id="S0", weight_source="Q_WEIGHT", mechanism="CAPPED_REPEAT", cap="1", M="64", seed="NA", seed_scope="DETERMINISTIC", global_cell="9", no_tax_roi="-0.10", stake_yuan="100", matched_full_lift="0.01"),
    ]
    with gzip.open(screen / "ensemble_metrics.csv.gz", "wt", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
    with (screen / "raw_pareto_front.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerow(rows[1])
    (screen / "SHA256SUMS.json").write_text("{}\n")
    frozen = POST.candidate_rows(screen)
    assert len(frozen) == 2
    assert frozen[0]["candidate_inclusion"] == "RAW_PARETO"
    assert "ABSOLUTE_POSITIVE" in frozen[1]["candidate_inclusion"]
    for i, r in enumerate(frozen): r["candidate_index"] = i
    n = 3
    values = {name: [array.array("d", value), array.array("d", value)] for name, value in {
        "net": [2.0, -1.0, 0.0], "stake": [2.0, 2.0, 2.0], "gross": [4.0, 1.0, 2.0], "tax": [0.0, 0.0, 0.0], "hit": [1.0, 1.0, 1.0],
        "full_net": [0.0, -3.0, -1.0], "full_stake": [4.0, 4.0, 4.0], "full_gross": [4.0, 1.0, 3.0], "full_tax": [0.0, 0.0, 0.0],
    }.items()}
    # The two candidates intentionally share this small fixture's ledger;
    # the assertion below confirms every target uses the same stored issue
    # resample matrix rather than advancing a per-target RNG.
    issue_order = ["I1", "I2", "I3"]
    issue_meta = {x: {"year": "2024" if x != "I3" else "2025", "fold": "OOS_2024", "first_kickoff_ts": x} for x in issue_order}
    boot = POST.bootstrap_rows(frozen, values, issue_order, issue_meta, out)
    assert len(boot) == 2 and boot[0]["bootstrap_draw_matrix_sha256"] == boot[1]["bootstrap_draw_matrix_sha256"]
    assert boot[0]["candidate_ci95_low"] is not None and boot[0]["paired_lift_two_sided_p"] is not None
    assert json.loads((out / "paired_bootstrap_draw_matrix.json").read_text())["replicate_count"] == 20_000
    shutil.rmtree(FIXTURE)


def test_production_role_vector_q_delete_and_native_profile():
    """Use a real Gate-A role shape, not a uniform synthetic tie vector."""
    role_file = sorted(POST.R.GA.glob("selector_role_vectors-*.csv.gz"))[0]
    with gzip.open(role_file, "rt", newline="") as f:
        raw = [next(csv.DictReader(f))]
    # Re-open because DictReader cannot be recreated after consuming the first
    # construction without a header; retain seven roles of one identity.
    with gzip.open(role_file, "rt", newline="") as f:
        reader = csv.DictReader(f); first = next(reader); key = (first["selector_id"], first["issue_instance"], first["portfolio_id"])
        source_rows = [first]
        while len(source_rows) < 7:
            nxt = next(reader)
            assert (nxt["selector_id"], nxt["issue_instance"], nxt["portfolio_id"]) == key
            source_rows.append(nxt)
    roles = [POST.R.role_values(r) for r in source_rows]
    _pl, _pc, ql, qc = POST.R.derive_delete(roles)
    expected = min(((i, c) for i in range(7) for c in range(3)), key=lambda x: (roles[x[0]]["source"]["Q_WEIGHT"][x[1]], x[0], x[1]))
    assert (ql, qc) == expected
    lib = POST.configure_native(); buffers = POST.profile_buffers()
    vec = array.array("d", [v for role in roles for v in role["source"]["Q_WEIGHT"]])
    lib.bj167_profile_allocation(POST.R.ptr(vec, __import__("ctypes").c_double), 0, b"production-role-fixture", *(POST.R.ptr(x, __import__("ctypes").c_int) for x in buffers))
    candidate = {"mechanism": "WOR_DISTINCT", "weight_source": "Q_WEIGHT", "M": "64", "cap": "NA", "seed_scope": "ENSEMBLE_100"}
    hit, unique, duplicate, _ = POST.metric_for(candidate, roles, 0, {"Q_WEIGHT": buffers})
    assert unique + duplicate == 100 * 64 and hit >= 0
